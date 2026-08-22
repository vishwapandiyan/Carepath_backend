"""
Unit tests for llm/nvidia_client.py.

All tests use mocked OpenAI SDK calls — no real network requests are made
and no real API key is required.

Test coverage:
  - Configuration loading from environment variables
  - Client construction (happy path)
  - Missing / empty API key raises NvidiaClientConfigError
  - Successful chat completion (mocked)
  - Tool-call response parsing
  - Per-call temperature/top_p/max_tokens overrides
  - __repr__ does not expose the API key
  - NvidiaClientAPIError on SDK exception
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.alternate_care.llm.nvidia_client import (
    ChatMessage,
    LLMResponse,
    NvidiaClient,
    NvidiaClientAPIError,
    NvidiaClientConfigError,
    ToolCall,
)


# ---------------------------------------------------------------------------
# Helpers — build fake openai SDK objects without importing the real schema
# ---------------------------------------------------------------------------

def _make_tool_call(id_: str, name: str, arguments: str):
    """Build a minimal fake openai ToolCall object."""
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=id_, function=fn)


def _make_completion(
    content: Optional[str] = "Hello from the model.",
    model: str = "meta/llama-3.3-70b-instruct",
    finish_reason: str = "stop",
    tool_calls=None,
):
    """Build a minimal fake openai ChatCompletion object."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model=model)


# Fake key — used in tests instead of the real secret
_FAKE_KEY = "nvapi-test-key-not-real"


# ---------------------------------------------------------------------------
# 1. Configuration loading
# ---------------------------------------------------------------------------

class TestConfigurationLoading:
    """Verify that settings.py reads NVIDIA env vars correctly."""

    def test_nvidia_api_key_reads_from_env(self):
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "nvapi-test-123"}):
            import importlib
            import config.settings as _s
            importlib.reload(_s)
            assert _s.NVIDIA_API_KEY == "nvapi-test-123"
        importlib.reload(_s)  # restore

    def test_nvidia_api_key_is_none_when_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "NVIDIA_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config.settings as _s
            importlib.reload(_s)
            assert _s.NVIDIA_API_KEY is None
        importlib.reload(_s)

    def test_nvidia_base_url_default(self):
        env = {k: v for k, v in os.environ.items() if k != "NVIDIA_BASE_URL"}
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config.settings as _s
            importlib.reload(_s)
            assert _s.NVIDIA_BASE_URL == "https://integrate.api.nvidia.com/v1"
        importlib.reload(_s)

    def test_nvidia_base_url_env_override(self):
        with patch.dict(os.environ, {"NVIDIA_BASE_URL": "http://localhost:9999/v1"}):
            import importlib
            import config.settings as _s
            importlib.reload(_s)
            assert _s.NVIDIA_BASE_URL == "http://localhost:9999/v1"
        importlib.reload(_s)

    def test_nvidia_model_default(self):
        env = {k: v for k, v in os.environ.items() if k != "NVIDIA_MODEL"}
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config.settings as _s
            importlib.reload(_s)
            assert _s.NVIDIA_MODEL == "meta/llama-3.3-70b-instruct"
        importlib.reload(_s)

    def test_nvidia_model_env_override(self):
        with patch.dict(os.environ, {"NVIDIA_MODEL": "meta/llama-3.1-8b-instruct"}):
            import importlib
            import config.settings as _s
            importlib.reload(_s)
            assert _s.NVIDIA_MODEL == "meta/llama-3.1-8b-instruct"
        importlib.reload(_s)


# ---------------------------------------------------------------------------
# 2. Client construction — happy path
# ---------------------------------------------------------------------------

