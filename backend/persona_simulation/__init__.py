"""Ascala persona simulation module."""

from persona_simulation.errors import (
    GraphIncomplete,
    SchemaValidationError,
    SimulationError,
)
from persona_simulation.runner import simulate
from persona_simulation.schema import (
    AgentDecision,
    AgentPath,
    CategorizedIssues,
    GlobalMetrics,
    SampledAgent,
    Screen,
    ScreenGraph,
    SimulationConfig,
    SimulationInputs,
    SimulationReport,
    SimulationResult,
)

__all__ = [
    "simulate",
    "SimulationInputs",
    "SimulationResult",
    "SimulationReport",
    "SimulationConfig",
    "ScreenGraph",
    "Screen",
    "SampledAgent",
    "AgentDecision",
    "AgentPath",
    "GlobalMetrics",
    "CategorizedIssues",
    "SimulationError",
    "GraphIncomplete",
    "SchemaValidationError",
]
