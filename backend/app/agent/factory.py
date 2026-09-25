"""LLM provider factory (ADR-004): builds the Strands model and the
`MessageInterpreter` from `Settings`, fail-closed.

Provider SDKs are imported lazily inside the functions, so the API boots
without any provider package installed. `build_interpreter()` never raises on
the API path: when the provider is disabled, a credential is missing or the
SDK is absent it returns `None` and the orchestrator degrades to the
deterministic parser (spec §9.3). Strands is imported only here and in
`app.agent.llm` (ADR-002 boundary); the agent runs WITHOUT tools — the LLM
interprets language, it never mutates state.
"""

from pathlib import Path
from typing import Any

import structlog

from app.agent.interpreter import PROMPT_VERSION, MessageInterpreter
from app.core.config import Settings

logger = structlog.get_logger(__name__)

# USD per 1K tokens (provider defaults; overridable via Settings).
PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
    "bedrock": "eu.anthropic.claude-haiku-4-5-v1:0",
}

PROVIDER_DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "openai": {"input": 0.00015, "output": 0.0006},
    "anthropic": {"input": 0.0008, "output": 0.004},
    "bedrock": {"input": 0.0008, "output": 0.004},
}

# Settings attribute and environment variable holding each provider credential.
_CREDENTIAL_SETTINGS: dict[str, str] = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
}
_CREDENTIAL_ENV_VARS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class LLMNotConfiguredError(Exception):
    """Raised when the provider cannot be built (missing credential, unknown
    provider). The message names the missing environment variable."""


def _provider(settings: Settings) -> str:
    return settings.llm_provider.strip().lower()


def resolve_model_id(settings: Settings) -> str:
    """Configured model id, or the provider default for empty/unknown values."""
    if settings.llm_model_interpreter:
        return settings.llm_model_interpreter
    return PROVIDER_DEFAULT_MODELS.get(_provider(settings), PROVIDER_DEFAULT_MODELS["openai"])


def resolve_price(settings: Settings) -> dict[str, float]:
    """Per-1K USD prices: provider default, overridable per direction when > 0."""
    price = dict(
        PROVIDER_DEFAULT_PRICES.get(_provider(settings), PROVIDER_DEFAULT_PRICES["openai"])
    )
    if settings.llm_price_input_per_1k > 0.0:
        price["input"] = settings.llm_price_input_per_1k
    if settings.llm_price_output_per_1k > 0.0:
        price["output"] = settings.llm_price_output_per_1k
    return price


def _missing_credential_reason(settings: Settings) -> str:
    """Secret-free reason naming the missing credential variable."""
    var = _CREDENTIAL_ENV_VARS.get(_provider(settings))
    if var is None:
        return f"Unknown llm_provider {_provider(settings)!r}"
    return f"{var} is not set — add it to backend/.env"


def is_provider_configured(settings: Settings) -> bool:
    """Pure configuration check (ADR-004): provider enabled **and** its
    credential present. Constructs nothing and performs no network call — the
    single source of truth for "is the LLM path usable" (spec §9.3).
    """
    if not settings.llm_enabled:
        return False
    provider = _provider(settings)
    if provider == "bedrock":
        return True  # AWS credentials come from the instance role (ADR-004)
    attr = _CREDENTIAL_SETTINGS.get(provider)
    return bool(attr is not None and getattr(settings, attr))


def _build_openai_model(settings: Settings, model_id: str) -> Any:
    from strands.models.openai import OpenAIModel

    if not settings.openai_api_key:
        raise LLMNotConfiguredError(_missing_credential_reason(settings))
    client_args: dict[str, str] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_args["base_url"] = settings.openai_base_url
    return OpenAIModel(
        model_id=model_id,
        params={"max_tokens": settings.llm_max_tokens, "temperature": settings.llm_temperature},
        client_args=client_args,
    )


def _build_anthropic_model(settings: Settings, model_id: str) -> Any:
    # Signature verified for strands 1.56.0: AnthropicModel takes client_args
    # (it builds its own AsyncAnthropic client); max_tokens/model_id are
    # required config keys, temperature rides in params.
    from strands.models.anthropic import AnthropicModel

    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError(_missing_credential_reason(settings))
    return AnthropicModel(
        model_id=model_id,
        max_tokens=settings.llm_max_tokens,
        params={"temperature": settings.llm_temperature},
        client_args={"api_key": settings.anthropic_api_key},
    )


def _build_bedrock_model(settings: Settings, model_id: str) -> Any:
    # Signature verified (strands 1.56.0): BedrockModel takes keyword-only
    # region_name plus flat model_config keys (model_id, temperature, max_tokens).
    # Credentials come from the instance role; never exercised in unit tests.
    from strands.models.bedrock import BedrockModel

    return BedrockModel(
        model_id=model_id,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        region_name=settings.aws_region,
    )


def build_model(settings: Settings) -> Any:
    """Build the Strands model for the configured provider."""
    provider = _provider(settings)
    model_id = resolve_model_id(settings)
    builders = {
        "openai": _build_openai_model,
        "anthropic": _build_anthropic_model,
        "bedrock": _build_bedrock_model,
    }
    builder = builders.get(provider)
    if builder is None:
        raise LLMNotConfiguredError(
            f"Unknown llm_provider {provider!r} — expected: {', '.join(sorted(builders))}, none"
        )
    return builder(settings, model_id)


def load_system_prompt(version: str = PROMPT_VERSION) -> str:
    """Interpreter prompt (baked into the image with the app package).

    Prompt edits ship as a new versioned file: the version is recorded on every
    interpretation, so a quality change is always attributable to a prompt.
    """
    return (Path(__file__).parent / "prompts" / f"{version}.md").read_text(encoding="utf-8")


def build_interpreter(settings: Settings) -> MessageInterpreter | None:
    """Fail-closed entry point: `MessageInterpreter` or `None`.

    Never raises on the API path; never logs or returns a credential. A `None`
    result means the orchestrator answers with the deterministic parser.
    """
    if not is_provider_configured(settings):
        reason = (
            "provider is disabled"
            if not settings.llm_enabled
            else _missing_credential_reason(settings)
        )
        logger.warning("llm_disabled", reason=reason)
        return None
    try:
        model = build_model(settings)
    except (ImportError, ModuleNotFoundError):
        logger.warning("llm_disabled", reason="provider SDK is not installed")
        return None

    from strands import Agent

    from app.agent.llm import StrandsLLMClient
    from app.agent.schemas import Interpretation

    model_id = resolve_model_id(settings)
    client = StrandsLLMClient(
        agent_factory=lambda: Agent(
            model=model,
            system_prompt=load_system_prompt(),
            structured_output_model=Interpretation,
            callback_handler=None,
        ),
        timeout_seconds=settings.llm_timeout_seconds,
        model_id=model_id,
        price_per_1k=resolve_price(settings),
    )
    return MessageInterpreter(
        llm=client,
        prompt_version=PROMPT_VERSION,
        confidence_threshold=settings.llm_confidence_threshold,
    )


def describe_provider(settings: Settings) -> str:
    """One-line, secret-free provider/model description for structured logs."""
    return f"provider={_provider(settings)} model={resolve_model_id(settings)}"
