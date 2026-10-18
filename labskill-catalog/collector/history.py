"""Seed a local archive roster once; track small, resumable enrichment batches."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath

SOURCE_REPOSITORY = "antonkomarev/github-trending-archive"
SOURCE = f"archive:{SOURCE_REPOSITORY}"
MANIFEST = "trending-history-2026-04-18_2026-10-18.json"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
EMPTY_README_SHA = hashlib.sha256(b"").hexdigest()[:16]


def _require(condition):
    if not condition:
        raise ValueError("트렌딩 기록 파일의 이름·날짜·순위·개수가 올바르지 않습니다")


def _name(value):
    _require(isinstance(value, str) and NAME.fullmatch(value) is not None
             and value.split("/")[1] not in (".", ".."))
    return value


def _date(value):
    _require(isinstance(value, str))
    date = dt.date.fromisoformat(value)
    _require(date.isoformat() == value)
    return date


def _integer(value, minimum=0):
    _require(type(value) is int and value >= minimum)
    return value


def _record(record, start, end):
    _require(isinstance(record, dict))
    _require(start <= _date(record.get("date")) <= end)
    _require(record.get("period") == "daily" and record.get("scope") == "all")
    path = record.get("source_path")
    _require(isinstance(path, str) and bool(path) and not path.startswith("/")
             and ".." not in PurePosixPath(path).parts and "\\" not in path and "\x00" not in path)
    _require(isinstance(record.get("source_blob"), str) and SHA.fullmatch(record["source_blob"]) is not None)


def _validate(manifest):
    _require(isinstance(manifest, dict) and manifest.get("schema_version") == 1
             and manifest.get("kind") == "trending_history_roster"
             and manifest.get("source_repository") == SOURCE_REPOSITORY
             and manifest.get("source_period") == "daily" and manifest.get("scope") == "all")
    _require(isinstance(manifest.get("source_commit"), str)
             and SHA.fullmatch(manifest["source_commit"]) is not None)
    bounds = manifest.get("range")
    _require(isinstance(bounds, dict) and bounds.get("inclusive") is True)
    start, end = _date(bounds.get("start")), _date(bounds.get("end"))
    _require(start <= end)
    repos, snapshots, coverage = manifest.get("repositories"), manifest.get("snapshots"), manifest.get("coverage")
    _require(isinstance(repos, list) and bool(repos) and isinstance(snapshots, list) and isinstance(coverage, dict))
    expected, dates = {}, set()
    for snapshot in snapshots:
        _record(snapshot, start, end)
        day = snapshot["date"]
        _require(day not in dates)
        dates.add(day)
        names = snapshot.get("repositories")
        _require(isinstance(names, list))
        seen = set()
        for rank, name in enumerate(names, 1):
            key = _name(name).casefold()
            _require(key not in seen)
            seen.add(key)
            expected.setdefault(key, []).append({field: snapshot[field] for field in
                ("date", "period", "scope", "source_path", "source_blob")} | {"rank": rank})
    missing = [(start + dt.timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
               if (start + dt.timedelta(days=i)).isoformat() not in dates]
    _require(_integer(coverage.get("expected_days")) == (end - start).days + 1
             and _integer(coverage.get("available_days")) == len(snapshots)
             and _integer(coverage.get("nonempty_days")) == sum(bool(s["repositories"]) for s in snapshots)
             and coverage.get("missing_dates") == missing)
    seen, appearances = set(), 0
    for repo in repos:
        _require(isinstance(repo, dict))
        key = _name(repo.get("id")).casefold()
        _require(key not in seen and repo.get("url") == f"https://github.com/{repo['id']}")
        seen.add(key)
        history = repo.get("history")
        _require(isinstance(history, list) and bool(history))
        for item in history:
            _record(item, start, end)
            _integer(item.get("rank"), 1)
        history = sorted(history, key=lambda h: h["date"])
        _require(history == sorted(expected.get(key, []), key=lambda h: h["date"]))
        _require(repo.get("trending_first_seen") == history[0]["date"]
                 and repo.get("trending_last_seen") == history[-1]["date"]
                 and _integer(repo.get("appearance_days"), 1) == len(history)
                 and _integer(repo.get("best_daily_rank"), 1) == min(h["rank"] for h in history))
        appearances += len(history)
    _require(seen == set(expected) and _integer(manifest.get("count"), 1) == len(repos)
             and _integer(manifest.get("appearance_count"), 1) == appearances)


def _atomic_write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(doc, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _pending(repo_id, day):
    return {"id": repo_id, "url": f"https://github.com/{repo_id}", "description": "", "title_ko": repo_id,
            "summary_ko": "", "domain": None, "subcategory": None, "kind": None, "relevance": None,
            "tags": [], "tag_candidates": [], "evidence": [], "install_method": "unknown", "install_evidence": None,
            "summary_status": "pending", "review_reason": "", "classification_attempted": False,
            "raw_classification": None, "evidence_valid": False, "stars": None, "forks": None,
            "stars_7d": None, "stars_7d_source": None, "language": None, "license": None, "topics": [],
            "skills": [], "skill_count": None, "file_kind": None, "file_signals": {},
            "supports": {"claude_code": None, "codex": None}, "prescan": {"warnings": []},
            "commit": "", "pushed_at": None, "readme_sha": None, "sources_sha": None,
            "review": {"status": "unreviewed"}, "update_pending": False, "sources": [], "trending": {},
            "in_current_trending": False, "first_seen": day, "last_seen": day,
            "metadata_date": None, "file_signals_date": None, "stars_observed_at": None,
            "fetch_status": "pending", "fetch_error": None}


def ensure_seed(root: Path, today: dt.date | None = None) -> bool:
    """Merge the bundled roster atomically; an unchanged manifest never resets progress."""
    root = Path(root)
    manifest_path = root / "imports" / MANIFEST
    if not manifest_path.is_file():
        return False
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    _validate(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    path = root / "catalog" / "catalog.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"repos": []}
    _require(isinstance(doc, dict) and isinstance(doc.get("repos"), list))
    if isinstance(doc.get("history_import"), dict) and doc["history_import"].get("manifest_sha256") == digest:
        return False
    by_name = {}
    for entry in doc["repos"]:
        _require(isinstance(entry, dict))
        key = _name(entry.get("id")).casefold()
        _require(key not in by_name)
        by_name[key] = entry
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    day = (today or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()).isoformat()
    for repo in manifest["repositories"]:
        entry = by_name.get(repo["id"].casefold())
        if entry is None:
            entry = _pending(repo["id"], day)
            doc["repos"].append(entry)
        sources = entry.get("sources", [])
        _require(isinstance(sources, list) and all(isinstance(s, str) for s in sources))
        entry["sources"] = list(dict.fromkeys([*sources, SOURCE]))
        entry.update(trend_history=repo["history"], trending_first_seen=repo["trending_first_seen"],
                     trending_last_seen=repo["trending_last_seen"], appearance_days=repo["appearance_days"],
                     best_daily_rank=repo["best_daily_rank"])
        if "history_backfill_status" not in entry:
            complete = entry.get("fetch_status") == "ok" and isinstance(entry.get("readme_sha"), str) and bool(entry["readme_sha"])
            entry.update(history_backfill_status="complete" if complete else "pending",
                         history_backfill_at=now if complete else None, history_last_attempt=None)
    doc.update(count=len(doc["repos"]), generated_at=now, date=day, history_import={
        "source_repository": SOURCE_REPOSITORY, "source_commit": manifest["source_commit"],
        "manifest_sha256": digest, "range": manifest["range"], "total": manifest["count"], "imported_at": now})
    _atomic_write(path, doc)
    return True


def _actual_output(entry):
    return entry.get("classification_attempted") is True and (
        isinstance(entry.get("raw_classification"), dict) or isinstance(entry.get("raw_response"), str)
        and bool(entry["raw_response"].strip()))


def _screened(entry):
    result = entry.get("agent_catalog")
    return (isinstance(result, dict) and result.get("version") == 1
            and result.get("status") in ("selected", "companion", "reference", "not_target", "unconfirmed"))


def _awaiting_classification(entry):
    readme_sha = entry.get("readme_sha")
    return (entry.get("history_backfill_status") == "complete" and isinstance(readme_sha, str)
            and bool(readme_sha) and readme_sha != EMPTY_README_SHA
            and not _screened(entry) and not _actual_output(entry))


def pending_names(catalog: dict, limit: int = 25, include_failed: bool = False) -> list[str]:
    """Choose at most one batch; failed entries require an explicit retry."""
    if type(limit) is not int or limit < 1:
        raise ValueError("배치 크기는 양의 정수여야 합니다")
    statuses = {"pending", "failed"} if include_failed else {"pending"}
    entries = [entry for entry in catalog.get("repos", []) if SOURCE in entry.get("sources", [])
               and ((entry.get("history_backfill_status") in statuses
                     and (not _screened(entry) or entry.get("history_backfill_status") == "failed"))
                    or _awaiting_classification(entry))]
    entries.sort(key=lambda e: (e.get("trending_last_seen", ""), e.get("appearance_days", 0), e["id"]), reverse=True)
    return [e["id"] for e in entries[:min(limit, 25)]]


def summary(catalog: dict) -> dict:
    """Report archive progress separately from unrelated existing catalog records."""
    state = catalog.get("history_import")
    state = state if isinstance(state, dict) else {}
    entries = [e for e in catalog.get("repos", []) if SOURCE in e.get("sources", [])]
    pending = sum(e.get("history_backfill_status") == "pending" and not _screened(e)
                  or _awaiting_classification(e) for e in entries)
    failed = sum(e.get("history_backfill_status") == "failed" for e in entries)
    selected = sum(_screened(e) and e["agent_catalog"]["status"] == "selected" for e in entries)
    classified = sum(_actual_output(e) or _screened(e) and e["agent_catalog"]["status"] == "selected" for e in entries)
    return {"available": bool(state), "source_repository": state.get("source_repository"), "range": state.get("range"),
            "total": len(entries), "enriched": sum(e.get("history_backfill_status") == "complete" for e in entries),
            "classified": classified, "screened": sum(_screened(e) for e in entries), "selected": selected,
            "metadata_only": sum(_screened(e) and e["agent_catalog"].get("candidate") is False
                                 and e["agent_catalog"]["status"] == "unconfirmed"
                                 and not e["agent_catalog"].get("error") and e.get("fetch_status") != "failed"
                                 for e in entries),
            "pending": pending, "failed": failed, "remaining": pending + failed,
            "needs_resume": pending + failed > 0}
