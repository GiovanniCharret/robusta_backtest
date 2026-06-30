# Mapa de Testes — ROBUSTA Rebuild

> Data: 2026-06-29 · Fonte da verdade: `planning/2026-06-29-robusta-rebuild-plan.md` (plano) e
> `planning/2026-06-29-robusta-rebuild-design.md` (design). Este documento é um **mapa de QA**:
> permite a um humano repetir e validar cada fase, e lista o que o plano **já cobre** versus as
> **lacunas** que valem a pena adicionar.

## 1. Como rodar os testes

Ambiente `uv` (ver `CLAUDE.md` › Python environment). A partir da raiz do projeto:

```bash
cd "C:/Users/gioch/Documents/Python_Projects/rebuild_robusta_backtests"
```

| Objetivo | Comando |
|---|---|
| Rodar a suíte inteira (verbose) | `uv run pytest -v` |
| Rodar um arquivo de teste | `uv run pytest tests/test_target.py -v` |
| Rodar um único teste (pelo nome) | `uv run pytest tests/test_target.py::test_add_labels_adds_continuous_and_binary -v` |
| Rodar por palavra-chave | `uv run pytest -k "tolerance" -v` |
| Parar no primeiro erro | `uv run pytest -x` |
| Ver print/saída de stdout | `uv run pytest -s` |

**Onde ficam os testes:** todos em `tests/`. O `pyproject.toml` coloca `src` no `pythonpath`
(`[tool.pytest.ini_options] pythonpath = ["src"]`) e define `testpaths = ["tests"]`, então não há
instalação editável e o import `robusta` funciona direto.

**Fixtures compartilhadas:** `tests/conftest.py` expõe `synthetic_prices` (ver seção 5).

### Princípio inviolável: sem rede nos testes unitários

- `yfinance` é a **única** fonte de rede e está isolada em `src/robusta/data.py` (`load_prices`).
- Nenhum teste unitário pode chamar `load_prices` nem a internet. Todo teste usa a fixture
  `synthetic_prices` ou DataFrames montados à mão.
- `load_prices` é validado **manualmente** (ver Fase 6) e o e2e completo (`main`) também
  (ver Fase 7, passo 7 do plano — networked check).

---

## 2. Fases de teste (Tarefa 1 a 7)

Legenda de status por caso de borda:
- **[coberto]** — já existe um teste no plano que exercita o caso.
- **[lacuna sugerida]** — o plano NÃO cobre; recomendado adicionar (ver seção 4, priorizado).

---

### Fase 1 — Scaffolding & ambiente

**Unidade sob teste:** o pacote `robusta` importa e a fixture carrega.
**Arquivo de teste:** `tests/test_smoke.py` (fixture em `tests/conftest.py`).

**Caminhos felizes (plano):**

| Teste | O que garante |
|---|---|
| `test_package_imports_and_fixture_loads` | `import robusta` funciona (pythonpath OK) e `synthetic_prices` entrega um DataFrame com coluna `Close` e exatamente 300 linhas. |

**Casos de borda / o que poderia quebrar:**

| Caso | Status | Observação |
|---|---|---|
| Fixture é determinística (mesmos valores entre execuções) | [lacuna sugerida] | Asserir `round(df["Close"].iloc[0], 4)` num valor fixo, para travar a reprodutibilidade da série senoidal. |
| Índice da fixture é de datas úteis (`bdate_range`) e está ordenado | [lacuna sugerida] | `assert df.index.is_monotonic_increasing` e `isinstance(df.index, pd.DatetimeIndex)`. |
| Schema OHLCV completo na fixture (`Open,High,Low,Close,Volume`) | [lacuna sugerida] | O smoke só checa `Close`; checar as 5 colunas evita surpresas em fases posteriores. |

**Como testar:** rodar `uv run pytest tests/test_smoke.py -v`. Esperado: 1 passou.

---

### Fase 2 — `target.py` (rótulos deslocados no tempo)

**Unidade sob teste:** `add_labels(df, horizons) -> df` (adiciona `ret_{h}d` float e `y_{h}d` `Int8`).
**Arquivo de teste:** `tests/test_target.py`.

