"""Archive import tests use fake API responses, raw bytes, and temporary files only."""
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "labskill-catalog"))
from collector import history

REF = "a" * 40
TREE_SHAS = {name: str(index) * 40 for index, name in enumerate(["archive", "repository", "2025", "2026"], 1)}


def raw(day, names, **overrides):
    return json.dumps({"date": day, "language": None, "list": names, **overrides}).encode()


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def node(path, sha, kind="tree"):
    return {"path": path, "sha": sha, "type": kind, "mode": "040000" if kind == "tree" else "100644"}


class ArchiveAPI:
    def __init__(self, documents):
        self.calls = []
        self.documents = documents
        self.year_entries = {"2025": [], "2026": []}
        for day, data in documents.items():
            self.year_entries[day[:4]].append(node(day + "/(null).json", blob(data), "blob"))
        self.responses = {
            REF: [node("archive", TREE_SHAS["archive"])],
            TREE_SHAS["archive"]: [node("repository", TREE_SHAS["repository"])],
            TREE_SHAS["repository"]: [node(year, TREE_SHAS[year]) for year in self.year_entries],
            **{TREE_SHAS[year]: entries for year, entries in self.year_entries.items()},
        }
        self.truncated = set()

    def get_json(self, path, **params):
        self.calls.append((path, params))
        self.assert_source(path)
        sha = path.rsplit("/", 1)[1]
        return {"sha": sha, "truncated": sha in self.truncated, "tree": copy.deepcopy(self.responses[sha])}

    @staticmethod
    def assert_source(path):
        assert path.startswith("/repos/antonkomarev/github-trending-archive/git/trees/")


class ImportHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = PROJECT / "development/import_history.py"
        if not source.is_file():
            raise AssertionError("The archive importer CLI has not been implemented")
        spec = importlib.util.spec_from_file_location("import_history", source)
        cls.importer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.importer)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def generate(self, documents, *, start="2025-12-31", end="2026-01-02", api=None, fetch=None):
        api = api or ArchiveAPI(documents)
        calls = []

        def get(url):
            calls.append(url)
            day = url.split("/")[-2]
            return documents[day]

        result = self.importer.run(self.root, start, end, REF, github=api, fetch_raw=fetch or get)
        return result, calls, api

    def test_cross_year_manifest_preserves_ranks_casefold_identity_and_actual_missing_days(self):
        docs = {"2025-12-31": raw("2025-12-31", ["Owner/Tool", "other/repo", "owner/tool"]),
                "2026-01-01": raw("2026-01-01", ["third/tool", "owner/tool"])}
        api = ArchiveAPI(docs)
        api.year_entries["2026"].append(node("2026-01-01/python.json", "9" * 40, "blob"))
        result, calls, api = self.generate(docs, api=api)
        history._validate(result)
        self.assertEqual(result["range"], {"start": "2025-12-31", "end": "2026-01-02", "inclusive": True})
        self.assertEqual(result["coverage"], {"expected_days": 3, "available_days": 2,
                                             "nonempty_days": 2, "missing_dates": ["2026-01-02"]})
        by_name = {repo["id"]: repo for repo in result["repositories"]}
        self.assertEqual(len(by_name), 3)
        self.assertEqual(by_name["Owner/Tool"]["appearance_days"], 2)
        self.assertEqual([row["rank"] for row in by_name["Owner/Tool"]["history"]], [1, 2])
        self.assertEqual(result["snapshots"][0]["repositories"], ["Owner/Tool", "other/repo"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(url.startswith("https://raw.githubusercontent.com/antonkomarev/github-trending-archive/" + REF + "/") for url in calls))
        self.assertTrue(all("%28null%29.json" in url for url in calls))
        self.assertEqual(len(api.calls), 5)
        self.assertEqual(sum(params == {"recursive": "1"} for _, params in api.calls), 2)
        self.assertIsNotNone(dt.datetime.fromisoformat(result["generated_at"]).utcoffset())
        self.assertEqual(json.loads((self.root / "imports/trending-history-expanded.json").read_text()), result)

    def test_valid_manifest_same_blob_reuses_snapshot_and_invalid_manifest_does_not(self):
        docs = {"2025-12-31": raw("2025-12-31", ["owner/tool"])}
        first, _, _ = self.generate(docs, end="2025-12-31")
        old = self.root / "imports/trending-history-previous.json"
        earlier = copy.deepcopy(first)
        earlier["source_commit"] = "b" * 40
        for snapshot in earlier["snapshots"]:
            snapshot["source_url"] = snapshot["source_url"].replace(REF, "b" * 40)
        old.write_text(json.dumps(earlier))
        (self.root / "imports/trending-history-expanded.json").unlink()
        for path in (self.root / "cache/archive").glob("*"):
            path.unlink()
        again, calls, _ = self.generate(docs, end="2025-12-31")
        self.assertEqual(calls, [])
        self.assertEqual(again["snapshots"], first["snapshots"])
        old.write_text('{"schema_version":1,"snapshots":[]}')
        (self.root / "imports/trending-history-expanded.json").unlink()
        _, calls, _ = self.generate(docs, end="2025-12-31")
        self.assertEqual(len(calls), 1)

    def test_corrupt_cached_blob_is_refetched_and_successful_cache_needs_no_network(self):
        docs = {"2025-12-31": raw("2025-12-31", ["owner/tool"])}
        cached = self.root / "cache/archive" / (blob(docs["2025-12-31"]) + ".json")
        cached.parent.mkdir(parents=True)
        cached.write_bytes(b"CORRUPT")
        _, calls, _ = self.generate(docs, end="2025-12-31")
        self.assertEqual(len(calls), 1)
        self.assertEqual(cached.read_bytes(), docs["2025-12-31"])
        (self.root / "imports/trending-history-expanded.json").unlink()
        _, calls, _ = self.generate(docs, end="2025-12-31")
        self.assertEqual(calls, [])

    def test_failed_blob_keeps_previous_manifest_and_retry_reuses_successful_cache(self):
        docs = {"2025-12-31": raw("2025-12-31", ["one/tool"]),
                "2026-01-01": raw("2026-01-01", ["two/tool"])}
        output = self.root / "imports/trending-history-expanded.json"
        output.parent.mkdir()
        output.write_bytes(b"PREVIOUS_MANIFEST")

        def corrupt(url):
            return b"WRONG_SHA" if "/2026-01-01/" in url else docs["2025-12-31"]

        with self.assertRaisesRegex(ValueError, "blob"):
            self.generate(docs, fetch=corrupt)
        self.assertEqual(output.read_bytes(), b"PREVIOUS_MANIFEST")
        self.assertTrue((self.root / "cache/archive" / (blob(docs["2025-12-31"]) + ".json")).is_file())
        _, calls, _ = self.generate(docs)
        self.assertEqual(len(calls), 1)
        self.assertIn("/2026-01-01/", calls[0])

    def test_truncated_tree_and_unsafe_global_paths_fail_without_publishing(self):
        docs = {"2025-12-31": raw("2025-12-31", ["one/tool"])}
        api = ArchiveAPI(docs)
        api.truncated.add(TREE_SHAS["2025"])
        with self.assertRaisesRegex(ValueError, "truncated"):
            self.generate(docs, api=api)
        for bad_path in ["../2025-12-31/(null).json", "2025-02-30/(null).json", "2026-01-01/(null).json"]:
            with self.subTest(path=bad_path):
                api = ArchiveAPI(docs)
                api.year_entries["2025"].append(node(bad_path, "9" * 40, "blob"))
                with self.assertRaises(ValueError):
                    self.generate(docs, api=api)
        self.assertFalse((self.root / "imports/trending-history-expanded.json").exists())

    def test_invalid_source_json_date_language_or_repository_name_is_rejected(self):
        day = "2025-12-31"
        bad = [b"not json", b"[]", raw(day, ["valid/repo"], date="2025-12-30"),
               raw(day, ["valid/repo"], language="Python"), raw(day, ["owner/.."]),
               raw(day, ["https://github.com/owner/repo"]), raw(day, [123]),
               json.dumps({"date": day, "list": ["owner/repo"]}).encode()]
        for body in bad:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    self.generate({day: body}, end=day)
        self.assertFalse((self.root / "imports/trending-history-expanded.json").exists())

    def test_fetches_at_most_six_raw_files_at_once(self):
        days = [(dt.date(2026, 1, 1) + dt.timedelta(days=index)).isoformat() for index in range(10)]
        docs = {day: raw(day, ["owner/tool"]) for day in days}
        lock = threading.Lock()
        active = peak = 0

        def fetch(url):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return docs[url.split("/")[-2]]

        self.generate(docs, start=days[0], end=days[-1], fetch=fetch)
        self.assertGreater(peak, 1)
        self.assertLessEqual(peak, 6)

    def test_empty_snapshot_is_available_not_missing(self):
        docs = {"2025-12-31": raw("2025-12-31", []), "2026-01-01": raw("2026-01-01", ["owner/tool"])}
        result, _, _ = self.generate(docs)
        self.assertEqual(result["coverage"]["available_days"], 2)
        self.assertEqual(result["coverage"]["nonempty_days"], 1)
        self.assertEqual(result["coverage"]["missing_dates"], ["2026-01-02"])

    def test_invalid_input_fails_before_any_api_or_raw_request(self):
        api = ArchiveAPI({})
        for start, end, ref in [("2026-01-02", "2026-01-01", REF),
                                ("2026-02-30", "2026-03-01", REF),
                                ("2026-01-01", "2026-01-02", "main")]:
            with self.subTest(start=start, end=end, ref=ref):
                with self.assertRaises(ValueError):
                    self.importer.run(self.root, start, end, ref, github=api, fetch_raw=lambda _: self.fail("No raw fetch"))
        self.assertEqual(api.calls, [])

    def test_raw_fetch_uses_no_authorization_retries_and_has_timeout(self):
        response = io.BytesIO(b"{}")
        opener = mock.Mock()
        opener.open.side_effect = [urllib.error.URLError("temporary"), response]
        with mock.patch.object(self.importer.urllib.request, "build_opener", return_value=opener), mock.patch.object(self.importer.time, "sleep") as sleep:
            result = self.importer.fetch_raw("https://raw.githubusercontent.com/antonkomarev/github-trending-archive/" + REF + "/archive/repository/2025/2025-12-31/%28null%29.json")
        self.assertEqual(result, b"{}")
        self.assertEqual(opener.open.call_count, 2)
        for call in opener.open.call_args_list:
            request = call.args[0]
            self.assertIsNone(request.get_header("Authorization"))
            self.assertGreater(call.kwargs["timeout"], 0)
            self.assertLessEqual(call.kwargs["timeout"], 20)
        sleep.assert_called_once()

    def test_raw_fetch_rejects_unpinned_urls_redirects_and_permanent_failures(self):
        for url in ["https://evil.test/a.json", "https://raw.githubusercontent.com/antonkomarev/github-trending-archive/main/archive/repository/2025/2025-12-31/%28null%29.json"]:
            with self.subTest(url=url), mock.patch.object(self.importer.urllib.request, "build_opener") as build:
                with self.assertRaises(ValueError):
                    self.importer.fetch_raw(url)
                build.assert_not_called()
        self.assertIsNone(self.importer._NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil.test/"))
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://raw.githubusercontent.com/", 404, "missing", {}, None)
        url = "https://raw.githubusercontent.com/antonkomarev/github-trending-archive/" + REF + "/archive/repository/2025/2025-12-31/%28null%29.json"
        with mock.patch.object(self.importer.urllib.request, "build_opener", return_value=opener), mock.patch.object(self.importer.time, "sleep") as sleep:
            with self.assertRaises(urllib.error.HTTPError):
                self.importer.fetch_raw(url)
        opener.open.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
