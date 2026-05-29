"""Public entrypoint: generate_report()."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from persona_simulation.schema import SimulationResult
from persona_synthesis.llm.base import LLMProvider

from persona_report import distributions, exec_summary, filters, severity, stats, summaries
from persona_report.fixes import FixCache, draft_fixes_for_test_type
from persona_report.outcomes import compute_executive_summary, compute_outcome_context
from persona_report.predictions import build_scenarios
from persona_report.schema import (
    Report,
    ReportMeta,
    TestTypeReport,
)


TEST_TYPES: tuple[str, ...] = (
    "accessibility", "compliance", "onboarding",
    "activation", "engagement", "retention",
)


def _build_one_test_type(
    test_type: str,
    sim: SimulationResult,
    *,
    provider: LLMProvider,
    cache: FixCache,
) -> tuple[TestTypeReport, int, int, list[str]]:
    """Returns (TestTypeReport, llm_calls_made, tokens_used, warnings)."""
    slice_ = filters.select_for(test_type, sim)
    confidence = filters.confidence_from_touchpoints(slice_.touchpoint_count)

    # Pure: stats + distributions + trajectory + outcome framing
    key_stats = stats.compute(slice_, sim)
    persona_dists = distributions.build(slice_, sim)
    trajectory = distributions.compute_trajectory(slice_, sim)
    outcome_context = compute_outcome_context(test_type, slice_, sim)

    # Severity (pure) → fixes (LLM)
    classified = severity.classify_many(slice_.issues, sim)

    # Summary (1 LLM call)
    short_summary, summary_tokens = summaries.generate_short_summary(
        slice_, key_stats, data_confidence=confidence, provider=provider,
    )
    llm_calls = 1
    tokens_used = summary_tokens
    warnings: list[str] = []

    fixes: list = []
    if classified:
        fixes, fix_tokens, fix_warnings = draft_fixes_for_test_type(
            classified, sim, test_type=test_type, provider=provider, cache=cache,
        )
        # Each non-cached fix is at least 1 LLM call (and up to 2 with retry).
        llm_calls += sum(1 for f in fixes if f.related_issue_ids and f.related_issue_ids[0] not in (
            # we don't track retries separately here; underestimate is safer than overestimate
        ))
        # More precisely: count = len(selected) including drops; we don't know
        # about retries from the API surface. Approximate as len(fixes) + len(warnings).
        llm_calls = llm_calls + len(fixes) + len(fix_warnings) - 1  # subtract the "1" we already added
        # Simpler: track tokens, accept llm_calls is approximate.
        # Reset llm_calls and recompute cleanly:
        llm_calls = 1 + len(fixes) + len(fix_warnings)
        tokens_used += fix_tokens
        warnings.extend(fix_warnings)

    scenarios = build_scenarios(fixes, slice_, sim, test_type=test_type)

    retention_signals: list[str] = []
    if test_type == "retention":
        retention_signals = [
            f.summary.split(".")[0].strip() + "."
            for f in fixes
            if f.summary
        ]

    return (
        TestTypeReport(
            test_type=test_type,  # type: ignore[arg-type]
            short_summary=short_summary,
            key_stats=key_stats,
            persona_distributions=persona_dists,
            recommended_fixes=fixes,
            data_confidence=confidence,  # type: ignore[arg-type]
            trajectory=trajectory,
            scenarios=scenarios,
            retention_signals=retention_signals,
            outcome_context=outcome_context,
        ),
        llm_calls,
        tokens_used,
        warnings,
    )


def generate_report(
    sim: SimulationResult,
    *,
    provider: Optional[LLMProvider] = None,
    include_executive_summary: bool = False,
    simulation_run_id: Optional[str] = None,
) -> Report:
    """Run the full report pipeline against a finished SimulationResult.

    Args:
        sim: the upstream SimulationResult.
        provider: any LLMProvider. Defaults to AnthropicProvider() — lazily imported.
        include_executive_summary: emit one extra LLM call producing a top-level
            cross-test-type summary.
        simulation_run_id: opaque id stamped into Report.meta.

    Returns:
        Report with 6 TestTypeReports, optional executive_summary, and meta.
    """
    if provider is None:
        from persona_synthesis.llm.anthropic_client import AnthropicProvider
        provider = AnthropicProvider()

    cache = FixCache()
    test_type_reports: list[TestTypeReport] = []
    total_calls = 0
    total_tokens = 0
    all_warnings: list[str] = []

    for tt in TEST_TYPES:
        ttr, calls, tokens, warns = _build_one_test_type(
            tt, sim, provider=provider, cache=cache,
        )
        test_type_reports.append(ttr)
        total_calls += calls
        total_tokens += tokens
        all_warnings.extend(warns)

    exec_summary_text: Optional[str] = None
    if include_executive_summary:
        exec_summary_text, exec_tokens = exec_summary.generate(
            test_type_reports, provider=provider,
        )
        total_calls += 1
        total_tokens += exec_tokens

    structured_summary = compute_executive_summary(
        test_type_reports, sim, business_summary=exec_summary_text,
    )

    return Report(
        test_type_reports=test_type_reports,  # type: ignore[arg-type]
        executive_summary=exec_summary_text,
        summary=structured_summary,
        meta=ReportMeta(
            simulation_run_id=simulation_run_id,
            generated_at=datetime.now(timezone.utc),
            total_llm_calls=total_calls,
            tokens_used_total=total_tokens,
            budgets_engaged=list(sim.budgets_engaged),
            warnings=all_warnings,
        ),
    )
