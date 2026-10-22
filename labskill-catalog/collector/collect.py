"""GitHub candidates → file signals → local Python rules by default → one atomic catalog."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import agent_filter, discovery, functions
from .detect import detect, parse_frontmatter, supports
from .github_client import GitHub, GitHubError
from .prescan import prescan
from .rules import _readme
from .summarize import CLASSIFICATION_KEYS, Summarizer, load_taxonomy, validate_output
from .trending import parse_trending

MAX_CANDIDATES = 25
MAX_SKILL_MD_FETCH = 10
SNAPSHOT_KEEP_DAYS = 90
SUMMARY_KEYS = ("title_ko", "summary_ko", "domain", "subcategory", "tags", "tag_candidates", "evidence",
                "kind", "relevance", "install_method", "install_evidence", "summary_status", "review_reason",
                "raw_classification", "raw_response", "classification_attempted", "evidence_valid", "subcategory_candidate",
                *CLASSIFICATION_KEYS)
HISTORY_KEYS = ("trend_history", "trending_first_seen", "trending_last_seen", "appearance_days", "best_daily_rank",
                "history_backfill_status", "history_backfill_at", "history_last_attempt")
ARCHIVE_SOURCE = "archive:antonkomarev/github-trending-archive"


class CollectError(RuntimeError):
    pass


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (ValueError, UnicodeError) as exc:
        raise CollectError(f"JSON 파일을 읽지 못했습니다: {path.name}") from exc


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            tmp = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def gather_candidates(gh: GitHub, prev_catalog: list[dict], curation: dict,
                      search: bool = False) -> tuple[dict, dict]:
    """Compatibility arguments remain; candidates come only from this week's first 25."""
    try:
        items = parse_trending(gh.trending_html("weekly"))
    except GitHubError as exc:
        raise CollectError(f"주간 트렌딩을 읽지 못했습니다: {exc}") from exc
    cands = {}
    for rank, item in enumerate(items[:MAX_CANDIDATES], 1):
        trending = {"weekly_rank": rank}
        if item.get("period_stars") is not None:
            trending["weekly_stars"] = item["period_stars"]
        cands[item["full_name"]] = {"sources": ["trending:weekly"], "trending": trending, "html": item,
                                    "in_current_trending": True}
    return cands, {"weekly": len(items)}


def fetch_sources(gh: GitHub, name: str, commit: str, skill_mds: list[str]) -> tuple[dict[str, str], str]:
    sources = {}
    readme, readme_path = gh.readme(name, commit)
    if readme_path:
        sources[readme_path] = readme
    for md in skill_mds[:MAX_SKILL_MD_FETCH]:
        sources[md] = gh.file_text(name, md, commit)
    return sources, _sha(readme)


def analyze_repo(gh: GitHub, name: str, cache: dict, info: dict | None = None, partial: dict | None = None,
                 *, ref: str | None = None) -> dict:
    """Refresh file signals every week; only model classifications use the README cache."""
    info = info if info is not None else gh.repo(name)
    result = partial if partial is not None else {}
    result.update({"pushed_at": info.get("pushed_at"), "metadata_available": True})
    commit = ref if ref is not None else gh.head_commit(name, info["default_branch"])
    result["commit"] = commit
    det = detect(gh.tree(name, commit))
    result.update({"signals": {k: v for k, v in det.items() if k != "skills"},
                   "supports": supports(det), "file_signals_available": True,
                   "skills": [{"name": skill["dir"].rsplit("/", 1)[-1] or name.split("/")[-1],
                               "description": "", "path": skill["dir"], "has_scripts": bool(skill["scripts"]),
                               "scripts": skill["scripts"][:20]} for skill in det["skills"]]})
    sources, readme_sha = fetch_sources(gh, name, commit, [s["skill_md"] for s in det["skills"]])
    skills = []
    for skill in det["skills"]:
        meta = parse_frontmatter(sources.get(skill["skill_md"], ""))
        skills.append({"name": meta.get("name") or (skill["dir"].rsplit("/", 1)[-1] if skill["dir"] else name.split("/")[-1]),
                       "description": meta.get("description", ""), "path": skill["dir"],
                       "has_scripts": bool(skill["scripts"]), "scripts": skill["scripts"][:20]})
    result.update({"skills": skills, "readme_sha": readme_sha,
              "sources_sha": _sha(json.dumps(sources, sort_keys=True)),
              "prescan": prescan(sources, [p for s in skills for p in s["scripts"]])})
    cache[name] = result
    return {**result, "_sources": sources, "info": info}


