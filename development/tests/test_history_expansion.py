"""Archive expansion uses synthetic rosters and temporary catalogs only."""
import copy
import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2] / "labskill-catalog"
sys.path.insert(0, str(PROJECT))

from collector import collect, history
from collector.summarize import Summarizer

DAY = dt.date(2026, 10, 22)
EXPANDED = "trending-history-expanded.json"


def roster(days):
    snapshots, repositories = [], {}
    for day, names in sorted(days.items()):
        record = {"date": day, "period": "daily", "scope": "all",
                  "source_path": f"archive/repository/{day}/(null).json",
                  "source_blob": hashlib.sha1(day.encode()).hexdigest()}
        snapshots.append({**record, "repositories": names})
        for rank, name in enumerate(names, 1):
            repo = repositories.setdefault(name.casefold(), {"id": name, "url": f"https://github.com/{name}",
                                                              "history": []})
            repo["history"].append({**record, "rank": rank})
    start, end = min(days), max(days)
    first, last = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    for repo in repositories.values():
        records = repo["history"]
        repo.update(trending_first_seen=records[0]["date"], trending_last_seen=records[-1]["date"],
                    appearance_days=len(records), best_daily_rank=min(row["rank"] for row in records))
    return {"schema_version": 1, "kind": "trending_history_roster",
            "source_repository": history.SOURCE_REPOSITORY, "source_commit": "a" * 40,
            "source_period": "daily", "scope": "all", "range": {"start": start, "end": end, "inclusive": True},
            "count": len(repositories), "appearance_count": sum(len(names) for names in days.values()),
            "coverage": {"expected_days": (last - first).days + 1, "available_days": len(days),
                         "nonempty_days": sum(bool(names) for names in days.values()),
                         "missing_dates": [(first + dt.timedelta(days=index)).isoformat()
                                           for index in range((last - first).days + 1)
                                           if (first + dt.timedelta(days=index)).isoformat() not in days]},
            "snapshots": snapshots, "repositories": list(repositories.values())}


class FakeGitHub:
    def __init__(self):
        self.calls = 0
        self.description = "Coding agent skills."
        self.readme_text = "# Agent skills\nSkills for coding agents.\n"
        self.skill_text = "---\nname: helper\ndescription: Help coding agents.\n---\n"
        self.stars = 10

    def repo(self, name):
        self.calls += 1
        return {"full_name": name, "html_url": f"https://github.com/{name}", "description": self.description,
                "topics": [], "stargazers_count": self.stars, "forks_count": 1, "default_branch": "main",
                "pushed_at": "2026-10-22T00:00:00Z"}

    def head_commit(self, name, branch):
        self.calls += 1
        return "c" * 40

    def tree(self, name, sha):
        self.calls += 1
        return [{"path": path, "type": "blob"} for path in ("README.md", "SKILL.md")]

    def readme(self, name, sha):
        self.calls += 1
        return self.readme_text, "README.md"

    def file_text(self, name, path, sha):
        self.calls += 1
        return self.skill_text


class HistoryExpansionCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "catalog").mkdir()
        (self.root / "catalog/taxonomy.json").write_bytes((PROJECT / "catalog/taxonomy.json").read_bytes())

    def manifest(self, days, filename=EXPANDED):
        document = roster(days)
        collect._write_json(self.root / "imports" / filename, document)
        return document

    def catalog(self):
        return json.loads((self.root / "catalog/catalog.json").read_text())

    def seed(self):
        return history.ensure_seed(self.root, DAY)

    def collect(self, gh, names):
        return collect.run(self.root, gh, Summarizer(backend="python"), DAY, history_names=names)


