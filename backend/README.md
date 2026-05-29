# Ascala Backend

Two modules, same stack:

1. **`persona_synthesis/`** — raw context (files + chat) → 3 `PersonaGroup`s
2. **`persona_simulation/`** — those 3 groups + screenshots → multi-agent walkthrough + narrative report

See the `## Simulation stage` section below for the second module.

---

# Ascala · Persona Synthesis Backend

Turns raw context (uploaded files or a chat transcript) about a SaaS app's target market into **3 PersonaGroups** — behavioral clusters used downstream to simulate user testing.

Public entrypoint:

```python
from persona_synthesis import synthesize_personas, SynthesisInputs, ChatMessage, UploadedFile

result = synthesize_personas(SynthesisInputs(
    files=[UploadedFile(name="prd.pdf", mime="application/pdf", data=open("prd.pdf","rb").read())],
    chat_messages=[ChatMessage(role="user", text="Early-stage founders validating a B2B tool")],
))
print(result.groups)           # [PersonaGroup, PersonaGroup, PersonaGroup]
print(result.context_summary)  # ContextSummary used to generate them
```

## Data flow

```
SynthesisInputs
  ├── files[]       → parsers (pdf/csv/text/image) → ParsedFile[]
  └── chat_messages → formatted transcript

          ↓

summarize_files(ParsedFile[])  → ContextSummary_A  ┐
summarize_chat(messages)       → ContextSummary_B  ┼→ merge.combine()
                                                    ↓
                                            ContextSummary

          ↓  (system prompt + summary + image blocks)

Claude Messages API — tool_choice=emit_personas (input_schema = PersonaBundle.model_json_schema())

          ↓

tool_use.input → PersonaBundle (pydantic validates: 3 groups, shares sum ~100)
  ├── success  → SynthesisResult(groups, context_summary)
  └── ValidationError → 1 retry with stricter system prompt → SchemaValidationError
```

All three prompt files live in `./prompts/` and are hot-editable — iterate without touching code.

## Run the service

```bash
cd /Users/ob/ascala/backend
python -m venv .venv && source .venv/bin/activate
pip install -e .[test]
cp .env.example .env   # paste ANTHROPIC_API_KEY
uvicorn app:app --reload --port 8787
```

- Swagger UI: <http://localhost:8787/docs> — upload files + paste chat, hit Execute.
- Health: `GET /health`
- Synthesize: `POST /synthesize` (multipart: `payload` JSON + repeated `files`)
- Streaming: `POST /synthesize/stream` (SSE)

## Tests

```bash
pytest                    # all offline, no API key needed
pytest -m live            # one real Claude call; costs pennies
```

The test suite uses a `DummyProvider` that returns canned JSON from `tests/fixtures/`. The `synthesize_personas` contract is validated end-to-end without ever hitting the network.

## Swapping the LLM provider

The `persona_synthesis.llm.base.LLMProvider` Protocol is the only seam. It has two methods:

```python
class LLMProvider(Protocol):
    def complete(self, *, system, messages, tools, tool_choice) -> ToolCallResult: ...
    def stream(self, *, system, messages, tools, tool_choice) -> Iterator[StreamEvent]: ...
```

To use OpenAI / Gemini / local Llama:

1. Implement the Protocol in `persona_synthesis/llm/<provider>_client.py`. Translate the `tools`/`tool_choice` args into the provider's equivalent (OpenAI's `tools=[{"type":"function", ...}]`, Gemini's `function_declarations`, etc.). Return `ToolCallResult(name, input)`.
2. Inject it:

```python
from persona_synthesis import synthesize_personas
from persona_synthesis.llm.openai_client import OpenAIProvider

result = synthesize_personas(inputs, provider=OpenAIProvider())
```

The prompt files (`prompts/*.md`) are reusable unchanged — only the tool-call translation changes per provider.

## Directory map

```
app.py                          FastAPI server
persona_synthesis/
  synthesize.py                 orchestrator (public API)
  schema.py                     all pydantic models
  errors.py                     SynthesisError, SchemaValidationError
  llm/                          provider swap seam
  summarizers/                  files + chat → ContextSummary
  parsers/                      pdf/csv/text/image → ParsedFile
prompts/                        hot-editable system prompts
tests/                          offline unit + marked live test
```

