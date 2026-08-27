"""AI model access through OpenRouter.

Using OpenRouter instead of calling a provider directly means swapping
models is just an env var change, no code change.
"""

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _print_usage(model, usage, elapsed):
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cost = usage.get("cost")
    cost_str = f"${cost:.6f}" if isinstance(cost, (int, float)) else "n/a"

    print(
        "Discovr chatbot usage: "
        f"model={model} "
        f"input_tokens={prompt_tokens} "
        f"output_tokens={completion_tokens} "
        f"time={elapsed:.2f}s "
        f"cost={cost_str}",
        flush=True,
    )


def _chat_completion(messages, model=None, temperature=None, json_mode=False):
    api_key = os.environ["OPENROUTER_API_KEY"]
    model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    payload_dict = {"model": model, "messages": messages, "usage": {"include": True}}
    if temperature is not None:
        payload_dict["temperature"] = temperature
    if json_mode:
        # Asks the provider's native JSON mode to constrain output, so a
        # model can't hand back prose around the object in the first
        # place — belt-and-braces with extract_json_object() below,
        # since not every model/provider on OpenRouter honors this.
        payload_dict["response_format"] = {"type": "json_object"}
    payload = json.dumps(payload_dict).encode()

    request = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode()
        raise RuntimeError(f"OpenRouter request failed ({error.code}): {detail}") from error
    elapsed = time.monotonic() - start

    usage = data.get("usage", {})
    _print_usage(model, usage, elapsed)

    return {
        "content": data["choices"][0]["message"]["content"],
        "model": model,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "response_time_seconds": round(elapsed, 2),
    }


def ask(message, model=None):
    return _chat_completion([{"role": "user", "content": message}], model)["content"]


def ask_structured(messages, model=None, temperature=None, json_mode=False):
    """Like `ask`, but takes a full message list and returns the raw
    result dict (content, model, token counts, timing) instead of just
    the string, for callers that need more than a plain answer (e.g.
    src/clarity.py and src/scoring.py, which parse the content as JSON).
    Pass json_mode=True to also request the provider's native
    structured-output mode (see extract_json_object for the fallback
    when a model returns prose anyway)."""
    return _chat_completion(messages, model, temperature, json_mode)


def strip_code_fence(text):
    """Strip a ```json ... ``` or ``` ... ``` wrapper some models add
    around structured output despite being asked for raw JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json_object(text):
    """Pull a JSON object out of a model response that may fence it in
    markdown and/or pad it with prose before or after the object itself
    — some models do this even when told to return raw JSON only, which
    is what breaks a plain json.loads() with errors like "Expecting
    value: line 1 column N"."""
    text = text.strip()
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def load_prompt(name):
    return (PROMPTS_DIR / name).read_text()


def load_knowledge_base():
    return (DATA_DIR / "knowledge_base.md").read_text()


def save_prompt(name, content):
    (PROMPTS_DIR / name).write_text(content)


def save_knowledge_base(content):
    (DATA_DIR / "knowledge_base.md").write_text(content)