def stars_7d(name: str, stars: int | None, today: dt.date, snap_dir: Path, trending: dict):
    if trending.get("weekly_stars") is not None:
        return trending["weekly_stars"], "trending_week"
    if stars is None:
        return None, None
    for back in (7, 8, 6):
        snap = _read_json(snap_dir / f"{(today - dt.timedelta(days=back)).isoformat()}.json", None)
        if snap and name in snap.get("repos", {}):
            previous = snap["repos"][name].get("stars")
            if isinstance(previous, int) and not isinstance(previous, bool):
                return stars - previous, "snapshot"
    return None, None


def prune_snapshots(snap_dir: Path, today: dt.date) -> None:
    for path in snap_dir.glob("*.json"):
        try:
            date = dt.date.fromisoformat(path.stem)
        except ValueError:
            continue
        if (today - date).days > SNAPSHOT_KEEP_DAYS and date.weekday() != 0:
            path.unlink()


STRUCTURAL = {"id": str, "url": str, "stars": (int, type(None)), "skills": list, "supports": dict,
              "commit": str, "review": dict, "first_seen": str, "last_seen": str}
MODEL_TYPES = {"title_ko": str, "summary_ko": str, "domain": str, "subcategory": str,
               "tags": list, "summary_status": str, "install_method": str}


def validate_entry(entry: dict, taxonomy: dict) -> list[str]:
    """Classification disagreements are review warnings, never deletion rules."""
    warnings = [f"{key}: missing/{kind.__name__}" for key, kind in MODEL_TYPES.items()
                if not isinstance(entry.get(key), kind)]
    domain, sub = entry.get("domain"), entry.get("subcategory")
    if not isinstance(domain, str) or domain not in taxonomy["domains"]:
        warnings.append(f"domain: {domain!r} not in taxonomy")
    elif not isinstance(sub, str) or sub not in taxonomy["domains"][domain]["subcategories"]:
        warnings.append(f"subcategory: {sub!r} not in {domain}")
    for field, choices in (("kind", "kinds"), ("relevance", "relevance"), ("install_method", "install_methods")):
        value = entry.get(field)
        if value is not None and (not isinstance(value, str) or value not in taxonomy[choices]):
            warnings.append(f"{field}: {value!r} not in taxonomy")
    if entry.get("summary_status") not in ("ok", "needs_review", "pending"):
        warnings.append("summary_status: unknown status")
    if entry.get("file_signals_date"):
        if entry.get("relevance") == "unrelated" and entry.get("file_kind"):
            warnings.append(f"파일 신호({entry['file_kind']})와 모델 판단(unrelated)이 어긋남")
        if entry.get("kind") in ("skill", "skill_collection") and entry.get("skill_count") == 0:
            warnings.append(f"모델은 {entry['kind']}라고 했지만 SKILL.md 없음")
        if entry.get("kind") == "claude_plugin" and not entry.get("file_signals", {}).get("plugin_manifests"):
            warnings.append("모델은 claude_plugin이라고 했지만 플러그인 매니페스트 없음")
    return warnings


def sanity_check(catalog: list[dict], prev: list[dict], parsed_counts: dict, taxonomy: dict) -> None:
    if not any(parsed_counts.values()):
        raise CollectError("수집 결과가 0개이므로 기존 카탈로그를 유지합니다")
    ids = set()
    for entry in catalog:
        if not isinstance(entry, dict):
            raise CollectError("카탈로그 항목 구조가 올바르지 않습니다")
        for field, kind in STRUCTURAL.items():
            if not isinstance(entry.get(field), kind) or (field == "stars" and isinstance(entry[field], bool)):
                raise CollectError(f"카탈로그 구조 오류: {entry.get('id')}: {field}")
        if entry["id"] in ids:
            raise CollectError(f"중복 저장소: {entry['id']}")
        ids.add(entry["id"])
    if any(entry["id"] not in ids for entry in prev):
        raise CollectError("기존 저장소가 사라져 카탈로그 저장을 중단했습니다")


def _placeholder(name: str, description: str, reason: str) -> dict:
    return {"title_ko": description or name, "summary_ko": "", "domain": None, "subcategory": None,
            "tags": [], "tag_candidates": [], "evidence": [], "kind": None, "relevance": None,
            "install_method": "unknown", "install_evidence": None, "summary_status": "needs_review",
            "review_reason": reason, "raw_classification": None, "classification_attempted": False,
            "evidence_valid": False}


