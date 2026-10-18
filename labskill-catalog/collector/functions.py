"""모든 저장소의 주기능을 메타데이터와 README 도입부로만 분류한다.

에이전트 배포 여부·기존 분야 분류와 독립적이며 I/O나 모델 호출이 없다.
"""
from __future__ import annotations

import hashlib
import json
import re

from .rules import _normalize, _prose

VERSION = 1
RULES_REVISION = 2

# Purpose phrases only: a programming language, an install command or a skill file
# is not evidence that a repository's function is software development.
_KEYWORDS = {
    'code': (
        'software development', 'software engineering', 'development workflow', 'coding workflow',
        'code review', 'review code', 'code editor', 'code editing', 'code intelligence', 'code analysis', 'codebase',
        'coding', 'programming', 'debugging', 'debugger', 'test automation', 'test driven development',
        'unit testing', 'end to end testing', 'refactoring', 'minimal code', 'clean code', 'yagni',
        'developer tools', 'devtools', 'development environment', 'development framework',
        'frontend', 'front end', 'web framework', 'web development', 'web apps', 'web applications',
        'ui components', 'component library', 'design system', 'build tool', 'compiler', 'toolchain',
        'terminal', 'terminal emulator', 'terminal multiplexer', 'git', 'worktree', 'worktrees', 'pull request',
        'test framework', 'testing framework', 'unit tests', 'tdd', 'bdd', 'test runner', 'bundler',
        'package manager', 'version manager', 'javascript runtime', 'typescript runtime', 'runtime',
        'game engine', 'game development', 'gamedev', 'css framework', 'ui development', 'ui framework',
        'graphical user interface', 'gui toolkit', 'fullstack', 'full stack', 'vue framework',
        'domain specific language', 'programming language', 'typechecker', 'compiles', 'compile',
        'gpu kernel', 'gpu kernels', 'gemm', 'blas', 'software dev',
        'testing and mocking', 'yaml parser', 'json parser', 'stacked prs', 'checking out a repo',
        'dev tools', 'visual studio code', 'vscode', 'ide', 'code cli', 'ui skills',
        'load generator', 'http load', 'build management', 'code setup', 'source formatting',
        'source code', 'schema validation', 'type inference', '코드 리뷰', '개발 도구', '코딩',
    ),
    'literature': (
        'literature search', 'literature review', 'literature discovery', 'scientific literature',
        'academic papers', 'academic paper', 'scientific paper', 'scientific papers', 'paper search',
        'paper finder', 'research papers', 'research paper', 'citation management', 'reference manager', 'bibtex',
        'pubmed', 'arxiv', 'biorxiv', 'semantic scholar', 'google scholar', 'zotero', 'patent search',
        'patents', 'prior art', '문헌 검색', '문헌 검토', '논문 검색', '논문 작성', '学术', '论文',
    ),
    'visualization': (
        'visualization', 'visualisation', 'visualize', 'visualise', 'visualizing', 'visualising', 'visualizer', 'visualiser',
        'plotting', 'scientific plotting', 'matplotlib', 'seaborn', 'plotly', 'charts', 'chart',
        'diagrams', 'diagram', 'flowchart', 'dashboards', 'dashboard', 'infographic', 'mermaid',
        'drawio', 'draw io', 'excalidraw', 'data graphics', '시각화', '다이어그램', '数据可视化', '图表',
    ),
    'data': (
        'data analysis', 'data analytics', 'analytics', 'statistical analysis', 'statistics',
        'data science', 'data cleaning', 'data processing', 'data preprocessing', 'data engineering',
        'data pipeline', 'data pipelines', 'etl', 'elt', 'data warehouse', 'data modeling',
        'business intelligence', 'text to sql', 'sql engine', 'database', 'databases', 'dataframe',
        'pandas', 'polars', 'numpy', 'scipy', 'jupyter', 'duckdb', 'financial analysis',
        'stock analysis', 'backtesting', 'quantitative finance', '데이터 분석', '통계 분석', '数据分析',
    ),
    'ai': (
        'ai', 'artificial intelligence', 'agents', 'agent', 'agentic', 'multiagent', 'multi agent',
        'llm', 'llms', 'large language model', 'large language models', 'language models',
        'machine learning', 'deep learning', 'reinforcement learning', 'neural network',
        'neural networks', 'generative ai', 'model training', 'fine tuning', 'finetuning',
        'inference', 'rag', 'retrieval augmented generation', 'chatbot', 'chatbots',
        'prompt engineering', 'prompts', 'mcp', 'model context protocol', '에이전트', '인공지능',
        'codex', 'claude code', 'chatgpt', 'context compression', 'token savings',
        'foundation model', 'foundation models', 'moe models', 'expert parallel',
        'speculative decoding', 'attention kernels', 'natural language processing', 'nlp',
        'subagent', 'subagents', 'rl training',
    ),
    'search': (
        'search engine', 'web search', 'web research', 'deep research', 'deepresearch',
        'web scraper', 'web scraping', 'web crawler', 'scraper', 'scraping', 'crawler', 'crawling',
        'scrape', 'scrapes', 'scrapy', 'information retrieval', 'semantic search', 'file search',
        'filesearch', 'full text search', 'fulltext search', 'document search', 'search sdk',
        'data extraction', 'web extraction', 'osint', '웹 검색', '자료 수집', '爬虫', '搜索引擎',
        'download manager', 'downloader', 'bittorrent', 'torrent client',
    ),
    'automation': (
        'automation', 'automate', 'automated workflow', 'workflow automation', 'browser automation',
        'desktop automation', 'robotic process automation', 'task scheduling', 'scheduler',
        'scheduled tasks', 'workflow engine', 'workflow orchestration', 'durable execution',
        'durable workflows', 'automatically', '자동화', '自动化',
    ),
    'productivity': (
        'productivity', 'note taking', 'notes app', 'note app', 'notes', 'knowledge management',
        'personal knowledge', 'second brain', 'documents', 'document', 'document editor',
        'pdf editor', 'pdf', 'office', 'spreadsheet', 'slides', 'presentation', 'presentations',
        'task management', 'project management', 'task manager', 'calendar', 'email', 'newsletter',
        'academic writing', 'scientific writing', 'paper writing', 'dissertation writing',
        'mailing list', 'writing assistant', 'text humanizer', 'humanizer', 'translation',
        'translator', 'translate', 'markdown editor', 'markdown', 'md files', 'wiki', 'erp', 'crm', 'accounting',
        'knowledge workers', 'clipboard', 'launcher', 'hotkeys', 'publishing', 'newsletters',
        'blogging', 'cms', 'collaboration', 'chat', 'communication platform', 'asset management',
        'license management', 'web browser',
        'marketing', 'ecommerce', 'e commerce', 'commerce platform', '업무', '문서', '笔记', '翻译',
    ),
    'media': (
        'image generation', 'image editing', 'image editor', 'image processing', 'text to image',
        'image to image', 'imagegeneration', 'text2image', 'image2image', 'img2img', 'txt2img',
        'diffusion model', 'stable diffusion', 'video', 'videos', 'videoeditor', 'videogeneration',
        'filmmaking', 'animation', 'animate', '3d graphics', '3d modeling', '3d reconstruction',
        '3d generation', 'mesh processing', 'remeshing', 'retopology', 'multimedia', 'media player',
        'media system', 'media content', 'mediaplayer', 'iptv', 'tv channels',
        'video streaming', 'audio streaming', 'media streaming', 'live streaming',
        'gaussian splatting', 'music', 'audio', 'speech', 'voice recognition', 'voice studio', 'voice design',
        'voice generation', 'voice clone', 'voice ai', 'voice cloning', 'tts', 'stt',
        'transcription', 'transcribe', 'dictation', 'text to speech', 'speech to text',
        'photo', 'photos', 'photography', '영상', '음성', '이미지 생성', '视频', '语音', '音乐',
    ),
    'infrastructure': (
        'infrastructure', 'cloud native', 'cloud platform', 'cloud computing', 'kubernetes',
        'container', 'containers', 'docker', 'deployment', 'deploy', 'hosting', 'self hosting',
        'self hosted', 'web server', 'http server', 'reverse proxy', 'load balancer', 'networking',
        'observability', 'monitoring', 'metrics', 'logging', 'logs', 'object storage', 'file system',
        'filesystem', 'distributed storage', 's3 compatible', 'vpn', 'wireguard', 'backup',
        'file sharing', 'data transfer', 'proxy', 'dns', 'network stack', 'tcp tunnel', 'quic',
        '서버', '배포',
    ),
    'security': (
        'security', 'cybersecurity', 'infosec', 'reverse engineering', 'reverse engineer',
        'disassembler', 'disassembly', 'decompiler', 'decompilation', 'binary analysis',
        'malware', 'malware analysis', 'vulnerability', 'vulnerabilities', 'penetration testing',
        'ethical hacking', 'red team', 'threat hunting', 'threat intelligence', 'security audit',
        'authentication', 'authorization', 'identity and access management', 'encryption',
        'password manager', 'passwords profiler', 'dictionary attack', 'password strength',
        'secret scanner', 'secrets scanning', 'sandbox', 'isolation',
        'containment', 'jailbreak', 'jailbreaks', '보안', '역공학', '漏洞',
    ),
    'science': (
        'scientific computing', 'scientific research', 'scientific skills', 'ai scientist',
        'science', 'scientific', 'physics', 'chemistry', 'biology', 'bioinformatics', 'genomics',
        'proteomics', 'drug discovery', 'materials science', 'material science', 'molecular dynamics',
        'density functional theory', 'quantum espresso', 'dft', 'vasp', 'lammps', 'gromacs',
        'pymatgen', 'ase', 'crystal structure', 'spectroscopy', 'diffraction', 'xrd', 'tem',
        'sem', 'electrochemistry', 'battery materials', 'finite element', 'fluid dynamics',
        'physics based simulations', 'scientific simulation', 'hypothesis discovery',
        'weather forecast', 'weather forecasting', 'radar system', '과학', '재료과학', '분자동역학',
    ),
    'learning': (
        'learn', 'learning path', 'learning resources', 'self learning', 'self taught',
        'tutorial', 'tutorials', 'tutorial code', 'tutorial exercises', 'course', 'courses',
        'curriculum', 'education', 'educational', 'beginner', 'beginners', 'from scratch',
        'zero to hero', 'book', 'books', 'interview preparation', 'interview questions',
        'awesome list', 'curated list', 'resources', 'workshops', 'assignments', 'flashcard',
        'spaced repetition', 'interview guide', '学英语', '학습', '튜토리얼', '自学', '教程',
    ),
    'devices': (
        'operating system', 'operating systems', 'firmware', 'embedded', 'embedded systems',
        'microcontroller', 'microcontrollers', 'esp32', 'esp 32', 'arduino', 'raspberry pi', 'iot',
        'home assistant', 'home automation', 'robotics', 'robot', 'robots', 'device control',
        'android device', 'android screen', 'screen viewer', 'screen mirroring', 'second display', 'second monitor', 'virtual display',
        'emulator', 'emulation', 'game console', 'linux kernel', 'operating system kernel',
        'kernel driver', 'kernel module', 'bootloader', 'driver', 'drivers',
        'windows optimization', 'system optimization', 'debloat', 'bloatware removal', 'compositor',
        'wayland', 'virtual iphone', 'headunit', 'mouse remapping', 'sideloading', '기기', '펌웨어', '임베디드',
    ),
}
_PRIMARY_ORDER = ('learning', 'literature', 'visualization', 'security', 'science', 'search',
                  'automation', 'data', 'media', 'productivity', 'devices', 'infrastructure', 'code', 'ai')
