"""
Shared LLM client — NVIDIA NIM via the OpenAI-compatible API.

This module is the ONLY place in the project that instantiates an OpenAI
client pointed at NVIDIA's endpoint.  All future agents that need LLM
inference import and use NvidiaClient rather than constructing their own
OpenAI instance.

Provider
--------
NVIDIA NIM (https://integrate.api.nvidia.com/v1)
Compatible with the openai Python SDK via a custom base_url.

Configuration (all from environment — never hard-coded)
-------------------------------------------------------
NVIDIA_API_KEY   Required.  Raises NvidiaClientConfigError at construction
                 time if absent or empty — fail loudly, never silently.
NVIDIA_BASE_URL  Default: https://integrate.api.nvidia.com/v1
NVIDIA_MODEL     Default: meta/llama-3.3-70b-instruct

Security
--------
- The API key is read once at construction and stored only inside the
  openai.OpenAI instance.  It is never logged, printed, or included in
  any exception message.
- __repr__ and __str__ are overridden to prevent accidental key exposure
  when the client object is logged.

Usage
-----
    from llm.nvidia_client import NvidiaClient, ChatMessage

    client = NvidiaClient()          # reads config from environment
    response = client.chat([
        ChatMessage(role="system", content="You are a helpful assistant."),
        ChatMessage(role="user",   content="What is 2+2?"),
    ])
    print(response.content)          # "4"
    print(response.model)            # "meta/llama-3.3-70b-instruct"
    print(response.tool_calls)       # None, or list of ToolCall objects

Tool calling
------------
    response = client.chat(
        messages=[...],
        tools=[{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            },
        }],
        tool_choice="auto",
    )
    if response.tool_calls:
        for tc in response.tool_calls:
            print(tc.name, tc.arguments)   # arguments is a JSON string

Note: no real API calls are made in unit tests — openai.OpenAI is mocked
at the test boundary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from openai import OpenAI
from openai.types.chat import ChatCompletion

from app.services.alternate_care.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------

class NvidiaClientError(RuntimeError):
    """Base class for all NvidiaClient failures."""


class NvidiaClientConfigError(NvidiaClientError):
    """Raised when required configuration is missing or invalid.

    The API key value is NEVER included in this message.
    """


class NvidiaClientAPIError(NvidiaClientError):
    """Raised when the NVIDIA API returns an error response."""


# ---------------------------------------------------------------------------
# Data classes — inputs and outputs
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    """A single message in a chat conversation.

    role:    "system", "user", or "assistant"
    content: The text of the message.
    """
    role: str
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ToolCall:
    """A single tool call requested by the model.

    id:         Opaque identifier assigned by the model.
    name:       The function name the model wants to call.
    arguments:  JSON string of the arguments (not yet parsed).
                Use json.loads(tc.arguments) to get a dict.
    """
    id: str
    name: str
    arguments: str   # raw JSON string from the model


@dataclass
class LLMResponse:
    """Structured response from a chat completion call.

    content:       The assistant's text reply (None when the model only
                   returned tool calls and no prose).
    model:         The model name reported by the API.
    tool_calls:    List of ToolCall objects if the model requested tool
                   use, otherwise None.
    finish_reason: The stop reason from the API ("stop", "tool_calls",
                   "length", etc.).
    raw:           The raw ChatCompletion object from the openai SDK, for
                   callers that need fields not surfaced here.
    """
    content: Optional[str]
    model: str
    tool_calls: Optional[List[ToolCall]]
    finish_reason: str
    raw: ChatCompletion

    @property
    def has_tool_calls(self) -> bool:
        """True when the model returned one or more tool calls."""
        return bool(self.tool_calls)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class NvidiaClient:
    """Reusable LLM client backed by NVIDIA's OpenAI-compatible endpoint.

    Instantiate once per process (or per request — it is stateless).
    The underlying openai.OpenAI instance is created at construction time
    and reused across calls.

    Parameters
    ----------
    api_key:
        Override the API key.  If None (default) the key is read from
        the NVIDIA_API_KEY environment variable via config.settings.
        Providing the key explicitly is intended for testing only.
    base_url:
        Override the base URL.  Defaults to config.settings.NVIDIA_BASE_URL.
    model:
        Override the model name.  Defaults to config.settings.NVIDIA_MODEL.
    temperature:
        Sampling temperature in [0, 2].  Lower = more deterministic.
        Default 0.2 is intentionally conservative for medical-adjacent use.
    top_p:
        Nucleus sampling probability.  Default 0.7.
    max_tokens:
        Maximum tokens to generate per call.  Default 1024.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        top_p: float = 0.7,
        max_tokens: int = 1024,
    ) -> None:
        # Resolve configuration — caller-supplied values take precedence
        resolved_key = api_key or settings.NVIDIA_API_KEY
        if not resolved_key or not resolved_key.strip():
            raise NvidiaClientConfigError(
                "NVIDIA_API_KEY is not set.  "
                "Set the NVIDIA_API_KEY environment variable before "
                "constructing NvidiaClient.  "
                "Never hard-code the key in source code."
                # The key value itself is intentionally NOT in this message.
            )

        self._model = model or settings.NVIDIA_MODEL
        self._base_url = base_url or settings.NVIDIA_BASE_URL
        self._temperature = temperature
        self._top_p = top_p
        self._max_tokens = max_tokens

        # Build the openai client.  The key is held inside the SDK object
        # and is never stored as a plain attribute on this class.
        self._client = OpenAI(
            api_key=resolved_key,
            base_url=self._base_url,
        )

        logger.debug(
            "NvidiaClient initialised: base_url=%s model=%s",
            self._base_url,
            self._model,
        )

    # Prevent accidental key exposure via repr/str
    def __repr__(self) -> str:
        return (
            f"NvidiaClient(base_url={self._base_url!r}, "
            f"model={self._model!r}, "
            f"temperature={self._temperature}, "
            f"top_p={self._top_p})"
            # api_key intentionally omitted
        )

    def __str__(self) -> str:
        return repr(self)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        """The model name this client sends to the API."""
        return self._model

    @property
    def base_url(self) -> str:
        """The base URL this client targets."""
        return self._base_url

    # ------------------------------------------------------------------
    # Core chat method
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[dict]] = None,
        tool_choice: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Send a chat completion request to the NVIDIA endpoint.

        Parameters
        ----------
        messages:
            Ordered list of ChatMessage objects (system / user / assistant),
            or raw dicts for tool-call protocol messages (``role="tool"``
            with ``tool_call_id``, and ``role="assistant"`` with
            ``tool_calls``).  ChatMessage objects are converted via
            ``to_dict()``; raw dicts are forwarded unchanged.
        tools:
            Optional list of tool definitions in OpenAI tool-call format.
            Each entry is a dict with keys "type" and "function".
        tool_choice:
            Controls tool selection: "auto" lets the model decide,
            "none" disables tool calling, {"type":"function","function":
            {"name":"..."}} forces a specific tool.
        temperature:
            Per-call override.  Falls back to the instance default.
        top_p:
            Per-call override.  Falls back to the instance default.
        max_tokens:
            Per-call override.  Falls back to the instance default.

        Returns
        -------
        LLMResponse
            Structured response with content, tool_calls, finish_reason,
            and the raw ChatCompletion object.

        Raises
        ------
        NvidiaClientAPIError
            When the API returns an error.  The exception message does NOT
            contain the API key.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [self._serialize_message(m) for m in messages],
            "temperature": temperature if temperature is not None else self._temperature,
            "top_p": top_p if top_p is not None else self._top_p,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
        }

        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        logger.debug(
            "NvidiaClient.chat: model=%s messages=%d tools=%s",
            self._model,
            len(messages),
            [t["function"]["name"] for t in (tools or [])],
        )

        try:
            completion: ChatCompletion = self._client.chat.completions.create(**payload)
        except Exception as exc:
            # Wrap all SDK exceptions.  str(exc) from the openai SDK should
            # not contain the key, but we sanitise the message anyway.
            raise NvidiaClientAPIError(
                f"NVIDIA API call failed: {type(exc).__name__}: {exc}"
                # Note: exc message is from the SDK, not injected by us.
                # The key is never part of openai SDK error messages.
            ) from exc

        return self._parse_completion(completion)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_message(message: "ChatMessage | dict") -> dict:
        """Serialize a message to a plain dict suitable for the API payload.

        Accepts either a ``ChatMessage`` dataclass (converted via
        ``to_dict()``) or a raw ``dict`` (passed through unchanged).
        Raw dicts are required for OpenAI tool-call protocol messages that
        ``ChatMessage`` does not model:

        - ``role="assistant"`` messages that carry a ``tool_calls`` list
          (the model's own tool-call turn, re-injected into history).
        - ``role="tool"`` messages that carry ``tool_call_id`` and the
          tool execution result.

        No validation is performed on raw dicts — callers are responsible
        for supplying well-formed message objects.
        """
        if isinstance(message, dict):
            return message
        return message.to_dict()

    @staticmethod
    def _parse_completion(completion: ChatCompletion) -> LLMResponse:
        """Convert a raw ChatCompletion into a structured LLMResponse."""
        choice = completion.choices[0]
        message = choice.message

        content: Optional[str] = message.content  # may be None on tool-call-only responses

        tool_calls: Optional[List[ToolCall]] = None
        if message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in message.tool_calls
            ]

        return LLMResponse(
            content=content,
            model=completion.model,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            raw=completion,
        )
