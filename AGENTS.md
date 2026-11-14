# AGENTS.md — how humans and AI agents work in this repository

_Adapted from the two-agent operating manual in Yaseen Abdelal's AgroTwin repo (github.com/Yaseen-Saad/AgroTwin),
rewritten for this codebase's real layout. AI-generated (Claude, Anthropic) under human review._

> Version: see `VERSION` · Live state: `agents/STATUS.md` · Next work: `agents/TASKS.md` · Pick-up guide: `CONTINUE.md`

## 1. Read order (every new session, human or AI)

1. `CONTINUE.md`: what exists, how to run it, what's next.
2. `agents/STATUS.md` and `agents/TASKS.md`: the live board.
3. `agents/DECISIONS.md`: why things are the way they are (append-only).
4. `docs/METHODS.md`, `docs/DATA_SOURCES.md`: the science and every dataset.
5. `backend/config.py`: every editable assumption with its tag.

## 2. Prime directives

1. **Every number carries a source tag**: `nasa:<product>`, `computed`, `scout:<run_id>`, `quoted:<url>` or
   `assumption:<name>`. No exceptions, including chat replies and UI mock-ups.
2. **Ranges, not promises.** Never show one number where an ensemble exists. Never write "will", "guaranteed"
   or "certain" about an outcome, in any language.
3. **Honest modes.** `LIVE`, `REPLAY`, `SIMULATED`, `NONE` travel with robot data end to end and are always visible.
   Until the Verdex robot posts real runs, robot data is SIMULATED, and the demo says so out loud.
4. **No invented facts.** A coefficient, price or citation that can't be sourced becomes `assumption:<name>`
   in `backend/config.py` or `data/prices.csv`, editable, and listed as a weakness.
5. **Computed, never typed.** Validation numbers come from `qa/*.py` and are read live by the app and `/methods`.
   Never paste a metric into docs without the script that produces it.
6. **Disclose AI.** Header comment in every AI-written code file, an entry in `docs/AI_USE.md`, and the submission's AI field.
7. **No NASA logos, flags or insignia.** Text references to datasets are fine.
8. **Secrets stay out.** `farming_robot/` (camera password in `config.yaml`) is never copied into this repo.
   `.env`, `data/scout/`, `data/farms/`, `data/audio/` and `data/training/raw/` are git-ignored.

## 3. Ownership map

One writer per path per work session. Cross-folder needs go in `agents/MESSAGES.md`.

| Area | Paths | Owner | Notes |
|---|---|---|---|
| Data access | `backend/data_sources.py`, `backend/outlook.py`, `scripts/precache.py`, `scripts/fetch_*.py`, `data/cache/` | Builder | NASA POWER, MODIS (ORNL), SoilGrids, Open-Meteo |
| Engine | `backend/waterbalance.py`, `replay.py`, `crops.py`, `soil.py`, `history.py`, `config.py` | Builder | FAO-56 balance, replay, ranking |
| Economics | `backend/econ.py`, `data/prices.csv` | Builder | every price row quoted or tagged |
| Fusion and robot | `backend/fusion.py`, `scout.py`, `robot.py`, `disease.py`, `scripts/robot_bridge.py`, `contracts/` | Builder | robot runs SIMULATED until real |
| Model | `backend/pulse.py`, `backend/models/`, `qa/pulse_train.py` | Builder | Field Pulse; retrain → `qa/PULSE.md` |
| Assistant | `backend/chat.py`, `backend/council.py`, `frontend/chat.js` | Lead | Number Auditor guards every AI number |
| Unique features | `backend/unique.py` | Lead | time machine, canal mode |
| API | `backend/app.py`, `backend/contract.py` | Lead | `/api/*`, v1 contract |
| Front end | `frontend/` | Lead | no build step; Leaflet and Plotly vendored |
| QA | `qa/`, `tests/` | QA (read-only elsewhere) | `make test`, `make validate` |
| Docs and pitch | `README.md`, `docs/`, `CHANGELOG.md`, `CONTINUE.md`, `agents/` | Lead | |

People: **Ali Kotb** (lead, Verdex robot), **Mostafa Dawood** (Verdex robot, leaf model), **Yaseen Abdelal** (AgroTwin
plan and scaffold). AI: Claude Code sessions act as Builder or Lead as assigned on the board.

## 4. Definition of done

Done means the lead can run the command and see it pass:

| Change | Command | Pass condition |
|---|---|---|
| any code | `make test` | all tests green |
| engine, fusion | `make validate` | `qa/REPORT.md` regenerated, no new failures |
| forecasting | `python qa/backtest.py` | `qa/BACKTEST.md` regenerated, skill reported vs baselines |
| Field Pulse | `python qa/pulse_train.py` | `qa/PULSE.md` regenerated; 80% range coverage between 70% and 90% |
| front end | open `/`, `/methods`, Arabic + English, Simple + Advanced, all three lenses, 375 px wide | no console errors |
| assistant | ask the five suggested questions in both languages | each answer lists the tools it used |

## 5. Versioning and git

- `VERSION` is the single source of truth; bump it with `CHANGELOG.md` in the same commit.
  MAJOR = contract break, MINOR = new capability or endpoint, PATCH = fixes and docs.
- Commit style: `feat(model): …`, `fix(chat): …`, `docs: …`. Commit only when asked.
- Large pushes over this network fail; push in chunks with retries
  (`for a in 1 2 3 4; do timeout 240 git push -q origin main && break; sleep 5; done`).

## 6. Escalation

Blocked for more than 20 minutes → write it in `agents/MESSAGES.md` with what you tried, then take the next
unblocked task. Anything not green by the deadline is cut, not extended.