**Caminhos felizes (plano):**

| Teste | O que garante |
|---|---|
| `test_add_labels_adds_continuous_and_binary` | `ret_1d[0] = 11/10-1 = 0.1`; binário `[1,1,0]` nas 3 primeiras; última linha `NA` em `ret_1d` e `y_1d` (sem look-ahead); `dtype == "Int8"`. |
| `test_add_labels_nan_tail_length_matches_horizon` | Para `h=2`, exatamente 2 linhas finais ficam `NA` em `y_2d`. |

**Casos de borda / o que poderia quebrar:**

| Caso | Status | Detalhe / como testar |
|---|---|---|
| Múltiplos horizontes de uma vez (`horizons=[1,2,3]`) | [lacuna sugerida] | Um só `add_labels` deve criar `ret_1d,y_1d,ret_2d,y_2d,ret_3d,y_3d`; conferir todas as 6 colunas presentes e os NAs de cauda corretos por horizonte. |
| Retorno **exatamente zero** vira `0`, não `1` | [lacuna sugerida] | Regra é `> 0`. Montar `Close=[10,10,...]`; `ret` é 0 ⇒ `y` deve ser `0`. Caso de fronteira clássico do `>`. |
| Horizonte `h >= len(série)` ⇒ tudo `NA` | [lacuna sugerida] | `Close` com 3 linhas, `h=5`; `ret_5d`/`y_5d` inteiramente `NA`; o fit a jusante deve cair em `sem_eventos` (n=0). |
| Preserva o índice de datas do df de entrada | [lacuna sugerida] | Passar `synthetic_prices`; asserir `out.index.equals(synthetic_prices.index)` — o `copy()` não pode reindexar. |
| Não muta o df original do chamador | [lacuna sugerida] | Após `add_labels`, `"ret_1d" not in df_original.columns` (a função usa `out = df.copy()`). |
| Retorno negativo vira `0` | [coberto] | O 3º valor do teste feliz (`12→9`) já cobre o caso de queda. |
| `Close` com `NaN` no meio propaga `NA` no rótulo | [lacuna sugerida] | Garantir que um `NaN` de preço não vira `0` espúrio (a máscara `ret.notna()` deve protegê-lo). |

---

### Fase 3 — `indicators/mma.py` (dummy de rompimento, plug-in)

**Unidade sob teste:** `mma.add_columns(df, window, tol)`, `mma.value_col`, `mma.signal_col`, `mma.NAME`.
Adiciona `mma_w{window}` (valor), `mma_w{window}_t{tol}_above` (estado), `mma_w{window}_t{tol}_break` (dummy).
**Arquivo de teste:** `tests/test_mma.py`.

**Caminhos felizes (plano):**

| Teste | O que garante |
|---|---|
| `test_add_columns_creates_value_above_break` | Cria `value_col(3)` e `signal_col(3,0.0)`; a dummy é evento (`⊆{0,1}`) e acende `>= 1` vez; `dtype Int8`; `mma.NAME == "mma"`. |
| `test_tolerance_suppresses_marginal_cross` | Com `tol=0.03`, cruzamentos marginais geram `<=` eventos que com `tol=0.0` (a tolerância nunca aumenta os eventos). |

**Casos de borda / o que poderia quebrar:**

