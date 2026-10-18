"""Manual imports and personal library use fake GitHub data and temporary files only."""
import copy
import datetime as dt
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJECT = Path(__file__).resolve().parents[2] / "labskill-catalog"
sys.path.insert(0, str(PROJECT))

import app
from collector import collect, discovery, history
from collector.github_client import GitHubError
from collector.summarize import Summarizer

DAY = dt.date(2026, 10, 18)
PIN = "a" * 40


class FakeGitHub:
    token = ""

    def __init__(self):
        self.calls = 0
        self.paths = []
        self.description = "A plain terminal application."
        self.readme_text = "# Terminal\nA terminal application.\n"
        self.skill_text = "---\nname: helper\ndescription: A helper.\n---\n"
        self.stars = 100
        self.fail = False

    def repo(self, name):
        self.calls += 1
        self.paths.append(("repo", name))
        if self.fail:
            raise GitHubError("GitHub unavailable", 503)
        return {"full_name": name, "html_url": f"https://github.com/{name}", "description": self.description,
                "topics": [], "stargazers_count": self.stars, "forks_count": 2, "default_branch": "main",
                "pushed_at": "2026-10-18T00:00:00Z"}

    def head_commit(self, name, branch):
        self.calls += 1
        self.paths.append(("head", name))
        return "b" * 40

    def tree(self, name, ref):
        self.calls += 1
        self.paths.append(("tree", ref))
        return [{"path": "README.md", "type": "blob"}, {"path": "SKILL.md", "type": "blob"}]

    def readme(self, name, ref):
        self.calls += 1
        self.paths.append(("readme", ref))
        return self.readme_text, "README.md"

    def file_text(self, name, path, ref):
        self.calls += 1
        self.paths.append((path, ref))
        return self.skill_text

    def trending_html(self, since):
        self.calls += 1
        return '<article class="Box-row"><h2><a href="/acme/existing">existing</a></h2></article>'


class FeatureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "catalog").mkdir()
        (self.root / "catalog/taxonomy.json").write_bytes((PROJECT / "catalog/taxonomy.json").read_bytes())
        self.old = history._pending("acme/existing", DAY.isoformat())
        self.old.update(sources=["trending:weekly", history.SOURCE], in_current_trending=True,
                        trending={"weekly_rank": 3, "weekly_stars": 12}, stars_7d=12,
                        stars_7d_source="trending_week", description="A plain terminal application.",
                        trend_history=[{"date": DAY.isoformat(), "rank": 1}], history_backfill_status="complete")
        self.old["file_signals"] = {"skill_count": 1}
        self.doc = {"generated_at": "2026-10-17T00:00:00Z", "date": DAY.isoformat(), "count": 1,
                    "repos": [copy.deepcopy(self.old)], "history_import": {"total": 1}}
        collect._write_json(self.root / "catalog/catalog.json", self.doc)
        self.gh = FakeGitHub()

    def read_catalog(self):
        return json.loads((self.root / "catalog/catalog.json").read_text())

    def controller(self, **options):
        with mock.patch.dict(os.environ, {"LABSKILL_BACKEND": "python"}):
            controller = app.AppController(self.root, github_factory=lambda: self.gh,
                                           github_probe=lambda: True, codex_probe=lambda: False, **options)
        self.addCleanup(controller.close)
        return controller

    def run_collect(self, **options):
        return collect.run(self.root, self.gh, Summarizer(backend="python"), DAY, **options)