class TestHistoryExpansion(HistoryExpansionCase):
    def test_original_manifest_remains_the_fallback(self):
        self.manifest({"2026-10-18": ["acme/original"]}, history.MANIFEST)
        self.assertTrue(self.seed())
        self.assertEqual([row["id"] for row in self.catalog()["repos"]], ["acme/original"])

    def test_expanded_manifest_takes_priority_over_the_original(self):
        self.manifest({"2026-10-18": ["acme/original"]}, history.MANIFEST)
        self.manifest({"2025-10-22": ["acme/expanded"]})
        self.assertTrue(self.seed())
        self.assertEqual([row["id"] for row in self.catalog()["repos"]], ["acme/expanded"])

    def test_older_only_roster_adds_records_without_losing_recent_history(self):
        self.manifest({"2026-10-18": ["acme/kept"]}, history.MANIFEST)
        self.seed()
        old_history = copy.deepcopy(self.catalog()["repos"][0]["trend_history"])
        self.manifest({"2025-10-22": ["acme/older", "acme/kept"]})
        self.seed()
        doc = self.catalog()
        rows = {row["id"]: row for row in doc["repos"]}
        kept = rows["acme/kept"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(kept["trend_history"][1:], old_history)
        self.assertEqual((kept["trending_first_seen"], kept["trending_last_seen"], kept["appearance_days"],
                          kept["best_daily_rank"]), ("2025-10-22", "2026-10-18", 2, 1))
        self.assertEqual(doc["history_import"]["range"],
                         {"start": "2025-10-22", "end": "2026-10-18", "inclusive": True})
        self.assertEqual(doc["history_import"]["total"], 2)

    def test_overlap_keeps_the_existing_observation_and_deduplicates_appearances(self):
        self.manifest({"2026-10-18": ["acme/other", "acme/kept"]}, history.MANIFEST)
        self.seed()
        doc = self.catalog()
        kept = next(row for row in doc["repos"] if row["id"] == "acme/kept")
        kept["trend_history"][0]["annotation"] = "Previously checked observation"
        before = copy.deepcopy(kept["trend_history"][0])
        collect._write_json(self.root / "catalog/catalog.json", doc)
        self.manifest({"2026-10-18": ["acme/kept"], "2026-10-22": ["acme/kept"]})
        self.seed()
        kept = next(row for row in self.catalog()["repos"] if row["id"] == "acme/kept")
        self.assertEqual(kept["trend_history"][0], before)
        self.assertEqual(kept["appearance_days"], 2)
        self.assertEqual(kept["best_daily_rank"], 1)

    def test_case_insensitive_import_keeps_the_original_id(self):
        self.manifest({"2026-10-18": ["Acme/Kept"]}, history.MANIFEST)
        self.seed()
        self.manifest({"2025-10-22": ["acme/kept", "acme/new"]})
        self.seed()
        rows = self.catalog()["repos"]
        self.assertEqual([row["id"] for row in rows], ["Acme/Kept", "acme/new"])
        self.assertEqual(rows[0]["appearance_days"], 2)

    def test_existing_classifications_progress_and_personal_files_are_untouched(self):
        self.manifest({"2026-10-18": ["acme/kept"]}, history.MANIFEST)
        self.seed()
        doc = self.catalog()
        kept = doc["repos"][0]
        kept.update(title_ko="사람이 검토한 제목", description="Previously fetched description", stars=14,
                    raw_classification={"kind": "library"}, raw_response="Original model response",
                    readme_sha="original-readme", sources_sha="original-sources", first_seen="2020-01-01",
                    agent_catalog={"version": 1, "status": "selected"}, function_catalog={"primary": "code"},
                    history_backfill_status="failed", history_backfill_at="2026-10-18T12:00:00Z",
                    history_last_attempt="2026-10-19T12:00:00Z", personal_note="Local note")
        before = copy.deepcopy(kept)
        doc["local_metadata"] = {"keep": True}
        collect._write_json(self.root / "catalog/catalog.json", doc)
        library = self.root / "state/library.json"
        collect._write_json(library, {"saved": ["acme/kept"], "notes": {"acme/kept": "My note"}})
        library_bytes = library.read_bytes()
        self.manifest({"2025-10-22": ["acme/kept", "acme/new"]})
        self.assertTrue(self.seed())
        updated = self.catalog()
        kept = updated["repos"][0]
        history_fields = {"trend_history", "trending_first_seen", "trending_last_seen", "appearance_days", "best_daily_rank"}
        self.assertEqual({key: value for key, value in kept.items() if key not in history_fields},
                         {key: value for key, value in before.items() if key not in history_fields})
        self.assertEqual(updated["local_metadata"], {"keep": True})
        self.assertEqual(library.read_bytes(), library_bytes)
        self.assertEqual(updated["repos"][1]["summary_status"], "pending")

    def test_new_repositories_reuse_the_existing_25_item_queue(self):
        names = [f"acme/repo{index:02}" for index in range(32)]
        self.manifest({"2025-10-22": names})
        self.assertTrue(self.seed())
        doc = self.catalog()
        batch = history.pending_names(doc, limit=100)
        self.assertEqual(len(doc["repos"]), 32)
        self.assertEqual(len(batch), 25)
        self.assertTrue(set(batch) <= set(names))
        self.assertTrue(all(row["history_backfill_status"] == "pending" for row in doc["repos"]))
        self.assertTrue(all("catalog_updated_at" not in row for row in doc["repos"]))

    def test_reapplying_an_unchanged_manifest_is_a_byte_for_byte_noop(self):
        self.manifest({"2025-10-22": ["acme/kept"]})
        self.assertTrue(self.seed())
        path = self.root / "catalog/catalog.json"
        doc = self.catalog()
        doc["repos"][0]["history_backfill_status"] = "complete"
        collect._write_json(path, doc)
        before, modified = path.read_bytes(), path.stat().st_mtime_ns
        self.assertFalse(self.seed())
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime_ns, modified)

    def test_source_coverage_roundtrips_without_filling_a_missing_day(self):
        manifest = roster({"2026-10-21": ["acme/kept"]})
        manifest["range"]["end"] = "2026-10-22"
        manifest["coverage"].update(expected_days=2, missing_dates=["2026-10-22"])
        collect._write_json(self.root / "imports" / EXPANDED, manifest)
        self.seed()
        doc = self.catalog()
        self.assertEqual(doc["history_import"].get("coverage"), manifest["coverage"])
        self.assertEqual(history.summary(doc)["coverage"], manifest["coverage"])
        self.assertIsNone(history.summary({"history_import": {}, "repos": []})["coverage"])