| Caso | Status | Detalhe / como testar |
|---|---|---|
| Estado `*_above` vs evento `*_break` são distintos | [lacuna sugerida] | `above` pode ser `1` em vários dias seguidos; `break` deve ser `1` **só no 1º** dia da sequência. Asserir `break.sum() <= above.sum()` e que `break` só acende na transição `0→1` de `above`. |
| Rompimento **não acende** em dia sem cruzamento | [lacuna sugerida] | Numa janela em que `Close` fica sempre acima da média, `break` deve ser `0` depois do 1º dia (sem novo cruzamento). |
| Rompimento no **primeiro dia** da série (efeito do `shift`) | [lacuna sugerida] | `shift(1, fill_value=False)` faz o 1º dia ter "ontem = não-acima". Se `Close[0]` já está acima, o dia 0 acende `break=1`? Documentar e travar o comportamento esperado (provavelmente sim, por construção). |
| Janela **maior que a série** ⇒ `mma` toda `NaN` ⇒ sem eventos | [lacuna sugerida] | `Close` com 4 linhas, `window=200`: `mma_w200` toda `NaN`, `above` vira `0`/`<NA>`, `break.sum()==0`. Crítico porque o grid default usa `window=200`. |
| Tolerância **negativa** (`tol=-0.01`) | [lacuna sugerida] | A banda fica *abaixo* da média ⇒ acende mais eventos. Não é caso de uso, mas a função não deve quebrar; decidir se aceita ou valida. Asserir `eventos(tol=-0.01) >= eventos(tol=0.0)`. |
| `signal_col` casa exatamente com o nome criado por `add_columns` | [coberto] | O teste feliz usa `mma.signal_col(3,0.0)` para indexar a coluna criada — se não casasse, falharia. Reforço explícito recomendado para `tol` não-inteiro no nome (`t0.01`). |
| Formatação do `tol` no nome da coluna (`t0.0` vs `t0.01` vs `t0.03`) | [lacuna sugerida] | A f-string `f"...t{tol}..."` produz `t0.0`, `t0.01`, `t0.03`. Travar isso evita divergência entre `value_col`/`signal_col` e a coluna realmente criada (fonte comum de `KeyError` no sweep). |
| `add_columns` acumula sobre df já enriquecido (idempotência de chamadas repetidas) | [lacuna sugerida] | Chamar 2x com mesmos params não deve duplicar nem corromper colunas (o sweep chama em sequência sobre o mesmo df). |
| Não muta tipos de `Close` nem reordena o índice | [lacuna sugerida] | `out.index.equals(df.index)` e `Close` intacto. |

---

### Fase 4 — `modeling.py` (logit + OLS, casos de borda)

**Unidade sob teste:** `fit_logit(df, y_col, x_cols, min_events=5)` e `fit_ols(...)`; mesmo schema de dict
(`family, n, n_eventos, r2, coef, p_value, llf, accuracy, status`).
**Arquivo de teste:** `tests/test_modeling.py`.

**Caminhos felizes (plano):**

| Teste | O que garante |
|---|---|
| `test_fit_logit_recovers_positive_relationship` | Relação plantada ⇒ `status="ok"`, `family="logit"`, `coef>0`, `n==200`, `n_eventos==100`, `r2` não-NaN. |
| `test_fit_logit_no_events_returns_status` | Dummy toda `0` ⇒ `status="sem_eventos"`, `r2` NaN, `n_eventos==0` (degrada sem quebrar). |
| `test_fit_ols_returns_classic_r2_and_nan_accuracy` | OLS sobre `ret` ⇒ `family="ols"`, `coef>0`, `0<=r2<=1`, `accuracy` NaN. |

**Casos de borda / o que poderia quebrar:**

