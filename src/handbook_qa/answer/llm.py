"""Talking to the model through any OpenAI-compatible endpoint (D13: Gemini's, by default).

Errors are turned into LLMError with a message that is safe to show: the API key, and anything that
looks like a project or account id, is removed from provider error text before it goes anywhere.
"""

import json
import re
import time
from dataclasses import dataclass
from typing import Protocol

import openai
from openai import OpenAI


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class Completion:
    data: dict
    prompt_tokens: int | None
    completion_tokens: int | None
    seconds: float


class ChatModel(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: dict) -> Completion: ...


class OpenAICompatibleModel:
    def __init__(self, base_url: str, model: str, api_key: str | None, timeout: float = 60, max_retries: int = 3) -> None:
        if not api_key:
            raise LLMError("No API key found. Put GEMINI_API_KEY=... in the .env file (see README).")
        self.name = model
        self._key = api_key
        # The SDK retries 429 and 5xx responses itself, with exponential backoff.
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=max_retries)

    def complete_json(self, system: str, user: str, schema: dict) -> Completion:
        started = time.monotonic()
        for attempt in (1, 2):  # one extra try if the model breaks the JSON format
            try:
                response = self._client.chat.completions.create(
                    model=self.name,
                    temperature=0,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    response_format={"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": schema}},
                )
            except openai.RateLimitError as error:
                raise LLMError(f"The model's rate limit was reached (free tier: 15 requests a minute, 500 a day). {self._safe(error)}") from None
            except openai.APITimeoutError:
                raise LLMError("The model did not answer in time. Try again.") from None
            except openai.APIConnectionError:
                raise LLMError("Could not reach the model. Check the internet connection.") from None
            except openai.APIStatusError as error:
                raise LLMError(f"The model service returned HTTP {error.status_code}. {self._safe(error)}") from None
            content = response.choices[0].message.content or ""
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                if attempt == 2:
                    raise LLMError("The model replied with text that isn't valid JSON, twice.") from None
                continue
            usage = response.usage
            return Completion(
                data=data,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                seconds=round(time.monotonic() - started, 2),
            )
        raise AssertionError("unreachable")

    def _safe(self, error: Exception) -> str:
        return redact(str(error)[:300], self._key)


def redact(text: str, key: str | None = None) -> str:
    if key:
        text = text.replace(key, "[key]")
    text = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[key]", text)
    text = re.sub(r"(projects?/|project[ _-]?(?:id|number)?[\"': =]+)[\w-]+", r"\1[redacted]", text, flags=re.IGNORECASE)
    return text
