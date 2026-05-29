# Persona Simulation Module — Design Plan

## Context

The `persona_synthesis` module (already built at `/Users/ob/ascala/backend/persona_synthesis/`) produces 3 `PersonaGroup` objects from raw product context. This new module **consumes those 3 groups** plus uploaded prototype screenshots, runs a multi-agent walkthrough simulation, and produces a narrative simulation report backed by structured metrics.

**Scope of THIS phase:** design only. Output is this document. Implementation happens after approval.

**Infrastructure to reuse (verified):**
- `persona_synthesis/llm/base.py` — `LLMProvider` Protocol accepts image blocks in `messages` unchanged.
- `persona_synthesis/llm/anthropic_client.py` — passes `messages` to `self._client.messages.create()` with no transformation; vision works out of the box.
- `persona_synthesis/parsers/image.py:parse_image()` — UploadedFile → Claude-ready `{"type":"image","source":{...}}` block. Reused verbatim.
- `persona_synthesis/schema.py` — `PersonaGroup` + all sub-models. Imported as read-only input type.
- `tests/conftest.py` — `DummyProvider` + `make_dummy` fixture factory. Pattern cloned into `persona_simulation/tests/`.

**Scope boundaries:** screenshots only. No live URLs, no videos, no stubs for them in the public interface. No UI layer. No persistence (everything in memory, CLI serializes on stdout). No OCR/DOM/browser automation — vision LLM only.

---

## 1. Module structure

```
/Users/ob/ascala/backend/persona_simulation/
  __init__.py                # exports simulate(), SimulationInputs, SimulationResult, key types
  PLAN.md                    # this design doc
  schema.py                  # all pydantic models (§2)
  errors.py                  # SimulationError, BudgetExceeded, GraphIncomplete
  screen_graph.py            # build_screen_graph() — 1 multimodal LLM call, tool-use
  sampling.py                # sample_seed_agents() — range→concrete + 1 LLM/seed for backstory
  decisions.py               # agent_decision() — per-turn LLM call (multimodal)
  forking.py                 # should_fork() — pure deterministic, no LLM
  metrics.py                 # Screen/Global metrics accumulators, drop-off curve, friction ranking
  runner.py                  # simulate() orchestrator: walks, forks, budgets, concurrency
  categorize.py              # categorize_issues() — 1 post-sim LLM call
  report.py                  # curate_traces() + build_report() — 1 final LLM call
  run.py                     # `python -m persona_simulation.run` CLI
  prompts/                   # colocated, not at repo root (see §7 open Q on prompt layout)
    build_screen_graph.md
    seed_backstory.md
    agent_decision.md
    categorize_issues.md
    simulation_report.md
  tests/
    conftest.py              # cloned DummyProvider + make_dummy, extended to return token usage
    fixtures/
      shots/ (2–3 tiny PNGs)
      mock_screen_graph.json
      mock_decision_*.json
      mock_categorized_issues.json
      mock_report.json
      sample_personas.json   # 3 PersonaGroups for CLI / integration tests
    test_screen_graph.py
    test_sampling.py
    test_agent_step.py
    test_fork_logic.py       # pure, no LLM
    test_runner_budget.py
    test_report.py
    test_live.py             # @pytest.mark.live, gated off
```

**Deviation from user spec:** prompts colocated inside the module (`persona_simulation/prompts/`) rather than the repo-root `backend/prompts/` used by `persona_synthesis`. Reason: keeps the module self-contained, avoids name collisions across modules, and makes vendoring/packaging trivial. If consistency with `persona_synthesis` is preferred, move them.

---

## 2. Complete type schema (`persona_simulation/schema.py`)

Same style as `persona_synthesis/schema.py`: pydantic v2, `Literal` enums, `Field(ge=, le=)`, `conlist`, `@model_validator(mode="after")`.

