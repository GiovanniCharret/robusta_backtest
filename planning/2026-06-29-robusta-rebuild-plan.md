# ROBUSTA Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small, tested Python package that backtests a single technical indicator by regressing a binary "did price rise over h days" label on a breakout dummy, sweeping parameters and summarizing every model — keeping ONE accumulating foundation DataFrame for review.

**Architecture:** A single **foundation df** is seeded from `yfinance` OHLCV. Every step **adds columns** to it (legacy pattern): a fixed `target.py` adds the date-shifted labels (`ret_{h}d` continuous + `y_{h}d` binary); a swappable `indicators/<x>.py` plug-in adds the indicator value, the "above band" state and the breakout dummy; `modeling.py` fits **two families** per model — logistic on `y_{h}d` and OLS on `ret_{h}d` — via `statsmodels`; `sweep.py` accumulates all columns and returns `(analysis_df, summary_df)`; `run_mma.py` writes both to CSV.

**Tech Stack:** Python 3.11+, `uv` (env), `pandas`, `numpy`, `statsmodels`, `yfinance`, `openpyxl` (escrita .xlsx), `pytest`.

## Global Constraints

- **Documentation lives in `planning/`.** Decisions and progress in `planning/PLAN.md`. **Never edit `planning/PROJECT_BUILDING.md`.**
- **Code convention (mandatory, from CLAUDE.md):** every function has a docstring in this order — (1) *why the function exists*; (2) the input→output logic in **numbered phases** (Entrada → Fase 1 → … → Saída). **Every line of code is commented**, including obvious ones.
- **One foundation df.** All calculations build on the df extracted from `yfinance` and **add columns to it** (so it can be reviewed row-by-row, aligned by date). Nothing returns a bare detached Series that the foundation df doesn't keep.
- **Two outputs (`.xlsx`):** `output/analysis_mma.xlsx` (the enriched foundation df — **1 row per day**, with the date index) and `output/summary_mma.xlsx` (**1 row per model**). Written via `pandas.to_excel` (engine `openpyxl`).
- **Target columns:** for each horizon `h`, add `ret_{h}d = Close[t+h]/Close[t]-1` (continuous, for review) and `y_{h}d = 1 if ret_{h}d > 0 else 0`. Last `h` rows are `NA` and dropped before fitting — no look-ahead in the predictor.
- **Indicator columns (mma):** `mma_w{window}` (value), `mma_w{window}_t{tol}_above` (state), `mma_w{window}_t{tol}_break` (the dummy: `1` only on the crossing day).
- **Two model families per model:** logistic (`statsmodels.Logit`) on `y_{h}d` **and** OLS (`statsmodels.OLS`) on `ret_{h}d`. Both return the **same dict schema** with a `family` key and a unified `r2` (McFadden pseudo for logit, classic R² for OLS); `accuracy` is logit-only (NaN for OLS). Both accept N predictors (future stepwise) though the sweep uses one. Variable-selection methods (stepwise/Lasso/SFS) are future (need multiple predictors).
- **No network in unit tests.** `yfinance` is isolated in `data.py`; all other tests use synthetic DataFrames.
- Default sweep grid: `window ∈ {5,10,20,50,200}`, `tol ∈ {0.0,0.01,0.03}`, `horizons = [10,20,30,45,90]`.
- **Test coverage:** beyond the happy-path tests shown per task, fold in the HIGH/MEDIUM gap tests from `planning/TESTES.md` in the **same** task (TDD). Key ones: target → retorno-zero→0, múltiplos horizontes, não-mutação; mma → janela>série→sem-eventos, `above`-vs-`break` transição; modeling → separação-perfeita→`separacao`, `min_events` fronteira, schema logit==ols; sweep → NaN no fim por família, `sem_eventos` em janela grande.

---

## File Structure

```
rebuild_robusta_backtests/
  pyproject.toml          # minimal: pytest pythonpath = ["src"]
  requirements.txt        # frozen deps (uv pip freeze)
  .gitignore
  src/robusta/
    __init__.py
    data.py               # load_prices + normalize_ohlcv (yfinance isolated here)
    target.py             # add_labels: adds ret_{h}d + y_{h}d   [GENERIC, FIXED]
    indicators/
      __init__.py
      base.py             # Indicator Protocol (NAME, signal_col, add_columns)
      mma.py              # add_columns: mma value, above, break  [PLUG-IN]
    modeling.py           # fit_logit  (1..N predictors)
    sweep.py              # run_sweep -> (analysis_df, summary_df)
    run_mma.py            # build_summary + write_outputs + main (writes .xlsx)
  tests/
    conftest.py           # shared synthetic-price fixtures
    test_smoke.py
    test_target.py
    test_mma.py
    test_modeling.py
    test_sweep.py
    test_data.py
    test_run_mma.py
  output/                 # .xlsx (gitignored)
```

---

### Task 1: Project scaffolding & environment

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `.gitignore`
- Create: `src/robusta/__init__.py`, `src/robusta/indicators/__init__.py`
- Create: `tests/conftest.py`, `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: a runnable `pytest`; the `robusta` import path (`src` on pythonpath); fixture `synthetic_prices` used by later tasks.

- [ ] **Step 1: Initialize git and the uv environment**

```bash
cd "C:/Users/gioch/Documents/Python_Projects/rebuild_robusta_backtests"
git init
uv venv
uv pip install pandas numpy statsmodels yfinance pytest
uv pip freeze > requirements.txt
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
output/
.pytest_cache/
```

- [ ] **Step 3: Create `pyproject.toml`** (only to put `src` on the pytest path — avoids an editable install)

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 4: Create the package marker files**

`src/robusta/__init__.py`:
```python
# Marca o diretório como o pacote `robusta`; sem exports nesta fase.
```

`src/robusta/indicators/__init__.py`:
```python
# Marca o diretório como o subpacote `robusta.indicators`; sem exports.
```

- [ ] **Step 5: Create the shared fixture in `tests/conftest.py`**

```python
# Importa pandas para construir o DataFrame de preços sintético.
import pandas as pd
# Importa numpy para gerar a série determinística (sem aleatoriedade).
import numpy as np
# Importa o decorator de fixture do pytest.
import pytest


