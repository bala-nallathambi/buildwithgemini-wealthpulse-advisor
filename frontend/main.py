"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google.protobuf.json_format import MessageToDict, ParseDict

from a2a.client import ClientConfig, ClientFactory
from a2a.types import AgentCard, Message, Part, Role, SendMessageRequest

_A2UI_MIME = "application/json+a2ui"

app = FastAPI(title="WealthPulse Advisor Frontend Proxy")

# Resolve Reasoning Engine A2A endpoints
RESOURCE_NAME = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/664309893743/locations/us-central1/reasoningEngines/2893472050876252160",
)
AGENT_DIR = os.environ.get("AGENT_DIRECTORY", "app")

_parts = RESOURCE_NAME.split("/")
_project = _parts[1] if len(_parts) > 1 else ""
_location = _parts[3] if len(_parts) > 3 else "us-central1"

A2A_BASE = (
    f"https://{_location}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE_NAME}/api/a2a/{AGENT_DIR}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"


def _auth_headers() -> dict[str, str]:
    creds, _ = google.auth.default()
    creds.refresh(google.auth.transport.requests.Request())
    return {"Authorization": f"Bearer {creds.token}"}


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


_contexts: dict[str, str] = {}
_card = None


async def _get_card(client: httpx.AsyncClient):
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        data = resp.json()
        data["url"] = A2A_BASE
        try:
            card = ParseDict(data, AgentCard(), ignore_unknown_fields=True)
        except Exception:
            card = AgentCard(**data)
            card.url = A2A_BASE
        _card = card
    return _card


def _extract_parts_from_item(item) -> tuple[str | None, list[dict]]:
    context_id = None
    parts = []
    if hasattr(item, "HasField"):
        if item.HasField("task"):
            context_id = item.task.context_id
        elif item.HasField("artifact_update"):
            art = item.artifact_update.artifact
            context_id = item.artifact_update.context_id
            for part in art.parts:
                if part.HasField("text") and part.text:
                    parts.append({"kind": "text", "text": part.text})
                elif part.HasField("data"):
                    d = MessageToDict(part.data)
                    mime = d.get("metadata", {}).get("mimeType")
                    if mime == _A2UI_MIME:
                        parts.append({"kind": "a2ui", "data": d.get("data", {})})
        elif item.HasField("status_update"):
            context_id = item.status_update.context_id
    elif isinstance(item, tuple):
        task, update = item
        if task is not None and getattr(task, "context_id", None):
            context_id = task.context_id
        if hasattr(update, "artifact") and hasattr(update.artifact, "parts"):
            for p in update.artifact.parts:
                root = getattr(p, "root", p)
                if hasattr(root, "text") and root.text:
                    parts.append({"kind": "text", "text": root.text})
                elif hasattr(root, "data") and root.data:
                    meta = getattr(root, "metadata", None) or {}
                    mime = meta.get("mimeType") if isinstance(meta, dict) else None
                    if mime == _A2UI_MIME:
                        parts.append({"kind": "a2ui", "data": root.data})
    return context_id, parts


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(ClientConfig(httpx_client=client))
        a2a_client = factory.create(card)

        ctx_id = _contexts.get(user_id)
        msg_kwargs = {
            "message_id": str(uuid.uuid4()),
            "role": Role.ROLE_USER,
            "parts": [Part(text=message)],
        }
        if ctx_id:
            msg_kwargs["context_id"] = ctx_id

        msg = Message(**msg_kwargs)
        request_obj = SendMessageRequest(message=msg)

        async for item in a2a_client.send_message(request_obj):
            cid, p = _extract_parts_from_item(item)
            if cid:
                _contexts[user_id] = cid
            if p:
                parts.extend(p)

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
