"""주어진 메타데이터·문서·파일 신호에서 배포용 에이전트 스킬을 선별한다.

I/O나 모델 호출이 없다. SKILL.md 하나나 플러그인 매니페스트만으로는
배포 저장소로 채택하지 않으며, README의 주목적과 실제 구조를 함께 본다.
"""
from __future__ import annotations

import re

from .detect import parse_frontmatter
from .rules import _domain, _normalize, _parts, _prose, _quotes, _readme

_VERSION = 1
RULES_REVISION = 4
_SKILL = re.compile(r"\bskills?\b|스킬", re.I)
_AGENT = re.compile(r"\b(?:codex|claude(?: code)?|agents?|agentic|coding assistants?|copilot|cursor|openclaw)\b|에이전트", re.I)
_PACKAGE = re.compile(r"\b(?:skills?|plugins?|marketplace|extensions?|hooks?|slash commands?)\b|스킬|플러그인", re.I)
_PRIMARY = re.compile(
    r"\bagent(?:ic)? skills?\b|\bskills? (?:for|library|catalog|collection|framework)\b|"
    r"\b(?:collection|catalog|library|set|composable) of (?:\w+ ){0,3}skills\b|"
    r"\bcomposable skills\b|\bplugins? (?:for|catalog|collection|marketplace)\b|"
    r"\b(?:catalog|collection|marketplace) of (?:\w+ ){0,3}plugins?\b|스킬\s*모음|플러그인\s*모음|\b(?:planning|workflow|agent) preset\b", re.I)
_REFERENCE = re.compile(r"\b(?:tutorial|how to|howto|visual.{0,20}guide|guide to|learning path|course)\b|튜토리얼|학습 가이드", re.I)
_APP = re.compile(r"\b(?:applications?|gui agent|it automation|linux containers?|virtual machines?|"
                  r"deterministic checks|terminal emulator|command.line tool|tool (?:for|that)|sdk|scanner|platform|editor|rendering|renderer|apps?)\b", re.I)
_INSTALL = re.compile(r"/plugin\s+(?:install|marketplace)|\bcodex\s+plugin\s+install|"
                      r"\bskills\s+add\b|\$skill-installer|\.codex/skills|\.claude/skills", re.I)
_DEV_PATH = re.compile(r"(?:^|/)(?:\.claude|\.agents|\.agent|\.github|tests?|fixtures?|examples?|templates?|demos?)(?:/|$)", re.I)
_FIXTURE_PATH = re.compile(r"(?:^|/)(?:tests?|fixtures?|examples?|templates?|demos?)(?:/|$)", re.I)
# Only purpose phrases are used; broad git/test/source words cannot classify a package.
_DOMAINS = {
    'code': {'subcategories': {
        '코드 간결화': ['minimal code', 'less code', 'yagni', 'code simplicity', 'code minimalism', 'laziest senior dev', 'lazy senior dev'],
        '코드 리뷰': ['code review', 'pull request review', 'react review', '코드 리뷰'],
        '테스트·디버깅': ['test driven development', 'systematic debugging', '테스트 자동화'],
        '개발 워크플로': ['software development methodology', 'development workflow', 'coding workflow', '.net', 'swiftui', 'flutter', '개발 워크플로'],
        '토큰·비용 절약': ['token optimization', 'context optimization', 'context engineering', 'context compression', 'reduce token costs'],
    }},
    'lit': {'subcategories': {
        '문헌 검색·정리': ['literature search', 'literature review', 'academic research', 'pubmed', 'arxiv', 'semantic scholar', '문헌 검색'],
        '인용 관리': ['citation management', 'bibtex', 'zotero'],
        '논문 작성': ['academic writing', 'paper writing', 'latex manuscript'],
    }},
    'mat': {'subcategories': {
        'DFT·제일원리': ['density functional theory', 'quantum espresso', 'vasp'],
        '분자동역학': ['molecular dynamics', 'lammps', 'gromacs'],
        '결정구조': ['pymatgen', 'crystal structure'],
        '회절·분광 분석': ['x ray diffraction', 'raman spectroscopy'],
        '전기화학·배터리': ['electrochemistry', 'battery materials'],
    }},
    'data': {'subcategories': {
        '데이터 정리': ['data cleaning', 'data engineering', 'data preprocessing'],
        '통계 분석': ['statistical analysis', 'statistics', 'regression analysis'],
        '그래프·그림': ['data visualization', 'matplotlib', 'scientific plotting'],
        '노트북 정리': ['jupyter notebook'],
    }},
    'verify': {'subcategories': {
        '보안 점검': ['security audit', 'vulnerability scanning', 'penetration testing', 'cybersecurity', 'security skills'],
        '출처·근거 확인': ['citation checking', 'evidence verification'],
        '할루시네이션 방지': ['fact checking', 'hallucination detection'],
    }},
    'work': {'subcategories': {
        '생활·업무 자동화': ['실생활', '한국인을 위한', 'personal productivity', 'life automation', 'office automation', '업무 자동화'],
        '마케팅·콘텐츠': ['marketing skills', 'marketing workflows', 'content marketing', 'search engine optimization', '마케팅'],
    }},
    'science': {'subcategories': {
        '과학 연구 종합': ['scientific agent skills', 'scientific skills', 'skills library for science', 'ai scientist', '과학 연구'],
    }},
}


