# PLAN — ROBUSTA Rebuild

> Documento-fonte do projeto. Decisões e progresso vivem aqui.
> Glossário de status: `[ ]` pendente · `[x]` concluído · `[a]` anulado · `[f]` revisão futura · `[n]` não se aplica · `[r]` rollback/falhou.

## Documentos

- **Design (spec):** `planning/2026-06-29-robusta-rebuild-design.md`
- **Plano de implementação:** `planning/2026-06-29-robusta-rebuild-plan.md`
- **Apoio visual:** `planning/robusta-design-explainer.html` e `planning/robusta-plan-explainer.html`
- **Mapa de testes:** `planning/TESTES.md` (cobertura das 7 fases + lacunas priorizadas)

## Decisões travadas (2026-06-29)

- **Duas famílias de modelo por sweep:** Logística sobre `y_{h}d` (0/1, pseudo-R² McFadden) **e** OLS sobre `ret_{h}d` (contínuo, R² clássico). Summary em formato longo com coluna `family`.
- **Seleção de variáveis** (stepwise/Lasso/SFS dos notebooks) é **futuro** — precisa de multi-preditor.
- **Ticker único** via `yfinance`; carga parametrizada por ticker/período.
- Variável independente = **dummy de rompimento** (Close cruza a mma hoje, com tolerância).
- **Sweep** de parâmetros, 1 preditor por modelo agora; `fit_logit` aceita N preditores (stepwise futuro).
- Alvo = **retorno do Close** `Close[t+h]/Close[t]-1` (não da SMA); coluna contínua `ret_{h}d` fica ao lado do `y_{h}d` para revisão.
- **Um df-fundação** (OHLCV do yfinance) ao qual todos os cálculos **adicionam colunas** (igual ao legado), revisável linha a linha.
- **Duas saídas:** `output/analysis_mma.xlsx` (1 linha/dia, df-fundação enriquecido) e `output/summary_mma.xlsx` (1 linha/modelo; **2 abas: `summary` + `dicionário`** com a legenda das colunas). Formato **.xlsx** (engine openpyxl).
- Stack: `statsmodels`, `pandas`, `yfinance`, `pytest`, ambiente `uv`. Indicador como **plug-in**.

## Fase 0 — Planejamento

- [x] Design aprovado e documentado (spec).
- [x] Plano de implementação escrito (TDD, tarefas bite-sized).
- [x] HTML de apoio à decisão.

## Fase 1 — Implementação (rastreio por tarefa do plano)

Concluída em 2026-06-29 — **28 testes passando** (`uv run pytest`); e2e verificado em `^BVSP` (3715 dias, 150 modelos).
Inclui as lacunas ALTA/MÉDIA de `TESTES.md` dobradas nos testes de cada fase.

- [x] T1 — Scaffolding & ambiente (git init, uv, pytest, fixtures). _smoke 2 testes_
- [x] T2 — `target.py` (rótulos binários deslocados). _5 testes_
- [x] T3 — `indicators/mma.py` + `base.py` (dummy de rompimento, plug-in). _5 testes_
- [x] T4 — `modeling.py` (logística + OLS + casos de borda). _6 testes_
- [x] T5 — `sweep.py` (grid → analysis + summary). _4 testes_
- [x] T6 — `data.py` (loader yfinance, rede isolada). _3 testes_
- [x] T7 — `run_mma.py` (entrypoint e2e → analysis_mma.xlsx + summary_mma.xlsx). _4 testes_

**Rodar o pipeline real:** `PYTHONPATH=src uv run python -m robusta.run_mma` (PowerShell: `$env:PYTHONPATH="src"; uv run python -m robusta.run_mma`).

## Itens futuros (fora desta fase)

- [f] Validação out-of-sample (split temporal / walk-forward).
- [f] Painel multi-ticker (empilhamento).
- [f] Multi-preditor + stepwise forward/backward.
- [f] Novos indicadores (mme, obv) via plug-ins.
- [ ] Preparar GitHub remoto e revisar `.gitignore` (ref. PROJECT_BUILDING).
- [ ] `planning/ADVERSARIAL_REVIEW.md` e `planning/TESTES.md` (ref. PROJECT_BUILDING).