| Caso | Status | Detalhe / como testar |
|---|---|---|
| **Separação perfeita real** no logit ⇒ `status="separacao"` | [lacuna sugerida] | Plantar `y == x` perfeitamente (dummy prevê 100%) e checar que captura `PerfectSeparationError` (pode também emergir como `"erro"` dependendo da versão do statsmodels — o teste deve aceitar `status in {"separacao","erro"}` e métricas NaN). **O plano só cita `sem_eventos`.** |
| **Alvo constante** no logit (`y` todo `1` ou todo `0`) | [lacuna sugerida] | `data[y_col].nunique() < 2` ⇒ `sem_eventos` antes de tentar ajustar. |
| **Dummy constante** (sem variância) no OLS | [lacuna sugerida] | `data[x_cols[0]].nunique() < 2` ⇒ `sem_eventos` (x sem variância quebraria o OLS). |
| `r2` do OLS sempre em `[0,1]` | [coberto] | Asserido no teste feliz do OLS; reforçar com efeito quase-nulo para o limite inferior. |
| `accuracy` é NaN no OLS, e numérica em `[0,1]` no logit | [parcial] | NaN do OLS [coberto]; o intervalo `0<=accuracy<=1` do logit é [lacuna sugerida]. |
| `n` e `n_eventos` corretos **após `dropna`** | [parcial] | `n==200`/`n_eventos==100` [coberto] no caso limpo; falta um caso **com NAs na cauda** (rótulos `y_{h}d`) para provar que o `dropna` reduz `n` corretamente. [lacuna sugerida] |
| `min_events` na **fronteira** (`n_eventos == min_events` ajusta; `== min_events-1` não) | [lacuna sugerida] | A condição é `n_eventos < min_events`. Testar os dois lados da fronteira para travar o `<` vs `<=`. |
| Schema idêntico entre logit e ols (mesmas chaves) | [lacuna sugerida] | `set(fit_logit(...).keys()) == set(fit_ols(...).keys())` — o sweep depende disso para empilhar linhas. |
| Status `"erro"` para falha numérica genérica | [lacuna sugerida] | Difícil de provocar sinteticamente; documentar que o `except Exception` cobre e que nunca deve propagar exceção (o sweep não pode cair). |
| `coef`/`p_value` referem-se a `x_cols[0]` (o preditor de interesse), não à constante | [lacuna sugerida] | Com 1 preditor, confirmar que `coef` é o do `*_break` e não do intercepto. |

---

### Fase 5 — `sweep.py` (acumula colunas → `(analysis_df, summary_df)`)

**Unidade sob teste:** `run_sweep(df, indicator, param_grid, horizons, min_events=5)`.
**Arquivo de teste:** `tests/test_sweep.py`.

**Caminhos felizes (plano):**

| Teste | O que garante |
|---|---|
| `test_run_sweep_accumulates_columns_and_two_families` | `len(summary) == |window|×|tol|×|horizons|×2` (= 16 no grid 2×2×2); ambas as famílias presentes; colunas-chave (`indicator,window,tol,horizon,family,r2,p_value,status`); `indicator=="mma"`; `analysis` ganhou `value_col(5)` e `signal_col(20,0.01)`; `len(analysis)==len(prices)` (1 linha/dia). |
| `test_run_sweep_sorted_within_family` | Dentro de cada família, os `r2` dos `status=="ok"` ficam em ordem **não-crescente**; `len(summary)==4` no grid 2×1×1×2. |

**Casos de borda / o que poderia quebrar:**

| Caso | Status | Detalhe / como testar |
|---|---|---|
| Nº de linhas `== |grid|×|horizontes|×2` | [coberto] | Asserido nos dois testes. Reforçar com grid 3×3 para pegar erro de produto cartesiano. |
| Presença das **duas famílias** logit+ols | [coberto] | `set(summary["family"]) == {"logit","ols"}`. |
| Ordenação por `r2` desc **dentro** de cada família, com NaN no fim | [parcial] | Ordem desc dos `ok` [coberto]; falta asserir explicitamente que linhas com `r2` **NaN** (status `sem_eventos`/`erro`) ficam **no fim** de cada família (`na_position="last"`). [lacuna sugerida] |
| Status `sem_eventos` aparece para **janelas grandes** | [lacuna sugerida] | Incluir `window=200` no grid com série de 300 dias: poucos cruzamentos ⇒ alguns modelos viram `sem_eventos`. Provar que o sweep não cai e marca o status. |
| Colunas **acumuladas** no `analysis` para TODAS as combinações | [parcial] | O plano checa só 2 colunas; conferir que todas as `|window|` colunas de valor e `|window|×|tol|` colunas de `break`/`above` existem no `analysis` final. [lacuna sugerida] |
| `analysis` continua **1 linha por dia** (não explode em linhas) | [coberto] | `len(analysis)==len(prices)`. |
| Schema completo do summary (todas as 12 colunas do design §7b) | [lacuna sugerida] | O plano checa um subconjunto; asserir o set completo `{indicator,window,tol,horizon,family,n,n_eventos,r2,coef,p_value,llf,accuracy,status}`. |
| Grid com **uma só** combinação / horizonte único | [lacuna sugerida] | Caso mínimo (`{window:[5],tol:[0.0]}`, `[10]`) ⇒ exatamente 2 linhas. Pega off-by-one no laço. |
| Injeção do **módulo** indicador (não-acoplamento ao mma) | [parcial] | O teste passa `mma`; o contrato é "qualquer módulo com `NAME/signal_col/add_columns`". Um fake-indicator minimalista provaria o desacoplamento. [lacuna sugerida] |
| `min_events` propaga para os fits | [lacuna sugerida] | Rodar com `min_events` alto ⇒ todos viram `sem_eventos`; com baixo ⇒ `ok`. Prova o repasse do parâmetro. |

