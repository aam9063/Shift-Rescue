"""Provider factory tests (hermetic: no network, no real key, no AWS)."""

import base64
import sys

import pytest
from structlog.testing import capture_logs

import app.agent.factory as factory_module
from app.agent.factory import (
    PROVIDER_DEFAULT_MODELS,
    PROVIDER_DEFAULT_PRICES,
    LLMNotConfiguredError,
    build_interpreter,
    describe_provider,
    resolve_model_id,
    resolve_price,
)
from app.agent.llm import StrandsLLMClient
from app.core.config import Settings

LLM_ENV_VARS = (
    "LLM_PROVIDER",
    "LLM_MODEL_INTERPRETER",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY",
    "LLM_PRICE_INPUT_PER_1K",
    "LLM_PRICE_OUTPUT_PER_1K",
)


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    """Keep host environment LLM variables out of these unit tests."""
    for name in LLM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {"_env_file": None}
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# --- provider defaults and overrides -----------------------------------------


@pytest.mark.parametrize("provider", ["openai", "anthropic", "bedrock"])
def test_resolve_model_id_uses_provider_defaults(provider: str) -> None:
    settings = make_settings(llm_provider=provider)
    assert resolve_model_id(settings) == PROVIDER_DEFAULT_MODELS[provider]


def test_resolve_model_id_env_override_wins() -> None:
    settings = make_settings(llm_model_interpreter="my-custom-model")
    assert resolve_model_id(settings) == "my-custom-model"


def test_resolve_model_id_unknown_provider_falls_back_to_openai_default() -> None:
    settings = make_settings(llm_provider="mistral")
    assert resolve_model_id(settings) == PROVIDER_DEFAULT_MODELS["openai"]


@pytest.mark.parametrize("provider", ["openai", "anthropic", "bedrock"])
def test_resolve_price_uses_provider_defaults(provider: str) -> None:
    settings = make_settings(llm_provider=provider)
    assert resolve_price(settings) == PROVIDER_DEFAULT_PRICES[provider]


def test_resolve_price_env_overrides_apply_only_when_positive() -> None:
    settings = make_settings(llm_price_input_per_1k=0.002, llm_price_output_per_1k=0.0)
    price = resolve_price(settings)
    assert price["input"] == 0.002
    assert price["output"] == PROVIDER_DEFAULT_PRICES["openai"]["output"]


# --- build_interpreter: fail-closed paths ------------------------------------


def test_build_interpreter_returns_none_when_provider_disabled() -> None:
    settings = make_settings(llm_provider="none", openai_api_key="test-key")
    with capture_logs() as logs:
        assert build_interpreter(settings) is None
    assert len(logs) == 1
    assert logs[0]["event"] == "llm_disabled"
    assert logs[0]["reason"] == "provider is disabled"
    assert "warning" in logs[0].values()


def test_build_interpreter_returns_none_when_openai_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = make_settings(llm_provider="openai")
    with capture_logs() as logs:
        assert build_interpreter(settings) is None
    assert len(logs) == 1
    assert logs[0]["event"] == "llm_disabled"
    assert "OPENAI_API_KEY" in logs[0]["reason"]


def test_build_interpreter_returns_none_when_provider_sdk_missing(monkeypatch) -> None:
    # A None entry in sys.modules makes the import raise ImportError.
    monkeypatch.setitem(sys.modules, "strands.models.openai", None)
    settings = make_settings(llm_provider="openai", openai_api_key="test-key")
    with capture_logs() as logs:
        assert build_interpreter(settings) is None
    assert len(logs) == 1
    assert logs[0]["event"] == "llm_disabled"
    assert logs[0]["reason"] == "provider SDK is not installed"
    assert "warning" in logs[0].values()


def test_build_model_raises_for_unknown_provider() -> None:
    with pytest.raises(LLMNotConfiguredError, match="Unknown llm_provider"):
        factory_module.build_model(make_settings(llm_provider="mistral", openai_api_key="test-key"))


# --- build_interpreter: happy path (model construction stubbed) --------------


class StubModel:
    pass


def test_build_interpreter_returns_strands_client_with_model_and_price(monkeypatch) -> None:
    settings = make_settings(llm_provider="openai", openai_api_key="test-key")
    settings.llm_timeout_seconds = 7.5
    monkeypatch.setattr(factory_module, "build_model", lambda _settings: StubModel())

    with capture_logs():
        interpreter = build_interpreter(settings)

    assert interpreter is not None
    llm = interpreter._llm
    assert isinstance(llm, StrandsLLMClient)
    assert llm._model_id == PROVIDER_DEFAULT_MODELS["openai"]
    assert llm._price == PROVIDER_DEFAULT_PRICES["openai"]
    assert llm._timeout == 7.5
    assert interpreter.confidence_threshold == settings.llm_confidence_threshold


# --- no secret leaks ---------------------------------------------------------


def test_describe_provider_never_contains_the_key() -> None:
    description = describe_provider(make_settings(openai_api_key="super-secret-key"))
    assert "super-secret-key" not in description
    assert "provider=openai" in description
    assert PROVIDER_DEFAULT_MODELS["openai"] in description


def test_disabled_logs_never_contain_the_key() -> None:
    settings = make_settings(llm_provider="openai", openai_api_key="super-secret-key")
    with capture_logs() as logs:
        build_interpreter(settings)
    assert all("super-secret-key" not in str(entry) for entry in logs)


def test_traces_auth_header_is_base64_of_keys() -> None:
    settings = make_settings(langfuse_public_key="pk", langfuse_secret_key="sk")
    expected = "Basic " + base64.b64encode(b"pk:sk").decode()
    assert settings.traces_auth_header == expected