class TestHistoryUpdateBaseline(HistoryExpansionCase):
    def test_first_metadata_only_backfill_does_not_announce_a_new_update(self):
        self.manifest({"2025-10-22": ["acme/plain"]}, history.MANIFEST)
        self.seed()
        gh = FakeGitHub()
        gh.description = "A plain terminal application."
        report = self.collect(gh, ["acme/plain"])
        row = self.catalog()["repos"][0]
        self.assertEqual(row["fetch_status"], "ok")
        self.assertEqual(row["description"], gh.description)
        self.assertNotIn("catalog_updated_at", row)
        self.assertEqual(report["model_usage"]["calls"], 0)

    def test_first_readme_and_skill_backfill_establishes_a_baseline_without_new_badges(self):
        self.manifest({"2025-10-22": ["acme/agent-skills"]}, history.MANIFEST)
        self.seed()
        report = self.collect(FakeGitHub(), ["acme/agent-skills"])
        row = self.catalog()["repos"][0]
        self.assertTrue(row["readme_sha"])
        self.assertTrue(row["sources_sha"])
        self.assertEqual(row["history_backfill_status"], "complete")
        self.assertNotIn("catalog_updated_at", row)
        self.assertEqual(report["model_usage"]["calls"], 0)

    def test_actual_readme_and_skill_changes_still_update_the_timestamp(self):
        self.manifest({"2025-10-22": ["acme/agent-skills"]}, history.MANIFEST)
        self.seed()
        gh = FakeGitHub()
        self.collect(gh, ["acme/agent-skills"])
        for field in ("readme_text", "skill_text"):
            with self.subTest(field=field):
                doc = self.catalog()
                doc["repos"][0]["catalog_updated_at"] = "2000-01-01T00:00:00+00:00"
                collect._write_json(self.root / "catalog/catalog.json", doc)
                setattr(gh, field, getattr(gh, field) + "A real content change.\n")
                self.collect(gh, ["acme/agent-skills"])
                timestamp = self.catalog()["repos"][0]["catalog_updated_at"]
                self.assertNotEqual(timestamp, "2000-01-01T00:00:00+00:00")
                self.assertIsNotNone(dt.datetime.fromisoformat(timestamp).utcoffset())


if __name__ == "__main__":
    unittest.main()