---

### Fase 6 — `data.py` (loader yfinance, rede isolada)

**Unidade sob teste:** `normalize_ohlcv(raw)` (puro). `load_prices` **fica fora** dos testes (rede).
**Arquivo de teste:** `tests/test_data.py`.

**Caminhos felizes (plano):**

| Teste | O que garante |
|---|---|
| `test_normalize_sorts_and_keeps_ohlcv` | Ordena o índice (01 antes de 02); mantém só as 5 colunas OHLCV na ordem canônica, descartando `Extra`; `Close.iloc[0]==1` (reordenou junto). |
| `test_normalize_requires_close` | `raw` sem `Close` ⇒ `ValueError`. |

**Casos de borda / o que poderia quebrar:**

| Caso | Status | Detalhe / como testar |
|---|---|---|
| `normalize` ordena o índice | [coberto] | Asserido. |
| Remove colunas extras | [coberto] | `Extra` é descartada. |
| Erro explícito sem `Close` | [coberto] | `pytest.raises(ValueError)`. |
| OHLCV **parcial** (faltam `Volume`/`Open`) mas com `Close` | [lacuna sugerida] | `cols = [c for c in _OHLCV if c in ordered.columns]` mantém só o que existe. Asserir que não levanta erro e devolve o subconjunto presente. |
| Índice **já ordenado** permanece ordenado (idempotência) | [lacuna sugerida] | `sort_index()` sobre já-ordenado não deve alterar nada. |
| Achatar `MultiIndex` (lógica de `load_prices`) | [lacuna sugerida] | Extrair a lógica de achatar colunas para um helper puro testável, OU montar um `raw` com `pd.MultiIndex` e testar só a parte sem rede. Hoje fica dentro de `load_prices` (não testável). |
| **`load_prices` (rede)** | manual | Ver verificação manual abaixo. |

**Verificação manual de `load_prices` (fora da suíte, requer rede):**

```bash
uv run python -c "from robusta.data import load_prices; df = load_prices('^BVSP', period='1y'); print(df.shape); print(df.columns.tolist()); print(df.head())"
```

Esperado: DataFrame indexado por data, colunas exatamente `['Open','High','Low','Close','Volume']`,
índice ordenado, sem `MultiIndex` nas colunas, `Close` numérico não-nulo.

---

### Fase 7 — `run_mma.py` (entrypoint e2e, escreve os 2 `.xlsx`)

**Unidade sob teste:** `build_summary(prices, *, windows, tols, horizons, min_events)` (puro, sem rede).
`main(...)` faz I/O+rede e é validado **manualmente**.
**Arquivo de teste:** `tests/test_run_mma.py`.

**Caminhos felizes (plano):**

| Teste | O que garante |
|---|---|
| `test_build_summary_end_to_end` | Pipeline completo sintético: `len(summary)==8` (2×1×2×2); schema essencial `{indicator,window,tol,horizon,family,r2,status}`; ambas as famílias; `indicator=="mma"`; `analysis` tem `y_10d`/`ret_10d`; `len(analysis)==len(prices)` (1 linha/dia). |

**Casos de borda / o que poderia quebrar:**

