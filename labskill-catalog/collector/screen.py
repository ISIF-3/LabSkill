"""Screen the existing roster with metadata first; inspect only agent-package candidates."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .collect import _function_assessment, _read_json, _write_json, analyze_repo
from .github_client import GitHub, GitHubError
from .detect import supports


def _metadata(info, name):
    return {key: info.get(key) for key in ('full_name', 'default_branch', 'description', 'topics',
            'stargazers_count', 'forks_count', 'language', 'license', 'pushed_at', 'archived')} | {
            'full_name': info.get('full_name') or name}


def _unknown(reason, candidate=False, error=None):
    out = {'version': 1, 'status': 'unconfirmed', 'kind': None, 'domain': 'other', 'subcategory': '미분류',
           'clients': {'codex': None, 'claude_code': None}, 'candidate': candidate,
           'reasons': [reason], 'evidence': [], 'classification_method': 'python_metadata_filter'}
    if error:
        out['error'] = error
    return out


def _persist(root, outcomes, report):
    doc = _read_json(root / 'catalog/catalog.json', {})
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    day = now[:10]
    for row in doc['repos']:
        name = row['id']
        if name not in outcomes:
            continue
        result = outcomes[name]
        info, agent = result.get('info'), result['agent_catalog']
        row['function_catalog'] = _function_assessment(name, info or row, result.get('analysis') or {}, row)
        prior = row.get('agent_catalog') or {}
        if result.get('error') and prior.get('version') == 1 and prior.get('status') != 'unconfirmed':
            row['agent_catalog'] = {**prior, 'last_check_at': now, 'last_check_error': result['error']}
        else:
            row['agent_catalog'] = {**agent, 'checked_at': now}
        if info:
            row.update(description=info.get('description') or '', topics=info.get('topics') or [],
                       canonical_id=info.get('full_name') or name, stars=info.get('stargazers_count'),
                       forks=info.get('forks_count'), language=info.get('language'),
                       license=(info.get('license') or {}).get('spdx_id'), pushed_at=info.get('pushed_at'),
                       metadata_date=day, stars_observed_at=day)
        analysis = result.get('analysis')
        if analysis:
            row.update(file_signals=analysis['signals'], file_kind=analysis['signals']['file_kind'],
                       skill_count=analysis['signals']['skill_count'], skills=analysis['skills'],
                       supports=analysis['supports'], commit=analysis['commit'], readme_sha=analysis['readme_sha'],
                       sources_sha=analysis['sources_sha'], prescan=analysis['prescan'], file_signals_date=day)
            row['agent_catalog']['readme_sha'] = analysis['readme_sha']
        if result.get('error'):
            row.update(fetch_error=result['error'])
            row['fetch_status'] = 'failed'
        else:
            row.update(fetch_status='ok' if analysis else row.get('fetch_status') if row.get('fetch_status') == 'ok'
                       else 'metadata_only', fetch_error=None)
        if any(source.startswith('archive:') for source in row.get('sources', [])):
            row.update(history_backfill_status='failed' if result.get('error') else 'complete', history_last_attempt=now)
            if not result.get('error'):
                row['history_backfill_at'] = now
    counts = Counter(row.get('agent_catalog', {}).get('status', 'unconfirmed') for row in doc['repos'])
    report.update({key: counts.get(key, 0) for key in ('selected', 'companion', 'reference', 'not_target', 'unconfirmed')})
    doc.update(count=len(doc['repos']), generated_at=now, screening_summary=report)
    from .organize import function_summary
    taxonomy = _read_json(root / 'catalog/taxonomy.json', {})
    doc['function_summary'] = function_summary(doc['repos'], taxonomy.get('functions') or {'other': {}})
    _write_json(root / 'catalog/catalog.json', doc)


def export(root):
    doc = _read_json(root / 'catalog/catalog.json', {})
    names = {'selected': '스킬·플러그인', 'companion': '부가 스킬', 'reference': '참고 자료',
             'not_target': '대상 아님', 'unconfirmed': '미확인'}
    rows = []
    for row in doc['repos']:
        agent = row.get('agent_catalog') or {}
        rows.append({'repository': row['id'], 'canonical_id': row.get('canonical_id') or row['id'],
                     'url': 'https://github.com/' + row['id'], 'status': agent.get('status', 'unconfirmed'),
                     'kind': agent.get('kind'), 'domain': agent.get('domain'), 'subcategory': agent.get('subcategory'),
                     'codex': (agent.get('clients') or {}).get('codex'),
                     'claude_code': (agent.get('clients') or {}).get('claude_code'),
                     'skill_count': row.get('skill_count'), 'stars': row.get('stars'),
                     'history': any(s.startswith('archive:') for s in row.get('sources', [])),
                     'reason': ' / '.join(agent.get('reasons') or []),
                     'error': agent.get('error') or agent.get('last_check_error') or row.get('fetch_error') or ''})
    rows.sort(key=lambda r: (r['status'] != 'selected', -(r['stars'] or 0), r['repository'].casefold()))
    folder = root / 'catalog/agent-selection'
    _write_json(folder / 'selection.json', {'generated_at': doc.get('generated_at'),
                'summary': doc.get('screening_summary'), 'repositories': rows})
    with (folder / 'selection.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['repository'])
        writer.writeheader()
        writer.writerows(rows)
    text = ['# 트렌딩에서 선별한 스킬·플러그인', '', 'Python 규칙의 결과이며 README 안내를 읽은 기록이다. 실행·호환성 검증은 하지 않았다.',
            '원본은 catalog/catalog.json에 모두 남아 있다. 미확인에는 메타데이터에 단서가 없어 상세 조회를 보류한 항목도 포함된다.', '']
    for status, label in names.items():
        group = [r for r in rows if r['status'] == status]
        text.extend([f'## {label} · {len(group)}개', '', '| 저장소 | 종류 | 분야 | 지원 안내 |', '| --- | --- | --- | --- |'])
        for r in group:
            clients = ', '.join(c for c, key in [('Codex', 'codex'), ('Claude Code', 'claude_code')] if r[key]) or '미확인'
            text.append(f'| [{r["repository"]}]({r["url"]}) | {r["kind"] or "—"} | {r["subcategory"] or "—"} | {clients} |')
        text.append('')
    (folder / 'README.md').write_text('\n'.join(text) + '\n')
    from .organize import export_functions
    export_functions(root, doc)
    return rows


def run(root, *, github_factory=None, workers=6, metadata_only=False, progress=None):
    root = Path(root)
    doc = _read_json(root / 'catalog/catalog.json', {})
    if not isinstance(doc.get('repos'), list) or not doc['repos']:
        raise ValueError('먼저 원본 저장소 명단을 가져와야 합니다')
    names = [row['id'] for row in doc['repos']]
    previous = {row['id']: row for row in doc['repos']}
    if len(set(names)) != len(names):
        raise ValueError('명단에 중복 이름이 있습니다')
    if github_factory is None:
        credential = GitHub.from_gh().token
        github_factory = lambda: GitHub(token=credential)
    cache_path = root / 'cache/agent-screen.json'
    cache = _read_json(cache_path, {'metadata': {}, 'analysis': {}})
    day = dt.datetime.now(dt.timezone.utc).date().isoformat()
    infos, failures, calls = {}, {}, 0

    def emit(stage, current, total, name):
        if progress:
            progress({'stage': stage, 'current': current, 'total': total, 'repo': name})

    def fetch_metadata(name):
        gh = github_factory()
        start = gh.calls
        try:
            return name, _metadata(gh.repo(name), name), None, gh.calls - start
        except GitHubError as exc:
            return name, None, str(exc), gh.calls - start

    todo = []
    for name in names:
        cached = cache['metadata'].get(name, {})
        if cached.get('day') == day and isinstance(cached.get('info'), dict):
            infos[name] = cached['info']
        else:
            todo.append(name)
    with ThreadPoolExecutor(max_workers=max(1, min(8, workers))) as executor:
        for i, future in enumerate(as_completed([executor.submit(fetch_metadata, name) for name in todo]), 1):
            name, info, error, used = future.result()
            calls += used
            if info:
                infos[name] = info
                cache['metadata'][name] = {'day': day, 'info': info}
            else:
                failures[name] = error
            if i % 25 == 0 or i == len(todo):
                _write_json(cache_path, cache)
            emit('metadata', i, len(todo), name)
    report = {'total': len(names), 'metadata_success': len(infos), 'metadata_failed': len(failures),
              'api_calls': calls, 'model_calls': 0, 'model_tokens': 0}
    if metadata_only:
        _write_json(cache_path, cache)
        return report
    from .agent_filter import assess, candidate
    outcomes = {name: {'agent_catalog': _unknown('GitHub 메타데이터 조회 실패', error=error), 'error': error}
                for name, error in failures.items()}
    targets = []
    for name, info in infos.items():
        old = previous[name]
        known = (isinstance(old.get('skill_count'), int) and old['skill_count'] > 0
                 or bool(old.get('file_signals', {}).get('plugin_manifests'))
                 or old.get('agent_catalog', {}).get('status') in ('selected', 'companion', 'reference'))
        if known or candidate(name, info.get('description') or '', info.get('topics') or []):
            targets.append(name)
        else:
            outcomes[name] = {'info': info, 'agent_catalog': _unknown('이름·설명·토픽에 스킬·플러그인 배포 단서가 없어 상세 조회를 보류했습니다.')}

    def inspect(name):
        info = infos[name]
        stamp = [info.get('pushed_at'), info.get('description'), info.get('topics')]
        cached = cache['analysis'].get(name, {})
        gh, used = None, 0
        try:
            if cached.get('stamp') == stamp and cached.get('analysis'):
                analysis = cached['analysis']
                analysis['supports'] = supports(analysis['signals'])
            else:
                gh = github_factory()
                start = gh.calls
                analysis = analyze_repo(gh, name, {}, info=info)
                analysis.pop('info', None)
                used = gh.calls - start
            agent = {**assess(name, info.get('description') or '', analysis['_sources'], analysis['signals'],
                              info.get('topics') or []), 'candidate': True}
            return name, {'info': info, 'analysis': analysis, 'agent_catalog': agent}, {'stamp': stamp, 'analysis': analysis}, used
        except GitHubError as exc:
            return name, {'info': info, 'agent_catalog': _unknown('후보 저장소의 README·파일 조회 실패', True, str(exc)),
                          'error': str(exc)}, None, gh.calls - start if gh else used

    def checkpoint():
        counts = Counter(result['agent_catalog']['status'] for result in outcomes.values())
        report.update({key: counts.get(key, 0) for key in ('selected', 'companion', 'reference', 'not_target', 'unconfirmed')})
        report.update(candidates=len(targets), processed=len(outcomes), metadata_only=sum(
            result['agent_catalog'].get('candidate') is False and not result.get('error') for result in outcomes.values()),
            failed=sum(bool(result.get('error')) for result in outcomes.values()), api_calls=calls)
        _write_json(cache_path, cache)
        _persist(root, outcomes, report)

    checkpoint()
    with ThreadPoolExecutor(max_workers=max(1, min(8, workers))) as executor:
        for i, future in enumerate(as_completed([executor.submit(inspect, name) for name in targets]), 1):
            name, outcome, analysis_cache, used = future.result()
            calls += used
            outcomes[name] = outcome
            if analysis_cache:
                cache['analysis'][name] = analysis_cache
            if i % 10 == 0 or i == len(targets):
                checkpoint()
            emit('inspect', i, len(targets), name)
    checkpoint()
    export(root)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--metadata-only', action='store_true')
    args = parser.parse_args()
    def progress(row):
        if row['current'] % 10 == 0 or row['current'] == row['total']:
            print(f'{row["stage"]} {row["current"]}/{row["total"]} {row["repo"]}', flush=True)
    print(json.dumps(run(args.root, workers=args.workers, metadata_only=args.metadata_only, progress=progress),
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
