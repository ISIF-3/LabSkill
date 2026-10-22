#!/usr/bin/env python3
"""Preview or create a release from explicit public files, never the working folder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path("development/distribution/manifest.json")
SCALARS = "id canonical_id description title_ko summary_ko kind domain subcategory relevance install_method summary_status stars forks stars_7d stars_7d_source language license skill_count file_kind commit pushed_at fetched_at first_seen last_seen metadata_date file_signals_date stars_observed_at fetch_status readme_sha sources_sha history_backfill_status history_backfill_at history_last_attempt trending_first_seen trending_last_seen appearance_days best_daily_rank in_current_trending classification_backend classification_method catalog_updated_at".split()
NESTED = {
    "skills": "name path description has_scripts",
    "agent_catalog": "version rules_revision status kind domain subcategory title_ko summary_ko candidate checked_at classification_method input_sha readme_sha",
    "function_catalog": "version rules_revision primary confidence classification_method input_sha metadata_sha",
    "trend_history": "date period scope rank source_path source_blob",
    "trending": "weekly_rank weekly_stars",
    "supports": "codex claude_code",
}


def selected_scalars(value, keys):
    return {key: value[key] for key in keys if key in value and
            (value[key] is None or isinstance(value[key], (str, int, float, bool)))}


def sanitize_catalog(document):
    """Keep selected public summary metadata; never copy unknown keys or raw documents."""
    result = selected_scalars(document, ["generated_at", "date"])
    result["repos"] = []
    for original in document["repos"]:
        repo = selected_scalars(original, SCALARS)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+", repo.get("id", "")):
            raise ValueError("Invalid public repository identifier")
        repo["url"] = "https://github.com/" + repo["id"]
        repo["review"] = {}
        for key in ("tags", "topics"):
            repo[key] = [item for item in original.get(key, []) if isinstance(item, str)]
        repo["sources"] = [item for item in original.get("sources", []) if item in {
            "trending:weekly", "archive:antonkomarev/github-trending-archive",
            "discovery:code", "discovery:lit", "discovery:mat", "discovery:data", "discovery:verify"}]
        for key, keys in NESTED.items():
            value = original.get(key)
            if isinstance(value, list):
                repo[key] = [selected_scalars(item, keys.split()) for item in value if isinstance(item, dict)]
            elif isinstance(value, dict):
                repo[key] = selected_scalars(value, keys.split())
        function = repo.get("function_catalog")
        if function is not None:
            function["functions"] = [item for item in original["function_catalog"].get("functions", []) if isinstance(item, str)]
        agent = repo.get("agent_catalog")
        if agent is not None:
            agent["clients"] = selected_scalars(original["agent_catalog"].get("clients", {}), ["codex", "claude_code"])
        result["repos"].append(repo)
    result["count"] = len(result["repos"])
    history = document.get("history_import")
    if isinstance(history, dict):
        result["history_import"] = selected_scalars(history, ["source_repository", "source_commit", "manifest_sha256", "total", "imported_at"])
        result["history_import"]["range"] = selected_scalars(history.get("range", {}), ["start", "end", "inclusive"])
        coverage = history.get("coverage")
        if isinstance(coverage, dict):
            result["history_import"]["coverage"] = selected_scalars(
                coverage, ["expected_days", "available_days", "nonempty_days"])
            result["history_import"]["coverage"]["missing_dates"] = [
                day for day in coverage.get("missing_dates", []) if isinstance(day, str)]
    return result


def manifest(root):
    return json.loads((root / MANIFEST).read_text(encoding="utf-8"))


def checked_path(root, relative):
    candidate = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Unsafe manifest path: " + relative)
    current = candidate
    while current != root:
        if current.is_symlink():
            raise ValueError("Refusing symlink: " + relative)
        current = current.parent
    return candidate


def checked_file(root, relative):
    candidate = checked_path(root, relative)
    if not candidate.is_file():
        raise ValueError("Required public file is missing: " + relative)
    return candidate


def plan_files(root, platform, macos_app=None):
    root = Path(root).resolve()
    config = manifest(root)
    catalog = json.loads(checked_file(root, config["seed"]["labskill-catalog/catalog/catalog.json"]).read_text(encoding="utf-8"))
    if sanitize_catalog(catalog) != catalog:
        raise ValueError("Public seed contains unsupported fields; review and sanitize it first")
    if re.search(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|/Users/[^/\\\s]+|/home/[^/\\\s]+|[A-Z]:\\\\Users\\\\", json.dumps(catalog, ensure_ascii=False)):
        raise ValueError("Public seed contains a token or personal filesystem path")
    names = config["common"] + (config["source"] + config["windows"] + list(config["seed"].values())
                                if platform == "source" else config[platform])
    result = {name: checked_file(root, name) for name in names}
    result.update({name: checked_file(root, source) for name, source in config["seed"].items()})
    if platform == "macos":
        if macos_app is None:
            raise ValueError("macOS packaging requires --macos-app pointing to a rebuilt LabSkill.app")
        app = Path(macos_app).resolve()
        for name in config["macos_bundle"]:
            result["LabSkill.app/" + name] = checked_file(app, name)
    return dict(sorted(result.items()))


def initialize(root):
    root = Path(root).resolve()
    for name, source in manifest(root)["seed"].items():
        target = checked_path(root, name)
        if target.exists():
            continue
        content = checked_file(root, source).read_bytes()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as output:
                output.write(content)
        except FileExistsError:
            pass


def write_archive(files, output, folder):
    output = Path(output)
    if output.exists():
        raise ValueError("Refusing to overwrite archive: " + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, source in files.items():
                info = zipfile.ZipInfo(folder + "/" + name, date_time=(2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                executable = name.endswith((".command", ".sh")) or name.endswith("Contents/MacOS/LabSkill")
                info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, source.read_bytes())
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["source", "macos", "windows"], default="source")
    parser.add_argument("--macos-app", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--write", action="store_true", help="Create ZIP; without this flag only preview filenames")
    parser.add_argument("--initialize", action="store_true", help="Fill missing local catalog files from the reviewed public seed")
    args = parser.parse_args()
    if args.initialize:
        initialize(ROOT)
        print("Missing seed files initialized; existing local files preserved.")
        return
    files = plan_files(ROOT, args.platform, args.macos_app)
    folder = "LabSkill-" + ("macos-arm64" if args.platform == "macos" else args.platform)
    output = args.output_dir / (folder + ".zip")
    for name in files:
        print(name)
    print(f"{len(files)} public files -> {output.name}")
    if args.write:
        write_archive(files, output, folder)
        print("ZIP created. No upload was performed.")
    else:
        print("Dry run only. Use --write after reviewing this list.")


if __name__ == "__main__":
    main()