```python
# ── Screen graph ─────────────────────────────────────────────────
ElementKind = Literal["button","link","input","checkbox","radio",
                      "toggle","select","tab","card","image","text","unknown"]

class InteractiveElement(BaseModel):
    id: str                          # stable slug, e.g. "s1.btn_signup"
    kind: ElementKind
    label: str                       # copy/alt the vision model read
    bbox_hint: Optional[str] = None  # natural-language location ("top-right")

class Screen(BaseModel):
    id: str                              # "s1", "s2"...
    source_filename: str                 # links back to the UploadedFile
    inferred_purpose: str                # one sentence
    copy: list[str]                      # notable text strings
    elements: list[InteractiveElement]
    duplicate_of: Optional[str] = None   # canonical screen id if this is a variant (see §7)

class Transition(BaseModel):
    from_screen: str
    via_element_id: str
    to_screen: str
    confidence: int = Field(ge=1, le=5)

class UnresolvedAction(BaseModel):
    from_screen: str
    via_element_id: str
    reason: str                          # "no destination screenshot provided"

class ScreenGraph(BaseModel):
    screens: conlist(Screen, min_length=1)
    transitions: list[Transition]
    unresolved: list[UnresolvedAction]
    entry_screen_id: str

    @model_validator(mode="after")
    def _refs_valid(self):
        ids = {s.id for s in self.screens}
        if self.entry_screen_id not in ids:
            raise ValueError(f"entry_screen_id {self.entry_screen_id!r} not in screens")
        for t in self.transitions:
            if t.from_screen not in ids or t.to_screen not in ids:
                raise ValueError("transition references unknown screen id")
        return self

# ── Sampled agent (per-walk concrete persona) ────────────────────
class SampledAgent(BaseModel):
    agent_id: str                        # "a_<cluster>_<n>"
    parent_agent_id: Optional[str] = None
    cluster_id: str                      # PersonaGroup.id
    cluster_name: str
    # concrete sampled scalars — ranges collapsed
    age: int
    tech_savviness: int = Field(ge=1, le=5)
    patience_threshold: Literal["low","medium","high"]
    pricing_sensitivity: int = Field(ge=1, le=5)
    primary_device: Literal["mobile","desktop","mixed"]
    # ...remaining PersonaGroup scalars flattened, lists kept as lists
    group: PersonaGroup                  # original group retained for prompt context
    personalized_backstory: str          # from seed_backstory LLM call; forks inherit parent's
    rng_seed: int                        # determinism marker for tests

# ── Per-turn agent decision (LLM tool output) ────────────────────
ActionKind = Literal["click_element","scroll","go_back","give_up","complete"]

class AlternativeAction(BaseModel):
    action: ActionKind
    target_element_id: Optional[str] = None
    reasoning: str

class EmotionalState(BaseModel):
    confusion:   int = Field(ge=1, le=5)
    frustration: int = Field(ge=1, le=5)
    interest:    int = Field(ge=1, le=5)
    trust:       int = Field(ge=1, le=5)

class AgentDecision(BaseModel):
    action: ActionKind
    target_element_id: Optional[str] = None     # required iff action == "click_element"
    reasoning: str
    confidence: int = Field(ge=1, le=5)
    emotional_state: EmotionalState
    estimated_seconds_on_screen: int = Field(ge=0, le=600)
    observed_issues: list[str] = Field(default_factory=list)
    alternative_actions: conlist(AlternativeAction, max_length=2) = Field(default_factory=list)

    @model_validator(mode="after")
    def _click_needs_target(self):
        if self.action == "click_element" and not self.target_element_id:
            raise ValueError("click_element requires target_element_id")
        return self
```

**Kept flat, not a discriminated union.** Anthropic's tool-use JSON-schema support for `Annotated[Union[...], Field(discriminator=...)]` is flaky; the `@model_validator` gives the same guarantee without surprising the model.

