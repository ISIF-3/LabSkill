#!/usr/bin/env python3
"""Build a pinned daily global Trending roster; never fetch or execute repository code."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "labskill-catalog"))
from collector import history
from collector.github_client import GitHub

SOURCE = history.SOURCE_REPOSITORY
OUTPUT = "trending-history-expanded.json"
MAX_RAW_BYTES = 2 * 1024 * 1024


def _blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _safe_path(value):
    if (not isinstance(value, str) or not value or value.startswith("/") or "\\" in value
            or any(ord(char) < 32 for char in value) or ".." in PurePosixPath(value).parts
            or str(PurePosixPath(value)) != value):
        raise ValueError("Unsafe archive source path")
    return value


def _tree(github, sha, *, recursive=False):
    params = {"recursive": "1"} if recursive else {}
    data = github.get_json(f"/repos/{SOURCE}/git/trees/{sha}", **params)
    if not isinstance(data, dict) or data.get("truncated") is not False:
        raise ValueError("Archive tree is truncated or incomplete")
    entries = data.get("tree")
    if not isinstance(entries, list):
        raise ValueError("Archive tree is not a list")
    seen = set()
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get("sha"), str)
                or not history.SHA.fullmatch(entry["sha"]) or entry.get("type") not in {"blob", "tree", "commit"}):
            raise ValueError("Invalid archive tree entry")
        path = _safe_path(entry.get("path"))
        if path in seen:
            raise ValueError("Duplicate archive tree path")
        seen.add(path)
    return entries


def _source_files(github, ref, start, end):
    sha = ref
    for component in ("archive", "repository"):
        entry = next((entry for entry in _tree(github, sha) if entry["path"] == component), None)
        if entry is None or entry["type"] != "tree":
            raise ValueError("Archive repository directory is missing")
        sha = entry["sha"]
    years = {entry["path"]: entry for entry in _tree(github, sha)}
    files = []
    for year in range(start.year, end.year + 1):
        entry = years.get(str(year))
        if entry is None:
            continue
        if entry["type"] != "tree":
            raise ValueError("Archive year is not a tree")
        for item in _tree(github, entry["sha"], recursive=True):
            path = item["path"]
            if PurePosixPath(path).name != "(null).json":
                continue
            parts = path.split("/")
            if len(parts) != 2 or item["type"] != "blob" or item.get("mode") != "100644":
                raise ValueError("Invalid global archive source path or file mode")
            day = history._date(parts[0])
            if day.year != year:
                raise ValueError("Archive source date disagrees with its year directory")
            if start <= day <= end:
                files.append({"date": day.isoformat(), "source_path": f"archive/repository/{year}/{path}",
                              "source_blob": item["sha"]})
    return sorted(files, key=lambda item: item["date"])


def _source_url(ref, path):
    return f"https://raw.githubusercontent.com/{SOURCE}/{ref}/" + urllib.parse.quote(path, safe="/")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def fetch_raw(url):
    """Use an independent unauthenticated opener; never forward GitHub credentials."""
    prefix = f"https://raw.githubusercontent.com/{SOURCE}/"
    suffix = url.removeprefix(prefix)
    if not url.startswith(prefix) or not re.fullmatch(
            r"[0-9a-f]{40}/archive/repository/[0-9]{4}/[0-9]{4}-[0-9]{2}-[0-9]{2}/%28null%29\.json", suffix):
        raise ValueError("Raw URL must identify a pinned global archive snapshot")
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "labskill-history-import", "Accept": "application/json"})
    for attempt in range(3):
        try:
            with opener.open(request, timeout=20) as response:
                data = response.read(MAX_RAW_BYTES + 1)
            if len(data) > MAX_RAW_BYTES:
                raise ValueError("Archive snapshot exceeds the size limit")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
        time.sleep(0.25 * (attempt + 1))


def _parse_snapshot(data, record, ref):
    if not isinstance(data, bytes) or len(data) > MAX_RAW_BYTES or _blob_sha(data) != record["source_blob"]:
        raise ValueError("Archive Git blob SHA mismatch: " + record["source_path"])
    source = json.loads(data)
    if (not isinstance(source, dict) or source.get("date") != record["date"]
            or "language" not in source or source["language"] is not None
            or not isinstance(source.get("list"), list)):
        raise ValueError("Invalid archive JSON date, language, or list: " + record["source_path"])
    names, seen = [], set()
    for value in source["list"]:
        name = history._name(value)
        if name.casefold() not in seen:
            names.append(name)
            seen.add(name.casefold())
    return {**record, "period": "daily", "scope": "all", "source_url": _source_url(ref, record["source_path"]),
            "repositories": names}


def _previous_snapshots(root):
    snapshots = {}
    for path in sorted((root / "imports").glob("trending-history*.json")):
        try:
            previous = json.loads(path.read_bytes())
            history._validate(previous)
        except (OSError, ValueError, TypeError, KeyError):
            continue
        for snapshot in previous["snapshots"]:
            snapshots[(snapshot["source_path"], snapshot["source_blob"])] = snapshot
    return snapshots


def _cache_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_manifest(root, start, end, ref, *, github=None, fetch_raw=None):
    start, end = history._date(start), history._date(end)
    if start > end or not isinstance(ref, str) or history.SHA.fullmatch(ref) is None:
        raise ValueError("Use an ordered date range and a 40-character lowercase commit SHA")
    root = Path(root)
    github = github if github is not None else GitHub.from_gh()
    download = fetch_raw if fetch_raw is not None else globals()["fetch_raw"]
    records = _source_files(github, ref, start, end)
    previous = _previous_snapshots(root)

    def snapshot(record):
        reused = previous.get((record["source_path"], record["source_blob"]))
        if reused is not None and reused["date"] == record["date"]:
            return {**reused, "source_url": _source_url(ref, record["source_path"])}
        cache = root / "cache/archive" / (record["source_blob"] + ".json")
        try:
            data = cache.read_bytes()
        except FileNotFoundError:
            data = None
        if data is not None and _blob_sha(data) == record["source_blob"]:
            return _parse_snapshot(data, record, ref)
        data = download(_source_url(ref, record["source_path"]))
        parsed = _parse_snapshot(data, record, ref)
        _cache_bytes(cache, data)
        return parsed

    with ThreadPoolExecutor(max_workers=6) as executor:
        snapshots = list(executor.map(snapshot, records))
    repositories = {}
    for item in snapshots:
        for rank, name in enumerate(item["repositories"], 1):
            repo = repositories.setdefault(name.casefold(), {"id": name, "url": f"https://github.com/{name}", "history": []})
            repo["history"].append({key: item[key] for key in ("date", "period", "scope", "source_path", "source_blob")} | {"rank": rank})
    for repo in repositories.values():
        appearances = repo["history"]
        repo.update(trending_first_seen=appearances[0]["date"], trending_last_seen=appearances[-1]["date"],
                    appearance_days=len(appearances), best_daily_rank=min(item["rank"] for item in appearances))
    available = {item["date"] for item in snapshots}
    expected = [(start + dt.timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]
    manifest = {"schema_version": 1, "kind": "trending_history_roster",
                "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "source_repository": SOURCE, "source_commit": ref, "source_license": "MIT",
                "source_period": "daily", "scope": "all",
                "range": {"start": start.isoformat(), "end": end.isoformat(), "inclusive": True},
                "coverage": {"expected_days": len(expected), "available_days": len(snapshots),
                             "nonempty_days": sum(bool(item["repositories"]) for item in snapshots),
                             "missing_dates": [day for day in expected if day not in available]},
                "appearance_count": sum(len(repo["history"]) for repo in repositories.values()),
                "count": len(repositories), "repositories": [repositories[key] for key in sorted(repositories)],
                "snapshots": snapshots}
    history._validate(manifest)
    return manifest


def run(root, start, end, ref, **options):
    manifest = build_manifest(root, start, end, ref, **options)
    history._atomic_write(Path(root) / "imports" / OUTPUT, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Inclusive date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Inclusive date, YYYY-MM-DD")
    parser.add_argument("--ref", required=True, help="Pinned 40-character source commit SHA")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "labskill-catalog")
    args = parser.parse_args()
    try:
        manifest = run(args.root, args.start, args.end, args.ref)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"History import failed; previous manifest preserved: {exc}\n")
    print(json.dumps({"output": str(args.root / "imports" / OUTPUT), "count": manifest["count"],
                      "coverage": manifest["coverage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
