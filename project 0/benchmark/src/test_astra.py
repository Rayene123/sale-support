import csv
import json
import tempfile
import unittest
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
import run
import score


class BenchmarkTests(unittest.TestCase):
    def test_real_http_transport_to_local_stub(self):
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                body=json.dumps({'choices':[{'message':{'content':'positive'},'finish_reason':'stop'}],
                                 'usage':{'prompt_tokens':12,'completion_tokens':1}}).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            config=self.config()
            config['base_url']=f'http://127.0.0.1:{server.server_port}/v1'
            result,raw=run.call_model(config,'Good')
            self.assertEqual(result['generated_answer'],'positive')
            self.assertEqual(result['input_tokens'],12)
            self.assertEqual(captured[0][0],'/v1/chat/completions')
            self.assertEqual(captured[0][1]['messages'],run.build_messages('Good'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def config(self, fmt="chat"):
        return dict(provider="compatible", model="example", base_url="http://localhost:1234/v1",
                    api_format=fmt, api_key_env=None, temperature=0, max_tokens=256,
                    reasoning_effort=None, token_parameter="max_tokens", timeout=1)

    def test_request_formats_share_prompt(self):
        for fmt in ("chat", "responses", "ollama"):
            request=run.make_request(self.config(fmt), "Great")
            data=json.loads(request.data)
            self.assertEqual(data.get("input", data.get("messages")), run.build_messages("Great"))
            self.assertNotIn("label", data)
        c=self.config("responses"); c["temperature"]=None; c["reasoning_effort"]="low"
        data=json.loads(run.make_request(c, "Great").data)
        self.assertNotIn("temperature", data)
        self.assertEqual(data["reasoning"], {"effort":"low"})

    def test_chat_usage_and_truncation(self):
        raw={"choices":[{"message":{"content":"positive"}, "finish_reason":"stop"}],
             "usage":{"prompt_tokens":20,"completion_tokens":1}, "model":"resolved"}
        result=run.extract_response(raw,"chat")
        self.assertEqual((result["generated_answer"],result["input_tokens"],result["response_model"]),("positive",20,"resolved"))
        raw["choices"][0]["finish_reason"]="length"
        self.assertEqual(run.extract_response(raw,"chat")["error_type"],"truncated")

    def test_responses_refusal(self):
        raw={"status":"completed","output":[{"content":[{"type":"refusal","refusal":"No"}]}]}
        self.assertEqual(run.extract_response(raw,"responses")["error_type"],"refusal")

    def test_responses_text_and_missing_usage(self):
        raw={"status":"completed","output":[{"content":[{"type":"output_text","text":"neutral"}]}]}
        result=run.extract_response(raw,"responses")
        self.assertEqual(result["generated_answer"],"neutral")
        self.assertEqual(result["input_tokens"],"")

    def test_ollama_decoding_rate(self):
        raw={"message":{"content":"mixed"},"eval_count":2,"eval_duration":500000000}
        self.assertEqual(run.extract_response(raw,"ollama")["tokens_per_second"],4)

    def test_timeout_and_redacted_errors(self):
        with patch("run.urllib.request.urlopen",side_effect=TimeoutError("secret-value")):
            result,_=run.call_model(self.config(),"Good")
        self.assertEqual(result["error_type"],"timeout")
        self.assertNotIn("secret-value",result["error"])
        self.assertGreaterEqual(result["latency_ms"],0)
        with patch("run.urllib.request.urlopen",side_effect=HTTPError("secret-url",401,"secret-key",None,None)):
            result,_=run.call_model(self.config(),"Good")
        self.assertEqual(result["error"],"HTTP 401")

    def test_dataset_validation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"items.json"
            item={"id":"1","text":"Good","label":"positive"}
            path.write_text(json.dumps([item,item]))
            with self.assertRaises(ValueError): run.load_items(path)
            path.write_text(json.dumps([item]))
            self.assertEqual(run.load_items(path),[item])

    def write_rows(self, path):
        rows=[]
        for i,(answer,error,kind,latency) in enumerate([
                ("positive","","","10"),("positive!","","","20"),
                ("","timeout","timeout","30"),("","refused","refusal","40"),
                ("positive","cut","truncated","50"),("","failure","api_error","60")]):
            rows.append(dict(provider="test",model="test",item_id=str(i),text="Good",
                             reference_answer="positive",generated_answer=answer,error=error,
                             error_type=kind,latency_ms=latency,input_tokens="",output_tokens=""))
        with path.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        return rows

    def test_scoring_all_failures_and_no_rewrites(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"per_item_test.csv"; self.write_rows(path); before=path.read_bytes()
            result=score.score_file(path)
            self.assertEqual(result["correct"],1)
            for key in ("parse_errors","execution_errors","timeouts","refusals","truncations"):
                self.assertEqual(result[key],1)
            self.assertEqual(result["p50_latency_ms"],35)
            self.assertEqual(result["p95_latency_ms"],57.5)
            self.assertEqual(result["input_tokens"],"")
            self.assertEqual(path.read_bytes(),before)

    def test_partial_results_use_full_denominator(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"per_item_test.csv"; rows=self.write_rows(path)
            items=[{"id":str(i),"text":"Good","label":"positive"} for i in range(8)]
            result=score.score_file(path,items)
            self.assertEqual(result["missing_items"],2)
            self.assertEqual(result["accuracy"],1/8)
            items[0]["text"]="Changed"
            with self.assertRaises(ValueError): score.score_file(path,items)

    def test_runner_checkpoint_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as d:
            dataset=Path(d)/"items.json"
            items=[{"id":"1","text":"Good","label":"positive"}]
            dataset.write_text(json.dumps(items))
            result=run.extract_response({"choices":[{"message":{"content":"positive"},"finish_reason":"stop"}]},"chat")
            result["latency_ms"]=10
            with patch("run.call_model",return_value=(result,{"model":"test"})):
                self.assertEqual(run.run_provider(self.config(),items,Path(d),dataset),0)
                with self.assertRaises(FileExistsError): run.run_provider(self.config(),items,Path(d),dataset)
            meta=json.loads(next(Path(d).glob("*.meta.json")).read_text())
            self.assertEqual(meta["status"],"complete")
            self.assertEqual(meta["completed_items"],1)
            self.assertNotIn("reference_answer", next(Path(d).glob("*.raw.jsonl")).read_text())


if __name__ == "__main__":
    unittest.main()