```python
# ── Paths / metrics ──────────────────────────────────────────────
class AgentStep(BaseModel):
    order: int
    screen_id: str
    decision: AgentDecision
    was_fork_point: bool = False
    elapsed_seconds_total: int

TerminalState = Literal["complete","give_up","dead_end","max_steps_reached","budget_stopped"]

class AgentPath(BaseModel):
    agent: SampledAgent
    steps: list[AgentStep]
    terminal_state: TerminalState
    screens_visited: list[str]
    fork_points: list[int]               # step orders where forks spawned
    cumulative_seconds: int
    tokens_used: int

class ActionDistribution(BaseModel):
    click_element: int = 0
    scroll: int = 0
    go_back: int = 0
    give_up: int = 0
    complete: int = 0

class ScreenMetrics(BaseModel):
    screen_id: str
    arrivals: int
    departures: dict[str, int]           # keys: "continued" | TerminalState values
    avg_emotional_state_on_arrival: EmotionalState
    avg_seconds: float
    action_distribution: ActionDistribution
    issues: list[str]

class DropOffPoint(BaseModel):
    step_index: int
    remaining_pct: float

class GlobalMetrics(BaseModel):
    total_agents: int
    completion_rate_overall: float
    completion_rate_by_cluster: dict[str, float]
    drop_off_curve: list[DropOffPoint]
    tokens_used_total: int
    top_friction_screens: list[str]      # top N by frustration + departure rate
    per_screen: list[ScreenMetrics]

# ── Categorized issues + report ──────────────────────────────────
TestCategory = Literal["accessibility","compliance","onboarding","activation","engagement_retention"]
Severity    = Literal["low","medium","high","critical"]

class CategorizedIssue(BaseModel):
    summary: str
    category: TestCategory
    severity: Severity
    evidence: list[str]                  # raw observed_issue strings
    affected_screens: list[str]

class CategorizedIssues(BaseModel):
    issues: list[CategorizedIssue]

class ClusterFinding(BaseModel):
    cluster_id: str
    cluster_name: str
    summary: str
    completion_rate: float
    key_friction: list[str]

class SimulationReport(BaseModel):
    executive_summary: str
    cluster_findings: conlist(ClusterFinding, min_length=1)
    top_friction_points: list[str]
    findings_by_category: dict[TestCategory, list[str]]
    recommended_next_tests: list[str]
    metrics: GlobalMetrics
    categorized_issues: CategorizedIssues

# ── Config + IO ──────────────────────────────────────────────────
class SimulationConfig(BaseModel):
    max_agents_budget: int = 150
    max_agents_per_cluster: int = 60
    max_depth: int = 25
    max_concurrent_llm_calls: int = 8
    hard_spend_cap_tokens: int = 5_000_000
    n_seed_per_group: int = 1
    history_window_k: int = 5
    give_up_frustration_streak: int = 2
    forks_per_decision: int = 2
    rng_seed: int = 0

class ForkSpec(BaseModel):
    parent_agent_id: str
    take_alternative_index: int          # 0 or 1 within the parent's alternative_actions

class SimulationInputs(BaseModel):
    groups: conlist(PersonaGroup, min_length=3, max_length=3)
    screenshots: list[UploadedFile]
    goal: Optional[str] = None
    screen_graph_override: Optional[ScreenGraph] = None   # caller-edited graph

class SimulationResult(BaseModel):
    screen_graph: ScreenGraph
    paths: list[AgentPath]
    report: SimulationReport
    budget_stopped: bool = False
    budgets_engaged: list[str] = Field(default_factory=list)  # e.g. ["max_agents_budget","hard_spend_cap_tokens"]
```

---

## 3. Data flow