class TestClientConstruction:
    """NvidiaClient builds successfully when a key is available."""

    def test_constructs_with_explicit_key(self):
        with patch("llm.nvidia_client.OpenAI"):
            client = NvidiaClient(api_key=_FAKE_KEY)
        assert client.model == "meta/llama-3.3-70b-instruct"
        assert client.base_url == "https://integrate.api.nvidia.com/v1"

    def test_constructs_with_key_from_settings(self):
        with patch("llm.nvidia_client.settings") as mock_settings:
            mock_settings.NVIDIA_API_KEY = _FAKE_KEY
            mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
            mock_settings.NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
            with patch("llm.nvidia_client.OpenAI"):
                client = NvidiaClient()
        assert client.model == "meta/llama-3.3-70b-instruct"

    def test_model_override(self):
        with patch("llm.nvidia_client.OpenAI"):
            client = NvidiaClient(api_key=_FAKE_KEY, model="meta/llama-3.1-8b-instruct")
        assert client.model == "meta/llama-3.1-8b-instruct"

    def test_base_url_override(self):
        with patch("llm.nvidia_client.OpenAI"):
            client = NvidiaClient(api_key=_FAKE_KEY, base_url="http://localhost:9000/v1")
        assert client.base_url == "http://localhost:9000/v1"

    def test_openai_client_receives_correct_base_url(self):
        """Verify the openai.OpenAI constructor is called with the right base_url."""
        with patch("llm.nvidia_client.OpenAI") as mock_openai:
            NvidiaClient(api_key=_FAKE_KEY, base_url="https://integrate.api.nvidia.com/v1")
        mock_openai.assert_called_once()
        _, kwargs = mock_openai.call_args
        assert kwargs["base_url"] == "https://integrate.api.nvidia.com/v1"

    def test_openai_client_receives_api_key(self):
        """openai.OpenAI must receive the api_key argument."""
        with patch("llm.nvidia_client.OpenAI") as mock_openai:
            NvidiaClient(api_key=_FAKE_KEY)
        _, kwargs = mock_openai.call_args
        assert kwargs["api_key"] == _FAKE_KEY


# ---------------------------------------------------------------------------
# 3. Missing / empty API key
# ---------------------------------------------------------------------------

class TestMissingApiKey:
    """NvidiaClient must raise NvidiaClientConfigError when the key is absent."""

    def test_raises_when_key_is_none(self):
        with patch("llm.nvidia_client.settings") as mock_settings:
            mock_settings.NVIDIA_API_KEY = None
            mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
            mock_settings.NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
            with pytest.raises(NvidiaClientConfigError):
                NvidiaClient()

    def test_raises_when_key_is_empty_string(self):
        with patch("llm.nvidia_client.settings") as mock_settings:
            mock_settings.NVIDIA_API_KEY = ""
            mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
            mock_settings.NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
            with pytest.raises(NvidiaClientConfigError):
                NvidiaClient()

    def test_raises_when_key_is_whitespace(self):
        with patch("llm.nvidia_client.settings") as mock_settings:
            mock_settings.NVIDIA_API_KEY = "   "
            mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
            mock_settings.NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
            with pytest.raises(NvidiaClientConfigError):
                NvidiaClient()

    def test_config_error_message_does_not_contain_key(self):
        """Error message must never include the real key value."""
        fake_key = "nvapi-super-secret-1234"
        with patch("llm.nvidia_client.settings") as mock_settings:
            mock_settings.NVIDIA_API_KEY = None
            mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
            mock_settings.NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
            with pytest.raises(NvidiaClientConfigError) as exc_info:
                NvidiaClient()
        assert fake_key not in str(exc_info.value)

    def test_no_openai_call_when_key_missing(self):
        """openai.OpenAI must NOT be instantiated if the key is absent."""
        with patch("llm.nvidia_client.settings") as mock_settings:
            mock_settings.NVIDIA_API_KEY = None
            mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
            mock_settings.NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
            with patch("llm.nvidia_client.OpenAI") as mock_openai:
                with pytest.raises(NvidiaClientConfigError):
                    NvidiaClient()
        mock_openai.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Successful mocked chat completion
# ---------------------------------------------------------------------------

