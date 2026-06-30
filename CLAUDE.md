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

**Current status: planning phase. There is no application source code yet.** The work right now
is design and documentation, not implementation.

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

## Note on this file

There is also a `CLAUDE.md.md` (double extension) in the repo root holding the original objective
notes — it appears to be a misnamed copy. Claude Code only auto-loads `CLAUDE.md`; treat that file
as superseded by this one.

## Project rules

- **Não faça alterações** em `planning/PROJECT_BUILDING.md`. Todas as decisões vivem em `planning/PLAN.MD`
- Toda a documentação estará em `planning` directory e o key document is PLAN.md
- Toda função com docstring explicando, nesta ordem: por que a função existe (o problema que ela resolve / o motivo de ser função separada); a lógica do input ao output, em fases numeradas (Entrada → Fase 1 → Fase 2 → … → Saída), descrevendo o que cada bloco transforma. Além disso, toda linha de código comentada — inclusive as que parecem óbvias.