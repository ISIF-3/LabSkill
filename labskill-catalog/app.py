"""LabSkill loopback app. Run with: python3.11 -m app."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import http.client
import json
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from collector import collect
from collector import history as history_store
from collector.discovery import PROFILES
from collector.github_client import GitHub
from collector.summarize import Summarizer

APP_ID = "local-v1"
DEFAULT_PORT = 18765
WEEK = dt.timedelta(days=7)
KST = dt.timezone(dt.timedelta(hours=9))
EMPTY_CATALOG = {"generated_at": None, "date": None, "count": 0, "repos": []}
EMPTY_LIBRARY = {"schema_version": 1, "saved_ids": [], "collections": [], "notes": {}}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


def _local_command(command: str, args: list[str]) -> bool:
    executable = shutil.which(command)
    if not executable:
        return False
    try:
        result = subprocess.run([executable, *args], capture_output=True, text=True, timeout=5)
        return result.returncode == 0 and (bool(result.stdout.strip()) if command == "gh" else True)
    except (OSError, subprocess.SubprocessError):
        return False


def github_auth_available() -> bool:
    """Read the CLI's local credential store, without making a REST request."""
    return _local_command("gh", ["auth", "token", "--hostname", "github.com"])


def codex_available() -> bool:
    return _local_command("codex", ["login", "status"])


def _safe_text(value: str, token: str = "") -> str:
    for secret in (token, os.environ.get("GITHUB_TOKEN"), os.environ.get("GH_TOKEN"), os.environ.get("OPENAI_API_KEY")):
        if secret:
            value = value.replace(secret, "[redacted]")
    return re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "[redacted]", value)


class RepositoryConflict(ValueError):
    pass


def parse_repo_url(value) -> tuple[str, str | None]:
    """Accept repository coordinates only; never pass a user URL to the HTTP client."""
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError("GitHub 저장소 URL이 필요합니다")
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or parsed.query or parsed.fragment:
        raise ValueError("https://github.com/소유자/저장소 URL을 입력하세요")
    match = re.fullmatch(r"/([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/([A-Za-z0-9._-]{1,104})"
                         r"(?:/tree/([a-fA-F0-9]{40}))?/?", parsed.path)
    if not match:
        raise ValueError("저장소 URL 또는 40자리 SHA의 tree URL만 지원합니다")
    owner, repo, ref = match.groups()
    repo = repo[:-4] if repo.endswith(".git") else repo
    if not repo or repo in (".", "..") or len(repo) > 100:
        raise ValueError("올바른 GitHub 저장소 이름이 필요합니다")
    return f"{owner}/{repo}", ref.lower() if ref else None


