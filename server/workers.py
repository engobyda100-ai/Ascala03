"""Background workers: run_synthesis / run_simulation / run_report.

Each worker mutates the corresponding RunState. Failures (ValidationError,
SchemaValidationError, anything else) become status="failed" with a
human-readable error string. No silent fallback to mock.
"""
from __future__ import annotations

import json
import mimetypes
import traceback
from pathlib import Path

from persona_synthesis import (
    ChatMessage,
    SchemaValidationError,
    SynthesisInputs,
    UploadedFile as SynUploadedFile,
    synthesize_personas,
)
from persona_synthesis.schema import SynthesisResult
from persona_simulation import simulate
from persona_simulation.schema import (
    SimulationConfig,
    SimulationInputs,
    SimulationResult,
)
from persona_report.generator import generate_report

from server.mocks import (
    build_report_mock_provider,
    build_simulation_mock_provider,
    load_mock_synthesis_result,
)
from server.runs import registry
from server.storage import cleanup_tempdir


def _file_to_uploaded(path: Path) -> SynUploadedFile:
    mime, _ = mimetypes.guess_type(path.name)
    return SynUploadedFile(
        name=path.name,
        mime=mime or "application/octet-stream",
        data=path.read_bytes(),
    )


# ──────────────────────────── synthesis ────────────────────────────


def run_synthesis(
    *,
    run_id: str,
    file_paths: list[Path],
    chat_transcript: list[dict],
    product_url: str | None,
    mock: bool,
    tempdir: Path | None,
) -> None:
    try:
        if mock:
            result: SynthesisResult = load_mock_synthesis_result()
        else:
            files = [_file_to_uploaded(p) for p in file_paths]
            chat = [ChatMessage.model_validate(m) for m in chat_transcript]
            inputs = SynthesisInputs(
                files=files,
                chat_messages=chat,
                product_url=product_url or None,
            )
            result = synthesize_personas(inputs)
        registry.mark_done(run_id, result.model_dump(mode="json"))
    except SchemaValidationError as e:
        registry.mark_failed(
            run_id,
            f"schema_validation_failed (attempts={e.attempts}): {e.last_errors}",
        )
    except Exception as e:
        registry.mark_failed(run_id, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
    finally:
        cleanup_tempdir(tempdir)


# ──────────────────────────── simulation ────────────────────────────


def run_simulation(
    *,
    run_id: str,
    synthesis_result: dict,
    screenshot_paths: list[Path],
    goal: str | None,
    budget_overrides: dict | None,
    mock: bool,
    tempdir: Path | None,
) -> None:
    try:
        synthesis = SynthesisResult.model_validate(synthesis_result)
        screenshots = [_file_to_uploaded(p) for p in screenshot_paths]
        config_kwargs = {**(budget_overrides or {})}
        config = SimulationConfig(**config_kwargs) if config_kwargs else SimulationConfig()
        inputs = SimulationInputs(
            groups=synthesis.groups,
            screenshots=screenshots,
            goal=goal,
        )
        provider = build_simulation_mock_provider() if mock else None
        result = simulate(inputs, provider=provider, config=config)
        registry.mark_done(run_id, result.model_dump(mode="json"))
    except Exception as e:
        registry.mark_failed(run_id, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
    finally:
        cleanup_tempdir(tempdir)


# ──────────────────────────── report ────────────────────────────


def run_report(
    *,
    run_id: str,
    simulation_result: dict,
    simulation_run_id: str,
    mock: bool,
) -> None:
    try:
        sim = SimulationResult.model_validate(simulation_result)
        provider = build_report_mock_provider() if mock else None
        report = generate_report(
            sim,
            provider=provider,
            include_executive_summary=True,
            simulation_run_id=simulation_run_id,
        )
        registry.mark_done(run_id, report.model_dump(mode="json"))
    except Exception as e:
        registry.mark_failed(run_id, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