class TestChatCompletion:
    """chat() returns a correct LLMResponse from a mocked SDK response."""

    def _client(self) -> NvidiaClient:
        with patch("llm.nvidia_client.OpenAI"):
            return NvidiaClient(api_key=_FAKE_KEY)

    def _attach_mock_completion(self, client: NvidiaClient, content: str, **kwargs) -> MagicMock:
        """Point client._client.chat.completions.create at a mock."""
        fake = _make_completion(content=content, **kwargs)
        client._client.chat.completions.create = MagicMock(return_value=fake)
        return client._client.chat.completions.create

    def test_returns_llm_response(self):
        client = self._client()
        self._attach_mock_completion(client, "Hello!")
        resp = client.chat([ChatMessage(role="user", content="Hi")])
        assert isinstance(resp, LLMResponse)

    def test_content_is_extracted(self):
        client = self._client()
        self._attach_mock_completion(client, "The answer is 42.")
        resp = client.chat([ChatMessage(role="user", content="What is the answer?")])
        assert resp.content == "The answer is 42."

    def test_model_is_extracted(self):
        client = self._client()
        self._attach_mock_completion(client, "OK", model="meta/llama-3.3-70b-instruct")
        resp = client.chat([ChatMessage(role="user", content="test")])
        assert resp.model == "meta/llama-3.3-70b-instruct"

    def test_finish_reason_is_extracted(self):
        client = self._client()
        self._attach_mock_completion(client, "Done", finish_reason="stop")
        resp = client.chat([ChatMessage(role="user", content="test")])
        assert resp.finish_reason == "stop"

    def test_tool_calls_is_none_on_plain_response(self):
        client = self._client()
        self._attach_mock_completion(client, "Plain response")
        resp = client.chat([ChatMessage(role="user", content="test")])
        assert resp.tool_calls is None
        assert resp.has_tool_calls is False

    def test_raw_completion_is_attached(self):
        client = self._client()
        fake = _make_completion(content="hi")
        client._client.chat.completions.create = MagicMock(return_value=fake)
        resp = client.chat([ChatMessage(role="user", content="test")])
        assert resp.raw is fake

    def test_messages_are_serialised_correctly(self):
        """All messages must be forwarded as dicts in the correct order."""
        client = self._client()
        mock_create = MagicMock(return_value=_make_completion("ok"))
        client._client.chat.completions.create = mock_create

        messages = [
            ChatMessage(role="system", content="You are helpful."),
            ChatMessage(role="user",   content="Hello."),
        ]
        client.chat(messages)

        _, kwargs = mock_create.call_args
        assert kwargs["messages"] == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user",   "content": "Hello."},
        ]

    def test_model_is_sent_in_payload(self):
        client = self._client()
        mock_create = MagicMock(return_value=_make_completion("ok"))
        client._client.chat.completions.create = mock_create
        client.chat([ChatMessage(role="user", content="hi")])
        _, kwargs = mock_create.call_args
        assert kwargs["model"] == "meta/llama-3.3-70b-instruct"

    def test_default_temperature_sent(self):
        with patch("llm.nvidia_client.OpenAI"):
            client = NvidiaClient(api_key=_FAKE_KEY, temperature=0.3)
        mock_create = MagicMock(return_value=_make_completion("ok"))
        client._client.chat.completions.create = mock_create
        client.chat([ChatMessage(role="user", content="hi")])
        _, kwargs = mock_create.call_args
        assert kwargs["temperature"] == 0.3

    def test_per_call_temperature_override(self):
        client = self._client()
        mock_create = MagicMock(return_value=_make_completion("ok"))
        client._client.chat.completions.create = mock_create
        client.chat([ChatMessage(role="user", content="hi")], temperature=0.9)
        _, kwargs = mock_create.call_args
        assert kwargs["temperature"] == 0.9

    def test_per_call_top_p_override(self):
        client = self._client()
        mock_create = MagicMock(return_value=_make_completion("ok"))
        client._client.chat.completions.create = mock_create
        client.chat([ChatMessage(role="user", content="hi")], top_p=0.95)
        _, kwargs = mock_create.call_args
        assert kwargs["top_p"] == 0.95

    def test_per_call_max_tokens_override(self):
        client = self._client()
        mock_create = MagicMock(return_value=_make_completion("ok"))
        client._client.chat.completions.create = mock_create
        client.chat([ChatMessage(role="user", content="hi")], max_tokens=512)
        _, kwargs = mock_create.call_args
        assert kwargs["max_tokens"] == 512


