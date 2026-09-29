import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from judge.evaluate_versions import main


class VersionTests(unittest.TestCase):
    def test_all_versions_and_bias_are_wired_without_network_grading(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "comparison"
            with patch("judge.evaluate_versions.Judge") as judge, patch("urllib.request.urlopen") as request:
                judge.return_value.provider = "ollama"
                judge.return_value.base = "http://localhost:11434"
                judge.return_value.model = "qwen3:14b"
                request.return_value.__enter__.return_value.read.return_value = json.dumps({"models": [{"name": "qwen3:14b"}]}).encode()
                calls = []

                def run(options):
                    calls.append(options)
                    directory = Path(options[options.index("--output") + 1])
                    directory.mkdir()
                    report = {"successful_responses": 40, "failed_responses": 0,
                              "unlabeled_responses": 40, "quality": {}, "position_bias": {}, "verbosity_bias": {}}
                    (directory / "reliability.json").write_text(json.dumps(report), encoding="utf-8")
                    return 0

                with patch("judge.evaluate_versions.run_judge", side_effect=run):
                    self.assertEqual(main(["--output", str(output)]), 0)
                self.assertEqual(len(calls), 3)
                self.assertNotIn("--pairs", calls[0])
                self.assertIn("--pairs", calls[2])
                pairs = [json.loads(line) for line in (output / "position_pairs.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertEqual(len(pairs), 10)
                self.assertTrue(all(p["answer_a"] != p["answer_b"] for p in pairs))
                self.assertEqual(len({p["item_id"] for p in pairs}), 10)
                result = json.loads((output / "comparison.json").read_text())
                self.assertEqual(set(result["versions"]), {"v1", "v2", "v3"})
                self.assertIn("Pending", result["human_validation"])


if __name__ == "__main__":
    unittest.main()