```
SimulationInputs (3 PersonaGroups + screenshots + optional goal)
   │
   ▼
[parse_image × N  from persona_synthesis.parsers.image]
   │                   → list[ParsedFile with image_block]
   ▼
build_screen_graph ──(1 LLM call, multimodal, tool=emit_screen_graph)──▶ ScreenGraph
   │      (caller may pass screen_graph_override to skip)
   ▼
sample_seed_agents ──(n_seed × 3 LLM calls, tool=emit_backstory)──▶ list[SampledAgent]
   │
   ▼
┌──────────── runner.simulate loop ─────────────────────────────┐
│ thread-pool (max_concurrent_llm_calls)                        │
│ for each live agent, per turn:                                │
│   screen    = graph.screens[agent.current_screen]             │
│   decision  = agent_decision(...)  ──(1 LLM call/turn)──▶     │
│   metrics.record(screen, decision, tokens)                    │
│   if tokens_total ≥ cap: set budget_stopped, stop forks,      │
│                           let alive agents finish current turn│
│                           then break outer loop               │
│   forks    = should_fork(decision, totals, depth, cfg) [pure] │
│   spawn siblings (inherit history, take alternative action)   │
│   apply_transition(decision) → next_screen OR terminal_state  │
└───────────────────────────────────────────────────────────────┘
   │
   ▼
aggregate metrics → GlobalMetrics
   │
   ▼
categorize_issues ──(1 LLM call)──▶ CategorizedIssues
   │
   ▼
curate_traces (heuristic: per cluster → highest-friction, most-successful, median)
   │
   ▼
build_report ──(1 LLM call, sees metrics + 9 curated traces)──▶ SimulationReport
   │
   ▼
SimulationResult
```

---

## 4. LLM call map + cost estimate

Model: **claude-sonnet-4-6**. All calls use tool-use (`tool_choice={"type":"tool","name":"..."}`) with `input_schema` built from pydantic `model_json_schema()` — same pattern as `persona_synthesis/synthesize.py:_persona_tool_def`.

| Call | What gets sent | Input tok | Output tok | Multimodal |
|---|---|---|---|---|
| `build_screen_graph` | system (~1.2k) + N screenshots at 1568px (~1.6k tok each, say N=10 → 16k) + goal text | ~18,000 | ~3,000 | yes |
| `seed_backstory` × 3 | system (~0.6k) + 1 PersonaGroup JSON (~1.5k) + sampled trait dict (~0.3k) | ~2,400 | ~500 | no |
| `agent_decision` × 1,800 | system (~1.5k) + agent profile (~1.8k) + 1 screen image (~1.6k) + last-5 history JSON (~1.5k) + graph excerpt (~0.8k) + goal (~0.1k) | ~7,300 | ~500 | yes |
| `categorize_issues` | system (~0.8k) + deduped issues list (~5k assuming ~500 issues) | ~5,800 | ~2,000 | no |
| `build_report` | system (~1.5k) + metrics JSON (~4k) + categorized issues (~3k) + 9 curated traces (~9k) | ~17,500 | ~4,000 | no |

### Worked total at defaults (150 agents × 12 avg steps = 1,800 turns)

- screen_graph:     18k + 3k =            **21,000**
- 3 × backstory:    3 × 2.9k =            **8,700**
- 1,800 × decision: 1,800 × 7.8k =    **14,040,000**
- categorize:       5.8k + 2k =           **7,800**
- report:           17.5k + 4k =         **21,500**
- **Total ≈ 14.1 M tokens**

This is **2.8× over the 5 M hard cap**. At default settings the cap will engage early — effectively capping real runs at ~640 turns (~53 agents × 12 steps) unless prompt caching is on. This is intended behavior per spec ("if hit, abort further forks and finalize the report with what's been collected") — the system degrades gracefully. Implementation surfaces `budgets_engaged` in `SimulationResult` so callers see which cap fired.

**Recommended follow-up (not in this phase):** enable Anthropic prompt caching on `agent_decision`'s stable prefix (system + agent profile + graph excerpt) — repeats per-agent across turns. Estimated savings: ~60–70% on turns 2..N of each agent → total drops to ~5.5 M. A later micro-task, trivially added once the core pipeline is proven.

---

## 5. Public interfaces

