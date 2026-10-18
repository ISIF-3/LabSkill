"""GitHub REST metadata, file paths, README and SKILL.md; fetched code is never run."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
UA = "labskill-collector"


def _api_host(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname == "api.github.com"
            and parsed.port in (None, 443) and parsed.username is None and parsed.password is None)


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and not _api_host(newurl):
            redirected.remove_header("Authorization")
        return redirected


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class GitHub:
    def __init__(self, token: str | None = None, min_interval: float = 0.2):
        self.token = token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        self.min_interval = min_interval
        self._last = 0.0
        self.calls = 0
        self._opener = urllib.request.build_opener(SafeRedirect())

    @classmethod
    def from_gh(cls):
        """Use an environment credential or the existing gh login."""
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            try:
                proc = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"],
                                      capture_output=True, text=True, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                raise GitHubError("GitHub 인증이 필요합니다. gh auth login을 실행하세요.") from None
            token = proc.stdout.strip() if proc.returncode == 0 else ""
        if not token:
            raise GitHubError("GitHub 인증이 필요합니다. gh auth login을 실행하세요.")
        return cls(token=token)

    def _request(self, url: str, accept: str = "application/vnd.github+json") -> tuple[bytes, dict]:
        headers = {"User-Agent": UA, "Accept": accept}
        if self.token and _api_host(url):
            headers["Authorization"] = f"Bearer {self.token}"
        for attempt in range(3):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self.calls += 1
            try:
                with self._opener.open(urllib.request.Request(url, headers=headers), timeout=20) as resp:
                    return resp.read(), dict(resp.headers)
            except urllib.error.HTTPError as exc:
                retry = exc.code in (429, 500, 502, 503, 504)
                delay = attempt + 1
                if exc.code in (403, 429):
                    try:
                        advertised = float(exc.headers.get("Retry-After", 0))
                        if exc.headers.get("X-RateLimit-Remaining") == "0":
                            advertised = max(advertised, float(exc.headers.get("X-RateLimit-Reset", 0)) - time.time())
                    except (TypeError, ValueError):
                        advertised = 0
                    retry = advertised <= 5 and (exc.code == 429 or advertised > 0)
                    delay = max(delay, advertised)
                if retry and attempt < 2:
                    time.sleep(delay)
                    continue
                raise GitHubError(f"GitHub HTTP {exc.code}: {url}", exc.code) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                raise GitHubError(f"GitHub network error: {url}") from None
            finally:
                self._last = time.monotonic()
        raise GitHubError(f"GitHub request failed: {url}")

    def get_json(self, path: str, **params) -> dict | list:
        url = path if path.startswith("http") else f"{API}{path}"
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        body, _ = self._request(url)
        try:
            return json.loads(body)
        except (ValueError, UnicodeError):
            raise GitHubError(f"Invalid GitHub JSON: {url}") from None

    def trending_html(self, since: str = "weekly") -> str:
        body, _ = self._request(f"https://github.com/trending?since={since}", accept="text/html")
        return body.decode("utf-8", "replace")

    def repo(self, full_name: str) -> dict:
        return self.get_json(f"/repos/{full_name}")

    def search_repos(self, query: str, limit: int = 10) -> list[dict]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10:
            raise ValueError("검색 결과는 1~10개만 요청할 수 있습니다")
        data = self.get_json("/search/repositories", q=query, sort="stars", order="desc", per_page=limit)
        if (not isinstance(data, dict) or data.get("incomplete_results") is not False
                or not isinstance(data.get("items"), list)
                or any(not isinstance(item, dict) for item in data["items"])):
            raise GitHubError("GitHub 검색 결과가 불완전하거나 올바르지 않습니다")
        return data["items"][:limit]

    def head_commit(self, full_name: str, branch: str) -> str:
        return self.get_json(f"/repos/{full_name}/branches/{urllib.parse.quote(branch, safe='')}")["commit"]["sha"]

    def tree(self, full_name: str, sha: str) -> list[dict]:
        base = f"/repos/{full_name}/git/trees/"
        data = self.get_json(base + urllib.parse.quote(sha, safe=""), recursive="1")
        if not data.get("truncated"):
            return data.get("tree", [])
        # A truncated recursive response loses paths. Walk nonrecursive trees instead.
        pending = [(sha, "", frozenset())]
        fetched, entries = {}, []
        while pending:
            tree_sha, prefix, ancestors = pending.pop()
            if tree_sha in ancestors:
                raise GitHubError(f"Invalid cyclic GitHub tree: {full_name}")
            if tree_sha not in fetched:
                subtree = self.get_json(base + urllib.parse.quote(tree_sha, safe=""))
                if subtree.get("truncated"):
                    raise GitHubError(f"Incomplete GitHub tree: {full_name}/{prefix}")
                fetched[tree_sha] = subtree.get("tree", [])
            for item in fetched[tree_sha]:
                path = prefix + item["path"]
                entries.append({**item, "path": path})
                if item.get("type") == "tree":
                    pending.append((item["sha"], path + "/", ancestors | {tree_sha}))
        return entries

    def file_text(self, full_name: str, path: str, ref: str) -> str:
        data = self.get_json(f"/repos/{full_name}/contents/{urllib.parse.quote(path)}", ref=ref)
        if isinstance(data, dict) and data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", "replace")
        raise GitHubError(f"Unsupported GitHub file encoding: {full_name}/{path}")

    def readme(self, full_name: str, ref: str) -> tuple[str, str]:
        try:
            data = self.get_json(f"/repos/{full_name}/readme", ref=ref)
        except GitHubError as exc:
            if exc.status == 404:
                return "", ""
            raise
        return (base64.b64decode(data.get("content", "")).decode("utf-8", "replace"),
                data.get("path", "README.md"))