def _report_label(value):
    if value is None:
        return "미판정"
    return value if isinstance(value, str) else "형식 오류"


def _has_model_output(entry):
    return entry.get("classification_attempted") is True and (
        isinstance(entry.get("raw_classification"), dict)
        or isinstance(entry.get("raw_response"), str) and bool(entry["raw_response"].strip()))


def _function_assessment(name, info, analysis, old):
    """Classify every repository, retaining README context during metadata-only refreshes."""
    description, topics = info.get("description") or "", info.get("topics") or []
    metadata_sha = functions.function_input_sha(name, description, topics)
    sources = analysis.get("_sources")
    readme = next((text for path, text in (sources or {}).items()
                   if _readme(path) and isinstance(text, str)), "")
    cached = old.get("function_catalog")
    if (isinstance(cached, dict) and cached.get("version") == functions.VERSION
            and cached.get("rules_revision") == functions.RULES_REVISION):
        if sources is None and cached.get("metadata_sha") == metadata_sha:
            return cached
        if cached.get("input_sha") == functions.function_input_sha(name, description, topics, readme):
            return {**cached, "metadata_sha": metadata_sha}
    return {**functions.classify_functions(name, description, topics, readme), "metadata_sha": metadata_sha}


def _entry(name, info, analysis, summary, cand, old, today, snap_dir):
    stars = info.get("stargazers_count")
    if cand.get("preserve_weekly"):
        growth, growth_source = old.get("stars_7d"), old.get("stars_7d_source")
    else:
        growth, growth_source = stars_7d(name, stars, today, snap_dir,
                                       cand["trending"] if cand.get("in_current_trending", True) else {})
    review = old.get("review") or {"status": "unreviewed"}
    return {**{key: old[key] for key in (*HISTORY_KEYS, "agent_catalog", "canonical_id", "catalog_updated_at") if key in old},
            "id": name, "url": info.get("html_url") or f"https://github.com/{name}",
            "description": info.get("description") or "", **{k: summary[k] for k in SUMMARY_KEYS if k in summary},
            "function_catalog": _function_assessment(name, info, analysis, old),
            "stars": stars, "forks": info.get("forks_count"), "stars_7d": growth,
            "stars_7d_source": growth_source, "language": info.get("language"),
            "license": (info.get("license") or {}).get("spdx_id"), "topics": info.get("topics", []),
            "pushed_at": analysis["pushed_at"], "file_kind": analysis["signals"]["file_kind"],
            "file_signals": analysis["signals"], "skill_count": analysis["signals"]["skill_count"],
            "skills": analysis["skills"], "supports": analysis["supports"], "commit": analysis["commit"],
            "readme_sha": analysis.get("readme_sha"), "sources_sha": analysis.get("sources_sha"),
            "prescan": analysis["prescan"], "review": review,
            "update_pending": review.get("status") == "verified" and review.get("commit") != analysis["commit"],
            "sources": cand["sources"], "trending": cand["trending"],
            "in_current_trending": cand.get("in_current_trending", True),
            "first_seen": old.get("first_seen", today.isoformat()), "last_seen": today.isoformat(),
            "metadata_date": today.isoformat() if analysis.get("metadata_available") else None,
            "file_signals_date": today.isoformat() if analysis.get("file_signals_available") else None,
            "stars_observed_at": today.isoformat() if stars is not None else None,
            "fetch_status": "ok", "fetch_error": None,
            "classification_review_reason": summary.get("review_reason", ""),
            "classification_summary_status": summary.get("summary_status")}