class TestManualCollection(FeatureCase):
    def test_manual_import_is_deep_pinned_and_preserves_existing_records_and_weekly_files(self):
        snapshot = self.root / "snapshots" / f"{DAY}.json"
        collect._write_json(snapshot, {"date": str(DAY), "repos": {"acme/existing": {"stars": 99}}})
        before_snapshot = snapshot.read_bytes()
        report = self.run_collect(manual_repo="acme/plain", manual_ref=PIN)
        doc = self.read_catalog()
        existing = next(row for row in doc["repos"] if row["id"] == "acme/existing")
        added = next(row for row in doc["repos"] if row["id"] == "acme/plain")
        self.assertEqual(existing, self.old)
        self.assertEqual(doc["history_import"], self.doc["history_import"])
        self.assertEqual(added["commit"], PIN)
        self.assertEqual(added["skill_count"], 1)
        self.assertIn("manual", added["sources"])
        self.assertIn(f"manual:https://github.com/acme/plain/tree/{PIN}", added["sources"])
        self.assertEqual(added["classification_method"], "python_rules")
        self.assertEqual(report["source"], "manual")
        self.assertNotIn(("head", "acme/plain"), self.gh.paths)
        self.assertIn(("SKILL.md", PIN), self.gh.paths)
        self.assertEqual(snapshot.read_bytes(), before_snapshot)

    def test_manual_failure_does_not_publish_a_placeholder_or_damage_catalog(self):
        before = (self.root / "catalog/catalog.json").read_bytes()
        self.gh.fail = True
        with self.assertRaises(collect.CollectError):
            self.run_collect(manual_repo="acme/plain")
        self.assertEqual((self.root / "catalog/catalog.json").read_bytes(), before)

    def test_manual_pipeline_cannot_opt_into_codex(self):
        codex = Summarizer(lambda *_: self.fail("Manual import must not invoke Codex"), backend="codex")
        collect.run(self.root, self.gh, codex, DAY, manual_repo="acme/plain")
        added = next(row for row in self.read_catalog()["repos"] if row["id"] == "acme/plain")
        self.assertEqual(added["classification_method"], "python_rules")
        self.assertEqual(codex.usage["calls"], 0)

    def test_content_timestamp_ignores_stars_and_initial_field_introduction(self):
        self.run_collect()
        row = self.read_catalog()["repos"][0]
        self.assertNotIn("catalog_updated_at", row)
        self.gh.stars += 5
        self.run_collect()
        self.assertNotIn("catalog_updated_at", self.read_catalog()["repos"][0])
        self.gh.description += " New feature."
        self.run_collect()
        first = self.read_catalog()["repos"][0]["catalog_updated_at"]
        self.assertIsNotNone(dt.datetime.fromisoformat(first).utcoffset())
        self.gh.stars += 1
        self.run_collect()
        self.assertEqual(self.read_catalog()["repos"][0]["catalog_updated_at"], first)

    def test_readme_and_skill_changes_update_timestamp_across_collection_modes(self):
        self.run_collect()
        for index, mode in enumerate(({}, {"history_names": ["acme/existing"]}, {"discovery_domain": "code"})):
            doc = self.read_catalog()
            doc["repos"][0]["catalog_updated_at"] = "2000-01-01T00:00:00+00:00"
            collect._write_json(self.root / "catalog/catalog.json", doc)
            if index == 1:
                self.gh.skill_text += "Changed skill only.\n"
            else:
                self.gh.readme_text += "Changed README only.\n"
            with mock.patch.object(discovery, "gather_candidates", return_value=({"acme/existing": {
                    "sources": ["discovery:code"], "trending": {}, "html": {}, "in_current_trending": False}}, {"discovery": 1})):
                self.run_collect(**mode)
            row = self.read_catalog()["repos"][0]
            self.assertNotEqual(row["catalog_updated_at"], "2000-01-01T00:00:00+00:00")
            self.assertEqual(row["trend_history"], self.old["trend_history"])


