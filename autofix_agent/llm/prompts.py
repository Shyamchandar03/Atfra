from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, Field


class LlmEdit(BaseModel):
    file_path: str = Field(..., description="Repo-relative file path.")
    anchor: str = Field(
        ...,
        description="Exact literal snippet that must exist once; used as safe anchor for change.",
    )
    replacement: str = Field(..., description="Replacement text for anchor.")


class LlmFixPlan(BaseModel):
    summary: str
    category: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    edits: list[LlmEdit]
    notes: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PromptInputs:
    repo: str
    failure_excerpt: str
    classification: dict
    code_context: dict
    artifact_context: dict | None = None


def build_fix_prompt(inputs: PromptInputs) -> str:
    schema = LlmFixPlan.model_json_schema()
    artifact_section = ""
    if inputs.artifact_context:
        artifact_section = (
            "\nArtifact context (DOM/screenshot/trace metadata):\n"
            f"{json.dumps(inputs.artifact_context, indent=2)}\n"
        )
    return (
        "You are an Autonomous Test Failure Resolution Agent for Playwright (Python) + Pytest.\n"
        "Goal: propose a minimal, safe code fix for the failing test based on logs + code context.\n"
        "\n"
        "Hard constraints:\n"
        "- Output MUST be JSON only (no markdown, no prose).\n"
        "- Only propose edits that are anchored by an exact literal snippet present in the file.\n"
        "- Keep diffs minimal; prefer adding explicit waits / robust locators / stable assertions.\n"
        "- Do NOT invent new files.\n"
        "\n"
        "Repository:\n"
        f"{inputs.repo}\n"
        "\n"
        "Failure classification (heuristics):\n"
        f"{json.dumps(inputs.classification, indent=2)}\n"
        "\n"
        "Failure log excerpt:\n"
        f"{inputs.failure_excerpt}\n"
        "\n"
        "Code context (snippets around suspected failure):\n"
        f"{json.dumps(inputs.code_context, indent=2)}\n"
        f"{artifact_section}"
        "\n"
        "Return JSON matching this schema:\n"
        f"{json.dumps(schema, indent=2)}\n"
    )
