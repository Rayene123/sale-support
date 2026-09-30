"""Configuration resolution for the evaluation harness.

Precedence, highest first:

1. explicit command line options
2. process environment (``SYSTEM_*`` / ``JUDGE_*`` / ``HARNESS_*``)
3. ``harness/.env`` (local, git-ignored)

Only the *name* of an API-key variable is ever written to a run's
``metadata.json``; the value stays in memory and is sent to the provider.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigurationError

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = Path(__file__).resolve().parent / ".env"
DEFAULT_RESULTS_ROOT = PROJECT / "results" / "harness"

PROVIDERS = ("ollama", "openai")
DEFAULT_BASE_URL = {
    "ollama": "http://localhost:11434",
    "openai": "https://api.groq.com/openai/v1",
}
DEFAULT_MODELS = {
    "ollama": "qwen2.5:14b",
    "openai": "openai/gpt-oss-20b",
}


def read_env_file(path):
    """Parse a ``NAME=value`` file. Unreadable or malformed lines are errors."""
    values = {}
    if not path or not Path(path).exists():
        return values
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            raise ConfigurationError(f"{path}:{number}: expected NAME=value")
        values[key.strip()] = value.strip().strip("\"'")
    return values


@dataclass(frozen=True)
class SystemConfig:
    """How the evaluated customer-support system is called."""

    provider: str = "ollama"
    model: str = DEFAULT_MODELS["ollama"]
    base_url: str = ""
    api_key_env: str = ""
    temperature: float = 0.0
    max_tokens: int = 512
    timeout: float = 300.0
    prompt_version: str = "v1"

    def __post_init__(self):
        # A hosted provider must not silently inherit the local base URL.
        if not self.base_url:
            object.__setattr__(self, "base_url", DEFAULT_BASE_URL.get(self.provider, ""))

    @property
    def priced(self):
        """Local inference has no API price; hosted providers do."""
        return self.provider != "ollama"

    def to_record(self):
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env or None,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout,
            "prompt_version": self.prompt_version,
        }


@dataclass(frozen=True)
class JudgeConfig:
    """How Person 3's judge is called. The key value is never serialised."""

    provider: str = "ollama"
    model: str = DEFAULT_MODELS["ollama"]
    base_url: str = DEFAULT_BASE_URL["ollama"]
    api_key: str = ""
    timeout: float = 300.0
    max_tokens: int = 2048
    prompt_version: str = "judge_v2"

    def to_client_config(self):
        """Configuration mapping consumed by ``judge.client.Judge``."""
        config = {
            "JUDGE_PROVIDER": self.provider,
            "JUDGE_MODEL": self.model,
            "JUDGE_BASE_URL": self.base_url,
            "JUDGE_API_KEY": self.api_key,
            "JUDGE_TIMEOUT": str(self.timeout),
            "JUDGE_MAX_TOKENS": str(self.max_tokens),
            "JUDGE_PROMPT_VERSION": self.prompt_version,
        }
        return config

    def to_record(self):
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
            "timeout_seconds": self.timeout,
            "max_tokens": self.max_tokens,
            "prompt_version": self.prompt_version,
        }


@dataclass(frozen=True)
class PricingConfig:
    """USD per 1,000,000 tokens. ``None`` means "not configured", not zero."""

    system_input_per_m: float = None
    system_output_per_m: float = None
    judge_input_per_m: float = None
    judge_output_per_m: float = None
    local_cost_per_hour: float = None
    currency: str = "USD"

    def system_configured(self):
        return self.system_input_per_m is not None and self.system_output_per_m is not None

    def judge_configured(self):
        return self.judge_input_per_m is not None and self.judge_output_per_m is not None

    def to_record(self):
        return {
            "currency": self.currency,
            "system_input_per_million_tokens": self.system_input_per_m,
            "system_output_per_million_tokens": self.system_output_per_m,
            "judge_input_per_million_tokens": self.judge_input_per_m,
            "judge_output_per_million_tokens": self.judge_output_per_m,
            "local_compute_cost_per_hour": self.local_cost_per_hour,
            "note": "Prices are operator-supplied estimates in USD per million "
                    "tokens; verify against the provider's current price list. "
                    "local_compute_cost_per_hour is an assumption, not a tariff.",
        }


@dataclass(frozen=True)
class HarnessConfig:
    system: SystemConfig = field(default_factory=SystemConfig)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    pricing: PricingConfig = field(default_factory=PricingConfig)
    results_root: Path = DEFAULT_RESULTS_ROOT
    run_id: str = ""
    env_file: Path = DEFAULT_ENV_FILE

    def to_record(self):
        return {
            "system": self.system.to_record(),
            "judge": self.judge.to_record(),
            "pricing": self.pricing.to_record(),
            "results_root": str(self.results_root),
            "env_file": str(self.env_file) if Path(self.env_file).exists() else None,
            "note": "API-key values are never written to results; only the "
                    "variable name (system.api_key_env) is recorded.",
        }


def _number(raw, name, cast, default):
    if raw in (None, ""):
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        raise ConfigurationError(f"{name} must be numeric, got {raw!r}") from None


def _text(raw, default=""):
    return default if raw in (None, "") else str(raw).strip()


