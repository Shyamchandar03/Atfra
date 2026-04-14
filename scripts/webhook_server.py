from __future__ import annotations

import hmac
import hashlib
import json
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse


app = FastAPI(title="Autofix GitHub Webhook Listener")


def _verify_signature(secret: str, body: bytes, signature_header: str | None) -> None:
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing/invalid signature.")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1].strip()
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Signature mismatch.")


@app.post("/github/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
) -> JSONResponse:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Missing GITHUB_WEBHOOK_SECRET.")
    body = await request.body()
    _verify_signature(secret, body, x_hub_signature_256)

    if x_github_event != "workflow_run":
        return JSONResponse({"ok": True, "ignored": x_github_event})

    payload: dict[str, Any] = json.loads(body.decode("utf-8"))
    run = payload.get("workflow_run", {})
    return JSONResponse({"ok": True, "run_id": run.get("id"), "conclusion": run.get("conclusion")})

