"""Small, fixed GitHub searches for tools missing from global weekly Trending."""
from __future__ import annotations

import re
from itertools import zip_longest

from .github_client import GitHub, GitHubError

MAX_CANDIDATES = 10
PUBLIC = " is:public archived:false fork:false"
PROFILES = {
    "code": {"label": "코딩·개발", "description": "ponytail·코드 간결화·리뷰용 스킬과 MCP",
             "queries": ["ponytail in:name,description" + PUBLIC,
                         '"minimal code" skill in:name,description' + PUBLIC,
                         '"code review" mcp in:name,description' + PUBLIC]},
    "lit": {"label": "문헌·논문", "description": "문헌 검색·논문 읽기·인용을 돕는 스킬과 MCP",
            "queries": ['literature skill in:name,description' + PUBLIC,
                        'literature mcp in:name,description' + PUBLIC,
                        'paper mcp in:name,description' + PUBLIC]},
    "mat": {"label": "재료과학", "description": "재료·화학 계산과 분석을 돕는 에이전트 도구",
            "queries": ['"materials science" mcp in:name,description' + PUBLIC,
                        '"materials science" agent skill in:name,description' + PUBLIC,
                        'chemistry agent in:name,description' + PUBLIC]},
    "data": {"label": "데이터·시각화", "description": "데이터 분석·그래프·노트북용 스킬과 MCP",
             "queries": ['"data analysis" skill in:name,description' + PUBLIC,
                         'visualization mcp in:name,description' + PUBLIC,
                         'jupyter mcp in:name,description' + PUBLIC]},
    "verify": {"label": "정확성·검증", "description": "출처·재현성·보안 검증을 돕는 에이전트 도구",
               "queries": ['"fact checking" mcp in:name,description' + PUBLIC,
                           'security skill in:name,description' + PUBLIC,
                           'citation mcp in:name,description' + PUBLIC]},
}
REPO_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+\Z")


def gather_candidates(gh: GitHub, domain: str) -> tuple[dict, dict]:
    if not isinstance(domain, str) or domain not in PROFILES:
        raise GitHubError("알 수 없는 탐색 분야입니다")
    groups = [gh.search_repos(query, limit=MAX_CANDIDATES) for query in PROFILES[domain]["queries"]]
    candidates, seen = {}, set()
    # Alternate queries so one broad result set cannot hide the niche keywords.
    for row in zip_longest(*groups):
        for hit in row:
            if not isinstance(hit, dict):
                continue
            name = hit.get("full_name")
            if (not isinstance(name, str) or not REPO_NAME.fullmatch(name)
                    or name.split("/")[1] in (".", "..") or hit.get("private") is True
                    or name.casefold() in seen):
                continue
            seen.add(name.casefold())
            candidates[name] = {
                "sources": [f"discovery:{domain}"], "trending": {}, "in_current_trending": False,
                "html": {"stars": hit.get("stargazers_count"), "description": hit.get("description"),
                         "language": hit.get("language")},
            }
            if len(candidates) == MAX_CANDIDATES:
                return candidates, {f"discovery:{domain}": len(candidates)}
    return candidates, {f"discovery:{domain}": len(candidates)}
