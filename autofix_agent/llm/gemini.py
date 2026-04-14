from __future__ import annotations

import json
from typing import Any

import requests


class GeminiError(RuntimeError):
    pass


def generate_json(
    *,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float = 0.2,
    max_output_tokens: int = 1400,
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
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise GeminiError(f"Gemini did not return valid JSON: {text[:2000]}") from e

