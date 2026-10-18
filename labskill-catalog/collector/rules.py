"""주어진 문자열과 파일 신호만 읽는 결정적 분류기. 모델·네트워크·명령 실행 없음.

같은 키워드는 각 범위에서 한 번만 센다. 경계가 있는 단어/구문을 사용하고,
저장소 이름·설명 3, README 도입부 2, 본문 1의 가중치를 적용한다.
근소한 차이·약한 일반 단어만으로는 분야를 정하지 않는다.
"""
from __future__ import annotations

import re
import unicodedata

CLASSIFICATION_VERSION = 2
_GENERIC = {
    "review", "test", "debug", "bug", "git", "commit", "branch", "token", "cost", "cache",
    "source", "evidence", "seed", "security", "audit", "fit", "survey", "abstract", "talk",
    "blog", "poster", "figure", "chart", "plot", "dataset", "hypothesis", "lean", "bloat",
}
_EXTRA = {
    ("code", "코드 간결화"): ("code simplicity", "code minimalism", "avoid overengineering"),
    ("code", "역공학"): ("reverse engineering", "disassembly", "decompilation", "decompiler", "역공학"),
    ("lit", "문헌 검색·정리"): ("systematic literature review", "literature search", "scoping review", "문헌 검색", "문헌 검토"),
}
_INSTALL_HEADING = re.compile(r"\b(?:install(?:ation)?|setup|quick\s?start|getting started)\b|설치|빠른 시작", re.I)
_DEV_HEADING = re.compile(r"\b(?:develop(?:ment|er)?|contribut(?:e|ing|ion)|test(?:ing|s)?)\b|개발|기여", re.I)
_METHODS = (
    ("plugin_marketplace", re.compile(r"/plugin\s+(?:install|marketplace)\b", re.I)),
    ("npm", re.compile(r"\b(?:npm\s+(?:install|i)\b|npx\s+|pnpm\s+(?:add|dlx)\b|yarn\s+add\b)", re.I)),
    ("pip", re.compile(r"\b(?:pip(?:3|x)?\s+install\b|uv\s+(?:pip\s+install|tool\s+install|tool\s+run|x)\b|uvx\s+)", re.I)),
    ("binary_release", re.compile(r"\b(?:brew\s+install|winget\s+install|download (?:the |a )?(?:binary|installer|release|executable))\b|실행 파일.{0,20}다운로드", re.I)),
    ("mcp_config", re.compile(r'"mcpServers"\s*:|\[mcp_servers\.|\badd.{0,35}\bmcp.{0,25}\bconfig', re.I)),
    ("skill_folder", re.compile(r"(?:copy|cp\s).{0,100}(?:\.claude/skills|\.codex/skills|skills director)|스킬.{0,20}폴더.{0,20}복사", re.I)),
    ("manual", re.compile(r"\bgit\s+clone\b", re.I)),
)


def _normalize(text: str) -> str:
    return re.sub(r"[\s_-]+", " ", unicodedata.normalize("NFKC", text).casefold())

def _has(text: str, keyword: str) -> bool:
    # ASCII 경계로 ASE/database, TEM/template 등을 구분한다. 한국어는 구문 그대로 찾는다.
    term = _normalize(keyword)
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None

def _readme(path: str) -> bool:
    return bool(re.fullmatch(r"readme(?:\.[a-z0-9_-]+)*", path.rsplit("/", 1)[-1].lower()))

def _prose(text: str) -> str:
    text = re.sub(r"(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$", "", text)
    text = re.sub(r"(?m)^(?: {4}|\t).*$", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\[?!\[[^\]]*\]\([^\n]*?\)\]?(?:\([^\n]*?\))?", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\n)]*\)", r"\1", text)
    return text.replace("**", "").replace("__", "").replace("`", "")

def _parts(readme: str) -> tuple[str, str]:
    clean = _prose(readme)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
    title = next((p for p in paragraphs if p.startswith("#")), "")
    intro = next((p for p in paragraphs if not p.startswith(("#", "|", "[!", "- ", "* "))), "")
    selected = [p for p in (title, intro) if p]
    body = "\n\n".join(p for p in paragraphs if p not in selected)
    return "\n\n".join(selected), body

def _skill_frontmatter(sources: dict) -> str:
    descriptions = []
    for path, text in sources.items():
        if path.rsplit("/", 1)[-1] != "SKILL.md" or not isinstance(text, str):
            continue
        match = re.match(r"\ufeff?---\s*\n(.*?)\n---", text, re.S)
        if match:
            for line in match.group(1).splitlines():
                if re.match(r"(?:name|description)\s*:", line):
                    descriptions.append(line.partition(":")[2].strip(" '\""))
    return "\n".join(descriptions)