def _main_intro(readme: str) -> str:
    # Quoted testimonials and promotions describe another project, not this repository.
    own_text = re.sub(r'(?m)^\s*>.*$', '', readme)
    return _parts(own_text)[0]


def candidate(name: str, description: str, topics: list | None = None) -> bool:
    """이름·설명·토픽만으로 상세 읽기가 필요한 넓은 후보를 고른다."""
    repo = _normalize(name.rsplit('/', 1)[-1])
    text = _normalize(' '.join([repo, description or '', *(t for t in topics or [] if isinstance(t, str))]))
    return bool(_SKILL.search(repo) or ((_AGENT.search(text) or name.split('/')[0].casefold() in {'openai', 'anthropics'}) and _PACKAGE.search(text))
                or re.search(r'\b(?:codex|claude code|claude howto)\b', repo))


def _skill_paths(sources: dict, signals: dict) -> list[str]:
    paths = [p for p in sources if p.rsplit('/', 1)[-1] == 'SKILL.md']
    paths += [p for p in signals.get('skill_paths', []) if isinstance(p, str) and p.rsplit('/', 1)[-1] == 'SKILL.md']
    paths += [s['skill_md'] for s in signals.get('skills', []) if isinstance(s, dict) and isinstance(s.get('skill_md'), str)]
    return sorted(set(paths))


def _clients(readme: str) -> dict:
    result = {'codex': None, 'claude_code': None}
    patterns = {'codex': r'\bcodex\b', 'claude_code': r'\bclaude code\b'}
    negative = re.compile(r"\b(?:not|unsupported|incompatible|planned|planning|roadmap|future|coming soon|todo)\b|n['’]t|미지원|예정|지원하지", re.I)
    positive = re.compile(r'\b(?:supports?|supported|compatible|works? with|install(?:ation)?|for use|distribution with)\b|지원|호환', re.I)
    for key, client in patterns.items():
        install_scope = False
        blocked = False
        for line in readme.splitlines():
            clean = _prose(line)
            heading = re.match(r'\s*(#{1,6})\s+(.+)', line)
            label = line.strip().startswith('**') and bool(re.search(client, clean, re.I))
            if heading:
                level, title = len(heading[1]), _prose(heading[2])
                if level <= 2:
                    install_scope = bool(re.search(r'install|setup|getting started|설치', title, re.I))
                    blocked = False
                if re.search(client, title, re.I):
                    blocked = bool(negative.search(title))
                    if install_scope and not blocked:
                        result[key] = True
            elif label and install_scope:
                blocked = bool(negative.search(clean))
                if not blocked:
                    result[key] = True
            # A statement about a different client cannot make this client compatible.
            for clause in re.split(r'[.;!?\n]+', clean):
                if re.search(client, clause, re.I) and positive.search(clause) and not negative.search(clause):
                    result[key] = True
            command = (r'\.codex/skills|\bcodex\s+plugin\s+(?:install|add|marketplace\s+add)' if key == 'codex' else r'\.claude/skills')
            if not blocked and not negative.search(clean) and re.search(command, line, re.I):
                result[key] = True
    return result


def _purpose(name: str, description: str, readme: str, sources: dict, paths: list[str]) -> tuple[str, str]:
    # Main description/intro dominates. Auxiliary skill bodies and install snippets are not purpose text.
    intro = _main_intro(readme)
    declared = _normalize(description + '\n' + intro)
    domain, sub, _, _ = _domain({'purpose': (declared, 3)}, {'domains': _DOMAINS})
    if domain != 'other':
        return domain, sub
    public_paths = [p for p in paths if not _DEV_PATH.search(p)]
    if len(public_paths) != 1:
        return 'other', '범용 스킬·플러그인'
    public = []
    for path in public_paths:
        if _DEV_PATH.search(path) or not isinstance(sources.get(path), str):
            continue
        fm = parse_frontmatter(sources[path])
        public.append(_normalize(fm.get('name', '') + '\n' + fm.get('description', '')))
    votes = set()
    for text in public:
        d, s, _, _ = _domain({'skill': (text, 3)}, {'domains': _DOMAINS})
        if d != 'other':
            votes.add((d, s))
    if len(votes) == 1:
        return next(iter(votes))
    return 'other', '범용 스킬·플러그인'


