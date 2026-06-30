# Design — Rebuild ROBUSTA: dummies de rompimento + regressão logística

> Data: 2026-06-29 · Status: **aprovado** (design, revisado) · Spec de referência para o plano de implementação.
> Documento de apoio visual: `planning/robusta-design-explainer.html`.

## 1. Objetivo e escopo

Reconstruir o backtest legado ROBUSTA com rigor científico e código testável, servindo de **base limpa
de referência** para estudos futuros de indicadores técnicos.

O legado mistura, num único notebook, o cálculo de indicadores, uma máquina de gatilhos
(`_?value → _?gatilho → persistência → combinação de pares`) e a avaliação. Vamos:

- Trocar a máquina de gatilhos por **uma dummy de rompimento** por modelo.
- Manter o mecanismo de **deslocamento de datas** (a "daylist") que cria a variável dependente.
- Medir cada modelo com **regressão logística** (`statsmodels`).
- Isolar tudo em módulos pequenos, com o **indicador como plug-in**.

**Princípio de fundação (igual ao legado):** existe **um único df-fundação**, semeado pelo OHLCV do
`yfinance`. **Todo cálculo acrescenta colunas a esse mesmo df** — valor da média, estado "acima da banda",
dummy de rompimento, retorno futuro e rótulo — todos alinhados por data. Isso é o que permite **revisar
linha a linha** o que foi construído.

**Premissa assumida e aceita:** um único indicador técnico não tem valor preditivo real. Os pseudo-R²
serão minúsculos — e tudo bem. O valor entregue é o arcabouço, não a performance do sinal.

### Não-objetivos (YAGNI nesta fase)
- Não fazemos painel multi-ticker (só ticker único; a carga já fica parametrizada para evoluir).
- Não combinamos múltiplos indicadores no mesmo df (era a fonte do "df pesado" do legado).
- Não fazemos **seleção de variáveis** (stepwise / Lasso / SFS) agora — ela precisa de múltiplos preditores
  e cai no futuro multi-preditor (só deixamos a estrutura do `fit` aceitar N preditores).
- Rodamos **duas famílias** (logística + OLS), mas não um registry plugável de modelos — fica para o futuro.
- Não há otimização de portfólio, custos de transação, nem execução de ordens.

## 2. Decisões travadas

| Tema | Decisão |
|---|---|
| Alvo & modelos | **Duas famílias por modelo**: Logística sobre `y_{h}d` (0/1) **e** OLS sobre `ret_{h}d` (contínuo) |
| Métricas de comparação | `r2` (McFadden pseudo p/ logística; R² clássico p/ OLS), `coef`, `p_value`, `llf`, `accuracy` (só logística) |
| Universo | **Ticker único** via `yfinance`; carga parametrizada por ticker/período |
| Dummy independente | **Rompimento**: Close cruza a mma de baixo p/ cima, com tolerância |
| Grid de modelos | **Sweep**, 1 preditor por modelo agora; `fit` aceita N preditores depois |
| Fundação | **Um df-fundação** (OHLCV do yfinance) ao qual todos os cálculos **adicionam colunas** |
| Saídas | **Dois** `.xlsx`: `analysis_<ind>.xlsx` (1 linha/dia) e `summary_<ind>.xlsx` (1 linha/modelo) |
| Stack | `statsmodels`, `pandas`, `yfinance`; ambiente `uv` |

## 3. Definição exata da variável dependente (alvo)

Genérica, independente do indicador. Para cada horizonte `h` em `horizons` (a "daylist"), **duas colunas são
adicionadas ao df-fundação**:

```
ret_{h}d = Close[t+h] / Close[t] - 1            # retorno futuro do Close (contínuo) — espelha var_desloc do legado
y_{h}d   = 1 se ret_{h}d > 0, senão 0           # binário (o alvo da logística)
```

- Base: **retorno do Close** (não da média móvel). Aprovado via HTML; mais direto e interpretável.
- O `ret_{h}d` contínuo fica visível ao lado do `y_{h}d` para **revisão** (ver o % que gerou cada 0/1).
- As últimas `h` linhas ficam sem rótulo (`NA`) — **devem ser descartadas** antes do fit (sem vazamento).
- `horizons` default: `[10, 20, 30, 45, 90]` (a daylist do legado), configurável.

## 4. Definição exata da variável independente (dummy)

Específica do indicador (plug-in). Para a mma, **três colunas são adicionadas ao df-fundação** por
combinação de parâmetros (o valor da média depende só de `window`):