```python
# screen_graph.py
def build_screen_graph(
    screenshots: list[UploadedFile],
    *,
    goal: str | None = None,
    provider: LLMProvider,
) -> ScreenGraph: ...

# sampling.py
def sample_seed_agents(
    groups: list[PersonaGroup],
    *,
    n_per_group: int = 1,
    provider: LLMProvider,
    rng_seed: int = 0,
) -> list[SampledAgent]: ...

# decisions.py
def agent_decision(
    agent: SampledAgent,
    screen: Screen,
    history: list[AgentStep],
    *,
    goal: str | None,
    graph: ScreenGraph,
    provider: LLMProvider,
) -> tuple[AgentDecision, int]:          # int = tokens used for this call
    ...

# forking.py — pure, no LLM
def should_fork(
    decision: AgentDecision,
    *,
    total_agents: int,
    agents_in_cluster: int,
    current_depth: int,
    parent_agent_id: str,
    graph: ScreenGraph,                  # to check "meaningfully different path"
    current_screen_id: str,
    config: SimulationConfig,
) -> list[ForkSpec]: ...

# runner.py
def simulate(
    inputs: SimulationInputs,
    *,
    provider: LLMProvider | None = None,
    config: SimulationConfig | None = None,
    on_event: Callable[[StreamEvent], None] | None = None,
) -> SimulationResult: ...

# categorize.py
def categorize_issues(
    observed: list[str],
    *,
    provider: LLMProvider,
) -> CategorizedIssues: ...

# report.py
def curate_traces(paths: list[AgentPath]) -> dict[str, list[AgentPath]]: ...   # heuristic, no LLM
def build_report(
    metrics: GlobalMetrics,
    issues: CategorizedIssues,
    curated_traces: dict[str, list[AgentPath]],
    *,
    provider: LLMProvider,
) -> SimulationReport: ...

# run.py — CLI
def main(argv: list[str] | None = None) -> int:
    # flags: --personas PATH  --screenshots DIR  --goal STR
    #        [--mock] [--config-json PATH] [--out PATH] [--graph-override PATH]
    # --mock wires a DummyProvider from fixtures so the CLI runs offline end-to-end
    ...
```

`simulate()` lazily imports `AnthropicProvider` (same trick as `synthesize_personas`) so offline tests don't pull the SDK at import time.

---

## 6. Test plan

All LLM-calling tests use the cloned `DummyProvider` + `make_dummy` pattern. The fixture is extended to stash `usage` in `ToolCallResult.raw` so the runner's budget accounting can be exercised.

**`test_screen_graph.py`**
1. Two small PNG fixtures + canned `emit_screen_graph` output → valid `ScreenGraph`, `entry_screen_id` set, refs validate.
2. Unresolved action is preserved end-to-end.
3. Bad `entry_screen_id` in the canned output → `SchemaValidationError` after one retry (mirror the synthesize retry pattern).
4. `provider.calls[0]["messages"][0]["content"]` contains N image blocks + a goal text block.

**`test_sampling.py`**
1. Same `rng_seed` → identical sampled traits across runs.
2. Categorical sampling respects the group's stated set.
3. Int ranges respected (e.g. `tech_savviness ∈ [1,5]`).
4. One LLM call per seed for backstory; no calls for forks (forks inherit parent backstory verbatim — tested at the runner layer).

**`test_agent_step.py`**
1. Canned `click_element` + valid `target_element_id` → parses.
2. Canned `click_element` with missing `target_element_id` → validation error (triggers retry).
3. History window: feed 10 prior steps, assert only last 5 appear in the prompt content.
4. `observed_issues` list forwarded intact.
5. Tokens from provider raw are surfaced in the return tuple.

**`test_fork_logic.py`** (pure — no LLM, no `DummyProvider` needed)
1. `confidence=3`, 2 distinct alt targets, under budget → 2 ForkSpecs.
2. `confidence=4` → `[]`.
3. `confidence=3` but both alternatives click the same element → `[]` (not meaningfully different).
4. Total agents at `max_agents_budget` → `[]`.
5. Cluster at `max_agents_per_cluster` → `[]`.
6. `current_depth >= max_depth` → `[]`.