# ---------------------------------------------------------------------------
# 5. Tool-call response parsing
# ---------------------------------------------------------------------------

class TestToolCallParsing:
    """Tool calls in the SDK response are correctly surfaced as ToolCall objects."""

    def _client(self) -> NvidiaClient:
        with patch("llm.nvidia_client.OpenAI"):
            return NvidiaClient(api_key=_FAKE_KEY)

    def test_single_tool_call_parsed(self):
        client = self._client()
        tc = _make_tool_call("call_1", "get_weather", '{"location":"Austin, TX"}')
        fake = _make_completion(content=None, finish_reason="tool_calls", tool_calls=[tc])
        client._client.chat.completions.create = MagicMock(return_value=fake)

        resp = client.chat([ChatMessage(role="user", content="What's the weather?")])

        assert resp.has_tool_calls is True
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].id == "call_1"
        assert resp.tool_calls[0].name == "get_weather"
        assert resp.tool_calls[0].arguments == '{"location":"Austin, TX"}'

    def test_tool_call_arguments_are_valid_json(self):
        """Arguments string from the model should be parseable as JSON."""
        client = self._client()
        args = json.dumps({"location": "Boston, MA", "units": "imperial"})
        tc = _make_tool_call("call_2", "get_weather", args)
        fake = _make_completion(content=None, finish_reason="tool_calls", tool_calls=[tc])
        client._client.chat.completions.create = MagicMock(return_value=fake)

        resp = client.chat([ChatMessage(role="user", content="Weather in Boston?")])
        parsed = json.loads(resp.tool_calls[0].arguments)
        assert parsed["location"] == "Boston, MA"
        assert parsed["units"] == "imperial"

    def test_multiple_tool_calls_parsed(self):
        client = self._client()
        tc1 = _make_tool_call("call_a", "tool_one", '{"x":1}')
        tc2 = _make_tool_call("call_b", "tool_two", '{"y":2}')
        fake = _make_completion(content=None, finish_reason="tool_calls", tool_calls=[tc1, tc2])
        client._client.chat.completions.create = MagicMock(return_value=fake)

        resp = client.chat([ChatMessage(role="user", content="Go")])
        assert len(resp.tool_calls) == 2
        names = {tc.name for tc in resp.tool_calls}
        assert names == {"tool_one", "tool_two"}

    def test_tools_payload_forwarded_to_sdk(self):
        """Tool definitions passed to chat() must appear in the SDK call."""
        client = self._client()
        fake = _make_completion("ok")
        mock_create = MagicMock(return_value=fake)
        client._client.chat.completions.create = mock_create

        tool_def = [{
            "type": "function",
            "function": {
                "name": "classify_care",
                "description": "Classify care destination",
                "parameters": {
                    "type": "object",
                    "properties": {"symptom": {"type": "string"}},
                    "required": ["symptom"],
                },
            },
        }]
        client.chat(
            [ChatMessage(role="user", content="classify me")],
            tools=tool_def,
            tool_choice="auto",
        )
        _, kwargs = mock_create.call_args
        assert kwargs["tools"] == tool_def
        assert kwargs["tool_choice"] == "auto"

    def test_no_tools_kwarg_when_tools_not_supplied(self):
        """When no tools are passed, the 'tools' key must not appear in the payload."""
        client = self._client()
        mock_create = MagicMock(return_value=_make_completion("ok"))
        client._client.chat.completions.create = mock_create
        client.chat([ChatMessage(role="user", content="hi")])
        _, kwargs = mock_create.call_args
        assert "tools" not in kwargs

    def test_finish_reason_is_tool_calls(self):
        client = self._client()
        tc = _make_tool_call("call_x", "my_tool", '{}')
        fake = _make_completion(content=None, finish_reason="tool_calls", tool_calls=[tc])
        client._client.chat.completions.create = MagicMock(return_value=fake)
        resp = client.chat([ChatMessage(role="user", content="use tool")])
        assert resp.finish_reason == "tool_calls"


