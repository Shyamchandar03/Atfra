from __future__ import annotations

import json
from typing import Any

import requests


class GeminiError(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    """
    Gemini sometimes returns:
    - JSON wrapped in markdown fences
    - extra prose around JSON
    - truncated output (no closing brace)
    This tries to safely extract a single top-level JSON object.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise GeminiError(f"No JSON object found in model output: {cleaned[:400]}")

    candidate = cleaned[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise GeminiError(f"Model returned invalid JSON: {candidate[:800]}") from e


def generate_json(
    *,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
) -> dict[str, Any]:
    """
    Calls Gemini via Generative Language API (HTTP).
    Returns parsed JSON from the model response (must be JSON-only).
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    resp = requests.post(
        url,
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        timeout=60,
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
            },
        },
    )
    if resp.status_code >= 400:
        raise GeminiError(f"Gemini API error {resp.status_code}: {resp.text[:2000]}")
    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:  # noqa: BLE001
        raise GeminiError(f"Unexpected Gemini response shape: {json.dumps(data)[:2000]}") from e
    try:
        return _extract_json(text)
    except GeminiError:
        # One repair attempt: ask the model to re-emit JSON only.
        repair_prompt = (
            "Re-emit the response as STRICT JSON ONLY.\n"
            "Rules: no markdown, no trailing commas, ensure all strings are closed, ensure braces are balanced.\n"
            "Return only a single JSON object.\n\n"
            "Here is your previous output:\n"
            f"{text}\n"
        )
        resp2 = requests.post(
            url,
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            timeout=60,
            json={
                "contents": [{"role": "user", "parts": [{"text": repair_prompt}]}],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": max_output_tokens,
                    "responseMimeType": "application/json",
                },
            },
        )
        if resp2.status_code >= 400:
            raise GeminiError(f"Gemini API error {resp2.status_code}: {resp2.text[:2000]}")
        data2 = resp2.json()
        try:
            text2 = data2["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:  # noqa: BLE001
            raise GeminiError(
                f"Unexpected Gemini response shape (repair): {json.dumps(data2)[:2000]}"
            ) from e
        return _extract_json(text2)