**`test_runner_budget.py`** (DummyProvider canned with tuneable `usage`)
1. `hard_spend_cap_tokens=50_000` with ~6k per decision → terminates after ≤9 turns, `budget_stopped=True`, `budgets_engaged` contains the tripped cap, report still produced.
2. `max_agents_budget=5` → never more than 5 agents spawned even when forks would otherwise fire.
3. `max_depth=3` → no path exceeds 3 steps, terminal_state=`max_steps_reached`.
4. All agents receive `complete` → `budget_stopped=False`, `completion_rate_overall=1.0`.
5. Two consecutive `frustration=5` → terminal_state=`give_up`.
6. Click on an `UnresolvedAction` element → terminal_state=`dead_end`.

**`test_report.py`**
1. Canned `CategorizedIssues` + canned `SimulationReport` → `simulate()` returns well-formed `SimulationReport` with `cluster_findings` for all 3 clusters.
2. `curate_traces` picks highest-frustration, completed+fewest-steps, median-step paths per cluster (9 synthetic `AgentPath` objects, no LLM).
3. Report prompt receives metrics JSON + exactly 3 traces per cluster (assert via `provider.calls[-1]` content).
4. Zero agents complete → report still generates (`completion_rate=0`).

**`test_live.py`** — `@pytest.mark.live`, skipped by default. One end-to-end run against real Claude with 2 fixture screenshots, minimal `max_agents_budget=3`. Costs pennies.

---

## 7. Open questions — concrete answers

These resolve the four open questions in the brief. All can be overridden later.

**(a) Goal specification — Free text only.**
Designated "goal screen ID" creates a chicken-and-egg problem (caller needs graph IDs before the graph exists). Terminal `complete` is decided by the model reading the goal string each turn; the report compares completions vs. give-ups against it. This matches how product owners describe goals ("complete signup", "get to the dashboard").

**(b) Duplicate-purpose screens — `duplicate_of` field on `Screen`.**
The graph-builder prompt marks variants with `duplicate_of: "<canonical_id>"`. Canonical screen carries the element set; duplicates are alternate entry points. Metrics tallied on the canonical ID; transitions may point to either. One optional field, no new object type, lets the vision model express what it sees without forcing dedup.

**(c) Zero-transition graph — Fail loud (`GraphIncomplete`).**
`build_screen_graph` raises when `len(transitions) == 0 AND len(screens) > 1`. A single-screen graph is a legitimate degenerate case and allowed. A "first-impression mode" would produce something called a "simulation" that doesn't simulate — better to reject clearly and let the user upload connected screens.

**(d) Curated trace samples — Heuristic.**
Per cluster: highest-friction = max cumulative frustration across steps; most-successful = `terminal_state=="complete"` with fewest steps (tiebreak: least frustration); median = median step count among the remainder. Deterministic, zero extra LLM cost, easy to unit-test. The report-gen LLM call already supplies narrative judgment — no need for a separate curator call.

---

## 8. Verification (once implemented)

- `pytest persona_simulation/tests/` — all offline, no API key needed.
- `python -m persona_simulation.run --personas persona_simulation/tests/fixtures/sample_personas.json --screenshots persona_simulation/tests/fixtures/shots --goal "complete signup" --mock` — end-to-end offline dry run; prints `SimulationResult` JSON to stdout.
- `pytest -m live` (requires `ANTHROPIC_API_KEY`) — one real Claude call covering the full pipeline at `max_agents_budget=3`.

---

## 9. Deliberate non-goals (for this phase)

- No FastAPI endpoint wiring — unblocked but scoped to a follow-up once the CLI proves the module.
- No frontend integration.
- No prompt caching — noted as a cost follow-up.
- No async concurrency inside the runner beyond a bounded thread pool. If per-agent `AsyncAnthropic` is needed later, the `LLMProvider` Protocol can grow an `async_complete` sibling without breaking the existing surface.