| Caso | Status | Detalhe / como testar |
|---|---|---|
| Devolve `(analysis, summary)` coerentes | [coberto] | Asserido. |
| `analysis` é **por-dia** com rótulos acumulados | [coberto] | `y_10d`/`ret_10d` presentes; `len==len(prices)`. |
| `summary` tem coluna `family` com as duas famílias | [coberto] | `set(summary["family"])=={"logit","ols"}`. |
| `min_events` repassado até os fits | [parcial] | O teste usa `min_events=1`; falta um caso com `min_events` alto provando que tudo vira `sem_eventos`. [lacuna sugerida] |
| `build_summary` **não muta** o `prices` de entrada | [lacuna sugerida] | `add_labels` faz `copy()`, mas `add_columns` (via sweep) escreve no df rotulado; provar que o `prices` original do chamador continua só-OHLCV. |
| `write_outputs` cria `output/` e escreve **os dois** `.xlsx` legíveis | [coberto] | `test_write_outputs_writes_readable_xlsx` (tmp_path, sem rede): nomes corretos + roundtrip via `pd.read_excel`. |
| `analysis_mma.xlsx` preserva o índice de datas; `summary_mma.xlsx` é `index=False` | [coberto] | Escrita isolada em `write_outputs` (testada); `main` só a chama após o download. |
| Nº de linhas do summary networked (`150 = 75 modelos × 2`) | manual | Grid default 5×3×5 horizontes × 2 famílias = 150 linhas. |

**Verificação manual de `main` (fora da suíte, requer rede):**

```bash
uv run python -m robusta.run_mma
```

Esperado: imprime a mensagem de salvamento; `output/analysis_mma.xlsx` (por-dia, ~50 colunas) e
`output/summary_mma.xlsx` (150 linhas) existem. Abrir o `analysis` e conferir que cada coluna
(`mma_w*`, `*_above`, `*_break`, `ret_*d`, `y_*d`) está alinhada por data.

---

## 3. Matriz de cobertura

