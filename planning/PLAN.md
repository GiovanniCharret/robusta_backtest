# PLAN — ROBUSTA Rebuild

> Documento-fonte do projeto. Decisões e progresso vivem aqui.
> Glossário de status: `[ ]` pendente · `[x]` concluído · `[a]` anulado · `[f]` revisão futura · `[n]` não se aplica · `[r]` rollback/falhou.

## Documentos

- **Design (spec):** `planning/2026-06-29-robusta-rebuild-design.md`
- **Design Fase 3 (multi-indicador):** `planning/2026-07-01-multi-indicator-design.md`
- **Plano Fase 3 (implementação):** `planning/2026-07-07-multi-indicator-implementation-plan.md`
- **Plano de implementação:** `planning/2026-06-29-robusta-rebuild-plan.md`
- **Apoio visual (Fase 3):** `planning/fase3-plan-explainer.html` (os explainers das fases 1–2 foram removidos)
- **Mapa de testes:** `planning/TESTES.md` (cobertura das 7 fases + lacunas priorizadas)

## Decisões travadas (2026-06-29)

- **Duas famílias de modelo por sweep:** Logística sobre `y_{h}d` (0/1, pseudo-R² McFadden) **e** OLS sobre `ret_{h}d` (contínuo, R² clássico). Summary em formato longo com coluna `family`.
- **Seleção de variáveis** (stepwise/Lasso/SFS dos notebooks) é **futuro** — precisa de multi-preditor.
- **Associação 2×2 (complementar):** nas linhas `logit`, o summary traz `odds_ratio`, `lift` e `fisher_p` (tabela rompimento × alta) — à prova de falha, e `odds_ratio` ≈ `exp(coef)`. NaN nas linhas `ols`.
- **Persistência do rompimento (`persist_k`) (2026-06-30):** nova dummy = rompeu **e** ficou `above` por mais `k` dias. Decisões travadas: (1) **ancoragem no dia da confirmação** (o k-ésimo dia após o rompimento) — usa só passado/presente, **sem vazamento** para o alvo; (2) **contagem**: `persist3` = rompimento + 3 dias acima = `streak==4`; `persist4` = rompimento + 4 = `streak==5`; (3) **one-shot** (um único 1 por rompimento, `streak == k+1`), não estado contínuo como no legado. Vira parâmetro `persist` do `mma` (`0` = rompimento puro), mais uma dimensão do grid; `sweep.py` não muda. Não é indicador novo.
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

Concluída em 2026-06-29 — **33 testes passando** (`uv run pytest`); e2e verificado em `^BVSP` (`period="10y"`, ~2483 dias, 150 modelos). Dados via `yfinance` por **janela relativa** (`period`, ex. "5y"/"10y"), não datas fixas.
Inclui as lacunas ALTA/MÉDIA de `TESTES.md` dobradas nos testes de cada fase.

- [x] T1 — Scaffolding & ambiente (git init, uv, pytest, fixtures). _smoke 2 testes_
- [x] T2 — `target.py` (rótulos binários deslocados). _5 testes_
- [x] T3 — `indicators/mma.py` + `base.py` (dummy de rompimento, plug-in). _5 testes_
- [x] T4 — `modeling.py` (logística + OLS + casos de borda). _6 testes_
- [x] T5 — `sweep.py` (grid → analysis + summary). _4 testes_
- [x] T6 — `data.py` (loader yfinance, rede isolada). _3 testes_
- [x] T7 — `run_mma.py` (entrypoint e2e → analysis_mma.xlsx + summary_mma.xlsx). _4 testes_

**Parâmetros ajustáveis:** todos centralizados em `src/robusta/config.py` (ticker, period, janelas da mma, tolerâncias, horizontes, min_events, pasta de saída). Edite lá — nenhum outro código precisa mudar.

**Rodar o pipeline real:** `PYTHONPATH=src uv run python -m robusta.run_mma` (PowerShell: `$env:PYTHONPATH="src"; uv run python -m robusta.run_mma`).

