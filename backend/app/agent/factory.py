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

from app.agent.interpreter import MessageInterpreter
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


def _build_openai_model(settings: Settings, model_id: str) -> Any:
    from strands.models.openai import OpenAIModel

    if not settings.openai_api_key:
        raise LLMNotConfiguredError("OPENAI_API_KEY is not set — add it to backend/.env")
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
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY is not set — add it to backend/.env")
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


def load_system_prompt() -> str:
    """Interpreter prompt (baked into the image with the app package)."""
    return (Path(__file__).parent / "prompts" / "interpreter_v1.md").read_text(encoding="utf-8")


def build_interpreter(settings: Settings) -> MessageInterpreter | None:
    """Fail-closed entry point: `MessageInterpreter` or `None`.

    Never raises on the API path; never logs or returns a credential. A `None`
    result means the orchestrator answers with the deterministic parser.
    """
    if not settings.llm_enabled:
        logger.warning("llm_disabled", reason="provider is disabled")
        return None
    try:
        model = build_model(settings)
    except LLMNotConfiguredError as error:
        logger.warning("llm_disabled", reason=str(error))
        return None
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
    return MessageInterpreter(llm=client, confidence_threshold=settings.llm_confidence_threshold)


def describe_provider(settings: Settings) -> str:
    """One-line, secret-free provider/model description for structured logs."""
    return f"provider={_provider(settings)} model={resolve_model_id(settings)}"
