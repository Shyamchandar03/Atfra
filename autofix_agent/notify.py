from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import requests


class Notifier(Protocol):
    def send(self, title: str, body: str) -> None: ...


@dataclass(frozen=True)
class SlackNotifier:
    webhook_url: str

    def send(self, title: str, body: str) -> None:
        requests.post(
            self.webhook_url,
            json={"text": f"*{title}*\n{body}"},
            timeout=15,
        )


@dataclass(frozen=True)
class NoopNotifier:
    def send(self, title: str, body: str) -> None:  # noqa: ARG002
        return