_AI_PURPOSE = re.compile(
    r'\b(?:agent (?:framework|orchestrat\w*|harness)|multi ?agent|llm inference|model training|'
    r'fine tun(?:e|ing)|finetuning|ai (?:interface|assistant|chat)|reinforcement learning|machine learning|neural networks?|'
    r'retrieval augmented generation|rag|chatbots?)\b')
_PROMOTION = re.compile(r'\b(?:sponsor(?:ed|ship|s)?|advertisement|promoted|supported by|our partners)\b|후원|광고', re.I)
_INTRO_HEADING = re.compile(r'^(?:about|overview|introduction|what is\b|purpose|소개|개요)', re.I)
_FALLBACK = {'code': {'developer tools', 'devtools', 'codebase'},
             'learning': {'resources', 'awesome list', 'curated list'}}
_PATTERNS = {function: [(keyword, re.compile(r'(?<![a-z0-9])' + re.escape(_normalize(keyword)) + r'(?![a-z0-9])'))
                        for keyword in keywords] for function, keywords in _KEYWORDS.items()}
_LITERATURE_ACTION = re.compile(r'\b(?:search|review|discover\w*|find\w*|retriev\w*|download\w*|citation|'
                                r'reference|bibtex|pubmed|arxiv|biorxiv|scholar|zotero|patents?|prior art)\b|문헌|논문 검색')


