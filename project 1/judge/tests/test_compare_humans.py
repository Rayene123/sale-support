import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from judge.compare_humans import main
from judge.run import PROJECT
from test_judge import SCORES


class HumanComparisonTests(unittest.TestCase):
    def test_saved_scores_compare_only_to_matching_human_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = PROJECT / "data/dev.jsonl"
            (root / "metadata.json").write_text(json.dumps({"input_hashes": {"dataset": hashlib.sha256(dataset.read_bytes()).hexdigest()}}))
            row = {"item_id": "P1-001", "response_id": "baseline_v3", "response_text": "Pending.",
                   "status": "ok", "result": {"scores": SCORES, "reason": "Known status."}}
            (root / "results.jsonl").write_text(json.dumps(row) + "\n")
            label = {k: row[k] for k in ("item_id", "response_id", "response_text")}
            label.update(evaluator_id="human1", scores=SCORES, explanation="Checked status.")
            labels = root / "labels.jsonl"
            labels.write_text(json.dumps(label) + "\n")
            output = root / "comparison.json"
            options = ["--run", str(root), "--labels", str(labels), "--output", str(output), "--labels-reviewed"]
            self.assertEqual(main(options), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report["judge_agreement_by_evaluator"]["human1"]["total"]["agreement_percent"], 100)
            self.assertEqual(report["label_status"], "independently_reviewed_user_attestation")
            label["response_text"] = "Different answer."
            labels.write_text(json.dumps(label) + "\n")
            options[options.index("--output") + 1] = str(root / "bad.json")
            with self.assertRaises(SystemExit):
                main(options)
            self.assertFalse((root / "bad.json").exists())


if __name__ == "__main__":
    unittest.main()
