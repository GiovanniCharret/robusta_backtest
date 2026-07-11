# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A ground-up rebuild of **ROBUSTA**, a legacy financial backtesting system. The goal is an
**effective, interpretable predictive model of technical indicators** (e.g. `mma50`, `mme50` —
simple and exponential moving averages and similar financial indicators).

The legacy system has scientific testing gaps (*"furos científicos de testes"*). The rebuild's
mandate is to close them while keeping the model **as simple as possible**:

- Test very few variables, but test them extensively. Interpretability is a first-class goal.
- Evaluate **stepwise forward and backward** variable selection.
- Study **causal relationships** between variables — avoid heuristics, think structurally.
- Compare regression models to find which work best.

**nota do usuário** O sistema legado tem furos científicos de testes. Vamos cobrí-los e criar um modelo preditivo as simple as possible, mas eficaz de indicadores técnicos. 

**Current status: Phases 1–2 implemented, Phase 3 in planning.** The `mma` (moving-average
breakout) pipeline is built and tested (38 tests, e2e-verified on `^BVSP`). Phase 3 (nine more
indicator plug-ins + a unified ranked summary) is specced but not yet coded. `planning/PLAN.md`
tracks the live status per phase — read it first.

## Documentation workflow (read this before doing anything)

All project documentation lives in `planning/`. The conventions are strict:

- **`planning/PLAN.md` is the single source of truth.** All decisions, phases, and progress
  tracking live here. This is the key living document — read it first, update it as work happens.
- **Never edit `planning/PROJECT_BUILDING.md`.** It is a human-owned checklist for deciding *what*
  to build (not a task list for the AI). Treat it as read-only reference.
- `planning/BEHAVIORAL_GUIDELINES.md` — behavioral rules that apply to all work here (see below).

## Behavioral guidelines (from planning/BEHAVIORAL_GUIDELINES.md)

These bias toward caution over speed; use judgment on trivial tasks.

- **Think before coding.** State assumptions explicitly; if uncertain, ask. If multiple
  interpretations exist, surface them — don't pick silently. If a simpler approach exists, say so.
- **Simplicity first.** Minimum code that solves the problem, nothing speculative. No abstractions
  for single-use code, no unrequested configurability. If 200 lines could be 50, rewrite.
- **Surgical changes.** Touch only what the task requires. Don't refactor working code or "improve"
  adjacent code. Match existing style. Mention unrelated dead code rather than deleting it. Every
  changed line should trace directly to the request.