def _intro(readme: str) -> str:
    # Keep the title and first purpose paragraphs; later features/examples are not
    # a repository's declaration of purpose, even when they contain SKILL.md text.
    text = re.sub(r'<(?:table|picture|svg|script|style)\b[^>]*>.*?</(?:table|picture|svg|script|style)>',
                  '', readme or '', flags=re.I | re.S)
    text = re.sub(r'(?m)^\s*>.*$', '', text)
    text = _prose(text)
    text = re.sub(r'(?m)^(#{1,6}\s+[^\n]+)\n(?!\n)', r'\1\n\n', text)
    selected, prose_count = [], 0
    for paragraph in re.split(r'\n\s*\n', text):
        paragraph = paragraph.strip()
        if not paragraph or _PROMOTION.search(paragraph):
            continue
        heading = re.match(r'^(#{1,6})\s+(.+)', paragraph)
        if heading:
            if len(heading[1]) > 1 and not _INTRO_HEADING.search(heading[2]):
                break
            selected.append(heading[2])
            continue
        if paragraph.startswith(('|', '- ', '* ', '[!', '[')):
            continue
        selected.append(paragraph)
        prose_count += 1
        if prose_count == 2:
            break
    return '\n'.join(selected)[:2000]


def _inputs(name: str, description: str, topics: list | None, readme: str) -> dict:
    return {'name': _normalize((name or '').rsplit('/', 1)[-1]).strip(),
            'description': _normalize(_prose(description or '')).strip(),
            'topics': sorted({_normalize(topic).strip() for topic in topics or [] if isinstance(topic, str) and topic.strip()}),
            'intro': _normalize(_intro(readme)).strip()}