def assess(name: str, description: str, sources: dict, signals: dict, topics: list | None = None) -> dict:
    """배포용·부가 스킬·참고 자료·무관·미확인을 분리하고 원문 근거를 보존한다."""
    readmes = [(p, t) for p, t in sources.items() if _readme(p) and isinstance(t, str)]
    path, readme = readmes[0] if readmes else ('', '')
    description = description or ''
    clean = _prose(readme)
    declared = _normalize(description + '\n' + _main_intro(readme))
    paths = _skill_paths(sources, signals)
    skill_count = signals.get('skill_count', 0)
    has_skills = isinstance(skill_count, int) and not isinstance(skill_count, bool) and skill_count > 0
    if paths:
        has_public = any(not _DEV_PATH.search(p) for p in paths)
        only_fixtures = all(_FIXTURE_PATH.search(p) for p in paths)
    else:
        has_public = has_skills  # The tree-derived count still proves files when body previews are omitted.
        only_fixtures = False
    manifests = [p for p in signals.get('plugin_manifests', []) if isinstance(p, str) and not _FIXTURE_PATH.search(p)]
    has_structure = has_skills or bool(manifests)
    primary = bool(_PRIMARY.search(declared) or (_SKILL.search(_normalize(name.rsplit('/', 1)[-1])) and _SKILL.search(clean[:3500])))
    # Generic apps can ship agent integration without becoming skill distribution repositories.
    self_skill = bool(re.search(
        r'(?:^|[.!?]\s+)(?:an? |this (?:is an? )?)?(?:claude code|codex|ai agent|agent) skills?\b',
        _normalize(description + '\n' + _main_intro(readme))))
    app_purpose = bool(_APP.search(declared)) and not self_skill and not re.search(
        r'\b(?:collection|catalog|library|bundle) (?:of )?.{0,30}(?:skills|plugins)\b|\b(?:skills|plugins) (?:collection|catalog|library)\b',
        _normalize(description))
    tutorial = bool(_REFERENCE.search(_normalize(description)))
    link_list = bool(re.search(r'\b(?:awesome|curated list)\b', declared)) and not has_public
    status, kind, reasons = 'unconfirmed', None, []
    if not readme.strip():
        reasons.append('README를 읽지 못해 주목적과 설치 대상을 확인하지 못했습니다.')
    elif tutorial:
        status, kind = 'reference', 'prompt_guide'
        reasons.append('README와 설명의 주목적이 사용법·학습 안내입니다.')
    elif link_list:
        status, kind = 'reference', 'awesome_list'
        reasons.append('외부 스킬을 소개하는 링크 목록이며 자체 배포용 스킬 구조가 확인되지 않습니다.')
    elif has_structure and app_purpose:
        status = 'companion'
        kind = 'library' if re.search(r'\b(?:library|sdk)\b', declared) else ('agent_tool' if _AGENT.search(declared) else 'app')
        reasons.append('주목적은 일반 도구이며 포함된 스킬·플러그인은 부가 기능입니다.')
    elif has_structure and not only_fixtures and (primary or (has_public and _AGENT.search(_normalize(description)) and _INSTALL.search(readme))):
        status = 'selected'
        codex = any('.codex-plugin/' in p for p in manifests) or (
            '.codex-plugin/' in signals.get('top_level', []) and bool(re.search(r'\bcodex\s+plugin\s+', readme, re.I)))
        claude = any('.claude-plugin/' in p for p in manifests)
        if codex and claude:
            kind = 'plugin_collection'
        elif codex:
            kind = 'codex_plugin'
        elif claude:
            kind = 'claude_plugin'
        else:
            kind = 'skill' if skill_count == 1 else 'skill_collection'
        reasons.append('README의 주목적이 에이전트 스킬·플러그인 배포이며 실제 파일 구조가 확인됩니다.')
    elif has_structure:
        status = 'companion'
        reasons.append('스킬 파일은 있으나 배포가 주목적이라는 근거가 부족하거나 개발·예제용 파일입니다.')
    elif candidate(name, description, topics) or primary:
        reasons.append('스킬·플러그인 후보이지만 실제 배포 파일을 확인하지 못했습니다.')
    else:
        status = 'not_target'
        reasons.append('README와 파일 신호에서 배포용 에이전트 스킬·플러그인이 확인되지 않습니다.')
    domain, subcategory = _purpose(name, description, readme, sources, paths) if status == 'selected' else ('other', '미분류')
    if status == 'reference':
        domain, subcategory = 'code', '스킬·플러그인 안내'
    evidence = _quotes(readme, path, [{'keyword': k} for k in ('skills', 'plugin', 'codex', 'claude code')])
    labels = {'selected': '배포용 스킬·플러그인', 'companion': '부가 스킬 포함', 'reference': '스킬 참고 자료',
              'not_target': '일반 저장소', 'unconfirmed': '스킬 후보'}
    title = f"{name.rsplit('/', 1)[-1]} · {labels[status]}"[:40]
    summary = reasons[0]
    if status == 'selected':
        kind_label = {'skill': '단일 스킬', 'skill_collection': '스킬 모음', 'claude_plugin': 'Claude Code 플러그인',
                      'codex_plugin': 'Codex 플러그인', 'plugin_collection': '여러 클라이언트 플러그인'}[kind]
        summary = f'{subcategory} 용도의 {kind_label}입니다.'
        if description:
            summary += ' 원문 소개: ' + description[:200]
    return {'version': _VERSION, 'rules_revision': RULES_REVISION, 'status': status, 'kind': kind, 'domain': domain, 'subcategory': subcategory,
            'title_ko': title, 'summary_ko': summary, 'clients': _clients(readme), 'reasons': reasons,
            'evidence': evidence, 'classification_method': 'python_agent_filter'}
