"""Organize every saved repository by function, using local inputs only."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import io
import json
import re
from collections import Counter
from pathlib import Path


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _functions(row, definitions):
    result = row.get('function_catalog') or {}
    values = result.get('functions') or []
    values = list(dict.fromkeys(value for value in values if value in definitions))
    primary = result.get('primary')
    if primary not in values:
        primary = values[0] if values else 'other'
    return primary, values or ['other']


def function_summary(rows, definitions):
    primary, counts = Counter(), Counter()
    for row in rows:
        main, values = _functions(row, definitions)
        primary[main] += 1
        counts.update(values)
    return {'total': len(rows), 'assigned': len(rows) - primary['other'],
            'unclassified': primary['other'],
            'primary_counts': {key: primary[key] for key in definitions},
            'counts': {key: counts[key] for key in definitions}}


def _write_text(path, text, encoding='utf-8'):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding=encoding)
    temporary.replace(path)


def _cell(value):
    return html.escape(str(value or '')).replace('|', '\\|').replace('\n', ' ').replace('\r', '')


def export_functions(root, doc=None, taxonomy=None):
    """Export an index of existing results; never reclassify or fetch sources."""
    from .collect import _read_json, _write_json

    root = Path(root)
    doc = doc if doc is not None else _read_json(root / 'catalog/catalog.json', {})
    taxonomy = taxonomy if taxonomy is not None else _read_json(root / 'catalog/taxonomy.json', {})
    definitions = taxonomy.get('functions') or {'other': {'label': '기타·미분류'}}
    rows = doc.get('repos') or []
    summary = function_summary(rows, definitions)
    label = lambda key: definitions.get(key, {}).get('label', key)
    exported = []
    for row in rows:
        result = row.get('function_catalog') or {}
        primary, functions = _functions(row, definitions)
        name = row['id']
        url = 'https://github.com/' + name if re.fullmatch(r'[\w-]+/[\w.\-]+', name, re.ASCII) else ''
        exported.append({'repository': name, 'canonical_id': row.get('canonical_id') or name, 'url': url,
                         'primary': primary, 'primary_label': label(primary),
                         'functions': functions, 'function_labels': [label(key) for key in functions],
                         'description': row.get('description') or '', 'stars': row.get('stars'),
                         'confidence': result.get('confidence') or 'low',
                         'rules_revision': result.get('rules_revision'),
                         'matched': result.get('matched') or [],
                         'fetch_error': row.get('fetch_error') or ''})
    folder = root / 'catalog/functions'
    _write_json(folder / 'index.json', {'generated_at': doc.get('generated_at'),
                                      'summary': summary, 'functions': definitions, 'repositories': exported})
    stream = io.StringIO(newline='')
    columns = ['repository', 'canonical_id', 'url', 'primary', 'primary_label', 'functions',
               'function_labels', 'description', 'stars', 'confidence', 'rules_revision', 'fetch_error']
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    for row in exported:
        writer.writerow({**row, 'functions': ';'.join(row['functions']),
                         'function_labels': ';'.join(row['function_labels'])})
    _write_text(folder / 'catalog.csv', stream.getvalue(), 'utf-8-sig')
    text = ['# 전체 저장소의 기능별 목록', '',
            f'전체 {summary["total"]}개를 보존했습니다. 기능이 겹치면 앱의 여러 목록에 표시됩니다.',
            '아래 표는 대표 기능으로 한 번씩 묶었습니다. JSON·CSV에는 모든 기능이 포함됩니다.',
            'Python이 설명·토픽·보관한 README 도입부를 읽은 규칙 분류이며, 정확도를 보장하는 확률이 아닙니다.',
            '원본 분류·근거·이력은 catalog/catalog.json에 그대로 남아 있습니다.', '',
            '| 기능 | 해당 기능 포함 | 대표 기능 |', '| --- | ---: | ---: |']
    text.extend(f'| {label(key)} | {summary["counts"][key]} | {summary["primary_counts"][key]} |'
                for key in definitions)
    text.append('')
    for key in definitions:
        group = [row for row in exported if row['primary'] == key]
        if not group:
            continue
        text.extend([f'## {label(key)} · {len(group)}개', '', '| 저장소 | 기능 | 설명 | 조회 오류 |',
                     '| --- | --- | --- | --- |'])
        for row in sorted(group, key=lambda row: (-(row['stars'] or 0), row['repository'].casefold())):
            link = f'[{_cell(row["repository"])}]({row["url"]})' if row['url'] else _cell(row['repository'])
            text.append(f'| {link} | {_cell(", ".join(row["function_labels"]))} | '
                        f'{_cell(row["description"])} | {_cell(row["fetch_error"])} |')
        text.append('')
    _write_text(folder / 'README.md', '\n'.join(text) + '\n')
    return summary


def run(root):
    from .collect import _function_assessment, _read_json, _write_json

    root = Path(root)
    path = root / 'catalog/catalog.json'
    doc = _read_json(path, {})
    rows = doc.get('repos')
    if not isinstance(rows, list) or not rows:
        raise ValueError('먼저 원본 저장소 명단을 가져와야 합니다')
    names = [row.get('id') for row in rows]
    if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
        raise ValueError('명단의 이름이 없거나 중복되어 있습니다')
    cache = _read_json(root / 'cache/agent-screen.json', {})
    reused = 0
    for row in rows:
        # Catalog metadata is newer than a stale screening cache after weekly refresh.
        info = {key: row.get(key) for key in ('description', 'topics', 'pushed_at')}
        cached = (cache.get('analysis') or {}).get(row['id']) or {}
        stamp = [info.get('pushed_at'), info.get('description'), info.get('topics') or []]
        analysis = (cached.get('analysis') or {}) if cached.get('stamp') == stamp else {}
        result = _function_assessment(row['id'], info, analysis, row)
        reused += result == row.get('function_catalog')
        row['function_catalog'] = result
    taxonomy = _read_json(root / 'catalog/taxonomy.json', {})
    summary = function_summary(rows, taxonomy.get('functions') or {'other': {'label': '기타·미분류'}})
    doc.update(generated_at=_now(), count=len(rows), function_summary={**summary, 'generated_at': _now()})
    _write_json(path, doc)
    export_functions(root, doc, taxonomy)
    return {**summary, 'reused': reused, 'updated': len(rows) - reused, 'api_calls': 0,
            'model_calls': 0, 'model_tokens': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.root), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