# Fixture reutilizada por vários testes: preços sintéticos determinísticos.
@pytest.fixture
def synthetic_prices():
    """
    Por quê: vários testes precisam de um DataFrame OHLCV realista porém
    determinístico (sem rede, sem aleatoriedade) para checar rótulos, dummies,
    fit e sweep de forma reprodutível.

    Lógica (Entrada → Saída):
      Entrada: nenhum argumento.
      Fase 1: cria um índice de datas úteis.
      Fase 2: gera um Close com tendência + ondas senoidais (cruza médias).
      Fase 3: deriva OHLCV simples a partir do Close.
      Saída: DataFrame indexado por data com colunas OHLCV.
    """
    # Fase 1: 300 dias úteis a partir de uma data fixa.
    idx = pd.bdate_range("2020-01-01", periods=300)
    # Fase 2: vetor de posições 0..299 para compor a série.
    t = np.arange(len(idx))
    # Fase 2: Close = nível base + tendência leve + duas ondas (gera cruzamentos).
    close = 100 + 0.05 * t + 8 * np.sin(t / 13) + 3 * np.sin(t / 3.0)
    # Fase 3: monta o DataFrame OHLCV derivando High/Low/Open/Volume do Close.
    df = pd.DataFrame(
        {
            # Open aproximado pelo Close do dia anterior (primeiro = próprio Close).
            "Open": np.r_[close[0], close[:-1]],
            # High = Close + 0.5 (banda superior simples).
            "High": close + 0.5,
            # Low = Close - 0.5 (banda inferior simples).
            "Low": close - 0.5,
            # Close é a própria série gerada.
            "Close": close,
            # Volume constante (irrelevante para mma, mas mantém o schema OHLCV).
            "Volume": 1_000_000,
        },
        # Índice de datas criado na Fase 1.
        index=idx,
    )
    # Saída: DataFrame pronto para os testes.
    return df
```

- [ ] **Step 6: Create a smoke test in `tests/test_smoke.py`**

```python
# Importa o módulo do pacote só para provar que o pythonpath está correto.
import robusta


# Teste de fumaça: garante que o pacote importa e a fixture funciona.
def test_package_imports_and_fixture_loads(synthetic_prices):
    """
    Por quê: validar o scaffolding (import do pacote + fixture) antes de
    qualquer lógica de negócio.

    Lógica: Entrada (fixture) → Fase 1 checa o pacote → Fase 2 checa o df → Saída (asserts).
    """
    # Fase 1: o módulo `robusta` foi importado sem erro.
    assert robusta is not None
    # Fase 2: a fixture entregou um DataFrame com a coluna Close e 300 linhas.
    assert "Close" in synthetic_prices.columns and len(synthetic_prices) == 300
```

- [ ] **Step 7: Run the smoke test (expect PASS)**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: PASS (1 passed).

- [ ] **Step 8: Commit**

```bash
git add .gitignore pyproject.toml requirements.txt src tests
git commit -m "chore: scaffold robusta package, uv env, pytest"
```

---

### Task 2: `target.py` — date-shifted labels added to the foundation df

**Files:**
- Create: `src/robusta/target.py`
- Test: `tests/test_target.py`

**Interfaces:**
- Consumes: a DataFrame with a `Close` column (the foundation df).
- Produces: `add_labels(df: pd.DataFrame, horizons: list[int]) -> pd.DataFrame` — returns a copy with, per horizon, a `ret_{h}d` column (`float`, continuous forward return) and a `y_{h}d` column (`Int8`, `1/0`, `pd.NA` on the last `h` rows).

- [ ] **Step 1: Write the failing test**

`tests/test_target.py`:
```python
# pandas para montar um Close mínimo e checar tipos/valores.
import pandas as pd
# A função sob teste.
from robusta.target import add_labels


# Teste do caminho feliz: retorno contínuo + binário + cauda NA (sem vazamento).
def test_add_labels_adds_continuous_and_binary():
    """
    Por quê: o df-fundação precisa ganhar AMBAS as colunas — o retorno contínuo
    (para revisão) e o binário (o alvo) — e ficar sem rótulo nas últimas h linhas.

    Lógica: Entrada (Close conhecido) → Fase 1 add_labels → Fase 2 ret → Fase 3 y
    → Fase 4 cauda NA → Saída (asserts).
    """
    # Entrada: Close cresce e depois cai.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 9.0]})
    # Fase 1: rótulos para horizonte 1.
    out = add_labels(df, horizons=[1])
    # Fase 2: ret_1d[0] = 11/10 - 1 = 0.1.
    assert round(out["ret_1d"].iloc[0], 4) == 0.1
    # Fase 3: sobe, sobe, cai → 1, 1, 0.
    assert out["y_1d"].tolist()[:3] == [1, 1, 0]
    # Fase 4: última linha sem t+1 → NA em ambas as colunas.
    assert pd.isna(out["y_1d"].iloc[-1]) and pd.isna(out["ret_1d"].iloc[-1])
    # Saída: dtype inteiro anulável no alvo.
    assert str(out["y_1d"].dtype) == "Int8"


# Teste de horizonte maior: confere quantidade de NAs na cauda.
def test_add_labels_nan_tail_length_matches_horizon():
    """
    Por quê: garantir que exatamente h linhas finais ficam sem rótulo.

    Lógica: Entrada (5 closes) → Fase 1 add_labels h=2 → Fase 2 conta NAs → Saída.
    """
    # Entrada: cinco preços.
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0, 4.0, 5.0]})
    # Fase 1: horizonte 2.
    out = add_labels(df, horizons=[2])
    # Fase 2: as 2 últimas linhas devem ser NA.
    assert out["y_2d"].isna().sum() == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_target.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'robusta.target'`.

- [ ] **Step 3: Write minimal implementation**

`src/robusta/target.py`:
```python
# pandas é a base para shift/where e o tipo Int8 anulável.
import pandas as pd