def _domain(scopes: dict, taxonomy: dict) -> tuple[str, str, str, list]:
    scores, hits, matches = {}, {}, []
    definitions = {}
    for domain, info in taxonomy.get("domains", {}).items():
        if domain == "other":
            continue
        for subcategory, keywords in info.get("subcategories", {}).items():
            definitions[(domain, subcategory)] = set(keywords)
    for pair, keywords in _EXTRA.items():
        if pair[0] in taxonomy.get("domains", {}):
            definitions.setdefault(pair, set()).update(keywords)
    for pair, keywords in definitions.items():
        scores[pair], hits[pair] = 0, set()
        for keyword in sorted(keywords):
            term = _normalize(keyword)
            value = 1 if term in _GENERIC else (3 if " " in term else 2)
            for scope, (text, weight) in scopes.items():
                if _has(text, keyword):
                    score = value * weight
                    scores[pair] += score
                    hits[pair].add(term)
                    matches.append({"domain": pair[0], "subcategory": pair[1], "keyword": keyword,
                                    "scope": scope, "score": score})
    ranked = sorted(scores, key=lambda pair: (-scores[pair], pair))
    if not ranked:
        return "other", "미분류", "low", matches
    best = ranked[0]
    score = scores[best]
    runner = scores[ranked[1]] if len(ranked) > 1 else 0
    strong_hit = any(term not in _GENERIC for term in hits[best])
    # 최소 6점, 강한 단서, 2위와 최소 2점/20% 차이가 있어야 채택한다.
    if score < 6 or not strong_hit or score - runner < max(2, score * 0.2):
        return "other", "미분류", "low", matches
    confidence = "high" if score >= 12 and len(hits[best]) >= 2 and score >= runner * 1.5 else "medium"
    return best[0], best[1], confidence, matches

def _kind(declared: str, signals: dict) -> str | None:
    if signals.get("plugin_manifests"):
        return "claude_plugin"
    if re.search(r"\b(?:mcp|model context protocol) server\b", declared):
        return "mcp_server"
    count = signals.get("skill_count")
    if isinstance(count, (int, float)) and not isinstance(count, bool) and count > 0:
        return "skill" if count == 1 else "skill_collection"
    if signals.get("agent_files"):
        return "subagent"
    if re.search(r"\bawesome\b.{0,45}\b(?:list|collection)\b|\bcurated (?:list|collection)\b", declared):
        return "awesome_list"
    if re.search(r"\b(?:prompt|prompts|rules) (?:collection|guide|templates)\b|\b(?:claude\.md|agents\.md) templates?\b", declared):
        return "prompt_guide"
    if re.search(r"\b(?:agent|agents) (?:orchestrator|orchestration|cli|tool|framework)\b|\b(?:coding|ai) agent (?:tool|framework|orchestrator)\b", declared):
        return "agent_tool"
    if re.search(r"\b(?:library|sdk)\b", declared):
        return "library"
    if re.search(r"\b(?:app|application|desktop tool|command line (?:tool|application)|cli tool|reverse engineering)\b", declared):
        return "app"
    return None

def _quotes(readme: str, path: str, matches: list) -> list:
    if not readme:
        return []
    # 원문 단락을 유지한다. 정리한 문장을 원문 인용으로 반환하지 않는다.
    candidates = []
    fence = False
    paragraph = []
    for line in readme.splitlines(keepends=True) + ["\n"]:
        if re.match(r"\s*(`{3,}|~{3,})", line):
            fence = not fence
        skip = fence or re.match(r"\s*(?:#|!\[|<|\[!|\||```|~~~)", line)
        if not line.strip() or skip:
            if paragraph:
                quote = "".join(paragraph).strip()
                if quote and quote in readme:
                    candidates.append(quote)
                paragraph = []
        else:
            paragraph.append(line)
    scored = [(sum(_has(_normalize(q), m["keyword"]) for m in matches), i, q)
              for i, q in enumerate(candidates) if len(q) >= 15]
    if not scored:
        return []
    # 도입 문장 하나 + 분야 단서가 있는 문장 최대 둘. 정확한 원문만 남긴다.
    first = min(scored, key=lambda row: row[1])
    selected = [first[2]]
    for score, _, quote in sorted(scored, key=lambda row: (-row[0], row[1])):
        if score and quote not in selected and len(selected) < 3:
            selected.append(quote)
    return [{"file": path, "quote": quote} for quote in selected]

def _install(readme: str, path: str, taxonomy: dict) -> tuple[str, dict]:
    install_level, developer_level = None, None
    for line in readme.splitlines():
        heading = re.match(r"\s*(#{1,6})\s+(.+)", line)
        if heading:
            level, title = len(heading[1]), heading[2]
            # 하위 단계는 부모 문맥을 유지하고, 같은 깊이 또는 상위 제목에서 끝낸다.
            if developer_level is not None and level <= developer_level:
                developer_level = None
            if install_level is not None and level <= install_level:
                install_level = None
            if _DEV_HEADING.search(title):
                developer_level = developer_level or level
            if _INSTALL_HEADING.search(title) and developer_level is None:
                install_level = install_level or level
        inline = re.search(r"\binstall (?:with|using|via)|\bto install\b|설치하려면|설치 명령", line, re.I)
        if developer_level is not None or not (install_level is not None or inline):
            continue
        for method, pattern in _METHODS:
            if method in taxonomy.get("install_methods", {}) and pattern.search(line):
                return method, {"file": path, "quote": line}
    return "unknown", {"file": "", "quote": ""}