## Fase 2 — Persistência do rompimento (`persist_k`)

Concluída em 2026-06-30 — **38 testes passando** (`uv run pytest`); e2e verificado em `^BVSP` (2483 dias, **216 modelos**). Detalhe das tarefas em `planning/2026-06-29-robusta-rebuild-plan.md` (Task 8). TDD, 1 commit.

- [x] Dummy `persist_k` no `mma.py` (`signal_col`/`add_columns` ganham `persist`; one-shot na confirmação, `streak == k+1`).
- [x] `config.PERSISTENCES = [0, 3, 4]` (0 = rompimento puro).
- [x] Grid `{window, tol, persist}` em `run_mma` (sweep inalterado); coluna `persist` no summary + linha no `dicionário`.
- [x] Testes (mma, config, e2e) verdes. Grid: 4×3×3×3×2 = **216 linhas** de summary.

## Fase 3 — Multi-indicador + summary unificado (planejamento)

Spec aprovado em 2026-07-01: `planning/2026-07-01-multi-indicator-design.md`. Decisões travadas:
onset bullish como dummy (estado→transição); só bullish nesta passada; ranking do master por
**lift (logit) / coef (ols)**; **um módulo por indicador** (isolamento, duplicação aceita); config
com `INDICATORS` + `PARAM_GRIDS`. Roster (9 novos + mma): `mme, obv, vwap, alto_volume, exaustao_atr,
rsi, macd, donchian, bollinger`. Saídas: par por indicador + `summary_ALL.xlsx` (rankeável).

Decisões adicionais (2026-07-07/08, na revisão do plano): nomes harmonizados `*_state`/`*_signal`
(mma renomeado de `_above`/`_break`); grid **só** em `config.PARAM_GRIDS` (sem `PARAM_GRID` nos
módulos); saída plana em `output/` com sufixo (sem subpastas); **persist estendido aos 10 módulos**
(bloco de streak do mma sobre o `state` de cada um) — os 8 de regime varrem
`PERSISTENCES=[0,1,2,3,4]`, `alto_volume`/`exaustao_atr` ficam `[0]` (evento pontual);
`config.PERSISTENCES` atualizado de `[0,3,4]`. **`tolerancia_erro=0.005` do legado** (2026-07-10):
vira a dimensão `tol=[0.0, 0.005]` do grid de `exaustao_atr`/`alto_volume` (limiar
`≥ mult·ref·(1−tol)` — tol SUAVIZA, oposto do tol do mma); demais divergências vs legado
(só bullish; onset em vez de estado) são decisões do spec. **Confirmação de preço `confirm=[0..4]`**
(2026-07-10) nos 2 módulos de evento: evento no dia t + `Close[t+1..t+k] ≥ Close[t]`, dummy
one-shot em t+k — a variante de persistência que faz sentido onde o persist do estado não se
aplica. Master ≈ 1.290 linhas (215 combos × 3 × 2).

- [x] Spec revisado pelo usuário → plano de implementação escrito:
      `planning/2026-07-07-multi-indicator-implementation-plan.md` (15 tasks TDD).
- [ ] `runner.py` genérico + `run_all.py` (baixa preços 1×, itera roster, gera master).
- [ ] 9 módulos de indicador (cópia do padrão `mma`) + testes TDD por módulo.
- [ ] `config.INDICATORS` / `config.PARAM_GRIDS` + fixture `synthetic_prices_volume`.

## Itens futuros (fora desta fase)

- [f] Validação out-of-sample (split temporal / walk-forward).
- [f] Painel multi-ticker (empilhamento).
- [f] Multi-preditor + stepwise forward/backward.
- [f] Novos indicadores (mme, obv) via plug-ins.
- [ ] Preparar GitHub remoto e revisar `.gitignore` (ref. PROJECT_BUILDING).
- [ ] `planning/ADVERSARIAL_REVIEW.md` e `planning/TESTES.md` (ref. PROJECT_BUILDING).