# Constrói a variável dependente deslocando datas futuras de volta para hoje.
def add_labels(df: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """
    Por quê: separar a criação do alvo (genérica, independente de indicador) do
    resto do pipeline. É o mecanismo de "deslocamento de datas" herdado do legado
    que transforma cada dia numa amostra rotulada; adiciona as colunas ao
    df-fundação para revisão linha a linha.

    Lógica (Entrada → Saída):
      Entrada: df-fundação com coluna Close e a lista de horizontes (a "daylist").
      Fase 1: copia o df para não mutar o original do chamador.
      Fase 2: para cada horizonte h, calcula o retorno futuro contínuo do Close.
      Fase 3: anexa ret_{h}d (contínuo) e y_{h}d (binário), preservando NA sem futuro.
      Saída: df-fundação com ret_{h}d e y_{h}d por horizonte.
    """
    # Fase 1: trabalha sobre uma cópia (não mutar a entrada do chamador).
    out = df.copy()
    # Fase 2: itera cada horizonte da daylist.
    for h in horizons:
        # Fase 2: retorno futuro contínuo = Close[t+h]/Close[t] - 1 (shift traz o futuro).
        ret = out["Close"].shift(-h) / out["Close"] - 1
        # Fase 3: anexa a coluna contínua (para revisão), espelho do var_desloc do legado.
        out[f"ret_{h}d"] = ret
        # Fase 3: série de rótulos toda NA, dtype inteiro anulável.
        label = pd.Series(pd.NA, index=out.index, dtype="Int8")
        # Fase 3: onde há retorno (não-NA), marca 1 se positivo, senão 0.
        label[ret.notna()] = (ret[ret.notna()] > 0).astype("Int8")
        # Fase 3: anexa a coluna-alvo binária.
        out[f"y_{h}d"] = label
    # Saída: df-fundação com as colunas de retorno e rótulo.
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_target.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/target.py tests/test_target.py
git commit -m "feat: add date-shifted continuous + binary labels (target.py)"
```

---

### Task 3: `indicators/mma.py` — breakout dummy plug-in (adds columns)

**Files:**
- Create: `src/robusta/indicators/base.py`
- Create: `src/robusta/indicators/mma.py`
- Test: `tests/test_mma.py`

**Interfaces:**
- Consumes: the foundation df with a `Close` column.
- Produces:
  - `base.Indicator` — a `typing.Protocol` documenting `NAME`, `signal_col(**params) -> str`, `add_columns(df, **params) -> pd.DataFrame`.
  - `mma.NAME: str = "mma"`.
  - `mma.value_col(window: int) -> str` → `"mma_w{window}"`.
  - `mma.signal_col(window: int, tol: float = 0.0) -> str` → `"mma_w{window}_t{tol}_break"`.
  - `mma.add_columns(df: pd.DataFrame, window: int, tol: float = 0.0) -> pd.DataFrame` — adds `mma_w{window}`, `mma_w{window}_t{tol}_above`, `mma_w{window}_t{tol}_break` (all aligned to the index) and returns the df.

- [ ] **Step 1: Write the failing test**

`tests/test_mma.py`:
```python
# pandas para construir Closes com cruzamento conhecido.
import pandas as pd
# O módulo-plugin sob teste (passado inteiro ao sweep).
from robusta.indicators import mma


# Teste: add_columns cria valor, estado e a dummy de evento.
def test_add_columns_creates_value_above_break():
    """
    Por quê: o indicador é o PLUG-IN; precisa ACRESCENTAR ao df-fundação o valor
    da média, o estado "acima da banda" e a dummy de rompimento (evento), tudo
    com nomes canônicos que o sweep saberá achar.

    Lógica: Entrada (Close em V) → Fase 1 add_columns → Fase 2 colunas existem
    → Fase 3 dummy é evento 0/1 → Saída.
    """
    # Entrada: cai e volta a subir, cruzando a média de janela 3.
    df = pd.DataFrame({"Close": [10, 9, 8, 7, 9, 11, 13, 14]})
    # Fase 1: adiciona as colunas do mma, janela 3, sem tolerância.
    out = mma.add_columns(df.copy(), window=3, tol=0.0)
    # Fase 2: coluna de valor da média presente.
    assert mma.value_col(3) in out.columns
    # Fase 2: coluna-dummy presente, com o nome canônico.
    scol = mma.signal_col(3, 0.0)
    assert scol in out.columns
    # Fase 3: a dummy é evento → só 0/1 e acende pelo menos uma vez.
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert out[scol].sum() >= 1
    # Saída: dtype Int8 e nome do indicador exposto.
    assert str(out[scol].dtype) == "Int8" and mma.NAME == "mma"


# Teste: tolerância suprime cruzamentos pequenos dentro da banda.
def test_tolerance_suppresses_marginal_cross():
    """
    Por quê: a tolerância existe para ignorar rompimentos fracos; com tol alto,
    um cruzamento marginal não deve acender a dummy.

    Lógica: Entrada (cruzamento marginal) → Fase 1 dois tol → Fase 2 compara → Saída.
    """
    # Entrada: Close que cruza a média por margem pequena.
    df = pd.DataFrame({"Close": [10, 10, 10, 10, 10.05, 10.06, 10.07]})
    # Fase 1: conta eventos sem tolerância e com 3%.
    strict = mma.add_columns(df.copy(), window=3, tol=0.0)[mma.signal_col(3, 0.0)].sum()
    loose = mma.add_columns(df.copy(), window=3, tol=0.03)[mma.signal_col(3, 0.03)].sum()
    # Fase 2/Saída: a tolerância reduz (ou iguala) o número de eventos.
    assert loose <= strict
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mma.py -v`
Expected: FAIL with `ImportError: cannot import name 'mma'` / `No module named 'robusta.indicators.mma'`.

- [ ] **Step 3: Write the interface in `src/robusta/indicators/base.py`**

```python
# Protocol formaliza a interface que todo indicador-plugin deve cumprir.
from typing import Protocol
# pandas para os tipos das assinaturas.
import pandas as pd


# Contrato estrutural de um indicador plugável.
class Indicator(Protocol):
    """
    Por quê: documentar — em um só lugar — a forma que qualquer indicador novo
    (mme, obv, ...) precisa ter para entrar no sweep sem mudar mais nada.

    Lógica: não há execução; é só o contrato. Toda implementação expõe NAME,
    signal_col(**params) e add_columns(df, **params), que ACRESCENTA colunas ao
    df-fundação e o devolve.
    """

    # Nome curto do indicador, usado como coluna no summary.
    NAME: str

    # Devolve o nome canônico da coluna-dummy para os parâmetros dados.
    def signal_col(self, **params) -> str:
        # Protocol: corpo vazio, só assinatura.
        ...

    # Acrescenta as colunas do indicador ao df e devolve o df.
    def add_columns(self, df: pd.DataFrame, **params) -> pd.DataFrame:
        # Protocol: corpo vazio, só assinatura.
        ...
```

- [ ] **Step 4: Write minimal implementation in `src/robusta/indicators/mma.py`**

```python
# pandas para rolling/shift e o tipo Int8.
import pandas as pd


# Nome do indicador, exposto para o summary e para o entrypoint.
NAME = "mma"


# Nome canônico da coluna de valor da média móvel.
def value_col(window: int) -> str:
    """
    Por quê: centralizar a convenção de nome da coluna de valor, para que sweep e
    testes não dupliquem strings mágicas.

    Lógica: Entrada (janela) → Saída (nome `mma_w{window}`).
    """
    # Saída: nome do valor da média para a janela dada.
    return f"mma_w{window}"


# Nome canônico da coluna-dummy (evento de rompimento).
def signal_col(window: int, tol: float = 0.0) -> str:
    """
    Por quê: o sweep precisa descobrir o nome da dummy a partir dos parâmetros,
    sem conhecer o indicador por dentro.

    Lógica: Entrada (janela, tolerância) → Saída (nome `mma_w{window}_t{tol}_break`).
    """
    # Saída: nome da dummy para (janela, tolerância).
    return f"mma_w{window}_t{tol}_break"


# Acrescenta ao df-fundação o valor da média, o estado e a dummy de rompimento.
def add_columns(df: pd.DataFrame, window: int, tol: float = 0.0) -> pd.DataFrame:
    """
    Por quê: este é o PLUG-IN. Em vez de devolver uma série solta, ACRESCENTA suas
    colunas ao df-fundação (igual ao legado), para revisão linha a linha. Trocar
    de indicador = escrever outro arquivo com a mesma interface.

    Lógica (Entrada → Saída):
      Entrada: df-fundação com Close, janela da média e tolerância do rompimento.
      Fase 1: calcula a média móvel simples e a grava em mma_w{window}.
      Fase 2: grava o ESTADO "acima da banda" (Close > mma*(1+tol)).
      Fase 3: grava o EVENTO de cruzamento (acima hoje e não-acima ontem) = a dummy.
      Saída: o df-fundação com as três colunas anexadas.
    """
    # Fase 1: nome e cálculo da média móvel simples do Close.
    vcol = value_col(window)
    # Fase 1: grava o valor da média (depende só da janela).
    df[vcol] = df["Close"].rolling(window).mean()
    # Fase 2: estado booleano "Close acima da banda de tolerância".
    above = df["Close"] > df[vcol] * (1 + tol)
    # Fase 2: grava o estado como Int8 (coluna *_above) para revisão.
    df[f"mma_w{window}_t{tol}_above"] = above.astype("Int8")
    # Fase 3: cruzamento = acima hoje E não-acima ontem (shift preenche o 1º dia como False).
    cross = above & ~above.shift(1, fill_value=False)
    # Fase 3: grava a dummy de evento (coluna *_break) como Int8.
    df[signal_col(window, tol)] = cross.astype("Int8")
    # Saída: df-fundação enriquecido.
    return df
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_mma.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/robusta/indicators/base.py src/robusta/indicators/mma.py tests/test_mma.py
git commit -m "feat: add mma plug-in that appends value/above/break columns"
```

---

### Task 4: `modeling.py` — logistic + OLS fits with edge cases

**Files:**
- Create: `src/robusta/modeling.py`
- Test: `tests/test_modeling.py`

**Interfaces:**
- Consumes: a DataFrame with the target column and predictor column(s).
- Produces two functions with the **same return schema** (keys `family, n, n_eventos, r2, coef, p_value, llf, accuracy, status`; `coef`/`p_value` refer to `x_cols[0]`; `status ∈ {"ok","sem_eventos","separacao","erro"}`):
  - `fit_logit(df, y_col, x_cols, min_events=5) -> dict` — `family="logit"`, `r2`=McFadden pseudo, `accuracy`=in-sample.
  - `fit_ols(df, y_col, x_cols, min_events=5) -> dict` — `family="ols"`, `r2`=classic R², `accuracy`=`NaN`.

- [ ] **Step 1: Write the failing test**

`tests/test_modeling.py`:
```python
# pandas/numpy para plantar uma relação conhecida entre dummy e alvo.
import pandas as pd
import numpy as np
# As duas funções sob teste.
from robusta.modeling import fit_logit, fit_ols


# Teste: relação positiva plantada → coef positivo, family logit, status ok.
def test_fit_logit_recovers_positive_relationship():
    """
    Por quê: se a dummy realmente prevê o alvo binário, o coeficiente logístico
    deve ser positivo — prova de que o fit lê o sinal.

    Lógica: Entrada (alvo ≈ dummy) → Fase 1 fit → Fase 2 asserts → Saída.
    """
    # Entrada: 200 linhas; dummy alterna; alvo = dummy na maioria das vezes.
    n = 200
    x = np.tile([0, 1], n // 2)
    y = x.copy()
    # Introduz discordância determinística (a cada 10, inverte) para evitar separação perfeita.
    y[::10] = 1 - y[::10]
    df = pd.DataFrame({"y_20d": y, "mma_w20_t0.0_break": x})
    # Fase 1: ajusta a logística.
    res = fit_logit(df, y_col="y_20d", x_cols=["mma_w20_t0.0_break"])
    # Fase 2: convergiu, family correta, coeficiente positivo, contagens corretas.
    assert res["status"] == "ok" and res["family"] == "logit"
    assert res["coef"] > 0
    assert res["n"] == n and res["n_eventos"] == n // 2
    # Saída: r2 é um número (não NaN).
    assert res["r2"] == res["r2"]


# Teste: sem eventos → status sem_eventos, sem tentar ajustar.
def test_fit_logit_no_events_returns_status():
    """
    Por quê: a dummy de rompimento pode não ter nenhum 1 numa fatia; o fit deve
    degradar com elegância, não quebrar o sweep.

    Lógica: Entrada (dummy toda 0) → Fase 1 fit → Fase 2 status → Saída.
    """
    # Entrada: alvo variado, dummy constante em 0.
    df = pd.DataFrame({"y_20d": [0, 1, 0, 1, 1, 0], "x": [0, 0, 0, 0, 0, 0]})
    # Fase 1: tenta ajustar.
    res = fit_logit(df, y_col="y_20d", x_cols=["x"], min_events=5)
    # Fase 2: marcado como sem_eventos, métricas NaN.
    assert res["status"] == "sem_eventos"
    assert np.isnan(res["r2"])
    # Saída: contagem de eventos é zero.
    assert res["n_eventos"] == 0


# Teste: OLS sobre alvo contínuo → R² clássico e accuracy NaN.
def test_fit_ols_returns_classic_r2_and_nan_accuracy():
    """
    Por quê: a família OLS roda sobre o retorno contínuo (ret_{h}d) e entrega o R²
    clássico dos materiais de regressão; accuracy não se aplica.

    Lógica: Entrada (ret com efeito plantado da dummy) → Fase 1 fit_ols → Fase 2 asserts → Saída.
    """
    # Entrada: dummy alterna; retorno maior quando dummy=1 (efeito positivo) + ruído determinístico.
    n = 200
    x = np.tile([0, 1], n // 2)
    ret = 0.01 * x + 0.001 * np.sin(np.arange(n))
    df = pd.DataFrame({"ret_20d": ret, "mma_w20_t0.0_break": x})
    # Fase 1: ajusta o OLS sobre o retorno contínuo.
    res = fit_ols(df, y_col="ret_20d", x_cols=["mma_w20_t0.0_break"])
    # Fase 2: family correta, coef positivo, R² no intervalo [0,1], accuracy NaN.
    assert res["status"] == "ok" and res["family"] == "ols"
    assert res["coef"] > 0
    assert 0.0 <= res["r2"] <= 1.0
    assert np.isnan(res["accuracy"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_modeling.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'robusta.modeling'`.

- [ ] **Step 3: Write minimal implementation**

`src/robusta/modeling.py`:
```python
# numpy para NaN e contagens.
import numpy as np
# pandas para manipular as colunas do df.
import pandas as pd
# statsmodels fornece Logit com pseudo-R², p-valores e log-likelihood.
import statsmodels.api as sm
# Exceção específica de separação perfeita (modelo não identificável).
from statsmodels.tools.sm_exceptions import PerfectSeparationError


# Molde padrão de uma linha de métricas para os caminhos de borda (sem ajuste).
def _empty(family: str, n: int, n_eventos: int, status: str) -> dict:
    """
    Por quê: garantir que logit e ols devolvam EXATAMENTE o mesmo schema, mesmo
    quando não há ajuste — assim o sweep trata todas as linhas igual.

    Lógica: Entrada (família, n, eventos, status) → Saída (dict com métricas NaN).
    """
    # Saída: dicionário com contagens preenchidas e métricas NaN.
    return {
        # Identificação da família e contagens.
        "family": family, "n": n, "n_eventos": n_eventos,
        # Métricas indefinidas neste caminho.
        "r2": np.nan, "coef": np.nan, "p_value": np.nan,
        "llf": np.nan, "accuracy": np.nan,
        # Status do caminho de borda.
        "status": status,
    }


# Ajusta uma regressão logística de um (ou mais) preditor(es) e resume métricas.
def fit_logit(df: pd.DataFrame, y_col: str, x_cols: list[str], min_events: int = 5) -> dict:
    """
    Por quê: isolar o ajuste logístico (alvo binário) do laço do sweep, devolvendo
    uma linha plana do summary. Aceita N preditores para habilitar stepwise no futuro.

    Lógica (Entrada → Saída):
      Entrada: df + coluna-alvo binária + colunas-preditoras + mín. eventos.
      Fase 1: descarta NA no alvo/preditores.
      Fase 2: conta eventos; se poucos, alvo ou dummy constantes → sem_eventos.
      Fase 3: ajusta a Logit com constante; captura separação/erros.
      Fase 4: extrai r2 (pseudo), coef, p_value, llf e acurácia in-sample.
      Saída: dicionário (family=logit) com as métricas e o status.
    """
    # Fase 1: mantém só as colunas relevantes e remove NA (cauda do rótulo etc.).
    data = df[[y_col, *x_cols]].dropna()
    # Fase 1: tamanho amostral efetivo após limpeza.
    n = int(len(data))
    # Fase 2: nº de eventos = soma do 1º preditor (a dummy do indicador).
    n_eventos = int(data[x_cols[0]].sum()) if n else 0
    # Fase 2: poucos eventos, ou dummy/alvo constantes → não ajusta.
    if n_eventos < min_events or data[x_cols[0]].nunique() < 2 or data[y_col].nunique() < 2:
        # Retorna o molde marcado como sem_eventos.
        return _empty("logit", n, n_eventos, "sem_eventos")
    # Fase 3: matriz de preditores com constante (intercepto).
    X = sm.add_constant(data[x_cols].astype(float))
    # Fase 3: vetor-alvo como float para o statsmodels.
    y = data[y_col].astype(float)
    # Fase 3: tenta ajustar, capturando separação e quaisquer erros numéricos.
    try:
        # Ajuste silencioso (disp=0 não imprime o log de iterações).
        res = sm.Logit(y, X).fit(disp=0)
    except PerfectSeparationError:
        # Separação perfeita → modelo não identificável.
        return _empty("logit", n, n_eventos, "separacao")
    except Exception:
        # Qualquer outra falha numérica → marca erro, não derruba o sweep.
        return _empty("logit", n, n_eventos, "erro")
    # Fase 4: predição in-sample binarizada em 0.5 para a acurácia de referência.
    pred = (res.predict(X) > 0.5).astype(int)
    # Fase 4: acurácia = fração de acertos in-sample.
    accuracy = float((pred.values == y.values).mean())
    # Saída: dicionário plano com todas as métricas do modelo logístico.
    return {
        # Família e contagens.
        "family": "logit", "n": n, "n_eventos": n_eventos,
        # McFadden pseudo-R² na coluna unificada r2.
        "r2": float(res.prsquared),
        # Coeficiente e p-valor do preditor de interesse (o 1º).
        "coef": float(res.params[x_cols[0]]),
        "p_value": float(res.pvalues[x_cols[0]]),
        # Log-likelihood e acurácia in-sample.
        "llf": float(res.llf), "accuracy": accuracy,
        # Ajuste bem-sucedido.
        "status": "ok",
    }


# Ajusta um OLS de um (ou mais) preditor(es) sobre o retorno contínuo e resume métricas.
def fit_ols(df: pd.DataFrame, y_col: str, x_cols: list[str], min_events: int = 5) -> dict:
    """
    Por quê: a segunda família. Roda sobre o ret_{h}d contínuo e entrega o R²
    clássico dos materiais de regressão, no MESMO schema do fit_logit.

    Lógica (Entrada → Saída):
      Entrada: df + coluna-alvo contínua (ret) + colunas-preditoras + mín. eventos.
      Fase 1: descarta NA no alvo/preditores.
      Fase 2: conta eventos; se poucos ou dummy constante → sem_eventos.
      Fase 3: ajusta o OLS com constante; captura erros.
      Fase 4: extrai r2 (clássico), coef, p_value, llf; accuracy = NaN.
      Saída: dicionário (family=ols) com as métricas e o status.
    """
    # Fase 1: mantém só as colunas relevantes e remove NA.
    data = df[[y_col, *x_cols]].dropna()
    # Fase 1: tamanho amostral efetivo.
    n = int(len(data))
    # Fase 2: nº de eventos = soma do 1º preditor.
    n_eventos = int(data[x_cols[0]].sum()) if n else 0
    # Fase 2: poucos eventos ou dummy constante → não ajusta (x sem variância quebra o OLS).
    if n_eventos < min_events or data[x_cols[0]].nunique() < 2:
        # Retorna o molde marcado como sem_eventos.
        return _empty("ols", n, n_eventos, "sem_eventos")
    # Fase 3: matriz de preditores com constante (intercepto).
    X = sm.add_constant(data[x_cols].astype(float))
    # Fase 3: vetor-alvo contínuo como float.
    y = data[y_col].astype(float)
    # Fase 3: tenta ajustar o OLS, capturando erros numéricos.
    try:
        # OLS ordinário (sem iterações; não há disp).
        res = sm.OLS(y, X).fit()
    except Exception:
        # Falha numérica → marca erro, não derruba o sweep.
        return _empty("ols", n, n_eventos, "erro")
    # Saída: dicionário plano com as métricas do OLS.
    return {
        # Família e contagens.
        "family": "ols", "n": n, "n_eventos": n_eventos,
        # R² clássico na coluna unificada r2.
        "r2": float(res.rsquared),
        # Coeficiente e p-valor do preditor de interesse.
        "coef": float(res.params[x_cols[0]]),
        "p_value": float(res.pvalues[x_cols[0]]),
        # Log-likelihood; acurácia não se aplica ao OLS.
        "llf": float(res.llf), "accuracy": np.nan,
        # Ajuste bem-sucedido.
        "status": "ok",
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_modeling.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/modeling.py tests/test_modeling.py
git commit -m "feat: add logistic + OLS fits with edge-case handling (modeling.py)"
```

---

### Task 5: `sweep.py` — accumulate columns → (analysis_df, summary_df)

**Files:**
- Create: `src/robusta/sweep.py`
- Test: `tests/test_sweep.py`

**Interfaces:**
- Consumes: an already-labeled foundation df (`y_{h}d` and `ret_{h}d` present), an indicator **module** (exposing `NAME`, `signal_col`, `add_columns`), `modeling.fit_logit` + `modeling.fit_ols`.
- Produces: `run_sweep(df, indicator, param_grid, horizons, min_events=5) -> tuple[pd.DataFrame, pd.DataFrame]`.
  `param_grid: dict[str, list]` (e.g. `{"window":[...], "tol":[...]}`).
  Returns `(analysis_df, summary_df)`: `analysis_df` is the foundation df with every combo's columns accumulated; `summary_df` has **two rows per (param combo × horizon)** — `family="logit"` (fit on `y_{h}d`) and `family="ols"` (fit on `ret_{h}d`) — with columns `indicator, <params...>, horizon, family, n, n_eventos, r2, coef, p_value, llf, accuracy, status`, sorted by `["family","r2"]` (r2 desc, NaN last).

- [ ] **Step 1: Write the failing test**

`tests/test_sweep.py`:
```python
# As peças que o sweep orquestra.
from robusta.target import add_labels
from robusta.indicators import mma
from robusta.sweep import run_sweep


# Teste: o sweep acumula colunas no df e gera o summary com as DUAS famílias.
def test_run_sweep_accumulates_columns_and_two_families(synthetic_prices):
    """
    Por quê: validar as DUAS saídas — o df-fundação enriquecido (colunas
    acumuladas) e o summary (duas linhas por modelo: logit + ols) com schema correto.

    Lógica: Entrada (preços rotulados + grid) → Fase 1 run_sweep → Fase 2 summary
    → Fase 3 analysis acumulado → Saída.
    """
    # Entrada: rótulos para dois horizontes.
    horizons = [10, 20]
    df = add_labels(synthetic_prices, horizons=horizons)
    # Grid pequeno: 2 janelas × 2 tolerâncias.
    grid = {"window": [5, 20], "tol": [0.0, 0.01]}
    # Fase 1: roda o sweep passando o MÓDULO do indicador.
    analysis, summary = run_sweep(df, mma, grid, horizons)
    # Fase 2: 2×2×2 combinações×horizontes × 2 famílias = 16 linhas.
    assert len(summary) == 2 * 2 * 2 * 2
    # Fase 2: ambas as famílias presentes.
    assert set(summary["family"]) == {"logit", "ols"}
    # Fase 2: colunas-chave do summary presentes.
    for col in ["indicator", "window", "tol", "horizon", "family", "r2", "p_value", "status"]:
        assert col in summary.columns
    # Fase 2: indicador correto.
    assert (summary["indicator"] == "mma").all()
    # Fase 3: o df-fundação ganhou as colunas de valor e dummy acumuladas.
    assert mma.value_col(5) in analysis.columns
    assert mma.signal_col(20, 0.01) in analysis.columns
    # Saída: analysis continua com 1 linha por dia (mesmo tamanho da entrada).
    assert len(analysis) == len(synthetic_prices)


# Teste: ordenação do summary por r2 desc DENTRO de cada família, NaN no fim.
def test_run_sweep_sorted_within_family(synthetic_prices):
    """
    Por quê: o usuário compara modelos dentro de cada família; o r2 do logit
    (pseudo) e do ols (clássico) não estão na mesma escala, então cada família é
    rankeada em separado e NaN afunda.

    Lógica: Entrada (preços) → Fase 1 sweep → Fase 2 confere ordenação por família → Saída.
    """
    # Entrada/Fase 1: um horizonte, grid mínimo.
    df = add_labels(synthetic_prices, horizons=[10])
    analysis, summary = run_sweep(df, mma, {"window": [5, 200], "tol": [0.0]}, [10])
    # Fase 2: dentro de cada família, r2 dos ok em ordem não-crescente.
    for fam in ["logit", "ols"]:
        oks = summary[(summary["family"] == fam) & (summary["status"] == "ok")]["r2"].tolist()
        assert oks == sorted(oks, reverse=True)
    # Saída: 2 janelas × 1 tol × 1 horizonte × 2 famílias = 4 linhas.
    assert len(summary) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sweep.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'robusta.sweep'`.

- [ ] **Step 3: Write minimal implementation**

`src/robusta/sweep.py`:
```python
# itertools.product expande o grid de parâmetros em combinações.
from itertools import product
# pandas para montar o DataFrame de summary.
import pandas as pd
# As duas famílias de ajuste (cada uma vira uma linha do summary).
from robusta.modeling import fit_logit, fit_ols


# Percorre o grid, acumula colunas no df-fundação e resume cada modelo (2 famílias).
def run_sweep(df, indicator, param_grid, horizons, min_events=5):
    """
    Por quê: orquestrar o backtest sem conhecer o indicador — recebe o MÓDULO do
    indicador por injeção e usa sua interface (NAME/signal_col/add_columns). Mantém
    o princípio de "um df-fundação que acumula colunas" e entrega as duas saídas.

    Lógica (Entrada → Saída):
      Entrada: df já rotulado, o módulo do indicador, o grid {param: [valores]},
        a lista de horizontes e o mínimo de eventos.
      Fase 1: expande o grid em todas as combinações de parâmetros.
      Fase 2: para cada combinação, ACRESCENTA as colunas do indicador ao df.
      Fase 3: para cada horizonte, ajusta logit (em y) e ols (em ret) → DUAS linhas.
      Fase 4: monta o summary e ordena por [family, r2] (r2 desc, NaN no fim).
      Saída: (analysis_df enriquecido, summary_df).
    """
    # Fase 1: nomes dos parâmetros e listas de valores, na mesma ordem.
    names = list(param_grid.keys())
    # Fase 1: todas as combinações cartesianas dos valores.
    combos = list(product(*[param_grid[k] for k in names]))
    # df-fundação que vamos enriquecer ao longo do laço (sweep é dono dele).
    analysis = df
    # Acumulador das linhas do summary.
    rows = []
    # Fase 2: itera cada combinação de parâmetros.
    for combo in combos:
        # Fase 2: mapeia nome→valor desta combinação.
        params = dict(zip(names, combo))
        # Fase 2: ACRESCENTA as colunas do indicador ao df-fundação.
        analysis = indicator.add_columns(analysis, **params)
        # Fase 2: nome canônico da coluna-dummy desta combinação.
        x_col = indicator.signal_col(**params)
        # Fase 3: ajusta as duas famílias por horizonte.
        for h in horizons:
            # Fase 3: bloco de identificação compartilhado pelas duas linhas.
            ident = {"indicator": indicator.NAME, **params, "horizon": h}
            # Fase 3: logística sobre o alvo binário y_{h}d.
            logit = fit_logit(analysis, y_col=f"y_{h}d", x_cols=[x_col], min_events=min_events)
            # Fase 3: OLS sobre o retorno contínuo ret_{h}d.
            ols = fit_ols(analysis, y_col=f"ret_{h}d", x_cols=[x_col], min_events=min_events)
            # Fase 3: uma linha por família (identificação + métricas).
            rows.append({**ident, **logit})
            rows.append({**ident, **ols})
    # Fase 4: DataFrame com todas as linhas de modelo.
    summary = pd.DataFrame(rows)
    # Fase 4: ordena por família e r2 desc; na_position='last' joga NaN pro fim.
    summary = summary.sort_values(["family", "r2"], ascending=[True, False], na_position="last").reset_index(drop=True)
    # Saída: o df-fundação enriquecido e o summary.
    return analysis, summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sweep.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/sweep.py tests/test_sweep.py
git commit -m "feat: sweep accumulates columns and returns (analysis, summary)"
```

---

### Task 6: `data.py` — yfinance loader (network isolated)

**Files:**
- Create: `src/robusta/data.py`
- Test: `tests/test_data.py`

**Interfaces:**
- Consumes: nothing internal (wraps `yfinance`).
- Produces:
  - `normalize_ohlcv(raw: pd.DataFrame) -> pd.DataFrame` — pure: keeps `Open,High,Low,Close,Volume`, sorts by index, raises `ValueError` if `Close` missing.
  - `load_prices(ticker: str, start: str, end: str) -> pd.DataFrame` — calls `yfinance.download` then `normalize_ohlcv`. **Not unit-tested** (network).

- [ ] **Step 1: Write the failing test (pure helper only)**

`tests/test_data.py`:
```python
# pandas para montar um raw "à la yfinance".
import pandas as pd
# pytest para checar a exceção.
import pytest
# Só o helper puro é testado (load_prices usa rede e fica de fora).
from robusta.data import normalize_ohlcv


# Teste: normaliza colunas e ordena o índice.
def test_normalize_sorts_and_keeps_ohlcv():
    """
    Por quê: o yfinance pode devolver linhas fora de ordem e colunas extras; o
    pipeline assume OHLCV ordenado por data. Este helper garante isso e é puro
    (testável sem rede).

    Lógica: Entrada (raw desordenado) → Fase 1 normalize → Fase 2 asserts → Saída.
    """
    # Entrada: duas datas fora de ordem, com uma coluna extra.
    raw = pd.DataFrame(
        {"Open": [2, 1], "High": [2, 1], "Low": [2, 1], "Close": [2, 1],
         "Volume": [2, 1], "Extra": [9, 9]},
        index=pd.to_datetime(["2020-01-02", "2020-01-01"]),
    )
    # Fase 1: normaliza.
    out = normalize_ohlcv(raw)
    # Fase 2: índice ordenado (01 antes de 02).
    assert list(out.index) == sorted(out.index)
    # Fase 2: só as 5 colunas OHLCV permanecem.
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    # Saída: o Close foi reordenado junto (primeira linha = 1).
    assert out["Close"].iloc[0] == 1


# Teste: sem Close → erro explícito.
def test_normalize_requires_close():
    """
    Por quê: falhar cedo e claro se a fonte não trouxe o Close (alvo depende dele).

    Lógica: Entrada (sem Close) → Fase 1 espera ValueError → Saída.
    """
    # Entrada: raw sem a coluna Close.
    raw = pd.DataFrame({"Open": [1]}, index=pd.to_datetime(["2020-01-01"]))
    # Fase 1/Saída: deve levantar ValueError.
    with pytest.raises(ValueError):
        normalize_ohlcv(raw)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'robusta.data'`.

- [ ] **Step 3: Write minimal implementation**

`src/robusta/data.py`:
```python
# pandas para o tipo DataFrame e a ordenação.
import pandas as pd
# yfinance é a fonte de preços (isolada neste módulo).
import yfinance as yf


# Colunas OHLCV canônicas que o resto do pipeline assume.
_OHLCV = ["Open", "High", "Low", "Close", "Volume"]


# Padroniza um DataFrame bruto de preços para o schema OHLCV ordenado.
def normalize_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Por quê: blindar o pipeline contra variações da fonte (ordem das linhas,
    colunas extras). Função pura → testável sem rede. É a base do df-fundação.

    Lógica (Entrada → Saída):
      Entrada: DataFrame bruto indexado por data.
      Fase 1: valida a presença do Close (sem ele não há alvo).
      Fase 2: ordena por data crescente.
      Fase 3: seleciona apenas as colunas OHLCV presentes.
      Saída: DataFrame OHLCV ordenado (o df-fundação).
    """
    # Fase 1: Close é obrigatório; falha cedo e claro.
    if "Close" not in raw.columns:
        # Levanta erro explícito quando o Close não veio.
        raise ValueError("raw precisa da coluna 'Close'")
    # Fase 2: ordena pelo índice de datas.
    ordered = raw.sort_index()
    # Fase 3: mantém só as colunas OHLCV que existirem, na ordem canônica.
    cols = [c for c in _OHLCV if c in ordered.columns]
    # Saída: subconjunto ordenado.
    return ordered[cols]


# Baixa os preços de um ticker e devolve o df-fundação OHLCV normalizado.
def load_prices(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    Por quê: concentrar TODO o acesso à rede num único ponto, para que os demais
    módulos sejam puros e testáveis. Não é coberto por teste unitário (usa rede).

    Lógica (Entrada → Saída):
      Entrada: ticker e janela de datas (start, end).
      Fase 1: baixa os dados via yfinance.
      Fase 2: achata colunas MultiIndex se houver.
      Fase 3: normaliza para OHLCV ordenado.
      Saída: df-fundação pronto para add_labels.
    """
    # Fase 1: download bruto (auto_adjust=True usa preços ajustados no Close).
    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    # Fase 2: yfinance pode devolver colunas MultiIndex (1 ticker) → achata.
    if isinstance(raw.columns, pd.MultiIndex):
        # Mantém o primeiro nível (Open/High/.../Close), descartando o ticker.
        raw.columns = raw.columns.get_level_values(0)
    # Fase 3/Saída: normaliza e devolve.
    return normalize_ohlcv(raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/data.py tests/test_data.py
git commit -m "feat: add yfinance loader with pure normalize helper (data.py)"
```

---

### Task 7: `run_mma.py` — end-to-end entrypoint (writes both `.xlsx`)

**Files:**
- Create: `src/robusta/run_mma.py`
- Test: `tests/test_run_mma.py`

**Interfaces:**
- Consumes: `target.add_labels`, `indicators.mma`, `sweep.run_sweep`, `data.load_prices`.
- Produces:
  - `build_summary(prices: pd.DataFrame, *, windows, tols, horizons, min_events=5) -> tuple[pd.DataFrame, pd.DataFrame]` — pure orchestration over an already-loaded price df; returns `(analysis_df, summary_df)` (network-free; unit-tested).
  - `write_outputs(analysis, summary, outdir="output") -> tuple[Path, Path]` — creates `outdir` and writes `analysis_mma.xlsx` (with date index) + `summary_mma.xlsx` (`index=False`) via `to_excel`; network-free, unit-tested.
  - `main(ticker="^BVSP", start="2010-01-01", end="2024-12-31") -> None` — loads prices, calls `build_summary`, then `write_outputs`.

- [ ] **Step 1: Write the failing test**

`tests/test_run_mma.py`:
```python
# A orquestração pura sob teste.
from robusta.run_mma import build_summary


# Teste e2e (sem rede): df sintético → (analysis, summary) coerentes.
def test_build_summary_end_to_end(synthetic_prices):
    """
    Por quê: provar que as peças se conectam ponta a ponta (rótulo → dummy → fit →
    summary) e que as DUAS saídas saem corretas, sem tocar a rede.

    Lógica: Entrada (preços sintéticos) → Fase 1 build_summary → Fase 2 summary
    → Fase 3 analysis → Saída.
    """
    # Fase 1: roda o pipeline com um grid pequeno.
    analysis, summary = build_summary(
        synthetic_prices, windows=[5, 20], tols=[0.0], horizons=[10, 20], min_events=1
    )
    # Fase 2: 2 janelas × 1 tol × 2 horizontes × 2 famílias = 8 linhas de modelo.
    assert len(summary) == 8
    # Fase 2: schema essencial do summary presente (com family e r2 unificado).
    assert {"indicator", "window", "tol", "horizon", "family", "r2", "status"} <= set(summary.columns)
    assert set(summary["family"]) == {"logit", "ols"}
    assert (summary["indicator"] == "mma").all()
    # Fase 3: analysis é por-dia, com rótulos e retorno acumulados.
    assert "y_10d" in analysis.columns and "ret_10d" in analysis.columns
    # Saída: uma linha por dia (mesmo tamanho da entrada).
    assert len(analysis) == len(synthetic_prices)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_mma.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'robusta.run_mma'`.

- [ ] **Step 3: Write minimal implementation**

`src/robusta/run_mma.py`:
```python
# Path para criar a pasta output e escrever os .xlsx.
from pathlib import Path
# pandas para o tipo do df.
import pandas as pd
# As peças do pipeline.
from robusta.data import load_prices
from robusta.target import add_labels
from robusta.indicators import mma
from robusta.sweep import run_sweep


# Orquestração pura: de um df de preços às duas saídas (sem rede).
def build_summary(prices: pd.DataFrame, *, windows, tols, horizons, min_events: int = 5):
    """
    Por quê: separar a orquestração (testável, sem rede) do I/O (main). Recebe um
    df já carregado para que o teste e2e injete preços sintéticos.

    Lógica (Entrada → Saída):
      Entrada: df OHLCV + listas de janelas, tolerâncias e horizontes.
      Fase 1: cria os rótulos ret_{h}d/y_{h}d no df-fundação.
      Fase 2: monta o grid de parâmetros do mma.
      Fase 3: roda o sweep com o módulo mma (acumula colunas + resume).
      Saída: (analysis_df, summary_df).
    """
    # Fase 1: anexa as colunas-alvo para todos os horizontes.
    labeled = add_labels(prices, horizons=horizons)
    # Fase 2: grid de parâmetros do indicador.
    grid = {"window": windows, "tol": tols}
    # Fase 3/Saída: executa o sweep injetando o módulo plug-in mma.
    return run_sweep(labeled, mma, grid, horizons, min_events=min_events)


# Escreve as duas saídas em disco no formato .xlsx.
def write_outputs(analysis, summary, outdir="output"):
    """
    Por quê: isolar a escrita em disco (formato .xlsx, via engine openpyxl) da
    lógica e do download, para poder testá-la SEM rede e trocar o formato/local
    num só ponto.

    Lógica (Entrada → Saída):
      Entrada: analysis, summary e a pasta de saída.
      Fase 1: garante a existência da pasta.
      Fase 2: escreve o analysis (índice de datas) em .xlsx.
      Fase 3: escreve o summary (sem índice) em .xlsx.
      Saída: (caminho_analysis, caminho_summary).
    """
    # Fase 1: destino como Path; cria a pasta (e pais) se faltar.
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    # Fase 2: caminho e escrita do df-fundação por dia.
    analysis_path = out / "analysis_mma.xlsx"
    analysis.to_excel(analysis_path)
    # Fase 3: caminho e escrita do summary de modelos.
    summary_path = out / "summary_mma.xlsx"
    summary.to_excel(summary_path, index=False)
    # Saída: os dois caminhos.
    return analysis_path, summary_path


# Entrypoint de linha de comando: baixa, resume e salva os dois .xlsx.
def main(ticker: str = "^BVSP", start: str = "2010-01-01", end: str = "2024-12-31") -> None:
    """
    Por quê: ponto de entrada humano; concentra o I/O (download + escrita) fora da
    lógica pura para manter build_summary testável.

    Lógica (Entrada → Saída):
      Entrada: ticker e janela de datas.
      Fase 1: baixa os preços (rede).
      Fase 2: roda build_summary com o grid default.
      Fase 3: escreve as duas saídas .xlsx via write_outputs.
      Saída: output/analysis_mma.xlsx e output/summary_mma.xlsx em disco.
    """
    # Fase 1: download dos preços do ticker.
    prices = load_prices(ticker, start, end)
    # Fase 2: gera as duas saídas com os grids default do projeto.
    analysis, summary = build_summary(
        prices,
        # Janelas default do sweep.
        windows=[5, 10, 20, 50, 200],
        # Tolerâncias default do sweep.
        tols=[0.0, 0.01, 0.03],
        # Horizontes default (a daylist).
        horizons=[10, 20, 30, 45, 90],
    )
    # Fase 3: escreve os dois .xlsx via write_outputs.
    analysis_path, summary_path = write_outputs(analysis, summary)
    # Fase 3: feedback no console de onde os arquivos foram salvos.
    print(f"{analysis_path.name} ({len(analysis)} dias) e {summary_path.name} ({len(summary)} modelos) salvos em output/")


# Permite rodar como script: `python -m robusta.run_mma`.
if __name__ == "__main__":
    # Chama main com os defaults.
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_run_mma.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests PASS (smoke, target, mma, modeling, sweep, data, run_mma).

- [ ] **Step 6: Commit**

```bash
git add src/robusta/run_mma.py tests/test_run_mma.py
git commit -m "feat: end-to-end mma entrypoint writing analysis + summary CSVs"
```

- [ ] **Step 7 (optional manual check): run against a real ticker**

Run: `PYTHONPATH=src uv run python -m robusta.run_mma`
(The `PYTHONPATH=src` is required: the `pyproject.toml` `pythonpath` only applies to pytest, not to `python -m`. On PowerShell: `$env:PYTHONPATH="src"; uv run python -m robusta.run_mma`.)
Expected: prints the save message; `output/analysis_mma.xlsx` (per-day, ~50 columns) and `output/summary_mma.xlsx` (150 rows = 75 modelos × 2 famílias) exist. (Requires network; not part of the test suite.) **Verified 2026-06-29 on `^BVSP`: 3715 dias, 150 modelos.**

---

## Done When
- `uv run pytest -v` is green across all modules.
- `python -m robusta.run_mma` produces BOTH `output/analysis_mma.xlsx` (per-day foundation df) and `output/summary_mma.xlsx` (per-model) — manual, networked check.
- The foundation df accumulates all calculation columns and is reviewable row-by-row.
- Every function carries the structured docstring + line comments required by the project convention.
- `planning/PLAN.md` is updated to mark the build phase and link this plan.