def _metadata_only_entry(name, info, analysis, cand, old, today, snap_dir):
    """Keep prior analysis while recording this week's inexpensive metadata screen."""
    entry = dict(old) if old else _entry(name, info, analysis,
        _placeholder(name, info.get("description") or "", "메타데이터 단서 없음"), cand, {}, today, snap_dir)
    for field, api_field in (("url", "html_url"), ("description", "description"), ("forks", "forks_count"),
                             ("language", "language"), ("topics", "topics"), ("pushed_at", "pushed_at")):
        if api_field in info:
            entry[field] = info[api_field]
    stars = info.get("stargazers_count")
    if not cand.get("preserve_weekly"):
        entry["stars_7d"], entry["stars_7d_source"] = stars_7d(
            name, stars, today, snap_dir, cand["trending"] if cand["in_current_trending"] else {})
    entry.update(stars=stars, license=(info.get("license") or {}).get("spdx_id"),
                 stars_observed_at=today.isoformat() if stars is not None else None,
                 metadata_date=today.isoformat(), last_seen=today.isoformat(), sources=cand["sources"],
                 trending=cand["trending"], in_current_trending=cand["in_current_trending"],
                 fetch_status="ok", fetch_error=None,
                 agent_catalog={"version": 1, "rules_revision": getattr(agent_filter, "RULES_REVISION", 1),
                                "status": "unconfirmed", "candidate": False,
                                "kind": None, "domain": None, "subcategory": None,
                                "title_ko": name, "summary_ko": "", "clients": {"codex": None, "claude_code": None},
                                "reasons": ["메타데이터 단서 없음"], "evidence": [],
                                "classification_method": "python_agent_filter", "checked_at": today.isoformat()})
    entry["function_catalog"] = _function_assessment(name, info, analysis, entry)
    return entry


def _agent_assessment(name, info, analysis, old, today):
    revision = getattr(agent_filter, "RULES_REVISION", 1)
    fingerprint = _sha(json.dumps({"rules_revision": revision, "id": name,
                                  "description": info.get("description"), "topics": info.get("topics"),
                                  "sources_sha": analysis["sources_sha"], "signals": analysis["signals"]},
                                 sort_keys=True, ensure_ascii=False))
    cached = old.get("agent_catalog")
    if isinstance(cached, dict) and cached.get("version") == 1 and cached.get("input_sha") == fingerprint:
        return cached
    return {**agent_filter.assess(name, info.get("description") or "", analysis["_sources"],
                                 analysis["signals"], info.get("topics")),
            "rules_revision": revision,
            "candidate": agent_filter.candidate(name, info.get("description") or "", info.get("topics")),
            "checked_at": today.isoformat(), "readme_sha": analysis["readme_sha"], "input_sha": fingerprint}


def _agent_candidate(name, info, old):
    signals = old.get("file_signals") or {}
    assessment = old.get("agent_catalog") or {}
    return (agent_filter.candidate(name, info.get("description") or "", info.get("topics"))
            or isinstance(signals.get("skill_count"), int) and signals["skill_count"] > 0
            or bool(signals.get("plugin_manifests"))
            or assessment.get("status") in ("selected", "companion", "reference"))


def screening_summary(entries, previous=None, generated_at=None):
    """Count current records while retaining the initial batch's usage provenance."""
    previous = previous if isinstance(previous, dict) else {}
    statuses = ("selected", "companion", "reference", "not_target", "unconfirmed")
    assessments = [entry.get("agent_catalog") for entry in entries]
    assessments = [value if isinstance(value, dict) and value.get("version") == 1
                   and value.get("status") in statuses else {} for value in assessments]
    counts = Counter(value.get("status", "unconfirmed") for value in assessments)
    initial_run = previous.get("initial_run")
    if not isinstance(initial_run, dict):
        initial_run = {key: previous[key] for key in ("api_calls", "model_calls", "model_tokens",
                       "metadata_success", "metadata_failed") if key in previous}
    return {**previous, "initial_run": initial_run, "usage_scope": "initial_screening_run",
            "generated_at": generated_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "total": len(entries), "processed": sum(bool(value) for value in assessments),
            **{key: counts[key] for key in statuses},
            "candidates": sum(value.get("candidate") is True for value in assessments),
            "metadata_only": sum(value.get("status") == "unconfirmed" and value.get("candidate") is False
                                 and not value.get("error") and entry.get("fetch_status") != "failed"
                                 for value, entry in zip(assessments, entries)),
            "failed": sum(entry.get("fetch_status") == "failed" or bool(value.get("error"))
                          for value, entry in zip(assessments, entries))}