---

## Simulation stage

The `persona_simulation/` module consumes three `PersonaGroup`s (from the synthesis stage) plus uploaded prototype screenshots and runs a multi-agent walkthrough: many simulated individuals, each sampled from a group, walk through the screens, face ambiguous choices that can fork them into siblings, and log friction. The output is a narrative report plus structured metrics.

### Public API

```python
from persona_simulation import simulate, SimulationInputs
from persona_synthesis import PersonaGroup, UploadedFile

result = simulate(SimulationInputs(
    groups=[pg1, pg2, pg3],
    screenshots=[UploadedFile(name="s1.png", mime="image/png", data=open("s1.png","rb").read()),
                 UploadedFile(name="s2.png", mime="image/png", data=open("s2.png","rb").read())],
    goal="complete signup",
))
print(result.report.executive_summary)
print(result.report.metrics.completion_rate_overall)
```

### Pipeline

1. **Screen-graph build** — one multimodal Claude call looks at all screenshots and emits a `ScreenGraph` (screens, interactive elements, transitions, dead ends, entry screen).
2. **Seed sampling** — for each PersonaGroup, sample concrete trait values (age, tech savviness, etc.) and call Claude once per seed to personalize a backstory.
3. **Walk** — per live agent, per turn, one Claude call returns a structured `AgentDecision` (action + target + reasoning + confidence + emotional state + observed issues + alternative actions).
4. **Forking** — pure deterministic rule: when an agent's confidence is low and an alternative leads to a meaningfully different screen, spawn a sibling that takes the alternative path. No extra LLM call.
5. **Termination** — per-agent: `complete`, `give_up`, `dead_end`, `max_steps_reached`, `budget_stopped`.
6. **Categorize** — one post-sim Claude call buckets observed_issues into the 5 test categories (accessibility, compliance, onboarding, activation, engagement_retention).
7. **Report** — one final Claude call writes the narrative report, seeded with metrics + categorized issues + a curated trace bundle (highest-friction / most-successful / median per cluster).

### Budgets (configurable via `SimulationConfig`)

- `max_agents_budget` = 150 total across all clusters
- `max_agents_per_cluster` = 60
- `max_depth` = 25 steps per agent
- `max_concurrent_llm_calls` = 8
- `hard_spend_cap_tokens` = 5,000,000 per run

When a cap engages the runner stops forking and finalizes the report on collected data. `SimulationResult.budget_stopped` and `budgets_engaged` surface which cap fired.

**Cost note:** at defaults, a full run (~150 agents × ~12 turns) is ~14M tokens — 2.8× over the 5M cap. This is by design: the cap engages, the run finalizes gracefully, and the report includes whatever was collected. Prompt caching on the agent-decision turn (reusing the system + persona + graph excerpt prefix) brings the expected total to ~5.5M. That optimization is a trivial follow-up.

### CLI

```bash
python -m persona_simulation.run \
  --personas persona_simulation/tests/fixtures/sample_personas.json \
  --screenshots persona_simulation/tests/fixtures/shots \
  --goal "complete signup" \
  --mock
```

Flags: `--personas`, `--screenshots`, `--goal`, `--mock` (use bundled fixture responses, no network), `--config-json`, `--graph-override`, `--out`.

### Tests

```bash
pytest                    # 76 tests, all offline, no API key needed
pytest -m live            # one real end-to-end call at tiny budgets
```

Test files (7):
- `test_screen_graph.py` — graph-build, retry, `GraphIncomplete`
- `test_sampling.py` — deterministic RNG, one-call-per-seed, range respect
- `test_agent_step.py` — decision parsing, retry on missing target, history window, token accounting
- `test_fork_logic.py` — pure rule coverage (no LLM)
- `test_runner_budget.py` — completion path, max_depth, give_up streak, dead_end, token cap, agent cap
- `test_report.py` — `curate_traces` + `build_report` + category-key padding
- `test_live.py` — gated off by default

### Swapping the LLM provider

Same seam as `persona_synthesis` — implement `LLMProvider` in `persona_synthesis/llm/<provider>_client.py` and pass it via `simulate(inputs, provider=MyProvider())`. The prompt files in `persona_simulation/prompts/` are reusable unchanged; only the tool-schema translation changes per provider.