def _digest(inputs: dict) -> str:
    return hashlib.sha256(json.dumps(inputs, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def function_input_sha(name: str, description: str, topics: list | None = None, readme: str = '') -> str:
    """실제 분류에 쓰는 입력의 해시. README 본문 변경은 영향을 주지 않는다."""
    return _digest(_inputs(name, description, topics, readme))


def classify_functions(name: str, description: str, topics: list | None = None, readme: str = '') -> dict:
    """function_catalog에 저장할 독립적인 주기능과 여러 기능 라벨을 반환한다."""
    inputs = _inputs(name, description, topics, readme)
    scopes = {key: '\n'.join(value) if isinstance(value, list) else value for key, value in inputs.items()}
    matches, scores = [], {}
    weights = {'name': 6, 'description': 8, 'topics': 3, 'intro': 2}
    for function, patterns in _PATTERNS.items():
        sources = set()
        for source, text in scopes.items():
            for keyword, pattern in patterns:
                purpose_text = text
                if function == 'science' and keyword == 'science':
                    purpose_text = re.sub(r'\b(?:computer|data) science\b', '', text)
                if function == 'productivity' and keyword == 'web browser':
                    purpose_text = re.sub(r'\b(?:in|from|within)(?: (?:a|the|your|any))? web browser\b', '', text)
                if pattern.search(purpose_text):
                    sources.add(source)
                    matches.append({'function': function, 'keyword': keyword, 'source': source})
        if sources:
            # A list of incidental technologies cannot outvote a declared purpose.
            scores[function] = sum(weights[source] for source in sources)

    if 'literature' in scores and not _LITERATURE_ACTION.search('\n'.join(scopes.values())):
        scores.pop('literature')

    if len(scores) > 1:
        # Generic developer/AI technology labels are useful fallbacks, but should
        # not tag every plotting library or application that happens to use AI.
        for function, weak in _FALLBACK.items():
            hits = [m for m in matches if m['function'] == function]
            if hits and len(scores) > 1 and all(m['keyword'] in weak for m in hits):
                scores.pop(function, None)
        if 'visualization' in scores and len(scores) > 1 and all(
                m['keyword'] in {'dashboard', 'dashboards'} for m in matches if m['function'] == 'visualization'):
            if not re.search(r'\b(?:observability|analytics|metrics|analysis|intelligence)\b', scopes['description']):
                scores.pop('visualization')
        if 'ai' in scores and len(scores) > 1 and not _AI_PURPOSE.search(scopes['name'] + '\n' + scopes['description']):
            scores.pop('ai')
        if 'science' in scores:
            weak_science = {'scientific', 'ai scientist', 'science'} if {'literature', 'visualization'} & scores.keys() else {'scientific'}
            if all(m['keyword'] in weak_science for m in matches if m['function'] == 'science'):
                scores.pop('science')

    functions = sorted(scores, key=lambda function: (-scores[function], _PRIMARY_ORDER.index(function))) or ['other']
    matches = [match for match in matches if match['function'] in functions]
    primary_hits = [m for m in matches if m['function'] == functions[0]]
    metadata_hits = [m for m in primary_hits if m['source'] != 'intro']
    confidence = ('high' if len({m['source'] for m in metadata_hits}) >= 2 or
                  len({m['keyword'] for m in metadata_hits if m['source'] == 'description'}) >= 2
                  else 'medium') if metadata_hits else 'low'
    return {'version': VERSION, 'rules_revision': RULES_REVISION, 'primary': functions[0],
            'functions': functions, 'confidence': confidence, 'matched': matches,
            'input_sha': _digest(inputs), 'classification_method': 'python_functions'}
