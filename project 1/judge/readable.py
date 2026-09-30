"""Render saved judge evidence as Markdown, without making model requests."""
import argparse
import json
from pathlib import Path

from .run import PROJECT, read_jsonl


def quote(text):
    """Keep multiline answers readable without interpreting them as headings."""
    return '\n'.join('> ' + line for line in str(text).splitlines())


def render_run(directory, dataset):
    rows = read_jsonl(directory / 'results.jsonl')
    metadata = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
    totals = [r['result']['scores']['total'] for r in rows if r.get('status') == 'ok']
    lines = [f'# {directory.name}: saved judge results', '',
             f"Judge: **{metadata['model']}**, prompt **{metadata['prompt_version']}**.", '',
             f'Answers: **{len(rows)}**; successful grades: **{len(totals)}**.', '',
             'These are model-assigned scores. Independent human validation is pending.', '',
             'The dataset reference is a comparison aid, not independently verified truth. '
             'Some references assume a currency missing from the supplied context.', '',
             '| Item | Score /8 |', '| --- | ---: |']
    for row in rows:
        score = row.get('result', {}).get('scores', {}).get('total', 'error')
        lines.append(f"| [{row['item_id']}](#{row['item_id'].lower()}) | {score} |")
    for row in rows:
        item = dataset.get(row['item_id'], {})
        lines += ['', f"## {row['item_id']}", '', '**Customer question**', '',
                  quote(item.get('customer_message', 'Not available')), '',
                  '**System answer — exact saved text**', '', quote(row['response_text']), '',
                  '**Dataset reference**', '', quote(item.get('reference_answer', 'Not available')), '']
        grade = row.get('result', {})
        if row.get('status') != 'ok':
            lines += ['**Grading failed**', '', quote(row.get('error', 'Unknown error'))]
            continue
        lines += ['| Criterion | Score |', '| --- | ---: |']
        for name, value in grade['scores'].items():
            lines.append(f"| {name.replace('_', ' ').capitalize()} | {value} |")
        lines += ['', '**Judge explanation — exact saved text**', '', quote(grade['reason']), '',
                  f"Arithmetic correction applied: **{bool(grade.get('total_corrected'))}**.", '',
                  '<details><summary>Supplied order context</summary>', '', '```json',
                  json.dumps(item.get('order_context', {}), ensure_ascii=False, indent=2),
                  '```', '', '</details>']
    (directory / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return len(rows), sum(totals) / len(totals) if totals else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True, help='Comparison directory containing v1/v2/v3')
    parser.add_argument('--dataset', type=Path, default=PROJECT / 'data/dev.jsonl')
    args = parser.parse_args(argv)
    dataset = {r['id']: r for r in read_jsonl(args.dataset)}
    lines = ['# Persona 3: system-prompt comparison', '',
             '**v1, v2 and v3 are system prompt versions, not judge versions.**', '',
             '| System prompt | Judge / prompt | Answers | Average /8 | Read full answers |',
             '| --- | --- | ---: | ---: | --- |']
    for version in ('v1', 'v2', 'v3'):
        count, average = render_run(args.run / version, dataset)
        meta = json.loads((args.run / version / 'metadata.json').read_text(encoding='utf-8'))
        mean = f'{average:.3f}' if average is not None else 'unavailable'
        lines.append(f"| {version} | {meta['model']} / {meta['prompt_version']} | {count} | {mean} | [Report]({version}/report.md) |")
    lines += ['', '## Interpretation', '',
              '- Development-set comparison only; no final test-set evaluation.',
              '- Scores are model judgments, not demonstrated judge accuracy.',
              '- Independent human scoring of these exact replies remains pending.',
              '- Position and verbosity experiments did not run in these saved comparisons. '
              'Person 2 has separate screening results under `../harness/`.', '',
              '## File map', '',
              '- `v*/report.md`: human-readable questions, exact answers, criterion scores, reasons and context.',
              '- `v*/results.jsonl`: original machine-readable evidence; preserved unchanged for the harness.',
              '- `v*/metadata.json`: model settings and input hashes.',
              '- `v*/reliability.json` and `comparison.json`: machine-readable summaries.',
              '- The active judge implementation and prompts are in `project 1/judge/`.', '',
              'Regenerate the Markdown without model calls, from `project 1`:', '',
              '```powershell',
              'python -m judge.readable --run results/judge-comparison-v2-20260929', '```']
    (args.run / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