def validate_library(value) -> dict:
    if not isinstance(value, dict) or set(value) != set(EMPTY_LIBRARY) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("보관함 문서 형식이 올바르지 않습니다")
    def valid_id(repo_id):
        return (isinstance(repo_id, str) and len(repo_id) <= 140 and history_store.NAME.fullmatch(repo_id) is not None
                and repo_id.split("/")[1] not in (".", ".."))
    def repo_ids(ids):
        if (not isinstance(ids, list) or len(ids) > 5000
                or any(not valid_id(repo_id) for repo_id in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError("올바른 GitHub 저장소 ID를 중복 없이 최대 5000개 저장할 수 있습니다")
    repo_ids(value["saved_ids"])
    saved_ids = set(value["saved_ids"])
    collections, notes = value["collections"], value["notes"]
    if not isinstance(collections, list) or len(collections) > 100 or not isinstance(notes, dict) or len(notes) > 5000:
        raise ValueError("컬렉션은 최대 100개까지 저장할 수 있습니다")
    seen = set()
    for item in collections:
        if (not isinstance(item, dict) or set(item) != {"id", "name", "repo_ids"}
                or not isinstance(item["id"], str) or re.fullmatch(r"[A-Za-z0-9_-]{1,80}", item["id"]) is None
                or item["id"] in seen or not isinstance(item["name"], str)
                or not item["name"].strip() or len(item["name"]) > 60):
            raise ValueError("컬렉션 ID와 이름(1~60자)을 확인하세요")
        seen.add(item["id"])
        repo_ids(item["repo_ids"])
        if any(repo_id not in saved_ids for repo_id in item["repo_ids"]):
            raise ValueError("컬렉션에는 보관함에 저장한 저장소만 넣을 수 있습니다")
    if any(not valid_id(repo_id) or not isinstance(note, str) or len(note) > 4000 for repo_id, note in notes.items()):
        raise ValueError("메모는 올바른 GitHub 저장소 ID마다 최대 4000자까지 저장할 수 있습니다")
    return value


class AppController:
    """Keep the last good catalog readable while a single collection runs."""

    def __init__(self, root: Path, *, collector=None, github_factory=None,
                 summarizer_factory=None, github_probe=None, codex_probe=None, now=None):
        self.root = Path(root).resolve()
        self._collector = collector or collect.run
        self._github_factory = github_factory or GitHub.from_gh
        self._summarizer_factory = summarizer_factory or Summarizer.from_env
        self._github_probe = github_probe or github_auth_available
        self._codex_probe = codex_probe or codex_available
        self._classification_backend = os.environ.get("LABSKILL_BACKEND", "python").strip().lower()
        if self._classification_backend not in ("python", "codex", "none"):
            raise ValueError("LABSKILL_BACKEND는 python, none, codex 중 하나여야 합니다")
        self._now = now or (lambda: dt.datetime.now(dt.timezone.utc))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._worker = None
        self._scheduler = None
        self._last_attempt = None
        self._manual_repo = None
        self._history_active = False
        self._history_pause = threading.Event()
        try:
            if json.loads((self.root / "state/history.json").read_text()).get("paused") is True:
                self._history_pause.set()
        except (OSError, ValueError, AttributeError):
            pass
        self._catalog = copy.deepcopy(EMPTY_CATALOG)
        history_store.ensure_seed(self.root)
        self._load_catalog()
        codex_ready = bool(self._codex_probe()) if self._classification_backend == "codex" else False
        self._status = {
            "running": False, "stage": "idle", "message": "저장된 카탈로그를 표시합니다",
            "current": 0, "total": 0, "repo": None, "started_at": None, "finished_at": None,
            "last_error": None, "report": None,
            "github_authenticated": bool(self._github_probe()),
            "codex_available": codex_ready,
            "classification_backend": self._classification_backend,
            "classification_available": self._classification_backend == "python" or codex_ready,
            "generated_at": self._catalog.get("generated_at"),
            "discovery_domain": None,
        }

    def _load_catalog(self):
        try:
            doc = json.loads((self.root / "catalog" / "catalog.json").read_text(encoding="utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("repos"), list):
                self._catalog = doc
        except (OSError, ValueError):
            pass

    def catalog(self) -> dict:
        with self._lock:
            if not self._status["running"]:
                self._load_catalog()
            return copy.deepcopy(self._catalog)

    def taxonomy(self) -> dict:
        return json.loads((self.root / "catalog" / "taxonomy.json").read_text(encoding="utf-8"))

    def library(self) -> dict:
        with self._lock:
            document = collect._read_json(self.root / "state/library.json", copy.deepcopy(EMPTY_LIBRARY))
            return validate_library(document)

    def save_library(self, document: dict) -> dict:
        with self._lock:
            document = validate_library(document)
            collect._write_json(self.root / "state/library.json", document)
            return copy.deepcopy(document)

    def add_repo(self, url) -> str:
        name, ref = parse_repo_url(url)
        with self._lock:
            if self._status["running"] or self._stop.is_set():
                raise RepositoryConflict("다른 수집 작업이 진행 중입니다")
            self._load_catalog()
            if name.casefold() in {row["id"].casefold() for row in self._catalog["repos"]}:
                raise RepositoryConflict("이미 카탈로그에 있는 저장소입니다")
            self._manual_repo = name
            self._status.update(running=True, stage="manual", message=f"{name} 저장소를 추가합니다", repo=name,
                                current=0, total=1, started_at=self._now().isoformat(), finished_at=None,
                                last_error=None, report=None, discovery_domain=None)
            self._worker = threading.Thread(target=self._run, kwargs={"manual_repo": name, "manual_ref": ref},
                                            name="labskill-manual", daemon=True)
            self._worker.start()
            return name

    def discovery(self) -> dict:
        return {"profiles": copy.deepcopy(PROFILES)}

    def history(self) -> dict:
        with self._lock:
            return {**history_store.summary(self.catalog()), "active": self._history_active,
                    "pause_requested": self._history_pause.is_set()}

    def refresh_history(self, *, include_failed=True) -> bool:
        with self._lock:
            if self._status["running"] or self._stop.is_set() or (self._history_pause.is_set() and not include_failed):
                return False
            self._load_catalog()
            if not history_store.pending_names(self._catalog, include_failed=include_failed):
                return False
            if include_failed:
                collect._write_json(self.root / "state/history.json", {"paused": False})
                self._history_pause.clear()
            self._history_active = True
            self._status.update(running=True, stage="history", message="과거 트렌딩 저장소를 정리합니다",
                                current=0, total=0, repo=None, started_at=self._now().isoformat(),
                                finished_at=None, last_error=None, report=None, discovery_domain=None)
            self._worker = threading.Thread(target=self._run_history, args=(include_failed,),
                                            name="labskill-history", daemon=True)
            self._worker.start()
            return True

    def pause_history(self):
        with self._lock:
            collect._write_json(self.root / "state/history.json", {"paused": True})
            self._history_pause.set()

    def _classifier(self):
        codex_ready = bool(self._codex_probe()) if self._classification_backend == "codex" else False
        summarizer = self._summarizer_factory() if self._classification_backend == "python" or codex_ready else Summarizer()
        available = bool(summarizer.enabled)
        with self._lock:
            self._status.update(classification_backend=self._classification_backend,
                                classification_available=available, codex_available=codex_ready)
        return summarizer, available

    def _run_history(self, include_failed):
        path = self.root / "catalog/catalog.json"
        checkpoint = None
        token = ""
        visited = set()
        try:
            with self._lock:
                self._status["github_authenticated"] = False
            gh = self._github_factory()
            token = getattr(gh, "token", "") or ""
            summarizer, available = self._classifier()
            with self._lock:
                self._status.update(github_authenticated=True)
            while not self._stop.is_set() and not self._history_pause.is_set():
                with self._lock:
                    candidates = {"repos": [row for row in self._catalog["repos"] if row["id"] not in visited]}
                    names = history_store.pending_names(candidates, include_failed=include_failed)
                if not names:
                    break
                visited.update(names)
                checkpoint = path.read_bytes()
                report = self._collector(self.root, gh, summarizer, self._now().astimezone(KST).date(),
                                         dry_run=False, search=False, dump_dir=None, workers=2,
                                         progress=self._progress, history_names=names)
                checkpoint = None
                with self._lock:
                    self._load_catalog()
                    self._status["report"] = json.loads(_safe_text(json.dumps(report, ensure_ascii=False), token))
                if not available:
                    break
            with self._lock:
                progress = history_store.summary(self._catalog)
                remaining = progress["remaining"]
                message = "현재 묶음까지 저장하고 정리를 멈췄습니다" if self._history_pause.is_set() else (
                    f"선별 결과 저장 완료 · 선별 확인 {progress['screened']}개 · 남은 항목 {remaining}개")
                if not available:
                    message = ("GitHub 자료 저장 완료 · Codex 로그인 후 분류를 이어갈 수 있습니다"
                               if self._classification_backend == "codex" else "GitHub 자료 저장 완료 · 분류를 사용하지 않습니다")
                self._status.update(stage="complete", message=message, repo=None)
        except Exception as exc:
            error = _safe_text(str(exc), token)[:2000] or type(exc).__name__
            try:
                if checkpoint is not None and (not path.exists() or path.read_bytes() != checkpoint):
                    temporary = path.with_suffix(".history-restore.tmp")
                    temporary.write_bytes(checkpoint)
                    temporary.replace(path)
            except OSError:
                error += " · 마지막 저장본 복원에 실패했습니다"
            with self._lock:
                self._load_catalog()
                self._status.update(stage="error", message="정리 중단 · 완료된 항목은 저장했습니다", repo=None, last_error=error)
        finally:
            with self._lock:
                self._history_active = False
                self._status.update(running=False, finished_at=self._now().isoformat(),
                                    generated_at=self._catalog.get("generated_at"))

    def status(self) -> dict:
        with self._lock:
            status = copy.deepcopy(self._status)
            status["generated_at"] = self.catalog().get("generated_at")
            return status

    def refresh(self, discovery_domain: str | None = None) -> bool:
        if discovery_domain is not None and (not isinstance(discovery_domain, str) or discovery_domain not in PROFILES):
            raise ValueError("알 수 없는 발견 분야입니다")
        with self._lock:
            if self._status["running"] or self._stop.is_set():
                return False
            self._load_catalog()
            started = self._now()
            if discovery_domain is None:
                self._last_attempt = started
            self._status.update(running=True, stage="connecting", message="GitHub 연결을 확인합니다",
                                current=0, total=0, repo=None, started_at=started.isoformat(),
                                finished_at=None, last_error=None, report=None, discovery_domain=discovery_domain)
            self._worker = threading.Thread(target=self._run, args=(discovery_domain,), name="labskill-collector", daemon=True)
            self._worker.start()
            return True

    def _progress(self, event: dict):
        allowed = {}
        for key in ("stage", "message", "repo"):
            if key in event and (event[key] is None or isinstance(event[key], str)):
                allowed[key] = _safe_text(event[key][:1000]) if event[key] is not None else None
        for key in ("current", "total"):
            if isinstance(event.get(key), int):
                allowed[key] = max(0, event[key])
        with self._lock:
            if self._manual_repo is not None:
                allowed.update(stage="manual", repo=self._manual_repo)
            self._status.update(allowed)

    def _run(self, discovery_domain: str | None = None, *, manual_repo: str | None = None, manual_ref: str | None = None):
        path = self.root / "catalog" / "catalog.json"
        backup = None
        token = ""
        collection_started = False
        try:
            backup = path.read_bytes() if path.exists() else None
            with self._lock:
                self._status["github_authenticated"] = False
            gh = self._github_factory()
            token = getattr(gh, "token", "") or ""
            if manual_repo is not None:
                summarizer, available = Summarizer(backend="python"), True
                with self._lock:
                    self._status.update(classification_backend="python", classification_available=True, codex_available=False)
            else:
                summarizer, available = self._classifier()
            with self._lock:
                self._status.update(github_authenticated=True)
            collection_started = True
            report = self._collector(self.root, gh, summarizer, self._now().astimezone(KST).date(),
                                     dry_run=False, search=False, dump_dir=None, workers=2,
                                     progress=self._progress, discovery_domain=discovery_domain,
                                     **({"manual_repo": manual_repo, "manual_ref": manual_ref} if manual_repo is not None else {}))
            # The collector has validated and atomically published its result.
            with self._lock:
                self._load_catalog()
                report = json.loads(_safe_text(json.dumps(report, ensure_ascii=False), token))
                message = "수집과 분류를 완료했습니다" if available else (
                    "GitHub 수집 완료 · Codex 로그인 후 분류할 수 있습니다"
                    if self._classification_backend == "codex" else "GitHub 수집 완료 · 분류를 사용하지 않습니다")
                screening = report.get("screening")
                if available and isinstance(screening, dict):
                    message = (f"수집과 Python 선별을 완료했습니다 · 상세 확인 {screening.get('deeply_checked', 0)}개"
                               f" · 메타데이터 확인 {screening.get('metadata_only', 0)}개")
                self._status.update(stage="complete", message=message, repo=None, report=report)
        except Exception as exc:
            error = _safe_text(str(exc), token)[:2000] or type(exc).__name__
            try:
                if not collection_started:
                    pass
                elif backup is None:
                    path.unlink(missing_ok=True)
                elif not path.exists() or path.read_bytes() != backup:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(".app-restore.tmp")
                    temporary.write_bytes(backup)
                    temporary.replace(path)
            except OSError:
                error += " · 저장 파일 복원에 실패했습니다"
            with self._lock:
                self._status.update(stage="error", message="수집 실패 · 저장된 카탈로그를 표시합니다",
                                    repo=None, last_error=error)
        finally:
            with self._lock:
                self._manual_repo = None
                self._status.update(running=False, finished_at=self._now().isoformat(),
                                    generated_at=self._catalog.get("generated_at"))

    def check_due(self) -> bool:
        with self._lock:
            if self._status["running"] or self._stop.is_set():
                return False
            if self._last_attempt is None or self._now() - self._last_attempt >= WEEK:
                return self.refresh()
            if not self._history_pause.is_set() and self._status["classification_available"] and history_store.pending_names(self.catalog()):
                return self.refresh_history(include_failed=False)
            return False

    def start_scheduler(self):
        def schedule():
            while not self._stop.wait(60):
                self.check_due()
        if self._scheduler is None:
            self._scheduler = threading.Thread(target=schedule, name="labskill-weekly", daemon=True)
            self._scheduler.start()

    def wait(self, timeout=None) -> bool:
        worker = self._worker
        if worker is not None:
            worker.join(timeout)
        return worker is None or not worker.is_alive()

    def close(self):
        self._stop.set()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True


class AppHandler(BaseHTTPRequestHandler):
    server_version = "LabSkill"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        pass

    @property
    def controller(self):
        return self.server.controller

    def _trusted_request(self) -> bool:
        hosts = self.headers.get_all("Host", [])
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if len(hosts) != 1 or hosts[0].lower() not in allowed:
            self._json(403, {"error": "Local requests only"})
            return False
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1 or (origins and origins[0].lower() not in {"http://" + host for host in allowed}):
            self._json(403, {"error": "Origin rejected"})
            return False
        return True

    def _respond(self, code: int, content: bytes, content_type: str, *, api=False):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store" if api else "no-cache")
        self.send_header("X-LabSkill-App", APP_ID)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)

    def _json(self, code: int, value):
        self._respond(code, json.dumps(value, ensure_ascii=False).encode("utf-8"),
                      "application/json; charset=utf-8", api=True)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._trusted_request():
            return
        path = urllib.parse.urlsplit(self.path).path
        api = {"/api/catalog": self.controller.catalog, "/api/taxonomy": self.controller.taxonomy,
               "/api/status": self.controller.status, "/api/discovery": self.controller.discovery,
               "/api/history": self.controller.history, "/api/library": self.controller.library}
        if path in api:
            try:
                self._json(200, api[path]())
            except (OSError, ValueError, collect.CollectError):
                self._json(503, {"error": "저장된 데이터를 읽을 수 없습니다"})
            return
        self._static(path)

    def _static(self, url_path: str):
        try:
            path = urllib.parse.unquote(url_path, errors="strict")
            if "\\" in path or "\x00" in path or ".." in path.split("/"):
                raise ValueError
            relative = path.lstrip("/") or "index.html"
            public = {"index.html", "styles.css", "app.js", "catalog-data.mjs", "favicon.ico"}
            asset_types = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2"}
            if relative not in public and not (relative.startswith("assets/") and Path(relative).suffix.lower() in asset_types):
                raise ValueError
            web = (self.controller.root / "web").resolve()
            file = (web / relative).resolve()
            if not web.is_relative_to(self.controller.root) or not file.is_relative_to(web) or not file.is_file():
                raise ValueError
            content = file.read_bytes()
            content_type = {".mjs": "text/javascript", ".js": "text/javascript"}.get(file.suffix)
            content_type = content_type or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            self._respond(200, content, content_type)
        except (OSError, ValueError, UnicodeError):
            self._json(404, {"error": "Not found"})

    def do_POST(self):
        if not self._trusted_request():
            return
        action = urllib.parse.urlsplit(self.path).path
        if action not in ("/api/refresh", "/api/history/process", "/api/history/pause", "/api/repos", "/api/library"):
            self._json(404, {"error": "Not found"})
            return
        if self.headers.get("X-LabSkill-Request") != "1":
            self._json(403, {"error": "Request header required"})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "application/json required"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or self.headers.get("Transfer-Encoding"):
                raise ValueError
            if length > (1024 * 1024 if action == "/api/library" else 4096):
                self._json(413, {"error": "Request too large"})
                return
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body)
            allowed = ({"discovery_domain"} if action == "/api/refresh" else {"url"} if action == "/api/repos"
                       else set(EMPTY_LIBRARY) if action == "/api/library" else set())
            if not isinstance(payload, dict) or set(payload) - allowed:
                raise ValueError
            discovery_domain = payload.get("discovery_domain")
            if discovery_domain is not None and (not isinstance(discovery_domain, str) or discovery_domain not in PROFILES):
                raise ValueError
        except (ValueError, UnicodeError):
            self._json(400, {"error": "Invalid JSON request"})
            return
        if action in ("/api/repos", "/api/library"):
            try:
                if action == "/api/repos":
                    name = self.controller.add_repo(payload.get("url"))
                    self._json(202, {"accepted": True, "id": name})
                else:
                    self._json(200, self.controller.save_library(payload))
            except RepositoryConflict as exc:
                self._json(409, {"error": str(exc)})
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except OSError:
                self._json(503, {"error": "저장된 데이터를 변경할 수 없습니다"})
        elif action == "/api/history/process":
            self.controller.refresh_history()
            self._json(202, self.controller.history())
        elif action == "/api/history/pause":
            self.controller.pause_history()
            self._json(202, self.controller.history())
        else:
            self.controller.refresh(discovery_domain=discovery_domain)
            self._json(202, self.controller.status())

    def do_OPTIONS(self):
        if self._trusted_request():
            self._json(405, {"error": "Method not allowed"})


def create_server(controller: AppController, port: int = DEFAULT_PORT) -> LocalServer:
    server = LocalServer(("127.0.0.1", port), AppHandler)
    server.controller = controller
    return server


def is_existing_app(port: int) -> bool:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", "/api/status")
        response = connection.getresponse()
        body = response.read(65536)
        status = json.loads(body)
        return (response.status == 200 and response.getheader("X-LabSkill-App") == APP_ID
                and isinstance(status, dict) and isinstance(status.get("running"), bool))
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="LabSkill 로컬 카탈로그")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true", help="브라우저를 자동으로 열지 않음")
    parser.add_argument("--no-collect", action="store_true", help="시작 시 수집과 주간 자동 수집을 실행하지 않음")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    url = f"http://127.0.0.1:{args.port}/"
    if is_existing_app(args.port):
        if not args.no_open:
            webbrowser.open(url)
        print(f"LabSkill이 이미 실행 중입니다: {url}")
        return 0
    controller = AppController(Path(__file__).resolve().parent)
    try:
        server = create_server(controller, args.port)
    except OSError as exc:
        controller.close()
        if is_existing_app(args.port):
            if not args.no_open:
                webbrowser.open(url)
            return 0
        print(f"LabSkill을 시작할 수 없습니다: 포트 {args.port}을 확인하세요 ({exc})")
        return 98
    if not args.no_collect:
        controller.refresh()
        controller.start_scheduler()
    if not args.no_open:
        webbrowser.open(url)
    print(f"LabSkill: {url}\n종료: Ctrl+C · 앱이 열려 있는 동안 매주 수집합니다")
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        controller.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
