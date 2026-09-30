import json
import tempfile
import unittest
from pathlib import Path

from judge.readable import render_run
from judge.snapshots import save_snapshot


class ReadableResultsTests(unittest.TestCase):
    def test_report_preserves_answer_reason_and_failed_items_without_mutating_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = [
                {'item_id': 'P1-001', 'response_text': 'Line one\n€10 — exact text', 'status': 'ok',
                 'result': {'scores': {'total': 7}, 'reason': 'Missing quantity.', 'total_corrected': True}},
                {'item_id': 'P1-002', 'response_text': 'Other answer', 'status': 'error', 'error': 'timeout'}]
            raw = '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows).encode('utf-8')
            (root / 'results.jsonl').write_bytes(raw)
            (root / 'metadata.json').write_text(json.dumps({'model': 'test', 'prompt_version': 'judge_v2'}))
            count, mean = render_run(root, {'P1-001': {'customer_message': 'How much?', 'order_context': {}}})
            report = (root / 'report.md').read_text(encoding='utf-8')
            self.assertEqual((count, mean), (2, 7))
            self.assertIn('> Line one\n> €10 — exact text', report)
            self.assertIn('Missing quantity.', report)
            self.assertIn('## P1-002', report)
            self.assertIn('timeout', report)
            self.assertEqual((root / 'results.jsonl').read_bytes(), raw)

    def test_shared_snapshot_reuses_identical_code_and_rejects_different_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shared = root / 'snapshot'
            first = save_snapshot(root / 'v1', shared, 'frozen prompt')
            second = save_snapshot(root / 'v2', shared, 'frozen prompt')
            self.assertEqual(first, second)
            self.assertEqual(len(list(shared.iterdir())), 3)
            with self.assertRaisesRegex(ValueError, 'Snapshot content differs'):
                save_snapshot(root / 'v3', shared, 'changed prompt')
            self.assertEqual((shared / 'judge_prompt.txt').read_text(), 'frozen prompt')