| # | Caso de teste | Fase | Tipo | Status | Arquivo |
|---|---|---|---|---|---|
| 1 | import do pacote + fixture carrega | 1 | feliz | coberto | `test_smoke.py` |
| 2 | fixture determinística / índice de datas ordenado | 1 | borda | lacuna | `test_smoke.py` |
| 3 | `ret`/`y` corretos + cauda NA + dtype Int8 | 2 | feliz | coberto | `test_target.py` |
| 4 | nº de NAs de cauda == h | 2 | feliz | coberto | `test_target.py` |
| 5 | múltiplos horizontes de uma vez | 2 | borda | lacuna | `test_target.py` |
| 6 | retorno exatamente zero → 0 | 2 | borda | lacuna | `test_target.py` |
| 7 | horizonte >= tamanho da série → tudo NA | 2 | borda | lacuna | `test_target.py` |
| 8 | preserva índice / não muta entrada | 2 | borda | lacuna | `test_target.py` |
| 9 | cria valor/above/break + dummy 0/1 Int8 | 3 | feliz | coberto | `test_mma.py` |
| 10 | tolerância suprime cruzamento marginal | 3 | feliz | coberto | `test_mma.py` |
| 11 | estado `above` vs evento `break` (só na transição) | 3 | borda | lacuna | `test_mma.py` |
| 12 | não acende em dia sem cruzamento | 3 | borda | lacuna | `test_mma.py` |
| 13 | rompimento no 1º dia (shift) | 3 | borda | lacuna | `test_mma.py` |
| 14 | janela > série → mma NaN → sem eventos | 3 | borda | lacuna | `test_mma.py` |
| 15 | tolerância negativa | 3 | borda | lacuna | `test_mma.py` |
| 16 | formatação do `tol` no nome da coluna | 3 | borda | lacuna | `test_mma.py` |
| 17 | logit recupera relação positiva | 4 | feliz | coberto | `test_modeling.py` |
| 18 | logit sem eventos → `sem_eventos` | 4 | borda | coberto | `test_modeling.py` |
| 19 | OLS R² clássico + accuracy NaN | 4 | feliz | coberto | `test_modeling.py` |
| 20 | separação perfeita → `separacao`/`erro` | 4 | borda | lacuna | `test_modeling.py` |
| 21 | alvo constante (logit) → `sem_eventos` | 4 | borda | lacuna | `test_modeling.py` |
| 22 | dummy constante (OLS) → `sem_eventos` | 4 | borda | lacuna | `test_modeling.py` |
| 23 | `min_events` na fronteira (`<` vs `<=`) | 4 | borda | lacuna | `test_modeling.py` |
| 24 | `n`/`n_eventos` corretos após dropna com NAs | 4 | borda | lacuna | `test_modeling.py` |
| 25 | schema idêntico logit vs ols | 4 | borda | lacuna | `test_modeling.py` |
| 26 | accuracy do logit em [0,1] | 4 | borda | lacuna | `test_modeling.py` |
| 27 | acumula colunas + 2 famílias + nº de linhas | 5 | feliz | coberto | `test_sweep.py` |
| 28 | ordenação por r2 desc dentro da família | 5 | feliz | coberto | `test_sweep.py` |
| 29 | NaN no fim de cada família | 5 | borda | lacuna | `test_sweep.py` |
| 30 | `sem_eventos` aparece p/ janelas grandes | 5 | borda | lacuna | `test_sweep.py` |
| 31 | todas as colunas acumuladas presentes | 5 | borda | lacuna | `test_sweep.py` |
| 32 | schema completo do summary (12 colunas) | 5 | borda | lacuna | `test_sweep.py` |
| 33 | desacoplamento via módulo indicador fake | 5 | borda | lacuna | `test_sweep.py` |
| 34 | `min_events` propaga no sweep | 5 | borda | lacuna | `test_sweep.py` |
| 35 | normalize ordena + mantém OHLCV | 6 | feliz | coberto | `test_data.py` |
| 36 | normalize exige `Close` (ValueError) | 6 | feliz | coberto | `test_data.py` |
| 37 | OHLCV parcial (sem erro) | 6 | borda | lacuna | `test_data.py` |
| 38 | achatar MultiIndex (helper puro) | 6 | borda | lacuna | `test_data.py` |
| 39 | `load_prices` (rede) | 6 | feliz | manual | — |
| 40 | e2e build_summary devolve (analysis, summary) | 7 | feliz | coberto | `test_run_mma.py` |
| 41 | `build_summary` não muta `prices` | 7 | borda | lacuna | `test_run_mma.py` |
| 42 | `min_events` alto → tudo `sem_eventos` | 7 | borda | lacuna | `test_run_mma.py` |
| 43 | `write_outputs` escreve os 2 `.xlsx` (roundtrip) | 7 | feliz | coberto | `test_run_mma.py` |

**Resumo:** 9 casos felizes cobertos pelo plano + 1 borda coberta (`sem_eventos` no logit) +
2 felizes manuais (rede). 30 casos marcados como **lacuna sugerida** (1 feliz na Fase 1, demais bordas).

---

## 4. Lacunas e recomendações (priorizado)

Prioridade alta = pode mascarar um bug real no domínio ou derrubar o sweep em produção.

### Prioridade ALTA (adicionar junto da implementação)