```
mma_w{window}                = Close.rolling(window).mean()              # valor da média (revisão)
mma_w{window}_t{tol}_above   = Close > mma_w{window} * (1 + tol)         # estado: acima da banda
mma_w{window}_t{tol}_break   = above & ~above.shift(1)                   # evento: cruzou hoje → a DUMMY 0/1
```

- `window` (dias da média) e `tol` (tolerância do rompimento) são os parâmetros varridos.
- O preditor usa **apenas passado/presente** — sem vazamento.
- `window` default sweep: `[5, 10, 20, 50, 200]`; `tol` default sweep: `[0.0, 0.01, 0.03]`.
- Com 5 janelas × 3 tolerâncias o df-fundação ganha ~5 colunas de média + ~30 de above/break + 10 de
  rótulo/retorno ⇒ **~45 colunas, leve e revisável** (continua sendo um indicador só).

## 5. Arquitetura (módulos isolados)

```
src/robusta/
  config.py        # painel de parâmetros ajustáveis (ticker, period, grids, min_events, saída)
  data.py          # load_prices(ticker, period="10y") -> df-fundação OHLCV (yfinance)
  target.py        # add_labels(df, horizons) -> adiciona ret_{h}d, y_{h}d    [GENÉRICO, FIXO]
  indicators/
    base.py        # interface Indicator: NAME, signal_col(**p), add_columns(df, **p) -> df
    mma.py         # adiciona mma_w*, *_above, *_break ao df                   [PLUG-IN]
  modeling.py      # fit_logit(df, y_col, x_cols) + fit_ols(df, y_col, x_cols) -> dict de métricas
  sweep.py         # run_sweep(df, indicator, grid, horizons) -> (analysis_df, summary_df) [2 famílias/linha]
  run_mma.py       # entrypoint: data → target → sweep → analysis.xlsx + summary.xlsx
tests/
```

**Contratos entre unidades:**
- `data.py` → devolve o **df-fundação** indexado por data com colunas OHLCV padronizadas.
- `target.py` → recebe df + `horizons`, **anexa** `ret_{h}d` e `y_{h}d`; não conhece indicador.
- `indicators/<x>.py` (o plug-in) expõe:
  - `NAME` — nome curto (ex. `"mma"`).
  - `signal_col(**params)` — nome canônico da coluna-dummy (ex. `mma_w20_t0.01_break`).
  - `add_columns(df, **params)` — **acrescenta** as colunas do indicador ao df e o devolve.
  Trocar de indicador = escrever outro arquivo com a mesma interface.
