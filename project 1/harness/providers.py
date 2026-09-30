"""Provider adapters for the evaluated customer-support system.

Only the standard library is used, matching the judge client. Two wire formats
are supported:

* ``ollama``   – local ``POST /api/chat``
* ``openai``   – ``POST {base_url}/chat/completions`` (Groq, vLLM, LM Studio,
                 or any OpenAI-compatible gateway)

Each item costs exactly one request: no tools, no agent loop, no retrieval.
Every failure is translated into a :class:`~harness.errors.SystemError` with a
stable category, and provider error bodies are never echoed (they can contain
credentials).
"""
import json
import time
import urllib.error
import urllib.request

from .config import SystemConfig, system_api_key
from .errors import ConfigurationError, SystemError


class SystemClient:
    """One model call per item, with latency, token usage, and error mapping."""

    def __init__(self, config, prompt_text=None):
        self.config = config
        self.prompt_text = prompt_text
        self.requests_made = 0

    # ------------------------------------------------------------------ setup
    def preflight(self):
        """Check that the configured provider can be reached before a long run.

        Returns a record describing the check. Raises for problems that make a
        run pointless (missing key, missing local model, unreachable server).
        """
        checks = []
        if self.prompt_text is None:
            raise SystemError("configuration", "A system prompt must be loaded before running")
        if self.config.provider == "ollama":
            checks.append(self._preflight_ollama())
        else:
            checks.append(self._preflight_openai())
        return {"provider": self.config.provider, "model": self.config.model,
                "base_url": self.config.base_url, "checks": checks}

    def _preflight_ollama(self):
        try:
            with urllib.request.urlopen(self.config.base_url + "/api/tags", timeout=15) as response:
                models = {entry.get("name") for entry in json.load(response).get("models", [])}
        except (OSError, ValueError, KeyError) as exc:
            raise SystemError("network",
                              f"Cannot reach local Ollama at {self.config.base_url}: {exc}") from None
        wanted = self.config.model
        if wanted not in models and not any(name.split(":")[0] == wanted.split(":")[0] for name in models):
            raise SystemError("model_missing",
                              f"Local model {wanted!r} is not installed; run: ollama pull {wanted}")
        return {"check": "ollama_tags", "ok": True, "installed_models": len(models)}

    def _preflight_openai(self):
        try:
            system_api_key(self.config)
        except Exception as exc:  # ConfigurationError, re-typed for the system phase
            raise SystemError("configuration", str(exc)) from None
        record = {"check": "openai_key", "ok": True, "key_env": self.config.api_key_env}
        request = urllib.request.Request(self.config.base_url + "/models",
                                         headers={"Authorization": "Bearer " + system_api_key(self.config)})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                listed = {entry.get("id") for entry in json.load(response).get("data", [])}
            record["models_listed"] = len(listed)
            record["model_listed"] = self.config.model in listed
        except (OSError, ValueError, KeyError) as exc:
            # A gateway may not expose /models. That is a warning, not a stop.
            record["models_endpoint"] = f"unavailable: {type(exc).__name__}"
        return record

    # ---------------------------------------------------------------- request
    def _build_request(self, user_message):
        messages = [{"role": "system", "content": self.prompt_text},
                    {"role": "user", "content": user_message}]
        if self.config.provider == "ollama":
            body = {"model": self.config.model, "messages": messages, "stream": False,
                    "think": False,  # reasoning tokens are not needed for this task
                    "options": {"temperature": self.config.temperature,
                                "num_predict": self.config.max_tokens}}
            endpoint = self.config.base_url + "/api/chat"
            headers = {"Content-Type": "application/json"}
        else:
            body = {"model": self.config.model, "messages": messages,
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens}
            endpoint = self.config.base_url + "/chat/completions"
            headers = {"Content-Type": "application/json"}
            if self.config.priced:
                headers["Authorization"] = "Bearer " + system_api_key(self.config)
        return endpoint, headers, body

    def generate(self, user_message):
        """Send exactly one request and return text, latency, usage, and raw body."""
        try:
            endpoint, headers, body = self._build_request(user_message)
        except ConfigurationError as exc:
            # A missing key is an item-level row, not a crash: one category for
            # the whole run is reported by the preflight instead.
            raise SystemError("configuration", str(exc)) from None
        request = urllib.request.Request(endpoint, data=json.dumps(body).encode("utf-8"), headers=headers)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                raw = json.load(response)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, metadata={"latency_ms": (time.perf_counter() - started) * 1000,
                                                   "http_status": exc.code}) from None
        except TimeoutError:
            raise SystemError("timeout", f"No answer within {self.config.timeout:g}s",
                              {"latency_ms": (time.perf_counter() - started) * 1000}) from None
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError):
                raise SystemError("timeout", f"No answer within {self.config.timeout:g}s") from None
            raise SystemError("network", f"Request failed ({type(reason).__name__}); no retry was made") from None
        except (ValueError, UnicodeError):
            raise SystemError("api_error", "Provider returned a body that is not valid JSON") from None
        latency_ms = (time.perf_counter() - started) * 1000
        self.requests_made += 1
        return self._parse(raw, latency_ms)

    def _http_error(self, exc, metadata=None):
        metadata = metadata or {}
        status = getattr(exc, "code", None)
        if self.config.provider == "ollama" and status == 404:
            return SystemError("model_missing",
                               f"Local model {self.config.model!r} is missing; "
                               f"install it with: ollama pull {self.config.model}", metadata)
        if status in (401, 403):
            return SystemError("api_error",
                               f"Provider rejected the request (HTTP {status}); check "
                               f"${self.config.api_key_env} and model access.", metadata)
        if status == 429:
            return SystemError("api_error",
                               "Provider rate limit reached (HTTP 429); no retry was made.", metadata)
        return SystemError("api_error", f"Provider returned HTTP {status}.", metadata)

    def _parse(self, raw, latency_ms):
        if not isinstance(raw, dict):
            raise SystemError("api_error", "Provider returned an unexpected payload type")
        if self.config.provider == "ollama":
            if not raw.get("done", True):
                raise SystemError("incomplete_output", "Response did not finish normally.",
                                  {"latency_ms": latency_ms, "done_reason": raw.get("done_reason")})
            message = raw.get("message") or {}
            text = message.get("content")
            usage = {"prompt": raw.get("prompt_eval_count"),
                     "completion": raw.get("eval_count"),
                     "total": (raw.get("prompt_eval_count") or 0) + (raw.get("eval_count") or 0) or None}
            decode_rate = None
            if raw.get("eval_count") and raw.get("eval_duration"):
                decode_rate = raw["eval_count"] / (raw["eval_duration"] / 1e9)
        else:
            choices = raw.get("choices") or []
            if not choices:
                raise SystemError("api_error", "Provider returned no choices")
            choice = choices[0]
            if choice.get("finish_reason") in ("length", "content_filter"):
                raise SystemError("incomplete_output",
                                  f"Response stopped early (finish_reason={choice.get('finish_reason')}).",
                                  {"latency_ms": latency_ms})
            if (choice.get("message") or {}).get("refusal"):
                raise SystemError("refusal", "The model declined to answer.", {"latency_ms": latency_ms})
            text = (choice.get("message") or {}).get("content")
            reported = raw.get("usage") or {}
            usage = {"prompt": reported.get("prompt_tokens"),
                     "completion": reported.get("completion_tokens"),
                     "total": reported.get("total_tokens")}
            decode_rate = None
        if not isinstance(text, str) or not text.strip():
            raise SystemError("system_error", "The system returned an empty reply.", {"latency_ms": latency_ms})
        return {"text": text, "latency_ms": latency_ms, "usage": usage,
                "response_model": raw.get("model"), "raw_response": raw,
                "decode_tokens_per_second": decode_rate}


def system_client(config, prompt_text):
    return SystemClient(config, prompt_text)


__all__ = ["SystemClient", "SystemError", "system_client", "SystemConfig"]