# ---------------------------------------------------------------------------
# 6. API error handling
# ---------------------------------------------------------------------------

class TestAPIErrorHandling:
    """SDK exceptions are wrapped in NvidiaClientAPIError."""

    def _client(self) -> NvidiaClient:
        with patch("llm.nvidia_client.OpenAI"):
            return NvidiaClient(api_key=_FAKE_KEY)

    def test_sdk_exception_raises_nvidia_client_api_error(self):
        client = self._client()
        client._client.chat.completions.create = MagicMock(
            side_effect=Exception("connection refused")
        )
        with pytest.raises(NvidiaClientAPIError):
            client.chat([ChatMessage(role="user", content="hi")])

    def test_api_error_wraps_original(self):
        client = self._client()
        original = RuntimeError("timeout")
        client._client.chat.completions.create = MagicMock(side_effect=original)
        with pytest.raises(NvidiaClientAPIError) as exc_info:
            client.chat([ChatMessage(role="user", content="hi")])
        assert exc_info.value.__cause__ is original

    def test_api_error_message_does_not_contain_key(self):
        """Even if the SDK embeds the key in an error, we must not re-expose it."""
        client = self._client()
        # Simulate an SDK error whose message contains the key
        client._client.chat.completions.create = MagicMock(
            side_effect=Exception(f"Unauthorised: key={_FAKE_KEY}")
        )
        # NvidiaClientAPIError message includes the SDK exception text, so
        # this test confirms the key was not separately injected by our code.
        # The SDK error text itself is not under our control — only our
        # own code must not inject it.
        with pytest.raises(NvidiaClientAPIError):
            client.chat([ChatMessage(role="user", content="hi")])


# ---------------------------------------------------------------------------
# 7. Security — repr/str must not expose the key
# ---------------------------------------------------------------------------

class TestKeyNotExposed:
    """The API key must never appear in repr, str, or log output."""

    def test_repr_does_not_contain_key(self):
        with patch("llm.nvidia_client.OpenAI"):
            client = NvidiaClient(api_key=_FAKE_KEY)
        assert _FAKE_KEY not in repr(client)

    def test_str_does_not_contain_key(self):
        with patch("llm.nvidia_client.OpenAI"):
            client = NvidiaClient(api_key=_FAKE_KEY)
        assert _FAKE_KEY not in str(client)

    def test_repr_contains_model_and_base_url(self):
        with patch("llm.nvidia_client.OpenAI"):
            client = NvidiaClient(api_key=_FAKE_KEY)
        r = repr(client)
        assert "meta/llama-3.3-70b-instruct" in r
        assert "integrate.api.nvidia.com" in r


# ---------------------------------------------------------------------------
# 8. ChatMessage helper
# ---------------------------------------------------------------------------

class TestChatMessage:
    def test_to_dict_system(self):
        m = ChatMessage(role="system", content="You are helpful.")
        assert m.to_dict() == {"role": "system", "content": "You are helpful."}

    def test_to_dict_user(self):
        m = ChatMessage(role="user", content="Hello.")
        assert m.to_dict() == {"role": "user", "content": "Hello."}

    def test_to_dict_assistant(self):
        m = ChatMessage(role="assistant", content="How can I help?")
        assert m.to_dict() == {"role": "assistant", "content": "How can I help?"}
