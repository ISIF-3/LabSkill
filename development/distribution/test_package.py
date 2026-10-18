"""Packaging must never pick up live user data or unexpected files."""
import importlib.util
import datetime as dt
import json
from pathlib import Path
import tempfile
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]


class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = ROOT / "development/distribution/package.py"
        if not script.is_file():
            raise AssertionError("The explicit-whitelist packaging script is missing")
        spec = importlib.util.spec_from_file_location("package", script)
        cls.package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.package)

    def fixture(self, root):
        manifest = json.loads((ROOT / "development/distribution/manifest.json").read_text())
        for name in manifest["common"] + manifest["windows"] + ["development/distribution/manifest.json"]:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        for source in manifest["seed"].values():
            target = root / source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / source).read_bytes())

    def test_live_private_files_and_unlisted_files_never_enter_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            private = ["labskill-catalog/state/library.json", "labskill-catalog/state/launcher.log",
                       "labskill-catalog/catalog/catalog.json", "labskill-catalog/cache/repos.json",
                       "labskill-catalog/imports/manual/private.json", ".env", "credentials.json",
                       "labskill-catalog/collector/private_notes.py", "LabSkill.app/private.txt"]
            for name in private:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("PRIVATE_SENTINEL")
            output = root / "download.zip"
            self.package.write_archive(self.package.plan_files(root, "windows"), output, "LabSkill-windows")
            with zipfile.ZipFile(output) as archive:
                self.assertIn("LabSkill-windows/LabSkill.bat", archive.namelist())
                self.assertIn("LabSkill-windows/labskill-catalog/catalog/catalog.json", archive.namelist())
                for name in archive.namelist():
                    self.assertNotIn(b"PRIVATE_SENTINEL", archive.read(name))
                self.assertFalse(any("/state/" in name or "/imports/manual/" in name for name in archive.namelist()))

    def test_initialize_preserves_existing_catalog_and_only_fills_missing_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            catalog = root / "labskill-catalog/catalog/catalog.json"
            catalog.parent.mkdir(parents=True, exist_ok=True)
            catalog.write_text('{"repos":[],"personal":"KEEP"}')
            self.package.initialize(root)
            self.assertIn("KEEP", catalog.read_text())
            self.assertTrue((root / "labskill-catalog/catalog/taxonomy.json").is_file())

    def test_whitelisted_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            readme = root / "README.md"
            readme.unlink()
            readme.symlink_to(ROOT / "README.md")
            with self.assertRaisesRegex(ValueError, "symlink"):
                self.package.plan_files(root, "windows")

    def test_initialize_rejects_a_symlinked_data_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            outside = Path(temporary) / "outside"
            root.mkdir()
            outside.mkdir()
            self.fixture(root)
            (root / "labskill-catalog/catalog").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                self.package.initialize(root)
            self.assertEqual(list(outside.iterdir()), [])

    def test_initialize_missing_seed_does_not_leave_an_empty_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / "development/distribution/public-seed/catalog.json").unlink()
            with self.assertRaises(ValueError):
                self.package.initialize(root)
            self.assertFalse((root / "labskill-catalog/catalog/catalog.json").exists())

    def test_source_archive_contains_seed_sources_needed_to_rebuild_downloads(self):
        files = self.package.plan_files(ROOT, "source")
        config = json.loads((ROOT / "development/distribution/manifest.json").read_text())
        for source in config["seed"].values():
            self.assertIn(source, files)

    def test_public_seed_keeps_metadata_but_removes_raw_documents_and_private_fields(self):
        seed = self.package.sanitize_catalog({"repos": [{
            "id": "public/project", "url": "https://github.com/public/project", "summary_ko": "공개 요약",
            "raw_response": "RAW_README", "evidence": [{"quote": "RAW_README"}],
            "private_notes": "PRIVATE_SENTINEL", "sources": ["trending:weekly", "manual:private"],
            "skills": [{"name": "example", "path": "skills/example", "description": "메타데이터",
                        "body": "RAW_SKILL"}],
            "function_catalog": {"version": 1, "primary": "code", "functions": ["code"],
                                 "private_notes": "PRIVATE_SENTINEL"},
            "agent_catalog": {"version": 1, "status": "selected", "evidence": [{"quote": "RAW_README"}]}
        }]})
        text = json.dumps(seed)
        for forbidden in ["RAW_README", "RAW_SKILL", "PRIVATE_SENTINEL", "manual:private"]:
            self.assertNotIn(forbidden, text)
        self.assertEqual(seed["repos"][0]["skills"][0]["description"], "메타데이터")
        self.assertNotIn("evidence_valid", seed["repos"][0])
        self.assertEqual(seed["repos"][0].get("review"), {})

    def test_download_seed_satisfies_collector_and_accepts_manual_repository(self):
        sys.path.insert(0, str(ROOT / "labskill-catalog"))
        from collector import collect
        from collector.summarize import Summarizer

        class PublicGitHub:
            calls = 0

            def repo(self, name):
                return {"html_url": "https://github.com/" + name, "description": "A terminal application.",
                        "topics": [], "stargazers_count": 2, "forks_count": 0, "default_branch": "main",
                        "pushed_at": "2026-10-18T00:00:00Z"}

            def head_commit(self, name, branch):
                return "a" * 40

            def tree(self, name, ref):
                return [{"path": "README.md", "type": "blob"}]

            def readme(self, name, ref):
                return "# Terminal\nA terminal application.\n", "README.md"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            self.package.initialize(root)
            runtime = root / "labskill-catalog"
            catalog_file = runtime / "catalog/catalog.json"
            before = json.loads(catalog_file.read_text())
            self.assertEqual(before["count"], 791)
            for repo in before["repos"]:
                for key, kind in collect.STRUCTURAL.items():
                    self.assertIsInstance(repo.get(key), kind, (repo["id"], key))
            report = collect.run(runtime, PublicGitHub(), Summarizer(backend="python"),
                                 dt.date(2026, 10, 18), manual_repo="distribution-test/new-public")
            after = json.loads(catalog_file.read_text())
            self.assertEqual(after["count"], 792)
            self.assertEqual(report["source"], "manual")
            original = {repo["id"]: repo for repo in before["repos"]}
            preserved = {repo["id"]: repo for repo in after["repos"] if repo["id"] in original}
            self.assertEqual(preserved, original)

    def test_gitignore_is_default_deny_with_only_exact_public_file_exceptions(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        rules = [line for line in lines if line and not line.startswith("#")]
        self.assertEqual(rules[:2], ["*", "!*/"])
        approved = {rule[2:] for rule in rules[2:] if rule.startswith("!/")}
        manifest = json.loads((ROOT / "development/distribution/manifest.json").read_text())
        expected = set(manifest["common"] + manifest["source"] + manifest["windows"])
        expected.update(manifest["seed"].values())
        self.assertEqual(approved, expected)
        self.assertNotIn("labskill-catalog/state/library.json", approved)
        self.assertNotIn("labskill-catalog/catalog/catalog.json", approved)
        self.assertFalse(any("*" in rule for rule in rules[2:]))


if __name__ == "__main__":
    unittest.main()
