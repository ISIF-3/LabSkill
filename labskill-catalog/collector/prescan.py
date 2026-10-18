"""검토를 돕는 자동 사전 점검. 경고만 낼 뿐 사람의 검토를 대신하지 않는다.

지금은 README·SKILL.md 본문과 스크립트 '경로'만 본다.
스크립트 본문 점검은 검토 요청이 들어온 저장소에 대해 별도로 돌린다(호출 수 절약).
"""
from __future__ import annotations

import re

PATTERNS = [
    ("pipe_to_shell", "내려받아 바로 실행", re.compile(r"(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b", re.I)),
    ("encoded_exec", "인코딩된 코드 실행", re.compile(r"(base64\s+(-d|--decode)|eval\s*\(\s*atob|exec\s*\(\s*base64)", re.I)),
    ("secrets_path", "인증 정보 경로 접근", re.compile(r"(~|\$HOME)/\.(ssh|aws|config/gh|netrc|docker/config)|id_rsa|\.env\b", re.I)),
    ("prompt_injection", "지시 무시 유도 문구", re.compile(r"ignore (all |any )?(previous|prior|above) (instructions|rules)|disregard (the )?(system|previous)", re.I)),
    ("auto_approve", "권한 확인 우회", re.compile(r"--dangerously-skip-permissions|bypassPermissions|--yolo\b", re.I)),
]
INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿]")


def prescan(sources: dict[str, str], script_paths: list[str]) -> list[dict]:
    findings = []
    if script_paths:
        findings.append({"code": "has_scripts", "label": f"실행 스크립트 {len(script_paths)}개 포함", "file": None})
    for fname, text in sources.items():
        for code, label, rx in PATTERNS:
            m = rx.search(text)
            if m:
                findings.append({"code": code, "label": label, "file": fname, "match": m.group()[:80]})
        if INVISIBLE.search(text.lstrip("﻿")):
            findings.append({"code": "invisible_chars", "label": "보이지 않는 유니코드 문자", "file": fname})
    return findings
