"""FastAPI server exposing persona synthesis.

Run locally:
    uvicorn app:app --reload --port 8787

Endpoints:
    GET  /health                   — liveness
    POST /synthesize               — multipart: `payload` JSON + repeated `files`
    POST /synthesize/stream        — same inputs, SSE stream of events
    GET  /docs                     — Swagger UI (FastAPI default)
"""
from __future__ import annotations

import json
import queue
import threading
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError

from persona_synthesis import (
    ChatMessage,
    SchemaValidationError,
    SynthesisInputs,
    UploadedFile,
    synthesize_personas,
)
from persona_synthesis.schema import StreamEvent


load_dotenv()

app = FastAPI(
    title="Ascala · Persona Synthesis",
    description="Turns raw context into 3 behavioral PersonaGroups via Claude.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SynthesizePayload(BaseModel):
    """JSON body that rides alongside the multipart file uploads."""
    chat_messages: list[ChatMessage] = []
    product_url: Optional[str] = None


async def _collect_inputs(
    payload_json: str, files: list[UploadFile] | None
) -> SynthesisInputs:
    try:
        payload = SynthesizePayload.model_validate_json(payload_json)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    uploaded: list[UploadedFile] = []
    for f in files or []:
        data = await f.read()
        uploaded.append(
            UploadedFile(name=f.filename or "unnamed", mime=f.content_type or "application/octet-stream", data=data)
        )

    if not uploaded and not payload.chat_messages and not payload.product_url:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: files, chat_messages, product_url.",
        )

    return SynthesisInputs(
        files=uploaded,
        chat_messages=payload.chat_messages,
        product_url=payload.product_url,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/synthesize")
async def synthesize(
    payload: str = Form(..., description="JSON: {chat_messages?, product_url?}"),
    files: list[UploadFile] | None = None,
) -> dict:
    inputs = await _collect_inputs(payload, files)
    try:
        result = synthesize_personas(inputs)
    except SchemaValidationError as e:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "schema_validation_failed",
                "attempts": e.attempts,
                "last_errors": e.last_errors,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result.model_dump()


@app.post("/synthesize/stream")
async def synthesize_stream(
    payload: str = Form(...),
    files: list[UploadFile] | None = None,
) -> StreamingResponse:
    inputs = await _collect_inputs(payload, files)

    event_q: "queue.Queue[StreamEvent | None]" = queue.Queue()

    def run() -> None:
        try:
            synthesize_personas(
                inputs,
                stream=True,
                on_event=lambda ev: event_q.put(ev),
            )
        except SchemaValidationError as e:
            event_q.put(
                StreamEvent(
                    kind="error",
                    data={
                        "error": "schema_validation_failed",
                        "attempts": e.attempts,
                        "last_errors": e.last_errors,
                    },
                )
            )
        except Exception as e:
            event_q.put(StreamEvent(kind="error", data={"error": str(e)}))
        finally:
            event_q.put(None)  # sentinel

    threading.Thread(target=run, daemon=True).start()

    def sse() -> Any:
        while True:
            ev = event_q.get()
            if ev is None:
                return
            payload = json.dumps(ev.model_dump(), default=str)
            yield f"event: {ev.kind}\ndata: {payload}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")
