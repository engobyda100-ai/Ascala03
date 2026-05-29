# Wiring plan — local dev: frontend + new FastAPI server + 3 backends

## Context

The persona pipeline lives in three Python packages under `backend/`:
`persona_synthesis`, `persona_simulation`, `persona_report`.
The frontend at `project/` is a static React-via-CDN + Babel-standalone prototype that currently renders hardcoded data shaped to the backend Pydantic schemas.

Goal: a new top-level `server/` (FastAPI) wraps all three backends behind a tiny job-style HTTP API; the frontend swaps its hardcoded constants for `fetch` + 2-second polling; a `dev.sh` runs both processes; `samples/` makes the end-to-end click-through reproducible. Mock by default to avoid Claude spend; toggle to flip to real.

## Brief-vs-reality — three callouts

These differ from the brief; the plan picks a default.

1. **`persona_synthesis` has no built-in mock mode.** `persona_simulation` and `persona_report` ship `_CLIDummyProvider` + a `--mock` flag (loading canned tool responses from `tests/fixtures/`). `persona_synthesis` only takes an injectable `LLMProvider`; nothing more.
   **Default:** the new server, when `mock=true` for synthesis, **bypasses `synthesize_personas()`** and returns a static `SynthesisResult` from `server/mocks/mock_synthesis_result.json`. That JSON is derived 1:1 from the existing `SYNTHESIS_RESULT` constant in `Panel3.jsx:17–111` so the demo flow keeps the same personas. Cheaper and lower-risk than re-implementing a mock provider for the synthesis tool calls.

2. **`backend/app.py` is an existing FastAPI server.** It runs on port **8787** and exposes `/synthesize` + `/synthesize/stream` (synthesis only). The brief says "create a new top-level `server/`".
   **Default:** leave `backend/app.py` as-is, don't start it from `dev.sh`. The new `server/` on port 8000 covers all three stages.

3. **Frontend "context files" upload is a placeholder.** `Panel1.jsx:67 addContextFile()` synthesizes a fake `{name, size}` chip — there's no real file picker. Synthesis needs real bytes.
   **Default:** wire a hidden `<input type="file" multiple>` to that dropzone (mirrors the screenshots picker at `Panel1.jsx:115–122`) and stash the original `File` in state alongside `name/size`. Tiny addition; necessary for any non-mock synthesis call.

---

## Server (`/Users/ob/ascala/server/`)

### File structure

```
server/
├── main.py             # FastAPI app, routes, CORS, /api/health, lifespan startup hook
├── runs.py             # in-memory registry: dict[run_id → RunState]
├── workers.py          # background tasks: run_synthesis / run_simulation / run_report
├── mocks.py            # synthesis mock loader; build_simulation_mock_provider; build_report_mock_provider
├── storage.py          # tempdir-per-run helpers + 24h cleanup sweeper
├── mocks/
│   └── mock_synthesis_result.json
├── pyproject.toml      # editable-install package; depends on the backend package
└── README.md           # one-liner pointing to project root
```

Reuses the backend Python API directly:
- `from persona_synthesis import SynthesisInputs, UploadedFile, ChatMessage, synthesize_personas` (real mode only)
- `from persona_simulation import simulate, SimulationInputs, SimulationConfig`; `from persona_simulation.schema import SimulationResult`
- `from persona_report import generate_report`
- For sim/report mock providers, lift the implementations from `persona_simulation/run.py:84–147` and `persona_report/run.py:25–68` into `server/mocks.py`.

### `RunState`

```python
class RunState(BaseModel):
    run_id: str
    kind: Literal["synthesis", "simulation", "report"]
    status: Literal["running", "done", "failed"]
    result: Optional[dict] = None        # model_dump() of SynthesisResult / SimulationResult / Report
    error: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    tempdir: Optional[Path] = None
```

Run IDs: `f"{prefix}_{uuid.uuid4().hex[:12]}"` (`syn_…`, `sim_…`, `rep_…`).

### Endpoint contracts

All endpoints under `/api/`. CORS via `allow_origin_regex=r"http://localhost(:\d+)?"`.

#### `POST /api/synthesis/start` — `multipart/form-data`

Form fields:
- `chat_transcript: str` — JSON-encoded `[{role:"user"|"bot", text:str}, …]` (may be `"[]"`)
- `product_url: str` — optional; empty string → None
- `mock: str` — `"true"` | `"false"` (default `"false"`)
- `files: UploadFile[]` — repeated, optional (PDF/DOCX/MD/TXT/CSV/PNG)

Validation: at least one of `files`, non-empty `chat_transcript`, or non-empty `product_url`.

Response 200: `{"run_id": "syn_…"}`
Errors: 400 if all inputs empty; 422 if `chat_transcript` is not valid JSON or items don't fit `ChatMessage`.

#### `GET /api/synthesis/{run_id}`

```
running  → {"status": "running"}
done     → {"status": "done",   "result": <SynthesisResult.model_dump()>}
failed   → {"status": "failed", "error":  "<message>"}
```
404 for unknown id.