class TestUserHTTP(FeatureCase):
    def setUp(self):
        super().setUp()
        self.controller_instance = self.controller()
        self.server = app.create_server(self.controller_instance, 0)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.controller_instance.wait(3)
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(3)

    def request(self, method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request_headers = {"Content-Type": "application/json", "X-LabSkill-Request": "1"}
        if headers is not None:
            request_headers = headers
        try:
            conn.request(method, path, body, request_headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def library(self):
        return {"schema_version": 1, "saved_ids": ["acme/existing"],
                "collections": [{"id": "reading", "name": "읽을 자료", "repo_ids": ["acme/existing"]}],
                "notes": {"acme/existing": "연구 메모 " * 600}}

    def test_manual_api_accepts_url_and_background_status_finishes_with_python_data(self):
        status, body = self.request("POST", "/api/repos", {"url": f"https://github.com/acme/plain.git/tree/{PIN}/"})
        self.assertEqual(status, 202)
        self.assertTrue(body["accepted"])
        self.assertEqual(body["id"], "acme/plain")
        self.assertTrue(self.controller_instance.wait(3))
        state = self.request("GET", "/api/status")[1]
        self.assertFalse(state["running"])
        self.assertEqual(state["stage"], "complete")
        added = next(row for row in self.request("GET", "/api/catalog")[1]["repos"] if row["id"] == "acme/plain")
        self.assertTrue(added["catalog_updated_at"])

    def test_manual_import_is_python_even_when_codex_is_opted_in(self):
        self.controller_instance._classification_backend = "codex"
        with mock.patch.object(self.controller_instance, "_summarizer_factory", side_effect=AssertionError("No Codex")):
            self.assertEqual(self.request("POST", "/api/repos", {"url": "https://github.com/acme/plain/"})[0], 202)
            self.assertTrue(self.controller_instance.wait(3))
        self.assertIsNone(self.controller_instance.status()["last_error"])
        self.assertEqual(self.controller_instance.status()["classification_backend"], "python")
        added = next(row for row in self.controller_instance.catalog()["repos"] if row["id"] == "acme/plain")
        self.assertIn("manual:https://github.com/acme/plain", added["sources"])

    def test_duplicate_and_busy_imports_are_conflicts(self):
        self.assertEqual(self.request("POST", "/api/repos", {"url": "https://github.com/ACME/EXISTING.git"})[0], 409)
        entered, release = threading.Event(), threading.Event()
        original = self.gh.repo
        def blocked(name):
            entered.set()
            release.wait(3)
            return original(name)
        self.gh.repo = blocked
        self.addCleanup(release.set)
        self.assertEqual(self.request("POST", "/api/repos", {"url": "https://github.com/acme/plain"})[0], 202)
        self.assertTrue(entered.wait(1))
        status = self.controller_instance.status()
        self.assertEqual(status["stage"], "manual")
        self.assertEqual(status["repo"], "acme/plain")
        self.assertEqual(self.request("POST", "/api/repos", {"url": "https://github.com/acme/other"})[0], 409)
        self.assertFalse(self.controller_instance.refresh())
        release.set()

    def test_manual_api_rejects_non_repo_urls_without_any_github_access(self):
        invalid = ["file:///etc/passwd", "https://api.github.com/repos/acme/plain", "https://github.com.evil/acme/plain",
                   "https://user@github.com/acme/plain", "https://github.com:443/acme/plain", "https://github.com/acme/../plain",
                   "https://github.com/acme/%2e%2e", "https://github.com/acme/plain?url=http://localhost",
                   "https://github.com/acme/plain/tree/main", "https://github.com/acme/plain/issues", "https://github.com/acme/plain#readme"]
        for url in invalid:
            with self.subTest(url=url):
                self.assertEqual(self.request("POST", "/api/repos", {"url": url})[0], 400)
        self.assertEqual(self.gh.calls, 0)

    def test_manual_worker_failure_keeps_catalog_and_reports_failure(self):
        before = (self.root / "catalog/catalog.json").read_bytes()
        self.gh.fail = True
        self.assertEqual(self.request("POST", "/api/repos", {"url": "https://github.com/acme/plain"})[0], 202)
        self.assertTrue(self.controller_instance.wait(3))
        self.assertEqual(self.controller_instance.status()["stage"], "error")
        self.assertIn("GitHub", self.controller_instance.status()["last_error"])
        self.assertEqual((self.root / "catalog/catalog.json").read_bytes(), before)

    def test_library_defaults_and_utf8_roundtrip_survive_restart(self):
        self.assertEqual(self.request("GET", "/api/library"), (200, {
            "schema_version": 1, "saved_ids": [], "collections": [], "notes": {}}))
        payload = self.library()
        self.assertEqual(self.request("POST", "/api/library", payload), (200, payload))
        self.assertEqual(self.request("GET", "/api/library"), (200, payload))
        self.assertEqual(self.controller().library(), payload)
        self.assertIn("연구 메모", (self.root / "state/library.json").read_text(encoding="utf-8"))
        self.assertEqual(self.read_catalog(), self.doc)

    def test_invalid_library_updates_preserve_previous_file(self):
        payload = self.library()
        self.assertEqual(self.request("POST", "/api/library", payload)[0], 200)
        before = (self.root / "state/library.json").read_bytes()
        invalid = []
        for key, value in (("schema_version", True), ("saved_ids", ["unknown/../repo"]), ("saved_ids", ["acme/existing"] * 2),
                           ("notes", {"acme/existing": "x" * 4001}), ("notes", {"https://github.com/unknown/repo": "memo"}),
                           ("collections", [{"id": "a", "name": "x" * 61, "repo_ids": []}]),
                           ("collections", [{"id": str(i), "name": "n", "repo_ids": []} for i in range(101)]),
                           ("collections", [{"id": "same", "name": "n", "repo_ids": []}] * 2),
                           ("collections", [{"id": "../file", "name": "n", "repo_ids": []}])):
            invalid.append({**payload, key: value})
        invalid += [{**payload, "extra": True}, {**payload, "collections": [{"id": "a", "name": "n", "repo_ids": ["unknown/repo"]}]}]
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(self.request("POST", "/api/library", value)[0], 400)
                self.assertEqual((self.root / "state/library.json").read_bytes(), before)

    def test_library_disk_failure_preserves_previous_file(self):
        self.assertEqual(self.request("POST", "/api/library", self.library())[0], 200)
        before = (self.root / "state/library.json").read_bytes()
        with mock.patch.object(Path, "replace", side_effect=OSError("disk unavailable")):
            self.assertEqual(self.request("POST", "/api/library", app.EMPTY_LIBRARY)[0], 503)
        self.assertEqual((self.root / "state/library.json").read_bytes(), before)
        self.assertEqual(list((self.root / "state").glob("*.tmp")), [])

    def test_collection_cannot_contain_a_repo_missing_from_saved_ids(self):
        payload = self.library()
        self.assertEqual(self.request("POST", "/api/library", payload)[0], 200)
        before = (self.root / "state/library.json").read_bytes()
        self.assertEqual(self.request("POST", "/api/library", {**payload, "saved_ids": []})[0], 400)
        self.assertEqual((self.root / "state/library.json").read_bytes(), before)

    def test_legacy_ids_missing_from_catalog_roundtrip_without_being_added_to_catalog(self):
        payload = self.library()
        payload["saved_ids"].append("legacy/repository")
        payload["collections"][0]["repo_ids"].append("legacy/repository")
        payload["notes"]["legacy/repository"] = "이전 브라우저에 저장한 메모"
        self.assertEqual(self.request("POST", "/api/library", payload), (200, payload))
        self.assertEqual(self.request("GET", "/api/library"), (200, payload))
        self.assertEqual(self.controller().library(), payload)
        self.assertEqual(self.read_catalog(), self.doc)

    def test_legacy_ids_still_require_safe_bounded_repository_coordinates(self):
        payload = self.library()
        for repo_id in ("x/.", "x/..", "owner/repo/extra", "owner/%2e%2e", "owner/" + "r" * 135,
                        "file:///etc/passwd", "../repo", "owner/repo?query", 42):
            with self.subTest(repo_id=repo_id):
                self.assertEqual(self.request("POST", "/api/library", {**payload, "saved_ids": [repo_id]})[0], 400)
        self.assertEqual(self.request("POST", "/api/library", {
            **payload, "saved_ids": [f"legacy/repo{i}" for i in range(5001)]})[0], 400)

    def test_new_writes_require_existing_same_origin_and_json_protection(self):
        for endpoint, payload in (("/api/repos", {"url": "https://github.com/acme/plain"}), ("/api/library", self.library())):
            self.assertEqual(self.request("POST", endpoint, payload, headers={"Content-Type": "application/json"})[0], 403)
            self.assertEqual(self.request("POST", endpoint, payload, headers={
                "Content-Type": "application/json", "X-LabSkill-Request": "1", "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.gh.calls, 0)


if __name__ == "__main__":
    unittest.main()