- **Goal-driven execution.** Turn tasks into verifiable goals (e.g. "fix the bug" → "write a test
  that reproduces it, then make it pass"). State a brief numbered plan with a verify step each.

## Files and folders that are NOT inputs

Do not treat these as entry points or code to build on — they are reference/personal material:

- `scripts legados/` — the legacy ROBUSTA notebook
  (`Robust Decisor -v11.4.2-- Age of Triggers-Persistence.ipynb`, ~1666 LOC). It is the
  **specification reference** for behavior to reproduce/improve, not code to extend in place.
- `minhas_notas/` — personal notes (regression-model study notebooks, the operational manual PDF,
  HTML effectiveness examples).
- `bug_fix/` — workspace for isolating bug reproductions (currently empty).

The legacy notebook's domain stack, for context, is: `yfinance` (price data), `pandas` /
`pandas_ta` (indicators), `sklearn.linear_model` and `scipy.stats` (modeling), plus `requests` /
`bs4` (scraping), `matplotlib`, `tqdm`, `icecream`.

## Code architecture (`src/robusta/`)

The whole system is one **linear pipeline that enriches a single "df-fundação"** (the OHLCV frame
from yfinance): every step *adds columns* to that same DataFrame rather than passing new objects
around, so any day can be reviewed row-by-row (a deliberate carry-over from the legacy notebook).

Data flow (`run_mma.py:main` orchestrates it):

1. **`data.py`** — `load_prices(ticker, period)` is the *only* module that touches the network
   (yfinance, relative window like `"10y"`). It normalizes to ordered OHLCV. Not unit-tested (network);
   its pure helper `normalize_ohlcv` is.
2. **`target.py`** — `add_labels(df, horizons)` appends the dependent variables per horizon `h`:
   `ret_{h}d` (continuous forward return `Close[t+h]/Close[t]-1`) and `y_{h}d` (its 0/1 sign).
3. **`indicators/`** — each indicator is a **plug-in module** matching the `base.py` `Indicator`
   protocol: `NAME`, `signal_col(**params) -> str`, `add_columns(df, **params) -> df`. Only `mma.py`
   exists so far. `add_columns` appends the MA value, the `above` state, the `_break` dummy (the
   independent variable), and optionally a `persistK` dummy (broke out *and* stayed above `k` more
   days, stamped one-shot on the confirmation day — no look-ahead leakage).
4. **`sweep.py`** — `run_sweep(df, indicator_module, param_grid, horizons)` is **indicator-agnostic**:
   it expands the grid, calls `add_columns`/`signal_col` via the injected module, and per combo ×
   horizon fits **two model families**, emitting **two summary rows** each.
5. **`modeling.py`** — the two families over the same predictor: `fit_logit` (Logit on `y_{h}d`,
   McFadden pseudo-R²) and `fit_ols` (OLS on `ret_{h}d`, classic R²). Both return the *identical flat
   schema* so the sweep treats every row alike; edge cases (too few events, perfect separation,
   numeric failure) return that schema with a `status` string instead of raising. `contingency_metrics`
   adds fail-safe 2×2 association measures (`odds_ratio`, `lift`, `fisher_p`) — logit rows only, NaN on ols.
6. **`run_mma.py`** — writes two `.xlsx` outputs to `OUTPUT_DIR`: `analysis_mma.xlsx` (the enriched
   df-fundação, one row/day) and `summary_mma.xlsx` (one row/model; a second `dicionário` sheet
   documents every column).

**All tunable knobs live in `config.py`** (ticker, period, MA windows, tolerances, persistences,
horizons, min_events, output dir) — the grid is their Cartesian product. Change parameters there;
no other file should need editing. Adding an indicator = writing one new module under `indicators/`
that satisfies the protocol — `sweep.py` does not change.

## Python environment

The project uses [`uv`](https://docs.astral.sh/uv/). On Windows PowerShell:

```powershell
# Install uv (once)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Activate the virtual environment
.venv\Scripts\activate

# Add dependencies, then freeze
uv pip install <package>
uv pip freeze > requirements.txt
```

## Commands

`pyproject.toml` sets `pythonpath = ["src"]` and `testpaths = ["tests"]`, so pytest needs no flags.

```powershell
uv run pytest                          # full suite (38 tests, no network — uses synthetic fixtures)
uv run pytest tests/test_mma.py        # one file
uv run pytest tests/test_mma.py::test_break_is_event_not_state      # one test
uv run pytest -k persist               # tests matching an expression

# Run the real pipeline (downloads prices via yfinance, writes output/*.xlsx).
# Needs src on PYTHONPATH because run_mma.py is invoked as a module:
$env:PYTHONPATH="src"; uv run python -m robusta.run_mma
```

The test suite is offline by design (network is confined to `data.py`, which is not unit-tested).
Follow TDD for new work, per the behavioral guidelines below.

## Note on this file

There is also a `CLAUDE.md.md` (double extension) in the repo root holding the original objective
notes — it appears to be a misnamed copy. Claude Code only auto-loads `CLAUDE.md`; treat that file
as superseded by this one.

## Project rules

- **Não faça alterações** em `planning/PROJECT_BUILDING.md`. Todas as decisões vivem em `planning/PLAN.MD`
- Toda a documentação estará em `planning` directory e o key document is PLAN.md
- Toda função com docstring explicando, nesta ordem: por que a função existe (o problema que ela resolve / o motivo de ser função separada); a lógica do input ao output, em fases numeradas (Entrada → Fase 1 → Fase 2 → … → Saída), descrevendo o que cada bloco transforma. Além disso, toda linha de código comentada — inclusive as que parecem óbvias.