def run(root: Path, gh: GitHub, summarizer: Summarizer, today: dt.date, dry_run: bool = False,
        search: bool = False, dump_dir: Path | None = None, workers: int = 2, progress=None,
        *, discovery_domain: str | None = None, history_names: list[str] | None = None,
        manual_repo: str | None = None, manual_ref: str | None = None) -> dict:
    if sum(value is not None for value in (discovery_domain, history_names, manual_repo)) > 1:
        raise CollectError("저장소 수집 방식을 동시에 지정할 수 없습니다")
    if manual_repo is not None and (not isinstance(manual_repo, str)
            or not discovery.REPO_NAME.fullmatch(manual_repo) or manual_repo.split("/")[1] in (".", "..")):
        raise CollectError("유효한 GitHub 저장소 이름이 필요합니다")
    if manual_ref is not None and (manual_repo is None or not isinstance(manual_ref, str)
                                  or not re.fullmatch(r"[a-fA-F0-9]{40}", manual_ref)):
        raise CollectError("고정 버전은 40자리 커밋 SHA여야 합니다")
    if history_names is not None and (
            not isinstance(history_names, list) or not 1 <= len(history_names) <= MAX_CANDIDATES
            or any(not isinstance(name, str) or not discovery.REPO_NAME.fullmatch(name)
                   or name.split("/")[1] in (".", "..") for name in history_names)
            or len(set(history_names)) != len(history_names)):
        raise CollectError("과거 저장소 보강은 유효한 저장소 1~25개를 중복 없이 지정해야 합니다")
    weekly = discovery_domain is None and history_names is None and manual_repo is None
    if manual_repo is not None:
        summarizer = Summarizer(backend="python")
    python_backend = getattr(summarizer, "backend", None) == "python"
    filter_metadata = python_backend and discovery_domain is None and manual_repo is None
    root = Path(root)
    taxonomy = load_taxonomy(root / "catalog" / "taxonomy.json")
    catalog_path = root / "catalog" / "catalog.json"
    previous = _read_json(catalog_path, {"repos": []})
    if not isinstance(previous, dict) or not isinstance(previous.get("repos"), list):
        raise CollectError("기존 카탈로그 구조가 올바르지 않습니다")
    prev = previous["repos"]
    if any(not isinstance(e, dict) or not isinstance(e.get("id"), str) for e in prev):
        raise CollectError("기존 카탈로그 항목 구조가 올바르지 않습니다")
    for entry in prev:
        if any(not isinstance(entry.get(key), kind) or (key == "stars" and isinstance(entry[key], bool))
               for key, kind in STRUCTURAL.items()):
            raise CollectError(f"기존 카탈로그 항목 구조가 올바르지 않습니다: {entry['id']}")
    prev_by_id = {e["id"]: e for e in prev}
    if manual_repo is not None and manual_repo.casefold() in {name.casefold() for name in prev_by_id}:
        raise CollectError("이미 카탈로그에 있는 저장소입니다")
    if len(prev_by_id) != len(prev):
        raise CollectError("기존 카탈로그에 중복 저장소가 있습니다")
    if history_names is not None and any(
            name not in prev_by_id or not isinstance(prev_by_id[name].get("sources"), list)
            or ARCHIVE_SOURCE not in prev_by_id[name]["sources"] for name in history_names):
        raise CollectError("과거 아카이브에서 이미 가져온 저장소만 보강할 수 있습니다")
    cache = _read_json(root / "cache" / "repos.json", {})
    if not isinstance(cache, dict):
        raise CollectError("저장소 캐시 구조가 올바르지 않습니다")
    snap_dir = root / "snapshots"
    api_start, usage_start = gh.calls, dict(summarizer.usage)

    def emit(stage, message, current, total, repo=None):
        if progress:
            progress({"stage": stage, "message": message, "current": current, "total": total, "repo": repo})

    source = "manual" if manual_repo is not None else "history:backfill" if history_names is not None else (
        f"discovery:{discovery_domain}" if discovery_domain is not None else "trending:weekly")
    emit("fetching", f"{manual_repo} 저장소를 확인합니다" if manual_repo is not None else
         "과거 저장소의 현재 정보를 확인합니다" if history_names is not None else (
        "GitHub 분야별 저장소를 찾습니다" if discovery_domain is not None else "GitHub 주간 Trending을 확인합니다"), 0, 0)
    if manual_repo is not None:
        manual_url = f"https://github.com/{manual_repo}" + (f"/tree/{manual_ref.lower()}" if manual_ref else "")
        cands = {manual_repo: {"sources": ["manual", f"manual:{manual_url}"], "trending": {}, "html": {}, "in_current_trending": False}}
        parsed_counts = {"manual": 1}
    elif history_names is not None:
        cands = {name: {"sources": [], "trending": {}, "html": {
            "stars": prev_by_id[name].get("stars"), "description": prev_by_id[name].get("description"),
            "language": prev_by_id[name].get("language")}} for name in history_names}
        parsed_counts = {"history": len(cands)}
    elif discovery_domain is not None:
        try:
            cands, parsed_counts = discovery.gather_candidates(gh, discovery_domain)
        except GitHubError as exc:
            raise CollectError(f"분야별 저장소를 찾지 못했습니다: {exc}") from exc
    else:
        cands, parsed_counts = gather_candidates(gh, prev, {}, search)
    if not cands:
        raise CollectError("수집 결과가 0개이므로 기존 카탈로그를 유지합니다")
    for name, cand in cands.items():
        old = prev_by_id.get(name, {})
        old_sources = old.get("sources")
        old_sources = [value for value in old_sources if isinstance(value, str)] if isinstance(old_sources, list) else []
        cand["sources"] = list(dict.fromkeys([*old_sources, *cand["sources"]]))
        if not weekly and old:
            cand["in_current_trending"] = old.get("in_current_trending") is True
            cand["trending"] = old.get("trending") or {}
            cand["preserve_weekly"] = cand["in_current_trending"]
    entries = [{**e, **({"in_current_trending": False} if weekly else {})}
               for e in prev if e["id"] not in cands]
    jobs, failed, snapshot, warnings = [], [], {"date": today.isoformat(), "repos": {}}, []
    metadata_only = 0
    for current, (name, cand) in enumerate(cands.items(), 1):
        emit("fetching", f"{name} README와 파일 목록을 확인합니다", current - 1, len(cands), name)
        info, old = {}, prev_by_id.get(name, {})
        unknown = {**detect([]), "skill_count": None}
        unknown.pop("skills")
        analysis = {"pushed_at": None, "commit": "", "signals": unknown, "skills": [],
                    "supports": {"claude_code": None, "codex": None}, "prescan": [],
                    "metadata_available": False, "file_signals_available": False}
        try:
            info = gh.repo(name)
            if filter_metadata and not _agent_candidate(name, info, old):
                entries.append(_metadata_only_entry(name, info, analysis, cand, old, today, snap_dir))
                metadata_only += 1
                emit("fetching", f"{name} 메타데이터 확인 완료 · 상세 수집 생략", current, len(cands), name)
                continue
            analysis = analyze_repo(gh, name, cache, info=info, partial=analysis,
                                    **({"ref": manual_ref} if manual_ref is not None else {}))
        except GitHubError as exc:
            if manual_repo is not None:
                raise CollectError(f"저장소를 추가하지 못했습니다: {exc}") from exc
            failed.append(f"{name}: {exc}")
            observed = cand["html"]
            error = f"GitHub 조회 실패: {exc}"
            if old:
                entry = {**old, "in_current_trending": cand["in_current_trending"], "trending": cand["trending"],
                         "sources": cand["sources"], "last_seen": today.isoformat(),
                         "classification_review_reason": old.get("classification_review_reason", old.get("review_reason", "")),
                         "classification_summary_status": old.get("classification_summary_status", old.get("summary_status"))}
                if info:
                    for field, api_field in (("url", "html_url"), ("description", "description"),
                                             ("forks", "forks_count"), ("language", "language"),
                                             ("topics", "topics"), ("pushed_at", "pushed_at")):
                        if api_field in info:
                            entry[field] = info[api_field]
                    entry["metadata_date"] = today.isoformat()
                else:
                    entry["metadata_date"] = old.get("metadata_date", old.get("last_seen"))
                stars = info.get("stargazers_count", observed.get("stars"))
                if stars is not None:
                    entry.update({"stars": stars, "stars_observed_at": today.isoformat()})
                entry["file_signals_date"] = old.get("file_signals_date", old.get("last_seen"))
                if analysis["file_signals_available"]:
                    entry.update({"file_signals": analysis["signals"], "file_kind": analysis["signals"]["file_kind"],
                                  "skill_count": analysis["signals"]["skill_count"], "skills": analysis["skills"],
                                  "supports": analysis["supports"], "commit": analysis["commit"],
                                  "file_signals_date": today.isoformat()})
                if not cand.get("preserve_weekly"):
                    entry["stars_7d"], entry["stars_7d_source"] = stars_7d(
                        name, stars, today, snap_dir, cand["trending"] if cand["in_current_trending"] else {})
            else:
                info = {"stargazers_count": observed.get("stars"),
                        "description": observed.get("description") or "", "language": observed.get("language"), **info}
                entry = _entry(name, info, analysis, _placeholder(name, info.get("description") or "", error),
                               cand, {}, today, snap_dir)
            entry.update({"fetch_status": "failed", "fetch_error": str(exc), "summary_status": "needs_review"})
            entry["function_catalog"] = _function_assessment(name, entry, analysis, entry)
            reason = entry.get("review_reason") or ""
            if error not in reason:
                entry["review_reason"] = f"{reason}; {error}" if reason else error
            entries.append(entry)
            emit("fetching", f"{name} 조회 결과를 보존했습니다", current, len(cands), name)
            continue
        summary = None
        if python_backend and _has_model_output(old):
            summary = {key: old[key] for key in SUMMARY_KEYS if key in old}
        elif _has_model_output(old) and old.get("readme_sha") == analysis["readme_sha"]:
            if isinstance(old.get("raw_classification"), dict):
                summary = validate_output(old["raw_classification"], analysis["_sources"], taxonomy,
                                          analysis["signals"], raw_text=old.get("raw_response"))
                for key in CLASSIFICATION_KEYS:
                    if key in old:
                        summary[key] = old[key]
                    elif key in old["raw_classification"]:
                        summary[key] = old["raw_classification"][key]
                if "title_ko" not in old["raw_classification"] and isinstance(old.get("title_ko"), str):
                    summary["title_ko"] = old["title_ko"]
            else:
                summary = {key: old[key] for key in SUMMARY_KEYS if key in old}
                summary["review_reason"] = old.get("classification_review_reason", old.get("review_reason", ""))
                summary["summary_status"] = old.get("classification_summary_status", old.get("summary_status"))
        jobs.append({"name": name, "info": info, "analysis": analysis, "cand": cand, "old": old, "summary": summary})
        emit("fetching", f"{name} 파일 확인 완료", current, len(cands), name)

    todo = [job for job in jobs if job["summary"] is None]
    emit("classifying", f"README {len(todo)}개를 분류합니다", 0, len(todo))
    def classify(job):
        try:
            return summarizer.summarize(job["name"], job["info"].get("description") or "",
                                        job["analysis"]["_sources"], taxonomy, job["analysis"]["signals"])
        except Exception as exc:
            return _placeholder(job["name"], job["info"].get("description") or "", f"요약 호출 실패: {exc}")
    with ThreadPoolExecutor(max_workers=max(1, min(workers, MAX_CANDIDATES))) as executor:
        futures = {executor.submit(classify, job): job for job in todo}
        for current, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            job["summary"] = future.result()
            emit("classifying", f"{job['name']} 분류 완료", current, len(todo), job["name"])

    for job in jobs:
        entry = _entry(job["name"], job["info"], job["analysis"], job["summary"],
                       job["cand"], job["old"], today, snap_dir)
        if python_backend:
            entry["agent_catalog"] = _agent_assessment(job["name"], job["info"], job["analysis"], job["old"], today)
        entries.append(entry)
    sanity_check(entries, prev, parsed_counts, taxonomy)
    for entry in entries:
        # Pending placeholders have no model classification to validate yet.
        entry_warnings = validate_entry(entry, taxonomy) if entry.get("classification_attempted") else []
        if entry_warnings:
            entry["validation_warnings"] = entry_warnings
            entry["summary_status"] = "needs_review"
            reason = entry.get("review_reason") or ""
            additions = [warning for warning in entry_warnings if warning not in reason]
            entry["review_reason"] = "; ".join([reason, *additions] if reason else additions)
            warnings.extend(f"{entry['id']}: {warning}" for warning in entry_warnings)
        if entry.get("in_current_trending") and entry.get("stars_observed_at") == today.isoformat():
            snapshot["repos"][entry["id"]] = {"stars": entry["stars"], "forks": entry.get("forks", 0)}
    entries.sort(key=lambda e: (e.get("stars_7d") is None, -(e.get("stars_7d") or 0), e["stars"] is None, -(e["stars"] or 0)))
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for entry in entries:
        if entry["id"] not in cands:
            continue
        old = prev_by_id.get(entry["id"])
        # An archive's first current lookup establishes the content baseline.
        initial_history_fill = history_names is not None and old is not None and not (
            old.get("readme_sha") or old.get("sources_sha"))
        if initial_history_fill:
            continue
        if (old is None or entry.get("description") != old.get("description")
                or any(old.get(key) is not None and entry.get(key) is not None and entry[key] != old[key]
                       for key in ("readme_sha", "sources_sha"))):
            entry["catalog_updated_at"] = now
    if history_names is not None:
        for entry in entries:
            if entry["id"] not in cands:
                continue
            model_failed = (not python_backend and summarizer.enabled and entry.get("readme_sha") not in (None, "", _sha(""))
                            and not _has_model_output(entry))
            complete = entry.get("fetch_status") == "ok" and not model_failed
            entry.update(history_backfill_status="complete" if complete else "failed", history_last_attempt=now)
            if complete:
                entry["history_backfill_at"] = now
    doc = {"generated_at": now, "date": today.isoformat(), "count": len(entries), "repos": entries}
    from .organize import export_functions, function_summary
    doc["function_summary"] = function_summary(entries, taxonomy.get("functions") or {"other": {}})
    for key in ("history_import", "screening_summary"):
        if key in previous:
            doc[key] = previous[key]
    needs = sum(e.get("summary_status") == "needs_review" for e in entries)
    report = {"source": source, "candidates": len(cands), "catalog": len(entries),
              "by_kind": dict(Counter(_report_label(e.get("kind")) for e in entries).most_common()),
              "by_relevance": dict(Counter(_report_label(e.get("relevance")) for e in entries).most_common()),
              "needs_review": needs, "pending": sum(e.get("summary_status") == "pending" for e in entries),
              "needs_review_ratio": round(needs / len(entries), 3) if entries else 0.0,
              "trending_parsed": parsed_counts, "failed": failed, "validation_warnings": warnings,
              "api_calls": gh.calls - api_start,
              "model_usage": {key: value - usage_start.get(key, 0) for key, value in summarizer.usage.items()}}
    if python_backend:
        report["screening"] = {"metadata_only": metadata_only, "deeply_checked": len(jobs),
                               "by_status": dict(Counter(entry["agent_catalog"]["status"] for entry in entries
                                   if entry["id"] in cands and isinstance(entry.get("agent_catalog"), dict)))}
        doc["screening_summary"] = screening_summary(entries, previous.get("screening_summary"), now)
    emit("saving", "카탈로그를 저장합니다" if not dry_run else "수집 결과를 검증했습니다", 0, 1)
    if dump_dir:
        _write_json(Path(dump_dir) / "catalog.json", doc)
    if not dry_run:
        if weekly:
            by_id = {entry["id"]: entry for entry in entries}
            repositories = [{"id": name, "rank": cand["trending"]["weekly_rank"], "stars_total": by_id[name]["stars"],
                             "period_stars": by_id[name].get("stars_7d")
                             if by_id[name].get("stars_7d_source") == "trending_week" else None}
                            for name, cand in cands.items()]
            repositories.sort(key=lambda repo: repo["rank"])
            iso_year, iso_week, _ = today.isocalendar()
            _write_json(root / "weekly" / f"{iso_year}-W{iso_week:02}.json", {
                "schema_version": 1, "kind": "trending_snapshot", "period": "weekly", "scope": "all",
                "snapshot_date": today.isoformat(), "captured_at": now,
                "source_url": "https://github.com/trending?since=weekly",
                "count": len(repositories), "repositories": repositories})
        if manual_repo is None:
            _write_json(snap_dir / f"{today.isoformat()}.json", snapshot)
        _write_json(root / "cache" / "repos.json", cache)
        _write_json(catalog_path, doc)
        export_functions(root, doc, taxonomy)
        prune_snapshots(snap_dir, today)
    emit("saving", f"저장소 {len(entries)}개 확인 완료", 1, 1)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="GitHub 수집과 Python 규칙 분류 (Codex는 LABSKILL_BACKEND=codex 명시 시 사용)")
    parser.add_argument("--root", default=".")
    parser.add_argument("--date", help="YYYY-MM-DD (기본: 오늘, KST)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--trending-only", action="store_true", help="호환 옵션: 항상 주간 Trending만 수집")
    parser.add_argument("--dump", help="결과 catalog.json 사본을 저장할 폴더")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("LABSKILL_WORKERS", "2")))
    args = parser.parse_args(argv)
    kst = dt.timezone(dt.timedelta(hours=9))
    today = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(kst).date()
    try:
        report = run(Path(args.root), GitHub.from_gh(), Summarizer.from_env(), today, args.dry_run,
                     dump_dir=Path(args.dump) if args.dump else None, workers=args.workers)
    except (CollectError, GitHubError) as exc:
        print(f"[fail] 카탈로그를 갱신하지 않았습니다:\n{exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
