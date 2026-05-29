# Ascala — local dev

Persona synthesis → simulation → report, plus the React prototype, wired
through a small FastAPI server. Mock by default so clicking around doesn't
spend Claude credits.

See `WIRING_PLAN.md` for the full plan; this file is the operator's guide.

## Prerequisites

- **Python 3.11+** (the backend pins `requires-python = ">=3.11"`)
- `pip`, a modern browser
- `ANTHROPIC_API_KEY` — only needed when you flip the mock toggle off

No npm, no bundler. The frontend is static HTML + JSX transpiled in the
browser by Babel-standalone.

## One-time install

```bash
pip install -e backend
pip install -e server
```

A virtualenv is recommended:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e backend && pip install -e server
```

## Run

```bash
./dev.sh
```

Then open http://localhost:5173/Ascala%20Prototype.html

`dev.sh` starts:
- the FastAPI server on `:8000` (Swagger at `/docs`)
- a static Python HTTP server for the frontend on `:5173`

`Ctrl+C` stops both.

## How the mock toggle works

Bottom of the **Studio Space** panel. **On by default.**

- ON  → server returns canned responses; no Claude calls; ~2 s per stage.
- OFF → server runs `synthesize_personas()`, `simulate()`, `generate_report()`
  for real. Synthesis ≈ 30–60 s; simulation runs for several minutes
  depending on the agent budget; report ≈ 30–60 s after that. Errors
  bubble back to the UI as a `failed` state — there is no silent fall-through
  to mock data.

## End-to-end with sample inputs

`samples/` holds one complete input set.

1. **Left panel ("Project Assets"):**
   - Switch the product toggle to **Shots** and select all four PNGs in
     `samples/screenshots/`.
   - Under **Context Files**, click the dropzone and pick
     `samples/context.md`.
2. **Middle panel ("Ascala Intelligence"):** paste each `text` from
   `samples/chat_transcript.json` as a chat message (one at a time, hit Enter
   between them).
3. **Right panel ("Studio Space"):**
   - Confirm **Mock mode** is on (footer of this panel).
   - Click **Generate Persona**. After the run, three persona cards appear.
   - **Continue to tests** → tick all six tests → **Continue**.
   - **Run simulation**. The progress bar fills until the backend reports
     `done`; results rows appear with confidence pills.
   - Click any test row (or the Executive Summary banner) to open the report
     modal. Charts, fixes, and scenarios all render from the real backend
     response.

To do the same end-to-end against real Claude, untick the toggle, ensure
`ANTHROPIC_API_KEY` is set in your shell before running `./dev.sh`, and
expect each stage to take significantly longer.

## Troubleshooting

- **Port 8000 / 5173 in use** → `lsof -i :8000` (or `:5173`), kill the
  offending process, or edit the ports in `dev.sh`.
- **`ANTHROPIC_API_KEY` not set** → mock mode works without it. With the
  toggle off, you'll see a `failed` state in the relevant tab with the
  underlying error from the SDK.
- **Schema mismatch at runtime** → real backend responses are validated
  against the Pydantic schemas in `backend/persona_*/schema.py`. A
  validation failure shows as a `failed` state with the validation error;
  see `project/RECONCILIATION.md` for what was already aligned.
- **"Stuck running"** → the server logs to the terminal that ran `dev.sh`.
  Mock runs complete in < 5 s; real synthesis 30–60 s; real simulation
  several minutes (depends on `max_agents_budget`); real report 30–60 s.
- **Python 3.9 system default** → on macOS `which python3` may point at
  `/usr/bin/python3` (3.9). Install 3.11+ via Homebrew (`brew install
  python@3.13`) and create the venv with `/opt/homebrew/bin/python3.13 -m
  venv .venv`.

## Layout

```
ascala/
├── backend/                  # the three persona packages (unchanged logic)
│   ├── persona_synthesis/
│   ├── persona_simulation/
│   └── persona_report/
├── server/                   # FastAPI app wrapping all three (this PR)
├── project/                  # static React prototype (wired this PR)
├── samples/                  # sample inputs for the dev click-through
├── dev.sh
└── WIRING_PLAN.md            # implementation plan and contracts
```