1. **Janela maior que a série → `mma` toda NaN → sem eventos** (Fase 3, #14). O grid default
   inclui `window=200`; sem este teste, um df curto produziria silenciosamente zero eventos e
   poderia esconder um `KeyError`/`NaN` mal tratado. Crítico porque é caminho real do sweep default.
2. **Separação perfeita real no logit → `separacao`** (Fase 4, #20). O plano só testa `sem_eventos`;
   o design (§8) exige tratar `PerfectSeparationError`. Sem teste, o `except` pode estar errado e
   derrubar o sweep inteiro com um modelo ruim — exatamente o que o design proíbe.
3. **Estado `*_above` vs evento `*_break`** (Fase 3, #11/#12). É o coração da dummy de rompimento
   (cruzamento = evento de **transição**, não estado). Se `break` acender todo dia "acima", o modelo
   inteiro perde sentido. Teste central da semântica do indicador.
4. **Retorno exatamente zero → 0** (Fase 2, #6). Fronteira do `>`. Define o rótulo; um erro aqui
   contamina toda a variável dependente.
5. **NaN no fim de cada família no summary** (Fase 5, #29). O design (§7b) promete `na_position="last"`;
   sem teste, um ranking com NaN no topo enganaria o usuário na comparação de modelos.

### Prioridade MÉDIA

6. **Múltiplos horizontes num só `add_labels`** (Fase 2, #5) — o uso real sempre passa 5 horizontes.
7. **`min_events` na fronteira** (Fase 4, #23) — trava o `<` vs `<=`.
8. **`sem_eventos` aparece para janelas grandes no sweep** (Fase 5, #30) — prova robustez ponta-a-ponta.
9. **Schema idêntico logit vs ols** (Fase 4, #25) — o empilhamento do sweep depende disso.
10. **Schema completo do summary (12 colunas)** (Fase 5, #32) — garante o contrato do `.xlsx` de saída.
11. **`build_summary`/`add_labels` não mutam a entrada** (Fases 2/7, #8/#41) — efeito colateral é bug sutil.

### Prioridade BAIXA (bom ter)

12. Tolerância negativa (#15), formatação do `tol` no nome (#16), OHLCV parcial (#37),
    fixture determinística (#2), desacoplamento via indicador fake (#33), achatar MultiIndex como
    helper puro (#38).

**Honestidade sobre a cobertura atual:** o plano cobre bem os **caminhos felizes** de cada unidade
(1 a 3 testes por módulo) e UM caso de borda explícito (`sem_eventos` no logit). Ele **não** cobre a
maioria das fronteiras numéricas (retorno zero, janela > série, separação perfeita, `min_events` na
borda) nem as garantias de não-mutação e de ordenação-com-NaN. Essas lacunas são justamente os
"furos científicos de teste" que o `CLAUDE.md` manda fechar — recomendo adicioná-las **na mesma
fase** em que cada módulo é implementado (TDD), não depois.

---

## 5. Dados de teste

### Fixture `synthetic_prices` (em `tests/conftest.py`)

DataFrame OHLCV **determinístico** (sem rede, sem aleatoriedade), construído assim:

- **Índice:** `pd.bdate_range("2020-01-01", periods=300)` — 300 dias úteis.
- **Close:** `100 + 0.05*t + 8*sin(t/13) + 3*sin(t/3.0)`, com `t = 0..299`. A tendência leve garante
  retornos positivos no longo prazo; as duas ondas senoidais (períodos diferentes) geram **cruzamentos
  de média** em múltiplas janelas — essencial para a dummy de rompimento acender.
- **OHLCV derivado:** `Open` = Close do dia anterior; `High = Close+0.5`; `Low = Close-0.5`;
  `Volume = 1_000_000` (constante, irrelevante para a mma mas mantém o schema).

**Quando usar a fixture:** testes que precisam de uma série realista com cruzamentos e horizontes
longos — `test_mma` (cruzamentos reais), `test_sweep` e `test_run_mma` (pipeline ponta-a-ponta,
300 dias permitem horizontes até 90 e janelas até 200). 300 dias é o mínimo confortável para
`window=200 + horizon=90` ainda sobrar amostra.

**Quando montar DataFrames à mão (inline no teste):** quando o valor exato importa e precisa ser
óbvio na leitura do teste — por exemplo:

- `test_target`: `Close=[10,11,12,9]` para conferir `ret_1d[0]==0.1` e o padrão `[1,1,0]`.
- `test_mma`: `Close` em "V" (`[10,9,8,7,9,11,13,14]`) para forçar um cruzamento conhecido na janela 3.
- `test_modeling`: arrays `x`/`y` com relação plantada (`y=x` com discordância a cada 10) para um
  coeficiente de sinal previsível.
- `test_data`: `raw` minúsculo, fora de ordem, com coluna `Extra`, para o `normalize`.

Regra prática: **fixture** para integração e realismo; **df à mão** para asserir números exatos e
fronteiras (zero, constante, NA). Nunca usar aleatoriedade — toda discordância/ruído deve ser
**determinístico** (ex.: `0.001*sin(arange(n))` no `test_fit_ols`).