#### `POST /api/simulation/start` — `multipart/form-data`

Form fields:
- `synthesis_run_id: str` — must exist + be `done`. Server pulls `groups` from its stored result.
- `goal: str` — optional
- `budget_overrides: str` — optional JSON, partial `SimulationConfig`; merged into defaults.
- `mock: str` — same as synthesis
- `screenshots: UploadFile[]` — repeated, ≥1, PNG/JPG/JPEG/GIF/WEBP

Response 200: `{"run_id": "sim_…"}`
Errors: 400 if `synthesis_run_id` unknown / not `done`; 400 if no screenshots; 422 if `budget_overrides` malformed.

#### `GET /api/simulation/{run_id}` — same shape; result is `SimulationResult`.

#### `POST /api/report/start` — `application/json`

```json
{ "simulation_run_id": "sim_…", "mock": false }
```
Response 200: `{"run_id": "rep_…"}`
Errors: 400 if `simulation_run_id` unknown / not `done`.

#### `GET /api/report/{run_id}` — same shape; result is `Report`.

#### `GET /api/health` → `{"status":"ok"}`

### Background workers

- `BackgroundTasks` schedules each `run_*` worker.
- Worker writes results back to its `RunState`. Top-level `try/except` catches `SchemaValidationError`, `ValueError`, and `Exception` → `status="failed"`, `error=str(e)`. **No silent fallback to mock on failure.**
- Tempdir per run: `tempfile.mkdtemp(prefix=run_id+"_")`. Synthesis files written there; bytes passed to the backend via `UploadedFile(name=…, mime=…, data=<read>)`; same for simulation screenshots. Tempdir deleted at worker finish.
- A 5-minute interval sweeper (lifespan task) deletes any tempdir > 24 h old — defensive.

### Mock plumbing per stage

| Stage | `mock=true` | `mock=false` |
|---|---|---|
| synthesis  | Return `SynthesisResult.model_validate_json(server/mocks/mock_synthesis_result.json)` | `synthesize_personas(SynthesisInputs(files, chat_messages, product_url))` |
| simulation | `simulate(inputs, provider=_build_simulation_mock_provider(persona_simulation/tests/fixtures))` | `simulate(inputs)` |
| report     | `generate_report(sim, provider=_build_report_mock_provider(persona_report/tests/fixtures))` | `generate_report(sim)` |

---

## Frontend wiring (`/Users/ob/ascala/project/`)

### Stack

Static prototype. `Ascala Prototype.html` loads React 18 UMD + `@babel/standalone`, then 6 `.jsx` files via `<script type="text/babel">`. No npm, no bundler, no TS. Served by `python3 -m http.server 5173`.

### New: `project/config.js` (plain JS, before all `.jsx`)

```js
window.ASCALA_CONFIG = {
  API_BASE_URL: 'http://localhost:8000',
  DEFAULT_MOCK_MODE: true,
  POLL_INTERVAL_MS: 2000,
};
```

### New: `project/api.jsx` (loaded after `icons.jsx`, before `Login.jsx`)

Exports on `window.AscalaAPI`:
- `startSynthesis({files, chatTranscript, productUrl, mock}) → Promise<run_id>` — `FormData` POST
- `startSimulation({synthesisRunId, screenshots, goal, mock, budgetOverrides}) → Promise<run_id>`
- `startReport({simulationRunId, mock}) → Promise<run_id>` — JSON POST
- `poll(kind, runId) → Promise<{status, result?, error?}>`
- `useRun(kind, runId) → {status, result, error}` — custom hook, polls every `POLL_INTERVAL_MS`, stops on terminal status.

### Mock-data locations and replacements

| # | File:Line | Current | Replacement |
|---|---|---|---|
| 1 | `Panel3.jsx:17–111` `SYNTHESIS_RESULT` | hardcoded | **delete.** App holds `synthesisResult`; passed into Studio→PersonaTab. |
| 2 | `Panel3.jsx:171–174` `generate()` setTimeout | fake delay | replaced by polling. |
| 3 | `Panel3.jsx:177–188` `personas = SYNTHESIS_RESULT.groups.map(...)` | reads global | reads `props.synthesisResult.groups.map(...)` |
| 4 | `Panel3.jsx:326` `const totalAgents = SIM_RESULT.report.metrics.total_agents` | reads global | `props.simulationResult?.report.metrics.total_agents ?? 0` |
| 5 | `Panel3.jsx:331–345` simulated progress | 4.5s fake | progress ramps until poll says `done`/`failed`. |
| 6 | `Panel3.jsx:441` `REPORT.test_type_reports.find(...)` | reads global | `props.report.test_type_reports.find(...)` |
| 7 | `Report.jsx:10–205` `SIM_RESULT` const | hardcoded | **delete.** App holds `simulationResult`; passed into Report modal. |
| 8 | `Report.jsx:207` `window.SIM_RESULT = SIM_RESULT` | global publish | **delete.** |
| 9 | `Report.jsx:220–559` `REPORT` const | hardcoded | **delete.** App holds `report`; passed into Report modal. |
| 10 | `Report.jsx:850+` `REPORT.test_type_reports.find(...)` | reads global | `props.report.test_type_reports` |
| 11 | `Panel3.jsx:5–14` `UNIVERSAL_TESTS`/`PERSONA_TESTS` | hardcoded | **kept.** UI-only metadata. |
| 12 | `Panel3.jsx:314–322` `makeSimSteps()` | hardcoded | **kept.** Cosmetic copy. |
| 13 | `Panel2.jsx:5–22` `COACH_REPLIES` | hardcoded | **kept.** Discovery-mode coaching UI; user messages collected as `chat_transcript`. |