def classify(name: str, description: str, sources: dict, taxonomy: dict, signals: dict) -> dict:
    """이미 수집한 문자열에서 분류값·일치 규칙·README 원문 근거를 만든다."""
    readmes = [(path, text) for path, text in sources.items() if _readme(path) and isinstance(text, str)]
    path, readme = readmes[0] if readmes else ("", "")
    intro, body = _parts(readme)
    scopes = {"name": (_normalize(name.rsplit("/", 1)[-1]), 3),
              "description": (_normalize(description or ""), 3),
              "intro": (_normalize(intro), 2), "body": (_normalize(body), 1),
              "skill_frontmatter": (_normalize(_skill_frontmatter(sources)), 2)}
    domain, subcategory, confidence, matches = _domain(scopes, taxonomy)
    declared = _normalize((description or "") + "\n" + intro)
    kind = _kind(declared, signals)
    if kind not in taxonomy.get("kinds", {}):
        kind = None
    core = {"skill", "skill_collection", "claude_plugin", "mcp_server", "subagent", "prompt_guide"}
    relevance = "core" if kind in core else (
        "related" if kind == "agent_tool" or re.search(r"\b(?:codex|claude code|coding agents?)\b", declared) else "unrelated")
    evidence = _quotes(readme, path, matches)
    method, install_evidence = _install(readme, path, taxonomy)
    kind_label = taxonomy.get("kinds", {}).get(kind, {}).get("label", "저장소")
    domain_label = taxonomy.get("domains", {}).get(domain, {}).get("label", "기타")
    purpose = subcategory if domain != "other" else "분야 미분류"
    title = f"{purpose} · {kind_label} · {name.rsplit('/', 1)[-1]}"[:40]
    summary = f"파일 구조와 키워드 규칙 기준으로 {domain_label} 분야의 {kind_label}(으)로 분류했습니다."
    if evidence:
        extract = re.split(r"(?<=[.!?])\s", evidence[0]["quote"], maxsplit=1)[0][:240].rstrip()
        summary += " README 원문 발췌: “" + extract + "”"
    else:
        summary += " README 원문 근거가 없어 기능 요약은 제공하지 않습니다."
    tag_groups = {
        "코드 간결화": ["#코드간결화"], "코드 리뷰": ["#리뷰"], "테스트·디버깅": ["#테스트", "#디버깅"],
        "Git·PR 관리": ["#Git"], "토큰·비용 절약": ["#토큰절약"], "문헌 검색·정리": ["#문헌정리"],
        "논문 요약": ["#초록요약"], "인용 관리": ["#인용"], "논문 작성": ["#논문작성"],
        "발표 자료": ["#발표"], "DFT·제일원리": ["#DFT"], "분자동역학": [],
        "결정구조": [], "회절·분광 분석": [], "전기화학·배터리": ["#전기화학"],
        "데이터 정리": [], "통계 분석": ["#통계"], "그래프·그림": ["#그래프"], "노트북 정리": [],
        "할루시네이션 방지": ["#할루시네이션방지"], "출처·근거 확인": ["#출처"],
        "결과 재현": ["#재현성"], "보안 점검": ["#보안"],
    }
    # 특정 제품 태그는 그 문자열을 실제 읽었을 때만 붙인다.
    tags = list(tag_groups.get(subcategory, []))
    fulltext = "\n".join(value[0] for value in scopes.values())
    for keyword, tag in (("arxiv", "#arXiv"), ("latex", "#LaTeX"), ("vasp", "#VASP"),
                         ("pymatgen", "#pymatgen"), ("ase", "#ASE"), ("lammps", "#LAMMPS"),
                         ("xrd", "#XRD"), ("pandas", "#pandas"), ("matplotlib", "#matplotlib"),
                         ("jupyter", "#Jupyter"), ("doi", "#DOI")):
        if domain != "other" and _has(fulltext, keyword):
            tags.append(tag)
    return {"kind": kind, "relevance": relevance, "title_ko": title, "summary_ko": summary,
            "domain": domain, "subcategory": subcategory,
            "tags": sorted(set(tags).intersection(taxonomy.get("tags", []))), "evidence": evidence,
            "install_method": method, "install_evidence": install_evidence,
            "classification_method": "python_rules", "classification_version": CLASSIFICATION_VERSION,
            "rule_matches": matches, "rule_confidence": confidence}
