from __future__ import annotations

from dataclasses import dataclass
import re

from .logs import ParsedFailure


class FailureCategory:
    LOCATOR_NOT_FOUND = "locator_not_found"
    TIMEOUT = "timeout"
    ASSERTION = "assertion_failure"
    NETWORK = "network_or_api_failure"
    FLAKY = "flaky_or_infra"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FailureClassification:
    category: str
    confidence: float
    hints: list[str]


_TIMEOUT_PATTERNS = [
    re.compile(r"Timeout\s+\d+ms exceeded", re.IGNORECASE),
    re.compile(r"TimeoutError", re.IGNORECASE),
    re.compile(r"waiting for (selector|locator)", re.IGNORECASE),
]
_LOCATOR_PATTERNS = [
    re.compile(r"strict mode violation", re.IGNORECASE),
    re.compile(r"locator\(", re.IGNORECASE),
    re.compile(r"Selector.*resolved to", re.IGNORECASE),
    re.compile(r"element is not (attached|visible|enabled)", re.IGNORECASE),
]
_ASSERTION_PATTERNS = [
    re.compile(r"AssertionError", re.IGNORECASE),
    re.compile(r"expect\(", re.IGNORECASE),
]
_NETWORK_PATTERNS = [
    re.compile(r"net::ERR_", re.IGNORECASE),
    re.compile(r"ECONN", re.IGNORECASE),
    re.compile(r"502|503|504", re.IGNORECASE),
    re.compile(r"ConnectionError", re.IGNORECASE),
]


def classify_failure(failure: ParsedFailure) -> FailureClassification:
    text = failure.raw_excerpt
    hints: list[str] = []

    def _any(patterns: list[re.Pattern[str]]) -> bool:
        return any(p.search(text) for p in patterns)

    if _any(_NETWORK_PATTERNS):
        hints.append("Detected network/API error pattern in logs.")
        return FailureClassification(FailureCategory.NETWORK, 0.75, hints)

    if _any(_TIMEOUT_PATTERNS):
        hints.append("Detected timeout pattern in logs.")
        if _any(_LOCATOR_PATTERNS):
            hints.append("Locator interaction details present near timeout.")
        return FailureClassification(FailureCategory.TIMEOUT, 0.7, hints)

    if _any(_LOCATOR_PATTERNS):
        hints.append("Detected locator/strict-mode pattern in logs.")
        return FailureClassification(FailureCategory.LOCATOR_NOT_FOUND, 0.7, hints)

    if _any(_ASSERTION_PATTERNS):
        hints.append("Detected assertion failure pattern in logs.")
        return FailureClassification(FailureCategory.ASSERTION, 0.65, hints)

    hints.append("No strong heuristics matched.")
    return FailureClassification(FailureCategory.UNKNOWN, 0.35, hints)