### Mock-mode toggle

Bottom of `Studio` in `Panel3.jsx:471–502`. Checkbox + status hint. `mockMode` lifted to App; passed via props.

### Error rendering (no silent fallback)

Each consumer of `useRun` checks `status === 'failed'` and renders an `.error-block`:
- `PersonaTab`: error + `Try again` (clears synthesisRunId).
- `SimulationTab`: error + `Back` returns to confirm.
- `Report` modal: error block.

### File-picker fix (`Panel1.jsx`)

Hidden `<input type="file">` for context files; capture `File` refs alongside `{name, size, url}` for both context files and screenshots.

---

## `dev.sh` (project root)

```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "warn: ANTHROPIC_API_KEY not set — real (non-mock) calls will fail."
fi

uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload &
SERVER_PID=$!

( cd project && python3 -m http.server 5173 ) &
FRONT_PID=$!

cleanup() { echo; echo "shutting down..."; kill $SERVER_PID $FRONT_PID 2>/dev/null || true; wait 2>/dev/null || true; }
trap cleanup INT TERM EXIT

cat <<EOF

  server:   http://localhost:8000      (docs at /docs)
  frontend: http://localhost:5173/Ascala%20Prototype.html

  Press Ctrl+C to stop.
EOF
wait
```

---

## `samples/` (project root)

```
samples/
├── chat_transcript.json     # 3-turn user-only transcript
├── context.md               # 1-page fabricated PRD
├── screenshots/
│   ├── 01_signup.png
│   ├── 02_pricing.png
│   ├── 03_onboarding.png
│   └── 04_done.png
├── goal.txt
└── README.md
```

---

## Root README updates

1. **Prerequisites:** Python 3.11+, `pip`, `ANTHROPIC_API_KEY` for real mode, modern browser.
2. **Install:** `pip install -e backend && pip install -e server`.
3. **Run:** `./dev.sh`. Open `http://localhost:5173/Ascala%20Prototype.html`.
4. **Mock toggle:** bottom of Studio Space; on by default.
5. **Sample flow:** drag `samples/screenshots/*.png` into Shots; upload `samples/context.md`; chat lines from `samples/chat_transcript.json`; "Generate Persona" → all six tests → "Run simulation" → click any test row.
6. **Troubleshooting:** port conflicts (`lsof -i :8000`), missing API key (mock mode works without it), schema mismatches (real responses surface as `failed` with the validation error), stuck "running" (server logs in `dev.sh` terminal).

---

## Verification (post-implementation)

1. `./dev.sh` starts both processes; `curl http://localhost:8000/api/health` returns `{"status":"ok"}`.
2. **Mock end-to-end:** mock toggle ON. Drop samples + chat lines, "Generate Persona" → 3 personas, all six tests → simulation `done` < 5s, every test row opens the report.
3. **Failure path:** kill server mid-run → frontend flips to `failed` with a clear error block + retry.
4. **Real-mode smoke (synthesis only):** mock OFF + key set → response validates and renders.

---

## Files to add / edit

**New**
- `server/main.py`, `server/runs.py`, `server/workers.py`, `server/mocks.py`, `server/storage.py`
- `server/mocks/mock_synthesis_result.json`, `server/pyproject.toml`, `server/README.md`
- `project/config.js`, `project/api.jsx`
- `dev.sh`, `samples/{chat_transcript.json,context.md,goal.txt,README.md}`, `samples/screenshots/01..04_*.png`
- `WIRING_PLAN.md`

**Edit**
- `project/Ascala Prototype.html` — script tags + lifted state.
- `project/Panel1.jsx` — real context-file picker + capture File refs.
- `project/Panel3.jsx` — drop SYNTHESIS_RESULT; consume props; studio-footer mock toggle.
- `project/Report.jsx` — drop SIM_RESULT/REPORT; consume props.
- `project/styles.css` — ≈12 lines.
- `/Users/ob/ascala/README.md`.

## Out of scope

Backend prompts/schemas/logic untouched. No DB/queue/cache/auth. No bundler, no TS migration. No WebSockets/SSE. No new build steps beyond `pip install` + `python3 -m http.server`.