- `modeling.py` → `fit_logit` (alvo `y_{h}d`) e `fit_ols` (alvo `ret_{h}d`); ambos recebem df + coluna y +
  lista de colunas x (já aceitam N x's) e devolvem o **mesmo schema** de dicionário (com `family`).
- `sweep.py` → recebe o **módulo** do indicador + o grid + horizons; acumula as colunas no df-fundação e,
  para cada (combinação × horizonte), emite **duas linhas** (logística + OLS). Devolve `(analysis_df, summary_df)`.

## 6. Fluxo de dados (acúmulo de colunas no df-fundação)

```
ticker ─data.load_prices─► df-fundação [OHLCV]
                               │  + target.add_labels(horizons)
                               ▼
                    df [OHLCV, ret_10d, y_10d, ... , ret_90d, y_90d]
                               │  para cada (window, tol) do grid:
                               │     indicator.add_columns(df, window, tol)
                               ▼     → + mma_w*, *_above, *_break  (acumulando)
        df-fundação ENRIQUECIDO [tudo acima + todas as dummies]  ──► output/analysis_mma.xlsx
                               │  para cada (window, tol, h):
                               │     fit_logit(df, y_{h}d,  [*_break]) → linha family=logit
                               │     fit_ols  (df, ret_{h}d, [*_break]) → linha family=ols
                               ▼
              summary [2 linhas por modelo, ordenado] ──► output/summary_mma.xlsx
```

## 7. Os dois dfs de saída

### 7a. `analysis_<indicator>.xlsx` — df-fundação enriquecido (1 linha por **dia**)

Para auditoria/revisão. Colunas acumuladas na ordem em que o script avança:

| grupo | colunas |
|---|---|
| OHLCV (fundação) | `Open, High, Low, Close, Volume` (índice = data) |
| Alvo (target.py) | `ret_{h}d`, `y_{h}d` para cada horizonte |
| Indicador (plug-in) | `mma_w{window}`, `mma_w{window}_t{tol}_above`, `mma_w{window}_t{tol}_break` |

### 7b. `summary_<indicator>.xlsx` — comparação de modelos (**2 linhas por modelo**: logit + ols)

| coluna | descrição |
|---|---|
| `indicator` | nome do indicador (ex. `mma`) |
| `window` | janela da média |
| `tol` | tolerância do rompimento |
| `horizon` | horizonte `h` do alvo |
| `family` | `logit` (alvo `y_{h}d`) ou `ols` (alvo `ret_{h}d`) |
| `n` | nº de amostras usadas (após dropna) |
| `n_eventos` | nº de dias com dummy=1 |
| `r2` | McFadden pseudo-R² (logit) **ou** R² clássico (ols) |
| `coef` | coeficiente do preditor (log-odds no logit; efeito no retorno no ols) |
| `p_value` | p-valor do coeficiente |
| `llf` | log-likelihood |
| `accuracy` | acurácia in-sample — só `logit` (NaN no `ols`) |
| `status` | `ok` / `sem_eventos` / `separacao` / `erro` |
| `odds_ratio` | razão de chances da tabela 2×2 (rompimento × alta) — só `logit`; ≈ `exp(coef)` |
| `lift` | quantas vezes a alta é mais provável após rompimento vs taxa-base — só `logit` |
| `fisher_p` | p-valor do teste exato de Fisher na 2×2 — só `logit`; à prova de falha |

Summary ordenado por `family` e depois `r2` desc (NaN no fim) — cada família rankeada em separado, já que
o `r2` do logit (pseudo) e do ols (clássico) não estão na mesma escala.

## 8. Modelagem e casos de borda

Duas funções, **mesmo schema de retorno** (com `family`), para o sweep tratar igual:

- **`fit_logit`** — `statsmodels.api.Logit` com constante. `r2 = result.prsquared` (McFadden), `accuracy` in-sample.
- **`fit_ols`** — `statsmodels.api.OLS` com constante sobre o `ret_{h}d` contínuo. `r2 = result.rsquared` (clássico),
  `accuracy = NaN` (não se aplica).

Casos de borda (valem para as duas famílias):
- **Sem eventos / sem variância:** se `n_eventos < min_events` ou a dummy é constante (e, no logit, o alvo é
  constante), não ajustar → `status="sem_eventos"`, métricas `NaN`.
- **Separação perfeita / não convergência:** capturar `PerfectSeparationError`/exceção →
  `status="separacao"`/`"erro"`, métricas `NaN`. Nunca derrubar o sweep inteiro por um modelo ruim.
- Acurácia é **in-sample**, só referência. Esta fase não faz split treino/teste (registrado como item futuro).

## 9. Estratégia de testes

Dados sintéticos determinísticos (sem rede, sem aleatoriedade). Cobrir caminhos felizes e bordas:

- **`target.add_labels`**: série conhecida → `ret_{h}d`/`y_{h}d` corretos; últimas `h` linhas `NA` (teste de vazamento).
- **`indicators.mma.add_columns`**: adiciona as colunas esperadas; `*_break`=1 exatamente no dia do
  cruzamento; tolerância suprime cruzamentos dentro da banda; `signal_col` casa com o nome criado.
- **`modeling.fit_logit` / `fit_ols`**: relação plantada → coef no sinal esperado e `family` correta; logit
  sem eventos → `sem_eventos`; ols devolve `r2` clássico e `accuracy` NaN.
- **`sweep.run_sweep`**: grid pequeno → `analysis_df` com as colunas acumuladas; `summary_df` com
  |window|×|tol|×|horizons|×**2** linhas (logit+ols), ambas as famílias presentes, schema e ordenação corretos.
- **e2e (`run_mma.build_summary`)**: df sintético → devolve `(analysis, summary)` coerentes, sem rede.

`yfinance` (rede) é isolado em `data.py` e **não** entra nos testes unitários (usar fixture/df injetado).

## 10. Convenções de código (regra do projeto)

Conforme `CLAUDE.md` › Project rules:
- Toda função com **docstring** na ordem: (1) por que a função existe / o problema que resolve;
  (2) a lógica do input ao output em **fases numeradas** (Entrada → Fase 1 → … → Saída).
- **Toda linha de código comentada** — inclusive as óbvias.
- Documentação em `planning/`; decisões e progresso em `planning/PLAN.md`; **não** editar `PROJECT_BUILDING.md`.

## 11. Itens em aberto (futuro, fora desta fase)
- Validação out-of-sample (split temporal / walk-forward).
- Painel multi-ticker (empilhamento).
- Multi-preditor + stepwise forward/backward.
- Outros indicadores (mme, obv) via novos plug-ins.
