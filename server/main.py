"""FastAPI server wrapping persona_synthesis + persona_simulation + persona_report.

Run locally:
    uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload

Endpoints:
    GET  /api/health
    POST /api/synthesis/start          (multipart)   →  {"run_id": "syn_..."}
    GET  /api/synthesis/{run_id}       →  {"status": "running"|"done"|"failed", ...}
    POST /api/simulation/start         (multipart)   →  {"run_id": "sim_..."}
    GET  /api/simulation/{run_id}      →  ...
    POST /api/report/start             (json)        →  {"run_id": "rep_..."}
    GET  /api/report/{run_id}          →  ...
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    FastAPI,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from server.runs import RunState, registry
from server.storage import cleanup_tempdir, make_tempdir, sweeper_loop
from server.workers import run_report, run_simulation, run_synthesis


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    sweeper = asyncio.create_task(sweeper_loop())
    try:
        yield
    finally:
        sweeper.cancel()


app = FastAPI(
    title="Ascala · local dev server",
    description="Job-style HTTP API for synthesis → simulation → report.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


def _bool_form(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "on")


def _run_to_response(state: RunState) -> dict:
    if state.status == "running":
        return {"status": "running"}
    if state.status == "done":
        return {"status": "done", "result": state.result}
    return {"status": "failed", "error": state.error or "unknown error"}


# ──────────────────────────── health ────────────────────────────


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ──────────────────────────── synthesis ────────────────────────────


@app.post("/api/synthesis/start")
async def synthesis_start(
    background_tasks: BackgroundTasks,
    chat_transcript: str = Form("[]"),
    product_url: str = Form(""),
    mock: str = Form("false"),
    files: list[UploadFile] | None = None,
) -> dict:
    try:
        chat = json.loads(chat_transcript or "[]")
        if not isinstance(chat, list):
            raise ValueError("chat_transcript must be a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"invalid chat_transcript: {e}")

    files = files or []
    has_files = bool(files)
    has_chat = bool(chat)
    has_url = bool(product_url and product_url.strip())
    if not (has_files or has_chat or has_url):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: files, chat_transcript, product_url.",
        )

    state = registry.new("synthesis", tempdir=None)
    tempdir = make_tempdir(state.run_id)
    state.tempdir = tempdir

    file_paths: list[Path] = []
    for f in files:
        # Strip any path components from the client filename before joining.
        safe_name = Path(f.filename or "unnamed").name
        dest = tempdir / safe_name
        dest.write_bytes(await f.read())
        file_paths.append(dest)

    background_tasks.add_task(
        run_synthesis,
        run_id=state.run_id,
        file_paths=file_paths,
        chat_transcript=chat,
        product_url=product_url.strip() or None,
        mock=_bool_form(mock),
        tempdir=tempdir,
    )
    return {"run_id": state.run_id}


@app.get("/api/synthesis/{run_id}")
def synthesis_get(run_id: str) -> dict:
    state = registry.get(run_id)
    if state is None or state.kind != "synthesis":
        raise HTTPException(status_code=404, detail="run not found")
    return _run_to_response(state)


# ──────────────────────────── simulation ────────────────────────────


@app.post("/api/simulation/start")
async def simulation_start(
    background_tasks: BackgroundTasks,
    synthesis_run_id: str = Form(...),
    goal: str = Form(""),
    budget_overrides: str = Form(""),
    mock: str = Form("false"),
    screenshots: list[UploadFile] | None = None,
) -> dict:
    upstream = registry.get(synthesis_run_id)
    if upstream is None or upstream.kind != "synthesis":
        raise HTTPException(status_code=400, detail="unknown synthesis_run_id")
    if upstream.status != "done":
        raise HTTPException(
            status_code=400,
            detail=f"synthesis_run_id status is {upstream.status!r}; must be 'done'",
        )

    screenshots = screenshots or []
    if not screenshots:
        raise HTTPException(status_code=400, detail="at least one screenshot required")

    overrides_dict: dict | None = None
    if budget_overrides:
        try:
            overrides_dict = json.loads(budget_overrides)
            if not isinstance(overrides_dict, dict):
                raise ValueError("budget_overrides must be a JSON object")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=422, detail=f"invalid budget_overrides: {e}")

    state = registry.new("simulation", tempdir=None)
    tempdir = make_tempdir(state.run_id)
    state.tempdir = tempdir

    paths: list[Path] = []
    for f in screenshots:
        safe_name = Path(f.filename or "unnamed").name
        dest = tempdir / safe_name
        dest.write_bytes(await f.read())
        paths.append(dest)

    background_tasks.add_task(
        run_simulation,
        run_id=state.run_id,
        synthesis_result=upstream.result or {},
        screenshot_paths=paths,
        goal=goal.strip() or None,
        budget_overrides=overrides_dict,
        mock=_bool_form(mock),
        tempdir=tempdir,
    )
    return {"run_id": state.run_id}


@app.get("/api/simulation/{run_id}")
def simulation_get(run_id: str) -> dict:
    state = registry.get(run_id)
    if state is None or state.kind != "simulation":
        raise HTTPException(status_code=404, detail="run not found")
    return _run_to_response(state)


# ──────────────────────────── report ────────────────────────────


class ReportStartBody(BaseModel):
    simulation_run_id: str
    mock: bool = False


@app.post("/api/report/start")
def report_start(
    body: ReportStartBody,
    background_tasks: BackgroundTasks,
) -> dict:
    upstream = registry.get(body.simulation_run_id)
    if upstream is None or upstream.kind != "simulation":
        raise HTTPException(status_code=400, detail="unknown simulation_run_id")
    if upstream.status != "done":
        raise HTTPException(
            status_code=400,
            detail=f"simulation_run_id status is {upstream.status!r}; must be 'done'",
        )

    state = registry.new("report")
    background_tasks.add_task(
        run_report,
        run_id=state.run_id,
        simulation_result=upstream.result or {},
        simulation_run_id=body.simulation_run_id,
        mock=body.mock,
    )
    return {"run_id": state.run_id}


@app.get("/api/report/{run_id}")
def report_get(run_id: str) -> dict:
    state = registry.get(run_id)
    if state is None or state.kind != "report":
        raise HTTPException(status_code=404, detail="run not found")
    return _run_to_response(state)


# ──────────────────────────── chat (post-intake conversation) ────────────────────────────
#
# Synchronous, non-job endpoint: the intake summary is supplied by the client in
# `system`; `messages` is the post-intake conversational history. No registry /
# polling needed — this is a single request/response turn.

CHAT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
CHAT_MAX_TOKENS = 1024
DEFAULT_CHAT_SYSTEM = (
    "You are Ascala Intelligence, a product-validation and customer-discovery coach."
)


class ChatMessageBody(BaseModel):
    role: str
    content: str


class ChatStartBody(BaseModel):
    system: str = ""
    messages: list[ChatMessageBody] = []
    mock: bool = False


def _mock_chat_reply(system: str, last_user: str) -> str:
    """A canned reply that visibly consumes the intake context, so the demo
    exercises the full wiring even with mock mode on (the default)."""
    ctx = ""
    if "User Intake:" in system:
        ctx = system.split("User Intake:", 1)[1]
        ctx = ctx.split("persistent context", 1)[0]
        ctx = " ".join(ctx.split())[:240]
    return (
        f"(mock) Good question — \"{last_user}\". "
        f"Drawing on your intake context — {ctx or 'no answers were captured'} — "
        "my practical first take: lead with the segment you ranked highest and the "
        "test you prioritized, and frame messaging around the launch fear you weighted "
        "most heavily. Flip off Mock mode in the Studio panel for a full model-written answer."
    )


@app.post("/api/chat")
def chat_start(body: ChatStartBody) -> dict:
    msgs = [
        {"role": m.role, "content": m.content}
        for m in body.messages
        if m.content and m.content.strip()
    ]
    if not msgs:
        raise HTTPException(status_code=400, detail="messages required")
    if msgs[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="last message must be from the user")

    if body.mock:
        return {"reply": _mock_chat_reply(body.system, msgs[-1]["content"])}

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=CHAT_MAX_TOKENS,
            system=body.system.strip() or DEFAULT_CHAT_SYSTEM,
            messages=msgs,
        )
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
        ).strip()
        return {"reply": text or "(the model returned an empty response)"}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — surface any provider/SDK failure to the client
        raise HTTPException(status_code=502, detail=f"chat failed: {e}")