def resolve_config(overrides=None, env_file=DEFAULT_ENV_FILE):
    """Build a :class:`HarnessConfig` from file, environment, and overrides."""
    values = read_env_file(env_file)
    values.update({k: v for k, v in os.environ.items()
                   if k.startswith(("HARNESS_", "SYSTEM_", "JUDGE_"))})
    for key, value in (overrides or {}).items():
        if value not in (None, ""):
            values[key] = value

    system_provider = _text(values.get("SYSTEM_PROVIDER"), "ollama").lower()
    if system_provider not in PROVIDERS:
        raise ConfigurationError(
            f"SYSTEM_PROVIDER must be one of {', '.join(PROVIDERS)}; got {system_provider!r}")
    system_key_env = _text(values.get("SYSTEM_API_KEY_ENV"))

    system = SystemConfig(
        provider=system_provider,
        model=_text(values.get("SYSTEM_MODEL"), DEFAULT_MODELS[system_provider]),
        base_url=_text(values.get("SYSTEM_BASE_URL"),
                       DEFAULT_BASE_URL[system_provider]).rstrip("/"),
        api_key_env=system_key_env,
        temperature=_number(values.get("SYSTEM_TEMPERATURE"), "SYSTEM_TEMPERATURE", float, 0.0),
        max_tokens=_number(values.get("SYSTEM_MAX_TOKENS"), "SYSTEM_MAX_TOKENS", int, 512),
        timeout=_number(values.get("SYSTEM_TIMEOUT"), "SYSTEM_TIMEOUT", float, 300.0),
        prompt_version=_text(values.get("SYSTEM_PROMPT_VERSION"), "v1"),
    )
    if not system.model:
        raise ConfigurationError("SYSTEM_MODEL must not be empty")
    if system.max_tokens < 1 or system.timeout <= 0:
        raise ConfigurationError("SYSTEM_MAX_TOKENS and SYSTEM_TIMEOUT must be positive")
    if system.priced and not system.api_key_env:
        raise ConfigurationError(
            "A hosted system provider needs SYSTEM_API_KEY_ENV naming the "
            "environment variable that holds the key (for example GROQ_API_KEY)")

    judge_provider = _text(values.get("JUDGE_PROVIDER"), "ollama").lower()
    if judge_provider not in ("ollama", "groq"):
        raise ConfigurationError(
            f"JUDGE_PROVIDER must be ollama or groq; got {judge_provider!r}")
    judge_key = _text(values.get("JUDGE_API_KEY"))
    if judge_provider == "groq" and not judge_key:
        raise ConfigurationError("JUDGE_PROVIDER=groq requires JUDGE_API_KEY")

    judge = JudgeConfig(
        provider=judge_provider,
        model=_text(values.get("JUDGE_MODEL"), "qwen3:14b" if judge_provider == "ollama" else "openai/gpt-oss-20b"),
        base_url=_text(values.get("JUDGE_BASE_URL"),
                       "http://localhost:11434" if judge_provider == "ollama"
                       else "https://api.groq.com/openai/v1").rstrip("/"),
        api_key=judge_key,
        timeout=_number(values.get("JUDGE_TIMEOUT"), "JUDGE_TIMEOUT", float, 300.0),
        max_tokens=_number(values.get("JUDGE_MAX_TOKENS"), "JUDGE_MAX_TOKENS", int, 2048),
        prompt_version=_text(values.get("JUDGE_PROMPT_VERSION"), "judge_v2"),
    )

    pricing = PricingConfig(
        system_input_per_m=_number(values.get("SYSTEM_INPUT_PRICE_PER_M"), "SYSTEM_INPUT_PRICE_PER_M", float, None),
        system_output_per_m=_number(values.get("SYSTEM_OUTPUT_PRICE_PER_M"), "SYSTEM_OUTPUT_PRICE_PER_M", float, None),
        judge_input_per_m=_number(values.get("JUDGE_INPUT_PRICE_PER_M"), "JUDGE_INPUT_PRICE_PER_M", float, None),
        judge_output_per_m=_number(values.get("JUDGE_OUTPUT_PRICE_PER_M"), "JUDGE_OUTPUT_PRICE_PER_M", float, None),
        local_cost_per_hour=_number(values.get("HARNESS_LOCAL_COST_PER_HOUR"), "HARNESS_LOCAL_COST_PER_HOUR", float, None),
        currency=_text(values.get("HARNESS_CURRENCY"), "USD"),
    )

    return HarnessConfig(
        system=system,
        judge=judge,
        pricing=pricing,
        results_root=Path(_text(values.get("HARNESS_RESULTS_ROOT"), str(DEFAULT_RESULTS_ROOT))),
        run_id=_text(values.get("HARNESS_RUN_ID")),
        env_file=env_file,
    )


def system_api_key(system_config):
    """Read the key value at call time. The value is never logged or saved."""
    if not system_config.api_key_env:
        return ""
    value = os.environ.get(system_config.api_key_env, "").strip()
    if not value:
        raise ConfigurationError(
            f"{system_config.api_key_env} is not set; the hosted system provider "
            "cannot be called without it")
    return value
