"""저장소 파일 목록에서 신호를 모은다. 제외 판정은 하지 않는다 (README 기반 판단의 힌트로만 쓴다)."""
from __future__ import annotations

import posixpath
import re

SCRIPT_EXT = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".ps1", ".bat", ".cmd", ".rb", ".pl"}
PLUGIN_MANIFESTS = {".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
                    ".codex-plugin/plugin.json", ".codex-plugin/marketplace.json",
                    ".agents/plugins/marketplace.json", ".agents/plugins/api_marketplace.json"}
AGENT_DIRS = {"agents", ".claude/agents"}
MCP_FILES = {".mcp.json", "mcp.json", "smithery.yaml"}
INSTRUCTION_FILES = {"CLAUDE.md", "AGENTS.md"}
MAX_SKILLS = 40  # 수백 개짜리 모음은 앞 40개만 상세 수집
MAX_LIST = 20    # 신호 목록마다 앞 20개만 기록
MAX_TOP = 40

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*", re.S)
_MCP_PART = re.compile(r"(^|[._-])mcp([._-]|$)", re.I)


def parse_frontmatter(text: str) -> dict:
    """SKILL.md 앞머리(YAML)에서 name/description 정도만 읽는다 (PyYAML 없이)."""
    m = _FM_RE.match(text.lstrip("﻿"))
    if not m:
        return {}
    out, key = {}, None
    for line in m.group(1).splitlines():
        if re.match(r"^[A-Za-z0-9_-]+\s*:", line):
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            out[key] = val.strip("'\"") if val not in ("|", ">", "|-", ">-") else ""
        elif key and line.startswith((" ", "\t")):
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def detect(tree: list[dict]) -> dict:
    """Git Trees API 결과 → 파일 신호.

    file_kind: 파일만 보고 확실히 말할 수 있는 종류.
      "skill" (SKILL.md 1개) | "skill_collection" (여러 개) | "claude_plugin" (매니페스트) | "subagent" (agents/*.md) | None
    """
    paths = [t["path"] for t in tree if t.get("type") == "blob"]
    skill_mds = sorted(p for p in paths if posixpath.basename(p) == "SKILL.md")
    manifests = sorted(p for p in paths if any(p.endswith(m) for m in PLUGIN_MANIFESTS))
    agent_files = sorted(p for p in paths if p.endswith(".md") and posixpath.dirname(p) in AGENT_DIRS)
    mcp_files = sorted(p for p in paths
                       if posixpath.basename(p) in MCP_FILES or any(_MCP_PART.search(part) for part in p.split("/")))

    skills = []
    for md in skill_mds[:MAX_SKILLS]:
        d = posixpath.dirname(md)
        prefix = (d + "/") if d else ""
        scripts = sorted(
            p for p in paths
            if p.startswith(prefix) and posixpath.splitext(p)[1].lower() in SCRIPT_EXT
        )
        skills.append({"dir": d, "skill_md": md, "scripts": scripts})

    if len(skill_mds) == 1:
        file_kind = "skill"
    elif len(skill_mds) > 1:
        file_kind = "skill_collection"
    elif manifests:
        claude = any('.claude-plugin/' in path for path in manifests)
        codex = any('.codex-plugin/' in path or '.agents/plugins/' in path for path in manifests)
        file_kind = "plugin_collection" if claude and codex else "codex_plugin" if codex else "claude_plugin"
    elif agent_files:
        file_kind = "subagent"
    else:
        file_kind = None
    return {
        "file_kind": file_kind,
        "skill_count": len(skill_mds),
        "skill_paths": skill_mds,
        "skills": skills,
        "plugin_manifests": manifests,
        "agent_files": agent_files[:MAX_LIST],
        "mcp_files": mcp_files[:MAX_LIST],
        "instruction_files": sorted(p for p in paths if p in INSTRUCTION_FILES),
        "top_level": sorted({p.split("/")[0] + ("/" if "/" in p else "") for p in paths})[:MAX_TOP],
    }


def supports(det: dict) -> dict:
    """매니페스트의 대상만 표시한다. SKILL.md 존재만으로 클라이언트 호환을 단정하지 않는다."""
    manifests = det.get('plugin_manifests') or []
    return {'claude_code': True if any('.claude-plugin/' in p for p in manifests) else None,
            'codex': True if any('.codex-plugin/' in p or '.agents/plugins/' in p for p in manifests) else None}
