# Multi-indicador (9 plug-ins + summary unificado) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estender o backtest de 1 indicador (`mma`) para 10, cada um como plug-in isolado que vira uma dummy de *onset* bullish, com um summary por indicador e um `summary_ALL.xlsx` rankeável entre indicadores.

**Architecture:** Um `runner.py` genérico (extraído de `run_mma`) roda qualquer módulo-indicador via `sweep.run_sweep` (que já é agnóstico e **não muda**). `run_mma.py` vira wrapper fino do `mma`. `run_all.py` baixa preços 1×, itera o roster de `config.INDICATORS`/`config.PARAM_GRIDS`, escreve um par de `.xlsx` por indicador e concatena tudo num master rankeável. Cada indicador é um módulo separado (duplicação da lógica de transição aceita, por decisão do spec).

**Tech Stack:** Python, pandas, numpy, statsmodels, scipy, pytest, ambiente `uv`. Saída `.xlsx` (openpyxl).

## Global Constraints

- **Docstrings + comentário por linha** em toda função, na ordem exigida pelo `CLAUDE.md` (por quê → fases numeradas Entrada→Saída; toda linha comentada). É regra dura do projeto.
- **Onset bullish = transição para o estado**: `onset = state & ~state.shift(1, fill_value=False)` (1 só no 1º dia da sequência; usa só passado/presente → sem vazamento).
- **Nomes canônicos harmonizados** (decisão 2026-07-07): estado em `*_state` (Int8), onset em `*_signal` (Int8). Vale para os 10 módulos, **incluindo o `mma`** (renomeado de `_above`/`_break`).
- **Grid vem só de `config.PARAM_GRIDS`** (decisão 2026-07-07): módulos **não** têm `PARAM_GRID` próprio.
- **Saída plana** em `OUTPUT_DIR` com sufixo (decisão 2026-07-07): `analysis_<nome>.xlsx`, `summary_<nome>.xlsx`, `summary_ALL.xlsx`. Sem subpastas.
- **Só bullish** nesta fase. **Sem multi-preditor / stepwise / walk-forward.**
- Todos os dtypes de dummy/estado = `Int8`.
- `sweep.run_sweep` **não é alterado** por nenhuma task.

### Decisão persist (resolvida 2026-07-08)

**Todos os 10 módulos têm o parâmetro `persist`**, com o bloco de streak idêntico ao do `mma`
(trocando `above` pelo `state` do módulo): `persist=0` → onset puro (`*_signal`); `persist=k` →
onset + k dias mantendo o estado, carimbado **one-shot no dia da confirmação** (`*_persist{k}`),
sem vazamento. O **grid decide quem varre o quê** (painel único em config): os **8 indicadores de
regime** (`mma, mme, obv, vwap, rsi, macd, donchian, bollinger`) varrem
`PERSISTENCES = [0, 1, 2, 3, 4]`; os **2 de evento pontual** (`alto_volume, exaustao_atr`) ficam
em `persist=[0]` (o estado deles raramente dura 2+ dias consecutivos — o módulo suporta; ativar
depois é editar 1 linha do config). `config.PERSISTENCES` é atualizado de `[0, 3, 4]` para
`[0, 1, 2, 3, 4]`.

### Decisão tol do legado (resolvida 2026-07-10)

O legado suaviza os limiares de `exaustao_atr` e `alto_volume` com `tolerancia_erro = 0.005`
global. No rebuild isso vira a **dimensão `tol` do grid** desses dois módulos, com
`tol = [0.0, 0.005]`: limiar `≥ mult·referência·(1−tol)`. **Sentido do botão: tol maior →
limiar menor → MAIS eventos** (oposto do `tol` de mma/mme/vwap, que aperta a banda).

### Decisão confirm de preço (resolvida 2026-07-10)

`persist` não se aplica na prática aos 2 indicadores de evento (picos consecutivos são raros e
autodestrutivos — o pico infla a própria referência). A pergunta certa neles é outra: **depois do
evento, o preço SEGUROU por k dias?** Nova dimensão `confirm` (só `alto_volume` e `exaustao_atr`):
`confirm=0` → evento puro; `confirm=k` → evento no dia t **e** `Close[t+1..t+k] ≥ Close[t]`, com a
dummy carimbada **one-shot no dia t+k** (usa só passado/presente → sem vazamento). **Semântica
(confirmada 2026-07-10): a referência é FIXA no Close do dia do evento** — os k dias podem oscilar
entre si; o que não pode é fechar abaixo do nível do evento. NÃO exige altas consecutivas
(`Close[t+j] > Close[t+j−1]` seria outra medida — momentum monotônico — descartada por frágil). Grid:
`confirm = [0, 1, 2, 3, 4]` nos dois. Precedência de nome no `signal_col`: `confirm > persist > onset`
(no grid real nunca combinam: os eventos têm `persist=[0]`). Com isso os módulos de evento têm
20 combos cada. Total geral: **215 combos × 3 horizontes × 2 famílias ≈ 1.290 linhas** no master.

### Ordem canônica das colunas do summary (produzida por `run_sweep`)

`indicator`, `<params do indicador>`, `horizon`, `family`, `n`, `n_eventos`, `r2`, `coef`, `p_value`, `llf`, `accuracy`, `status`, `odds_ratio`, `lift`, `fisher_p`.

---

## Task 1: Harmonizar nomes de coluna do `mma` (`_above`→`_state`, `_break`→`_signal`)

**Files:**
- Modify: `src/robusta/indicators/mma.py`
- Modify: `tests/test_mma.py`

**Interfaces:**
- Consumes: nada novo.
- Produces: `mma.signal_col(window, tol=0.0, persist=0)` passa a devolver `mma_w{window}_t{tol}_signal` para `persist=0` (antes `_break`); a coluna de estado passa a se chamar `mma_w{window}_t{tol}_state` (antes `_above`). `value_col`/`persist{k}` inalterados. `NAME` continua `"mma"`.

- [ ] **Step 1: Atualizar os testes que fixam os nomes antigos**

Em `tests/test_mma.py`, trocar as duas referências a `_above` e ao helper `_break`:

```python
# test_break_is_event_not_state — trocar a leitura do estado:
    # Fase 2: o estado state fica ligado em vários dias (mais que o signal).
    state = out[f"mma_w3_t0.0_state"]   # era: mma_w3_t0.0_above
    sig = out[mma.signal_col(3, 0.0)]
    assert state.sum() > sig.sum()
    # Fase 3: cada signal=1 corresponde a uma transição (state hoje, não-state ontem).
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    # Saída: o nº de signals é exatamente o nº de transições 0→1.
    assert int(sig.sum()) == int(transitions)
```

E em `test_signal_col_persist_name`, o retorno de `persist=0` agora termina em `_signal` (o assert `== mma.signal_col(3, 0.0)` continua válido porque compara com a própria função — mantém como está).

- [ ] **Step 2: Rodar os testes do mma para vê-los FALHAR**

Run: `uv run pytest tests/test_mma.py -v`
Expected: FAIL — `mma.add_columns` ainda grava `_above`/`_break`, então `mma_w3_t0.0_state` não existe (KeyError) e `signal_col` devolve `_break`.

- [ ] **Step 3: Renomear as colunas no `mma.add_columns` e `signal_col`**

Em `src/robusta/indicators/mma.py`, no `signal_col`, trocar o sufixo do caminho `persist=0`:

```python
    # Saída: nome da dummy de onset para (janela, tolerância).
    return f"mma_w{window}_t{tol}_signal"   # era: _break
```

E em `add_columns`, renomear a coluna de estado e o comentário:

```python
    # Fase 2: estado booleano "Close acima da banda de tolerância".
    above = df["Close"] > df[vcol] * (1 + tol)
    # Fase 2: grava o ESTADO como Int8 (coluna *_state) para revisão.
    df[f"mma_w{window}_t{tol}_state"] = above.astype("Int8")   # era: _above
```

- [ ] **Step 4: Rodar a suíte inteira e ver tudo verde**

Run: `uv run pytest -v`
Expected: PASS — 38 testes (o rename é interno; `run_mma`/`sweep`/`config` usam `signal_col`/`value_col`, não os literais).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/indicators/mma.py tests/test_mma.py
git commit -m "refactor(mma): harmonize column names to _state/_signal for multi-indicator parity"
```

---

## Task 2: Extrair `runner.py` genérico e afinar `run_mma.py` para wrapper

**Files:**
- Create: `src/robusta/runner.py`
- Create: `tests/test_runner.py`
- Modify: `src/robusta/run_mma.py`

**Interfaces:**
- Consumes: `add_labels` (target), `run_sweep` (sweep), qualquer módulo-indicador (protocolo `NAME`/`signal_col`/`add_columns`).
- Produces:
  - `runner.build_summary(prices, indicator, param_grid, horizons, min_events=5) -> (analysis, summary)`
  - `runner.write_outputs(analysis, summary, name, outdir="output") -> (analysis_path, summary_path)` grava `analysis_{name}.xlsx` e `summary_{name}.xlsx` (2 abas: `summary` + `dicionário`).
  - `runner.summary_dictionary(summary) -> DataFrame[coluna, grupo, significado, como_ler]` com **uma linha por coluna presente** no summary (params variam por indicador).
  - `run_mma.build_summary(prices, *, windows, tols, horizons, persists=(0,), min_events=5)` e `run_mma.write_outputs(analysis, summary, outdir="output")` passam a **delegar** ao runner (assinaturas antigas preservadas → `test_run_mma.py`/`test_config.py` seguem verdes).

- [ ] **Step 1: Escrever o teste do runner genérico**

```python
# tests/test_runner.py
# pandas para reler o xlsx e checar colunas.
import pandas as pd
# As peças genéricas sob teste.
from robusta.runner import build_summary, write_outputs, summary_dictionary
# O mma serve de indicador-cobaia (já existe e é conhecido).
from robusta.indicators import mma


# Teste: build_summary genérico roda qualquer módulo via injeção.
def test_generic_build_summary_runs_any_indicator(synthetic_prices):
    """
    Por quê: provar que o runner é agnóstico ao indicador — recebe o MÓDULO e um
    grid arbitrário e devolve (analysis, summary) coerentes, sem conhecer o mma.

    Lógica: Entrada (preços + módulo mma + grid) → Fase 1 build_summary → Fase 2
    contagem/schema → Saída.
    """
    # Fase 1: grid pequeno do mma, dois horizontes.
    analysis, summary = build_summary(
        synthetic_prices, mma, {"window": [5, 20], "tol": [0.0]}, [10, 20], min_events=1
    )
    # Fase 2: 2 janelas × 1 tol × 2 horizontes × 2 famílias = 8 linhas.
    assert len(summary) == 8
    # Fase 2: schema essencial + indicador correto.
    assert {"indicator", "horizon", "family", "r2", "status"} <= set(summary.columns)
    assert (summary["indicator"] == "mma").all()
    # Saída: analysis é 1 linha por dia.
    assert len(analysis) == len(synthetic_prices)


# Teste: o dicionário cobre EXATAMENTE as colunas do summary (params variam).
def test_summary_dictionary_matches_columns(synthetic_prices):
    """
    Por quê: cada indicador tem params diferentes (window/tol/persist, N, mult...);
    o dicionário precisa ter uma linha por coluna real do summary — nem mais, nem menos.

    Lógica: Entrada (summary do mma com persist) → Fase 1 summary_dictionary → Saída.
    """
    # Fase 1: summary com a coluna extra `persist` no grid.
    _, summary = build_summary(
        synthetic_prices, mma, {"window": [5], "tol": [0.0], "persist": [0]}, [10], min_events=1
    )
    # Fase 1: gera a legenda a partir das colunas reais.
    dic = summary_dictionary(summary)
    # Saída: cobertura exata (inclui a coluna `persist`).
    assert set(dic["coluna"]) == set(summary.columns)
    assert "persist" in set(dic["coluna"])


# Teste: write_outputs genérico usa o `name` no nome dos arquivos.
def test_generic_write_outputs_names_files_by_indicator(synthetic_prices, tmp_path):
    """
    Por quê: o run_all grava um par por indicador; o nome do arquivo tem de derivar
    do `name` passado (não fixo em "mma").

    Lógica: Entrada (summary) → Fase 1 write_outputs(name='mma') → Fase 2 nomes/abas → Saída.
    """
    # Entrada: gera as saídas.
    analysis, summary = build_summary(
        synthetic_prices, mma, {"window": [5], "tol": [0.0]}, [10], min_events=1
    )
    # Fase 1: escreve em tmp com o nome do indicador.
    apath, spath = write_outputs(analysis, summary, "mma", outdir=tmp_path)
    # Fase 2: nomes derivados do `name`.
    assert apath.name == "analysis_mma.xlsx" and spath.name == "summary_mma.xlsx"
    # Saída: o summary.xlsx tem as duas abas.
    sheets = pd.ExcelFile(spath).sheet_names
    assert "summary" in sheets and "dicionário" in sheets
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: robusta.runner`.

- [ ] **Step 3: Criar `src/robusta/runner.py`**

```python
# src/robusta/runner.py
# Path para criar a pasta output e escrever os .xlsx.
from pathlib import Path
# pandas para o tipo do df e o ExcelWriter.
import pandas as pd
# add_labels cria o alvo deslocado (genérico, independente de indicador).
from robusta.target import add_labels
# run_sweep é o motor agnóstico (recebe o módulo do indicador por injeção).
from robusta.sweep import run_sweep


# Legenda por coluna: grupo + significado + como ler. Cobre métricas fixas E params de todos os indicadores.
_COLUMN_DESC = {
    # --- identificação comum ---
    "indicator": ("identificação", "Indicador técnico testado", "mma, mme, obv, vwap, rsi, macd, donchian, bollinger, alto_volume, exaustao_atr."),
    "horizon": ("identificação", "Dias à frente que o alvo olha", "Ex.: 20, 45, 90."),
    "family": ("identificação", "Pergunta que o modelo responde", "logit = 'subiu? (0/1)'; ols = 'quanto rendeu? (% contínuo)'."),
    # --- params por indicador (aparecem conforme o grid) ---
    "window": ("identificação", "Janela do indicador, em dias", "Ex.: 10, 20, 50, 200."),
    "tol": ("identificação", "Tolerância do rompimento (fração acima do valor)", "0 = toca; 0.015 = 1,5%; 0.03 = 3%."),
    "persist": ("identificação", "Persistência do estado (dias mantendo o estado após o onset)", "0 = onset puro; k = onset + k dias no estado, carimbado 1x no dia da confirmação (sem vazamento)."),
    "confirm": ("identificação", "Confirmação de PREÇO após o evento (só alto_volume/exaustao_atr)", "0 = evento puro; k = Close segurou ≥ Close do dia do evento por k dias; 1 no k-ésimo dia (sem vazamento)."),
    "mult": ("identificação", "Multiplicador do limiar (volume/ATR sobre a média)", "1.5 = 1,5× a média; 2.0 = 2×."),
    "atr_period": ("identificação", "Janela do ATR, em dias", "Ex.: 14."),
    "low": ("identificação", "Piso do RSI para sair do sobrevendido", "Ex.: 30 (onset = cruzar 30 p/ cima)."),
    "fast": ("identificação", "EMA rápida do MACD", "Ex.: 12."),
    "slow": ("identificação", "EMA lenta do MACD", "Ex.: 26."),
    "sig": ("identificação", "EMA da linha de sinal do MACD", "Ex.: 9."),
    "N": ("identificação", "Janela do canal de Donchian (máxima de N dias)", "Ex.: 20, 55."),
    "n_std": ("identificação", "Nº de desvios-padrão da banda de Bollinger", "Ex.: 2.0."),
    # --- amostra ---
    "n": ("amostra", "Nº de dias usados no ajuste (após remover NA das pontas)", "Cai com horizon e window."),
    "n_eventos": ("amostra", "Nº de dias com onset (dummy = 1)", "Poucos eventos = estimativa frágil; leia junto com r2/coef."),
    # --- métricas ---
    "r2": ("métrica", "Poder explicativo: pseudo-R² McFadden (logit) ou R² clássico (ols)", "0 = não explica; maior = melhor. Compare só dentro da mesma family. NÃO serve para cross-ranking."),
    "coef": ("métrica", "Efeito do onset sobre o alvo", "logit: log-odds (exp = razão de chances); ols: variação no retorno. Sinal indica direção."),
    "p_value": ("métrica", "Significância estatística do coef", "<0.05 = 'significativo'; com n alto quase tudo fica significativo (exploratório)."),
    "llf": ("métrica", "Log-likelihood (qualidade do ajuste)", "Diagnóstico; maior = melhor. Só compare dentro da mesma family."),
    "accuracy": ("métrica", "Só logit: % de acerto subir/não, in-sample", "~0.53 = pouco acima do acaso; NaN no ols."),
    "status": ("métrica", "Resultado do ajuste", "ok / sem_eventos / separacao / erro."),
    # --- associação 2×2 (só logit) ---
    "odds_ratio": ("associação 2×2", "Razão de chances de subir no onset vs dia normal", "Só logit. >1 = favorece alta; ≈ exp(coef). NaN no ols."),
    "lift": ("associação 2×2", "Quantas vezes mais provável subir após o onset vs a taxa-base", "Só logit. 1 = igual à base; 1,3 = 30% mais provável. Chave de ranking do logit. NaN no ols."),
    "fisher_p": ("associação 2×2", "p-valor do teste exato de Fisher na tabela 2×2", "Só logit. <0,05 = associação significativa; à prova de falha. NaN no ols."),
}


# Constrói a legenda (dicionário) a partir das colunas REAIS do summary.
def summary_dictionary(summary) -> pd.DataFrame:
    """
    Por quê: o summary é denso e seus params variam por indicador (mma tem
    window/tol/persist; donchian tem N; etc.). A legenda precisa ter exatamente
    uma linha por coluna presente — construída a partir do próprio summary para
    nunca divergir do schema.

    Lógica (Entrada → Saída):
      Entrada: DataFrame de summary (qualquer indicador).
      Fase 1: para cada coluna do summary, busca (grupo, significado, como_ler).
      Fase 2: colunas desconhecidas caem num texto genérico (à prova de falha).
      Saída: DataFrame [coluna, grupo, significado, como_ler], 1 linha por coluna.
    """
    # Acumulador das linhas da legenda.
    linhas = []
    # Fase 1: percorre as colunas na ordem em que aparecem no summary.
    for col in summary.columns:
        # Fase 1/2: descrição conhecida ou fallback genérico para param novo.
        grupo, significado, como_ler = _COLUMN_DESC.get(
            col, ("identificação", f"Parâmetro '{col}' do indicador", "Ver a definição do indicador no design.")
        )
        # Fase 1: uma linha por coluna.
        linhas.append({"coluna": col, "grupo": grupo, "significado": significado, "como_ler": como_ler})
    # Saída: DataFrame com a ordem de colunas fixada.
    return pd.DataFrame(linhas, columns=["coluna", "grupo", "significado", "como_ler"])


# Orquestração pura: de um df de preços + um módulo-indicador às duas saídas (sem rede).
def build_summary(prices, indicator, param_grid, horizons, min_events: int = 5):
    """
    Por quê: versão genérica (extraída de run_mma) — roda QUALQUER indicador via
    injeção do módulo + grid, separando orquestração (testável) do I/O.

    Lógica (Entrada → Saída):
      Entrada: df OHLCV, o módulo do indicador, o grid {param: [valores]}, horizontes, mín. eventos.
      Fase 1: cria os rótulos ret_{h}d/y_{h}d no df-fundação.
      Fase 2/Saída: roda o sweep injetando o módulo (acumula colunas + resume).
    """
    # Fase 1: anexa as colunas-alvo para todos os horizontes.
    labeled = add_labels(prices, horizons=horizons)
    # Fase 2/Saída: sweep agnóstico com o módulo e o grid recebidos.
    return run_sweep(labeled, indicator, param_grid, horizons, min_events=min_events)


# Escreve as duas saídas de UM indicador em disco (.xlsx), nomeadas pelo `name`.
def write_outputs(analysis, summary, name, outdir="output"):
    """
    Por quê: isolar a escrita em disco e parametrizar o nome pelo indicador, para o
    run_all gravar um par por indicador reusando o mesmo código.

    Lógica (Entrada → Saída):
      Entrada: df-fundação enriquecido, summary, nome do indicador e a pasta.
      Fase 1: garante a pasta de saída.
      Fase 2: grava analysis_{name}.xlsx (índice de datas preservado).
      Fase 3: grava summary_{name}.xlsx em 2 abas (summary + dicionário).
      Saída: (caminho_analysis, caminho_summary).
    """
    # Fase 1: normaliza o destino e cria a pasta (inclusive pais) se faltar.
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    # Fase 2: caminho e escrita do df-fundação por dia.
    analysis_path = out / f"analysis_{name}.xlsx"
    analysis.to_excel(analysis_path)
    # Fase 3: caminho do summary; writer para gravar duas abas no mesmo arquivo.
    summary_path = out / f"summary_{name}.xlsx"
    with pd.ExcelWriter(summary_path, engine="openpyxl") as writer:
        # Fase 3: 1ª aba 'summary' com os modelos.
        summary.to_excel(writer, sheet_name="summary", index=False)
        # Fase 3: 2ª aba 'dicionário' com a legenda derivada das colunas reais.
        summary_dictionary(summary).to_excel(writer, sheet_name="dicionário", index=False)
    # Saída: os dois caminhos escritos.
    return analysis_path, summary_path
```

- [ ] **Step 4: Rodar o teste do runner e ver PASSAR**

Run: `uv run pytest tests/test_runner.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Afinar `run_mma.py` para delegar ao runner**

Em `src/robusta/run_mma.py`: remover a `summary_dictionary` local (migrou) e trocar as implementações de `build_summary`/`write_outputs` por wrappers. Importar o runner e manter `mma`/`config`/`load_prices`.

Topo do arquivo — imports (substituir o bloco de imports atual por):

```python
# Path só é usado indiretamente via runner; mantemos pandas para o tipo.
import pandas as pd
# As peças do pipeline específicas do mma.
from robusta.data import load_prices
from robusta.indicators import mma
# Runner genérico: orquestração + escrita + legenda (compartilhados).
from robusta import runner
# Parâmetros ajustáveis centralizados.
from robusta import config
```

Substituir a função `build_summary` inteira por (wrapper fino que preserva a assinatura antiga):

```python
# Wrapper fino: mantém a assinatura histórica do mma e delega ao runner genérico.
def build_summary(prices: pd.DataFrame, *, windows, tols, horizons, persists=(0,), min_events: int = 5):
    """
    Por quê: preservar a interface pública do mma (usada por testes e pela main),
    montando o grid {window,tol,persist} e delegando ao runner genérico.

    Lógica (Entrada → Saída):
      Entrada: df OHLCV + listas de janelas, tolerâncias, horizontes, persistências.
      Fase 1: monta o grid do mma (persist é só mais uma dimensão).
      Fase 2/Saída: delega a build_summary genérico injetando o módulo mma.
    """
    # Fase 1: grid de parâmetros do mma.
    grid = {"window": windows, "tol": tols, "persist": list(persists)}
    # Fase 2/Saída: runner genérico com o módulo mma.
    return runner.build_summary(prices, mma, grid, horizons, min_events=min_events)
```

Remover a função `summary_dictionary` local por completo (migrou para o runner).

Substituir a função `write_outputs` inteira por (wrapper que fixa o nome "mma"):

```python
# Wrapper fino: escreve as saídas do mma delegando ao runner (nome fixo "mma").
def write_outputs(analysis, summary, outdir="output"):
    """
    Por quê: manter a assinatura histórica (sem `name`) que os testes do mma usam,
    fixando o nome do indicador em "mma" e delegando a escrita ao runner.

    Lógica: Entrada (analysis, summary, pasta) → Saída (caminhos), via runner.
    """
    # Saída: delega ao runner com o nome do indicador fixo.
    return runner.write_outputs(analysis, summary, "mma", outdir)
```

A `main` continua igual (já chama `build_summary`/`write_outputs` locais, agora wrappers).

- [ ] **Step 6: Rodar a suíte inteira**

Run: `uv run pytest -v`
Expected: PASS — 41 testes (38 + 3 do runner). `test_run_mma.py` e `test_config.py` seguem verdes (assinaturas preservadas).

- [ ] **Step 7: Commit**

```bash
git add src/robusta/runner.py tests/test_runner.py src/robusta/run_mma.py
git commit -m "refactor: extract generic runner.py; run_mma delegates to it"
```

---

## Task 3: `config.INDICATORS` + `config.PARAM_GRIDS`

**Files:**
- Modify: `src/robusta/config.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Produces: `config.INDICATORS: list[str]` (roster) e `config.PARAM_GRIDS: dict[str, dict[str, list]]` (grid por indicador). Chaves de `PARAM_GRIDS` == itens de `INDICATORS`.

- [ ] **Step 1: Escrever o teste do novo contrato do config**

Adicionar em `tests/test_config.py`:

```python
# Teste: o roster e os grids do multi-indicador estão bem formados e casados.
def test_indicators_and_param_grids_wellformed():
    """
    Por quê: o run_all itera INDICATORS e busca PARAM_GRIDS[nome]; se o roster e os
    grids desalinharem, o run_all quebra com KeyError. Este teste trava o contrato.

    Lógica: Entrada (config) → Fase 1 roster → Fase 2 grids → Fase 3 casamento → Saída.
    """
    # Fase 1: INDICATORS é lista não-vazia de strings, com o mma incluído.
    assert isinstance(config.INDICATORS, list) and config.INDICATORS
    assert all(isinstance(n, str) and n for n in config.INDICATORS)
    assert "mma" in config.INDICATORS
    # Fase 2: PARAM_GRIDS é dict; cada grid é dict de listas não-vazias.
    assert isinstance(config.PARAM_GRIDS, dict)
    for nome, grid in config.PARAM_GRIDS.items():
        assert isinstance(grid, dict) and grid
        for valores in grid.values():
            assert isinstance(valores, list) and len(valores) >= 1
    # Fase 3: todo indicador do roster tem um grid, e vice-versa.
    assert set(config.INDICATORS) == set(config.PARAM_GRIDS)
    # Fase 4: persist existe em TODO grid; regimes varrem PERSISTENCES, eventos ficam em [0].
    for grid in config.PARAM_GRIDS.values():
        assert "persist" in grid
    assert config.PERSISTENCES == [0, 1, 2, 3, 4]
    assert config.PARAM_GRIDS["mma"]["persist"] == config.PERSISTENCES
    # Fase 4: os dois indicadores de evento pontual não varrem persistência...
    assert config.PARAM_GRIDS["alto_volume"]["persist"] == [0]
    assert config.PARAM_GRIDS["exaustao_atr"]["persist"] == [0]
    # Fase 4/Saída: ...mas varrem a confirmação de PREÇO (o preço segurou k dias após o evento?).
    assert config.PARAM_GRIDS["alto_volume"]["confirm"] == [0, 1, 2, 3, 4]
    assert config.PARAM_GRIDS["exaustao_atr"]["confirm"] == [0, 1, 2, 3, 4]
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_config.py::test_indicators_and_param_grids_wellformed -v`
Expected: FAIL — `AttributeError: module 'robusta.config' has no attribute 'INDICATORS'`.

- [ ] **Step 3: Adicionar o roster e os grids ao `config.py`**

Duas mudanças em `src/robusta/config.py`:

**(a)** Atualizar a linha existente `PERSISTENCES = [0, 3, 4]` (herdada da Fase 2) para o novo
grid compartilhado, com o comentário ajustado:

```python
# Persistências do onset (dias mantendo o ESTADO após o onset): 0 = onset puro;
# k = onset + k dias no estado. Carimbadas no dia da confirmação (one-shot).
# Varrida pelos 8 indicadores de REGIME (via PARAM_GRIDS); run_mma standalone também usa.
PERSISTENCES = [0, 1, 2, 3, 4]
```

**(b)** Acrescentar ao fim do arquivo (antes da docstring `'''...'''` final de "Rodar o pipeline"):

```python
# === Roster multi-indicador (run_all) ===
# Nomes dos módulos em src/robusta/indicators/ a rodar no run_all.
INDICATORS = ["mma", "mme", "obv", "vwap", "alto_volume",
              "exaustao_atr", "rsi", "macd", "donchian", "bollinger"]

# Grid de parâmetros por indicador (painel único; ajuste manual).
# Regras: indicadores de REGIME varrem PERSISTENCES; os de EVENTO pontual
# (alto_volume, exaustao_atr) ficam em persist=[0] — 2+ dias consecutivos do
# estado deles é raríssimo; o módulo suporta, ativar aqui é trocar a lista.
PARAM_GRIDS = {
    "mma":          {"window": [10, 26, 50, 200], "tol": [0.0, 0.015, 0.03], "persist": PERSISTENCES},
    "mme":          {"window": [10, 26, 50, 200], "tol": [0.0, 0.015, 0.03], "persist": PERSISTENCES},
    "obv":          {"window": [20, 50], "persist": PERSISTENCES},
    "vwap":         {"window": [20, 50], "tol": [0.0, 0.015], "persist": PERSISTENCES},
    "alto_volume":  {"window": [20], "mult": [1.5, 2.0], "tol": [0.0, 0.005], "persist": [0], "confirm": [0, 1, 2, 3, 4]},
    "exaustao_atr": {"atr_period": [14], "mult": [1.5, 2.0], "tol": [0.0, 0.005], "persist": [0], "confirm": [0, 1, 2, 3, 4]},
    "rsi":          {"window": [14], "low": [30], "persist": PERSISTENCES},
    "macd":         {"fast": [12], "slow": [26], "sig": [9], "persist": PERSISTENCES},
    "donchian":     {"N": [20, 55], "persist": PERSISTENCES},
    "bollinger":    {"window": [20], "n_std": [2.0], "persist": PERSISTENCES},
}
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (3 testes: os 2 antigos + o novo).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/config.py tests/test_config.py
git commit -m "feat(config): add INDICATORS roster and PARAM_GRIDS panel"
```

---

## Task 4: Fixture `synthetic_prices_volume` (volume determinístico e variável)

**Files:**
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: fixture pytest `synthetic_prices_volume` → DataFrame OHLCV (300 dias úteis) com `Volume` variável e positivo, para obv/vwap/alto_volume/exaustao_atr.

- [ ] **Step 1: Escrever um teste-sentinela da fixture**

Adicionar ao fim de `tests/conftest.py` **não** é onde vai o teste; crie `tests/test_fixtures.py`:

```python
# tests/test_fixtures.py
# Teste: a fixture de volume tem Volume variável e positivo (obv/vwap dependem disso).
def test_synthetic_prices_volume_has_variable_positive_volume(synthetic_prices_volume):
    """
    Por quê: obv/vwap/alto_volume/exaustao_atr precisam de Volume que varia; a
    fixture antiga tinha Volume constante (não geraria sinal útil).

    Lógica: Entrada (fixture) → Fase 1 schema OHLCV → Fase 2 volume varia e é > 0 → Saída.
    """
    # Fase 1: schema OHLCV presente.
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        assert col in synthetic_prices_volume.columns
    # Fase 2: Volume varia (>1 valor distinto) e é estritamente positivo.
    vol = synthetic_prices_volume["Volume"]
    assert vol.nunique() > 1
    assert (vol > 0).all()
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_fixtures.py -v`
Expected: FAIL — `fixture 'synthetic_prices_volume' not found`.

- [ ] **Step 3: Adicionar a fixture ao `conftest.py`**

Acrescentar ao fim de `tests/conftest.py`:

```python
# Fixture com Volume determinístico e VARIÁVEL, para indicadores de volume/range.
@pytest.fixture
def synthetic_prices_volume():
    """
    Por quê: obv, vwap, alto_volume e exaustao_atr dependem de um Volume que muda
    dia a dia; a `synthetic_prices` tem Volume constante e não geraria sinal útil.

    Lógica (Entrada → Saída):
      Entrada: nenhum argumento.
      Fase 1: índice de 300 dias úteis a partir de uma data fixa.
      Fase 2: Close com tendência + ondas (gera cruzamentos), como na outra fixture.
      Fase 3: Volume determinístico, variável e sempre positivo.
      Fase 4: deriva OHLCV do Close + o Volume da Fase 3.
      Saída: DataFrame OHLCV indexado por data.
    """
    # Fase 1: 300 dias úteis a partir de uma data fixa.
    idx = pd.bdate_range("2020-01-01", periods=300)
    # Fase 2: vetor de posições 0..299.
    t = np.arange(len(idx))
    # Fase 2: Close = nível base + tendência leve + duas ondas (cruzamentos).
    close = 100 + 0.05 * t + 8 * np.sin(t / 13) + 3 * np.sin(t / 3.0)
    # Fase 3: Volume base + onda + rampa (sempre > 0; varia dia a dia).
    volume = (1_000_000 + 400_000 * np.sin(t / 7.0) + 2_000 * t).astype(int)
    # Fase 4: monta o OHLCV derivando High/Low/Open do Close e usando o Volume acima.
    df = pd.DataFrame(
        {
            # Open ≈ Close do dia anterior (primeiro = próprio Close).
            "Open": np.r_[close[0], close[:-1]],
            # High = Close + 0.5.
            "High": close + 0.5,
            # Low = Close - 0.5.
            "Low": close - 0.5,
            # Close é a série gerada.
            "Close": close,
            # Volume variável da Fase 3.
            "Volume": volume,
        },
        # Índice de datas da Fase 1.
        index=idx,
    )
    # Saída: DataFrame pronto para os testes de volume/range.
    return df
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_fixtures.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_fixtures.py
git commit -m "test: add synthetic_prices_volume fixture for volume/range indicators"
```

---

## Padrão comum das Tasks 5–13 (indicadores)

Cada módulo `src/robusta/indicators/<nome>.py` expõe `NAME`, `value_col(...)`, `signal_col(..., persist=0)`, `add_columns(df, ..., persist=0)` — que **acumula** `value → *_state → *_signal` (+ `*_persist{k}` se persist>0) no df-fundação. O bloco de persist é o do `mma`, trocando `above` pelo `state` do módulo. Cada teste cobre 5 verificações:
1. **cria colunas** (valor/estado/sinal presentes; sinal 0/1; dtype Int8; `NAME` certo);
2. **onset = transição** (invariante: `sum(signal) == nº de transições 0→1 do state`);
3. **comportamento específico** do indicador;
4. **robustez** (janela/série curta → 0 eventos, sem quebrar);
5. **persist** (one-shot k dias após o onset, com o estado ligado no intervalo).

Os 2 módulos de evento (`alto_volume`, `exaustao_atr`) ganham duas verificações extras:
6. **tol legado** — o `tol` **suaviza** o limiar (`≥ mult·ref·(1−tol)`); teste de fronteira que passa só com tol=0.005;
7. **confirm de preço** — evento + `Close[t+1..t+k] ≥ Close[t]` → 1 one-shot no dia t+k; se o preço devolve, não confirma.

Cada task: escrever teste → rodar (falha) → implementar módulo → rodar (passa) → commit.

---

## Task 5: Indicador `mme` (média móvel exponencial)

**Files:**
- Create: `src/robusta/indicators/mme.py`
- Create: `tests/test_mme.py`

**Interfaces:**
- Produces: `mme.NAME="mme"`; `mme.value_col(window)->"mme_w{window}"`; `mme.signal_col(window, tol=0.0, persist=0)` → `"mme_w{window}_t{tol}_signal"` (persist=0) / `"mme_w{window}_t{tol}_persist{k}"` (k>0); `mme.add_columns(df, window, tol=0.0, persist=0)->df` (colunas: valor, `*_state`, `*_signal`, +`*_persist{k}` se persist>0).

- [ ] **Step 1: Escrever `tests/test_mme.py`**

```python
# pandas para construir Closes com cruzamento conhecido.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import mme


# Teste: add_columns cria valor, estado e onset (evento 0/1).
def test_mme_creates_value_state_signal():
    """
    Por quê: o mme é plug-in; precisa acrescentar valor (EMA), estado (acima da
    banda) e a dummy de onset, com nomes canônicos que o sweep acha.

    Lógica: Entrada (Close em V) → Fase 1 add_columns → Fase 2 colunas → Fase 3 evento → Saída.
    """
    # Entrada: cai e volta a subir, cruzando a EMA curta.
    df = pd.DataFrame({"Close": [10, 9, 8, 7, 9, 11, 13, 14, 15, 16]})
    # Fase 1: EMA janela 3, sem tolerância.
    out = mme.add_columns(df.copy(), window=3, tol=0.0)
    # Fase 2: valor e sinal presentes.
    assert mme.value_col(3) in out.columns
    scol = mme.signal_col(3, 0.0)
    assert scol in out.columns
    # Fase 3: dummy é evento 0/1 e acende ao menos uma vez; dtype Int8; NAME certo.
    assert set(out[scol].dropna().unique()) <= {0, 1} and out[scol].sum() >= 1
    assert str(out[scol].dtype) == "Int8" and mme.NAME == "mme"


# Teste: onset é a transição 0→1 do estado (não o estado inteiro).
def test_mme_signal_equals_state_transitions():
    """
    Por quê: onset deve acender só no 1º dia da sequência bullish.

    Lógica: Entrada (sobe e fica acima) → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Entrada: cruza e permanece acima.
    df = pd.DataFrame({"Close": [10, 9, 8, 9, 12, 14, 16, 18, 20]})
    # Fase 1: EMA janela 3.
    out = mme.add_columns(df.copy(), window=3, tol=0.0)
    # Fase 2: sum(signal) == nº de transições 0→1 do estado.
    state = out[f"mme_w3_t0.0_state"]
    sig = out[mme.signal_col(3, 0.0)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: tolerância suprime cruzamentos marginais.
def test_mme_tolerance_suppresses_marginal():
    """
    Por quê: com tol alto, um cruzamento fraco não acende a dummy.

    Lógica: Entrada (cruzamento marginal) → Fase 1 dois tol → Fase 2 compara → Saída.
    """
    # Entrada: Close que sobe por margem pequena.
    df = pd.DataFrame({"Close": [10, 10, 10, 10, 10.05, 10.06, 10.07, 10.08]})
    # Fase 1: conta eventos sem tolerância e com 3%.
    strict = mme.add_columns(df.copy(), window=3, tol=0.0)[mme.signal_col(3, 0.0)].sum()
    loose = mme.add_columns(df.copy(), window=3, tol=0.03)[mme.signal_col(3, 0.03)].sum()
    # Fase 2/Saída: a tolerância reduz (ou iguala).
    assert loose <= strict


# Teste: janela > série → EMA indefinida → zero eventos.
def test_mme_window_larger_than_series_zero_events():
    """
    Por quê: o grid usa window=200; num df curto a EMA é NaN (min_periods) e a dummy
    não pode acender nem quebrar.

    Lógica: Entrada (4 closes, window=200) → Fase 1 add_columns → Fase 2 zero eventos → Saída.
    """
    # Entrada: série curta, janela enorme.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 13.0]})
    # Fase 1: EMA janela 200 sobre 4 linhas.
    out = mme.add_columns(df.copy(), window=200, tol=0.0)
    # Fase 2/Saída: nenhum evento.
    assert int(out[mme.signal_col(200, 0.0)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_mme_persist_fires_once_at_confirmation():
    """
    Por quê: persist generaliza o padrão do mma — onset confirmado por k dias
    mantendo o estado; carimbado one-shot no dia da confirmação, sem vazamento.

    Lógica: Entrada (cruza a EMA e fica acima) → Fase 1 add_columns(persist=2) →
    Fase 2 cada confirmação está 2 dias após um onset, com estado ligado no meio → Saída.
    """
    # Entrada: cai e depois sobe firme, cruzando a EMA3 e permanecendo acima.
    df = pd.DataFrame({"Close": [10, 9, 8, 7, 9, 11, 13, 15, 17, 19, 21]})
    # Fase 1: persist=2 (onset + 2 dias mantendo o estado).
    out = mme.add_columns(df.copy(), window=3, tol=0.0, persist=2)
    # Fase 2: colunas de onset, estado e persistência.
    onset = out[mme.signal_col(3, 0.0)]
    state = out["mme_w3_t0.0_state"]
    p = out[mme.signal_col(3, 0.0, persist=2)]
    # Fase 2: existe ao menos uma confirmação e o dtype é Int8.
    idxs = [i for i in range(len(out)) if int(p.iloc[i]) == 1]
    assert len(idxs) >= 1 and str(p.dtype) == "Int8"
    # Fase 2/Saída: cada confirmação está 2 dias após um onset, com o estado ligado no intervalo.
    for i in idxs:
        assert int(onset.iloc[i - 2]) == 1
        assert all(int(state.iloc[j]) == 1 for j in range(i - 2, i + 1))
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_mme.py -v`
Expected: FAIL — `ModuleNotFoundError: robusta.indicators.mme`.

- [ ] **Step 3: Criar `src/robusta/indicators/mme.py`**

```python
# pandas para ewm/shift e o tipo Int8.
import pandas as pd

# Nome do indicador, exposto para o summary e o runner.
NAME = "mme"


# Nome canônico da coluna de valor da EMA.
def value_col(window: int) -> str:
    """
    Por quê: centralizar a convenção de nome, para sweep e testes não duplicarem strings.

    Lógica: Entrada (janela) → Saída (nome `mme_w{window}`).
    """
    # Saída: nome do valor da EMA para a janela.
    return f"mme_w{window}"


# Nome canônico da coluna-dummy (onset puro ou persistência de k dias).
def signal_col(window: int, tol: float = 0.0, persist: int = 0) -> str:
    """
    Por quê: o sweep descobre o nome da dummy só pelos parâmetros do grid; um mesmo
    (janela, tol) pode gerar o onset puro (persist=0) OU a persistência de k dias.

    Lógica: Entrada (janela, tolerância, persist) → Saída:
      persist=0 → `mme_w{window}_t{tol}_signal`; persist=k → `mme_w{window}_t{tol}_persist{k}`.
    """
    # persist>0: nome dedicado da dummy de persistência de k dias.
    if persist:
        # Saída: nome da persistência para (janela, tolerância, k).
        return f"mme_w{window}_t{tol}_persist{persist}"
    # Saída: nome do onset para (janela, tolerância).
    return f"mme_w{window}_t{tol}_signal"


# Acrescenta EMA, estado, onset e (opcional) persistência ao df-fundação.
def add_columns(df: pd.DataFrame, window: int, tol: float = 0.0, persist: int = 0) -> pd.DataFrame:
    """
    Por quê: este é o PLUG-IN. Espelha o mma trocando SMA por EMA; ACRESCENTA colunas
    ao df-fundação (nunca série solta), revisável linha a linha.

    Lógica (Entrada → Saída):
      Entrada: df com Close, janela, tolerância e persistência (0 = desligada).
      Fase 1: EMA (min_periods=window → NaN até ter janela cheia) em mme_w{window}.
      Fase 2: estado bullish (Close > EMA·(1+tol)) em *_state.
      Fase 3: onset = transição 0→1 do estado em *_signal.
      Fase 4: se persist>0, dummy de persistência (onset + k dias no estado) em *_persist{k}.
      Saída: df-fundação com as colunas anexadas (3 fixas; +1 se persist>0).
    """
    # Fase 1: nome e cálculo da EMA (adjust=False = EMA padrão; min_periods evita valor precoce).
    vcol = value_col(window)
    df[vcol] = df["Close"].ewm(span=window, adjust=False, min_periods=window).mean()
    # Fase 2: estado booleano "Close acima da banda".
    state = df["Close"] > df[vcol] * (1 + tol)
    # Fase 2: grava o estado como Int8.
    df[f"mme_w{window}_t{tol}_state"] = state.astype("Int8")
    # Fase 3: onset = acima hoje e não-acima ontem.
    onset = state & ~state.shift(1, fill_value=False)
    # Fase 3: grava o onset como Int8.
    df[signal_col(window, tol)] = onset.astype("Int8")
    # Fase 4: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 4: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 4: acende só quando state=1 e a sequência tem exatamente k+1 dias (sem vazamento).
        df[signal_col(window, tol, persist)] = (state & (streak == persist + 1)).astype("Int8")
    # Saída: df enriquecido.
    return df
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_mme.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/indicators/mme.py tests/test_mme.py
git commit -m "feat(mme): exponential moving-average onset plug-in"
```

---

## Task 6: Indicador `obv` (On-Balance Volume vs sua média)

**Files:**
- Create: `src/robusta/indicators/obv.py`
- Create: `tests/test_obv.py`

**Interfaces:**
- Produces: `obv.NAME="obv"`; `obv.value_col(window)->"obv_ma{window}"`; `obv.signal_col(window, persist=0)` → `"obv_w{window}_signal"` (persist=0) / `"obv_w{window}_persist{k}"` (k>0); `obv.add_columns(df, window, persist=0)->df` (colunas: `obv`, `obv_ma{window}`, `*_state`, `*_signal`, +`*_persist{k}` se persist>0).

- [ ] **Step 1: Escrever `tests/test_obv.py`**

```python
# pandas para construir Close/Volume determinísticos.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import obv


# Teste: cria OBV, sua média, estado e onset.
def test_obv_creates_columns(synthetic_prices_volume):
    """
    Por quê: o obv acumula volume sinalizado e compara com a própria média; precisa
    acrescentar as colunas canônicas ao df-fundação.

    Lógica: Entrada (preços+volume) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: janela 20 sobre a fixture de volume.
    out = obv.add_columns(synthetic_prices_volume.copy(), window=20)
    # Fase 2: valor e sinal presentes; dummy 0/1; Int8; NAME certo.
    assert obv.value_col(20) in out.columns
    scol = obv.signal_col(20)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and obv.NAME == "obv"


# Teste: onset = transição 0→1 do estado (OBV cruza sua média p/ cima).
def test_obv_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset deve acender só quando OBV passa de abaixo para acima da média.

    Lógica: Entrada (preços+volume) → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1: janela 20.
    out = obv.add_columns(synthetic_prices_volume.copy(), window=20)
    # Fase 2: invariante evento == transições.
    state = out["obv_w20_state"]
    sig = out[obv.signal_col(20)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions) and sig.sum() >= 1


# Teste: OBV sobe em dias de alta e cai em dias de baixa (sinal do fluxo).
def test_obv_direction_follows_close():
    """
    Por quê: OBV soma volume quando Close sobe e subtrai quando cai; provamos essa
    definição num caso pequeno e controlado.

    Lógica: Entrada (2 altas, 1 baixa) → Fase 1 add_columns → Fase 2 OBV monotônico → Saída.
    """
    # Entrada: Close sobe, sobe, cai; volume constante 100.
    df = pd.DataFrame({"Close": [10, 11, 12, 11], "Volume": [100, 100, 100, 100],
                       "Open": [10, 10, 11, 12], "High": [10, 11, 12, 12], "Low": [10, 10, 11, 11]})
    # Fase 1: janela 2.
    out = obv.add_columns(df.copy(), window=2)
    # Fase 2: OBV = [0, +100, +200, +100] (sobe nos dias de alta, cai no de baixa).
    assert out["obv"].tolist() == [0.0, 100.0, 200.0, 100.0]


# Teste: janela > série → média do OBV NaN → zero eventos.
def test_obv_window_larger_than_series_zero_events():
    """
    Por quê: o grid usa window=50; num df curto a média do OBV é NaN e a dummy não acende.

    Lógica: Entrada (3 dias, window=50) → Fase 1 add_columns → Fase 2 zero eventos → Saída.
    """
    # Entrada: série curta, janela grande.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0], "Volume": [100, 100, 100],
                       "Open": [10, 10, 11], "High": [10, 11, 12], "Low": [10, 10, 11]})
    # Fase 1: janela 50 sobre 3 linhas.
    out = obv.add_columns(df.copy(), window=50)
    # Fase 2/Saída: nenhum evento.
    assert int(out[obv.signal_col(50)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_obv_persist_fires_once_at_confirmation():
    """
    Por quê: persist generaliza o padrão do mma para o estado do obv — onset (OBV
    cruza a média p/ cima) confirmado por k dias mantendo-se acima; one-shot.

    Lógica: Entrada (OBV cai e sobe firme) → Fase 1 add_columns(persist=2) → Fase 2
    confirmação 2 dias após o onset, estado ligado no intervalo → Saída.
    """
    # Entrada: Close cai 3 dias e sobe 8 (volume constante → OBV espelha o Close).
    df = pd.DataFrame({"Close": [10, 9, 8, 7, 8, 9, 10, 11, 12, 13, 14, 15],
                       "Volume": [100] * 12})
    # Fase 1: janela 3, persist=2.
    out = obv.add_columns(df.copy(), window=3, persist=2)
    # Fase 2: colunas de onset, estado e persistência.
    onset = out[obv.signal_col(3)]
    state = out["obv_w3_state"]
    p = out[obv.signal_col(3, persist=2)]
    # Fase 2: há ao menos uma confirmação; dtype Int8.
    idxs = [i for i in range(len(out)) if int(p.iloc[i]) == 1]
    assert len(idxs) >= 1 and str(p.dtype) == "Int8"
    # Fase 2/Saída: cada confirmação está 2 dias após um onset, com o estado ligado no meio.
    for i in idxs:
        assert int(onset.iloc[i - 2]) == 1
        assert all(int(state.iloc[j]) == 1 for j in range(i - 2, i + 1))
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_obv.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Criar `src/robusta/indicators/obv.py`**

```python
# numpy para o sinal (+1/-1/0) da variação diária.
import numpy as np
# pandas para cumsum/rolling/shift e Int8.
import pandas as pd

# Nome do indicador.
NAME = "obv"


# Nome canônico da coluna de valor (a MÉDIA do OBV — é ela que forma o estado).
def value_col(window: int) -> str:
    """
    Por quê: centralizar o nome; o estado compara OBV com esta média móvel.

    Lógica: Entrada (janela) → Saída (`obv_ma{window}`).
    """
    # Saída: nome da média do OBV.
    return f"obv_ma{window}"


# Nome canônico da coluna-dummy (onset puro ou persistência de k dias).
def signal_col(window: int, persist: int = 0) -> str:
    """
    Por quê: o sweep descobre o nome da dummy só pelos parâmetros (obv não tem tol);
    uma mesma janela pode gerar o onset puro (persist=0) OU a persistência de k dias.

    Lógica: Entrada (janela, persist) → Saída:
      persist=0 → `obv_w{window}_signal`; persist=k → `obv_w{window}_persist{k}`.
    """
    # persist>0: nome dedicado da dummy de persistência de k dias.
    if persist:
        # Saída: nome da persistência para (janela, k).
        return f"obv_w{window}_persist{persist}"
    # Saída: nome do onset.
    return f"obv_w{window}_signal"


# Acrescenta OBV, sua média, estado, onset e (opcional) persistência ao df-fundação.
def add_columns(df: pd.DataFrame, window: int, persist: int = 0) -> pd.DataFrame:
    """
    Por quê: PLUG-IN de fluxo de volume. OBV = volume sinalizado acumulado; o estado
    bullish é OBV acima da própria média móvel (fluxo comprador dominante).

    Lógica (Entrada → Saída):
      Entrada: df com Close e Volume, a janela da média do OBV e persist (0 = desligada).
      Fase 1: direção diária (+1 alta / -1 baixa / 0 igual) do Close.
      Fase 2: OBV = soma acumulada de direção·Volume (coluna `obv`).
      Fase 3: média móvel do OBV (min_periods=window → NaN até janela cheia).
      Fase 4: estado (OBV > média) em *_state e onset (transição 0→1) em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset + k dias no estado) em *_persist{k}.
      Saída: df-fundação com as colunas anexadas (4 fixas; +1 se persist>0).
    """
    # Fase 1: sinal da variação diária; 1º dia (diff NaN) tratado como 0.
    direction = np.sign(df["Close"].diff()).fillna(0)
    # Fase 2: OBV acumulado (volume somado/subtraído conforme a direção).
    obv_series = (direction * df["Volume"]).cumsum()
    # Fase 2: grava o OBV bruto para revisão.
    df["obv"] = obv_series
    # Fase 3: média móvel do OBV (NaN até ter `window` pontos).
    ma = obv_series.rolling(window, min_periods=window).mean()
    # Fase 3: grava a média do OBV.
    df[value_col(window)] = ma
    # Fase 4: estado bullish = OBV acima da média.
    state = obv_series > ma
    # Fase 4: grava o estado como Int8.
    df[f"obv_w{window}_state"] = state.astype("Int8")
    # Fase 4: onset = transição 0→1 do estado.
    onset = state & ~state.shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(window)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: acende só quando state=1 e a sequência tem exatamente k+1 dias (sem vazamento).
        df[signal_col(window, persist)] = (state & (streak == persist + 1)).astype("Int8")
    # Saída: df enriquecido.
    return df
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_obv.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/indicators/obv.py tests/test_obv.py
git commit -m "feat(obv): on-balance-volume onset plug-in"
```

---

## Task 7: Indicador `vwap` (VWAP rolante)

**Files:**
- Create: `src/robusta/indicators/vwap.py`
- Create: `tests/test_vwap.py`

**Interfaces:**
- Produces: `vwap.NAME="vwap"`; `vwap.value_col(window)->"vwap_w{window}"`; `vwap.signal_col(window, tol=0.0, persist=0)` → `"vwap_w{window}_t{tol}_signal"` (persist=0) / `"vwap_w{window}_t{tol}_persist{k}"` (k>0); `vwap.add_columns(df, window, tol=0.0, persist=0)->df` (colunas: valor, `*_state`, `*_signal`, +`*_persist{k}` se persist>0).

- [ ] **Step 1: Escrever `tests/test_vwap.py`**

```python
# pandas para o caso pequeno de robustez.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import vwap


# Teste: cria VWAP rolante, estado e onset.
def test_vwap_creates_columns(synthetic_prices_volume):
    """
    Por quê: VWAP rolante = Σ(Close·Vol)/Σ(Vol) na janela; o estado é Close acima do VWAP.

    Lógica: Entrada (preços+volume) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: janela 20, sem tolerância.
    out = vwap.add_columns(synthetic_prices_volume.copy(), window=20, tol=0.0)
    # Fase 2: valor e sinal presentes; 0/1; Int8; NAME.
    assert vwap.value_col(20) in out.columns
    scol = vwap.signal_col(20, 0.0)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and vwap.NAME == "vwap"


# Teste: onset = transição 0→1 do estado.
def test_vwap_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset só quando Close cruza o VWAP p/ cima.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1: janela 20.
    out = vwap.add_columns(synthetic_prices_volume.copy(), window=20, tol=0.0)
    # Fase 2: invariante.
    state = out["vwap_w20_t0.0_state"]
    sig = out[vwap.signal_col(20, 0.0)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions) and sig.sum() >= 1


# Teste: tolerância suprime cruzamentos marginais.
def test_vwap_tolerance_suppresses_marginal(synthetic_prices_volume):
    """
    Por quê: com tol maior, cruzamentos fracos do Close sobre o VWAP não contam.

    Lógica: Entrada → Fase 1 dois tol → Fase 2 loose ≤ strict → Saída.
    """
    # Fase 1: eventos sem tolerância e com 1,5%.
    strict = vwap.add_columns(synthetic_prices_volume.copy(), window=20, tol=0.0)[vwap.signal_col(20, 0.0)].sum()
    loose = vwap.add_columns(synthetic_prices_volume.copy(), window=20, tol=0.015)[vwap.signal_col(20, 0.015)].sum()
    # Fase 2/Saída.
    assert loose <= strict


# Teste: janela > série → VWAP NaN → zero eventos.
def test_vwap_window_larger_than_series_zero_events():
    """
    Por quê: janela grande num df curto → Σ rolante NaN → sem evento.

    Lógica: Entrada (3 dias, window=50) → Fase 1 add_columns → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0], "Volume": [100, 200, 300]})
    # Fase 1: janela 50.
    out = vwap.add_columns(df.copy(), window=50, tol=0.0)
    # Fase 2/Saída: zero eventos.
    assert int(out[vwap.signal_col(50, 0.0)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_vwap_persist_fires_once_at_confirmation():
    """
    Por quê: é o caso motivador do persist — fechar acima do vwap E os k dias
    seguintes persistirem acima é sinal diferente de fechar acima e devolver no
    dia seguinte. One-shot na confirmação, sem vazamento.

    Lógica: Entrada (parado, depois sobe firme) → Fase 1 add_columns(persist=2) →
    Fase 2 confirmação 2 dias após o onset, estado ligado no intervalo → Saída.
    """
    # Entrada: 5 dias parado (Close = vwap) e depois sobe firme (fica acima do vwap).
    df = pd.DataFrame({"Close": [10, 10, 10, 10, 10, 11, 12, 13, 14, 15],
                       "Volume": [100] * 10})
    # Fase 1: janela 3, persist=2.
    out = vwap.add_columns(df.copy(), window=3, tol=0.0, persist=2)
    # Fase 2: colunas de onset, estado e persistência.
    onset = out[vwap.signal_col(3, 0.0)]
    state = out["vwap_w3_t0.0_state"]
    p = out[vwap.signal_col(3, 0.0, persist=2)]
    # Fase 2: há ao menos uma confirmação; dtype Int8.
    idxs = [i for i in range(len(out)) if int(p.iloc[i]) == 1]
    assert len(idxs) >= 1 and str(p.dtype) == "Int8"
    # Fase 2/Saída: cada confirmação está 2 dias após um onset, com o estado ligado no meio.
    for i in idxs:
        assert int(onset.iloc[i - 2]) == 1
        assert all(int(state.iloc[j]) == 1 for j in range(i - 2, i + 1))
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_vwap.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Criar `src/robusta/indicators/vwap.py`**

```python
# pandas para rolling/shift e Int8.
import pandas as pd

# Nome do indicador.
NAME = "vwap"


# Nome canônico da coluna de valor (VWAP rolante).
def value_col(window: int) -> str:
    """
    Por quê: centralizar o nome do VWAP rolante.

    Lógica: Entrada (janela) → Saída (`vwap_w{window}`).
    """
    # Saída: nome do VWAP.
    return f"vwap_w{window}"


# Nome canônico da coluna-dummy (onset puro ou persistência de k dias).
def signal_col(window: int, tol: float = 0.0, persist: int = 0) -> str:
    """
    Por quê: o sweep descobre o nome pela (janela, tolerância, persist); um mesmo
    (janela, tol) pode gerar o onset puro (persist=0) OU a persistência de k dias.

    Lógica: Entrada (janela, tol, persist) → Saída:
      persist=0 → `vwap_w{window}_t{tol}_signal`; persist=k → `vwap_w{window}_t{tol}_persist{k}`.
    """
    # persist>0: nome dedicado da dummy de persistência de k dias.
    if persist:
        # Saída: nome da persistência para (janela, tolerância, k).
        return f"vwap_w{window}_t{tol}_persist{persist}"
    # Saída: nome do onset.
    return f"vwap_w{window}_t{tol}_signal"


# Acrescenta VWAP rolante, estado, onset e (opcional) persistência ao df-fundação.
def add_columns(df: pd.DataFrame, window: int, tol: float = 0.0, persist: int = 0) -> pd.DataFrame:
    """
    Por quê: PLUG-IN de preço-ponderado-por-volume. VWAP ROLANTE (janela W), não
    cumulativo (o cumulativo em 10 anos vira quase constante). Estado = Close acima do VWAP.

    Lógica (Entrada → Saída):
      Entrada: df com Close e Volume, janela, tolerância e persist (0 = desligada).
      Fase 1: soma rolante de Close·Volume e de Volume (min_periods=window).
      Fase 2: VWAP = Σ(Close·Vol)/Σ(Vol) na janela.
      Fase 3: estado (Close > VWAP·(1+tol)) em *_state.
      Fase 4: onset (transição 0→1) em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset + k dias no estado) em *_persist{k}.
      Saída: df-fundação com as colunas anexadas (3 fixas; +1 se persist>0).
    """
    # Fase 1: numerador e denominador rolantes (NaN até janela cheia).
    pv = (df["Close"] * df["Volume"]).rolling(window, min_periods=window).sum()
    vol = df["Volume"].rolling(window, min_periods=window).sum()
    # Fase 2: VWAP rolante.
    vwap_series = pv / vol
    # Fase 2: grava o VWAP.
    df[value_col(window)] = vwap_series
    # Fase 3: estado bullish = Close acima da banda do VWAP.
    state = df["Close"] > vwap_series * (1 + tol)
    # Fase 3: grava o estado como Int8.
    df[f"vwap_w{window}_t{tol}_state"] = state.astype("Int8")
    # Fase 4: onset = transição 0→1 do estado.
    onset = state & ~state.shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(window, tol)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: acende só quando state=1 e a sequência tem exatamente k+1 dias (sem vazamento).
        df[signal_col(window, tol, persist)] = (state & (streak == persist + 1)).astype("Int8")
    # Saída: df enriquecido.
    return df
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_vwap.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/indicators/vwap.py tests/test_vwap.py
git commit -m "feat(vwap): rolling VWAP onset plug-in"
```

---

## Task 8: Indicador `alto_volume` (pico de volume em dia de alta)

**Files:**
- Create: `src/robusta/indicators/alto_volume.py`
- Create: `tests/test_alto_volume.py`

**Interfaces:**
- Produces: `alto_volume.NAME="alto_volume"`; `alto_volume.value_col(window)->"volma_w{window}"`; `alto_volume.signal_col(window, mult, tol=0.0, persist=0, confirm=0)` → `"alto_volume_w{window}_m{mult}_t{tol}_signal"` / `..._persist{k}` / `..._confirm{k}` (precedência: confirm > persist > onset); `alto_volume.add_columns(df, window, mult, tol=0.0, persist=0, confirm=0)->df` (colunas: valor, `*_state`, `*_signal`, +`*_persist{k}`/`*_confirm{k}` opcionais). `tol` reproduz o `tolerancia_erro` do legado — SUAVIZA o limiar: `Volume ≥ mult·média·(1−tol)`. `confirm=k` = evento + Close segurando ≥ Close do evento por k dias (one-shot no dia t+k). O grid do config usa `persist=[0]` e `confirm=[0..4]`.

- [ ] **Step 1: Escrever `tests/test_alto_volume.py`**

```python
# pandas para casos pequenos controlados.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import alto_volume as av


# Teste: cria média de volume, estado e onset.
def test_av_creates_columns(synthetic_prices_volume):
    """
    Por quê: estado = volume ≥ mult·média E Close subiu; onset = 1º dia dessa condição.

    Lógica: Entrada (preços+volume) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: janela 20, mult 1,5.
    out = av.add_columns(synthetic_prices_volume.copy(), window=20, mult=1.5)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert av.value_col(20) in out.columns
    scol = av.signal_col(20, 1.5)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and av.NAME == "alto_volume"


# Teste: onset = transição 0→1 do estado.
def test_av_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset acende só no 1º dia de um pico (não em cada dia do pico).

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1: janela 20, mult 1,5.
    out = av.add_columns(synthetic_prices_volume.copy(), window=20, mult=1.5)
    # Fase 2: invariante evento == transições.
    state = out["alto_volume_w20_m1.5_t0.0_state"]
    sig = out[av.signal_col(20, 1.5)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: pico de volume em dia de BAIXA não acende (precisa de Close subindo).
def test_av_high_volume_down_day_does_not_fire():
    """
    Por quê: a definição exige alta E volume; um pico de volume num dia de queda
    (típico de venda) não é sinal bullish.

    Lógica: Entrada (dia de pico com Close caindo) → Fase 1 add_columns → Fase 2 zero → Saída.
    """
    # Entrada: volume baixo e estável, depois um pico gigante num dia de QUEDA do Close.
    df = pd.DataFrame({
        "Close": [10, 10, 10, 10, 9],           # último dia cai
        "Volume": [100, 100, 100, 100, 10_000],  # último dia é pico
    })
    # Fase 1: janela 3, mult 2.
    out = av.add_columns(df.copy(), window=3, mult=2.0)
    # Fase 2/Saída: o pico em dia de queda NÃO acende a dummy.
    assert int(out[av.signal_col(3, 2.0)].iloc[4]) == 0


# Teste: janela > série → média de volume NaN → zero eventos.
def test_av_window_larger_than_series_zero_events():
    """
    Por quê: janela grande num df curto → média NaN → high_vol False → sem evento.

    Lógica: Entrada (3 dias, window=20) → Fase 1 add_columns → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0], "Volume": [100, 200, 9_000]})
    # Fase 1: janela 20.
    out = av.add_columns(df.copy(), window=20, mult=1.5)
    # Fase 2/Saída: zero eventos.
    assert int(out[av.signal_col(20, 1.5)].sum()) == 0


# Teste: persist confirma dias CONSECUTIVOS de pico+alta (one-shot na confirmação).
def test_av_persist_confirms_consecutive_spike_days():
    """
    Por quê: o módulo suporta persist como os demais (mesmo bloco de streak), ainda
    que o grid do config use [0] — o estado de evento raramente dura. Aqui provamos
    a mecânica com um caso construído de 2 dias seguidos de pico em alta.

    Lógica: Entrada (2 picos consecutivos em dias de alta) → Fase 1 add_columns(persist=1)
    → Fase 2 confirmação uma única vez, no 2º dia do estado → Saída.
    """
    # Entrada: Close sobe todo dia; volume salta no idx3 (1000) e idx4 (2000, vence a média que subiu).
    df = pd.DataFrame({"Close": [10, 11, 12, 13, 14],
                       "Volume": [100, 100, 100, 1000, 2000]})
    # Fase 1: janela 3, mult 1,5, persist=1.
    out = av.add_columns(df.copy(), window=3, mult=1.5, persist=1)
    # Fase 2: estado ligado no idx3 (onset) e no idx4 (streak=2) → persist1 confirma no idx4.
    p = out[av.signal_col(3, 1.5, persist=1)]
    # Fase 2/Saída: uma única confirmação, no idx4, dtype Int8.
    assert int(p.sum()) == 1 and int(p.iloc[4]) == 1 and str(p.dtype) == "Int8"


# Teste: o tol do legado SUAVIZA o limiar — pico de fronteira só conta com tol=0.005.
def test_av_tol_softens_threshold():
    """
    Por quê: o legado usa tolerancia_erro=0.005 no limiar (Volume ≥ mult·média·(1−tol));
    aqui o fator vira o param `tol` varrível. Sentido do botão: tol MAIOR → limiar
    MENOR → MAIS eventos (oposto do tol do mma, que aperta a banda).

    Lógica: Entrada (pico de fronteira) → Fase 1 add_columns com tol 0 e 0.005 →
    Fase 2 o evento só conta com a tolerância → Saída.
    """
    # Entrada: Close subindo; volume de fronteira no idx3 (média=199 → limiar exato 398; suave 396.01).
    df = pd.DataFrame({"Close": [10, 11, 12, 13], "Volume": [100, 100, 100, 397]})
    # Fase 1: sem tolerância (limiar exato) e com a tolerância do legado.
    strict = av.add_columns(df.copy(), window=3, mult=2.0, tol=0.0)[av.signal_col(3, 2.0, 0.0)].sum()
    soft = av.add_columns(df.copy(), window=3, mult=2.0, tol=0.005)[av.signal_col(3, 2.0, 0.005)].sum()
    # Fase 2/Saída: 397 < 398 (exato, não conta) e 397 ≥ 396.01 (suave, conta).
    assert int(strict) == 0 and int(soft) == 1


# Teste: confirm_k = evento + preço SEGURANDO o nível por k dias (some se devolver).
def test_av_confirm_price_hold_after_event():
    """
    Por quê: persist não se aplica a evento pontual (picos consecutivos são raros);
    a pergunta certa aqui é outra — depois do pico, o PREÇO segurou? confirm_k =
    evento no dia t e Close[t+1..t+k] ≥ Close[t]; dummy 1 one-shot no dia t+k.

    Lógica: Entrada (pico com preço segurando vs pico que devolve) → Fase 1
    add_columns(confirm=2) → Fase 2 confirma só quando o preço segurou → Saída.
    """
    # Entrada A: pico no idx3 (Close=13) e o preço SEGURA (13 e 14 ≥ 13).
    segura = pd.DataFrame({"Close": [10, 11, 12, 13, 13, 14],
                           "Volume": [100, 100, 100, 1000, 100, 100]})
    # Entrada B: mesmo pico, mas o preço DEVOLVE no dia seguinte (12.5 < 13).
    devolve = pd.DataFrame({"Close": [10, 11, 12, 13, 12.5, 14],
                            "Volume": [100, 100, 100, 1000, 100, 100]})
    # Fase 1: janela 3, mult 1,5, confirm=2 (evento no idx3 nos dois cenários).
    out_a = av.add_columns(segura.copy(), window=3, mult=1.5, confirm=2)
    out_b = av.add_columns(devolve.copy(), window=3, mult=1.5, confirm=2)
    ca = out_a[av.signal_col(3, 1.5, confirm=2)]
    cb = out_b[av.signal_col(3, 1.5, confirm=2)]
    # Fase 2: no cenário que segura, confirma UMA vez, no idx5 (evento idx3 + 2 dias).
    assert int(ca.sum()) == 1 and int(ca.iloc[5]) == 1 and str(ca.dtype) == "Int8"
    # Fase 2/Saída: no cenário que devolve, nenhuma confirmação.
    assert int(cb.sum()) == 0
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_alto_volume.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Criar `src/robusta/indicators/alto_volume.py`**

```python
# pandas para rolling/shift e Int8.
import pandas as pd

# Nome do indicador.
NAME = "alto_volume"


# Nome canônico da coluna de valor (média móvel do volume).
def value_col(window: int) -> str:
    """
    Por quê: centralizar o nome da média de volume que forma o limiar.

    Lógica: Entrada (janela) → Saída (`volma_w{window}`).
    """
    # Saída: nome da média de volume.
    return f"volma_w{window}"


# Nome canônico da coluna-dummy (onset puro, persistência ou confirmação de preço).
def signal_col(window: int, mult: float, tol: float = 0.0, persist: int = 0, confirm: int = 0) -> str:
    """
    Por quê: o sweep descobre o nome pela (janela, múltiplo, tol, persist, confirm);
    um mesmo (janela, mult, tol) pode gerar o onset puro, a persistência do estado
    (persist=k) OU a confirmação de preço (confirm=k). Precedência: confirm > persist.

    Lógica: Entrada (janela, mult, tol, persist, confirm) → Saída:
      confirm=k → `..._confirm{k}`; persist=k → `..._persist{k}`;
      ambos 0 → `alto_volume_w{window}_m{mult}_t{tol}_signal`.
    """
    # confirm>0: nome dedicado da confirmação de preço (precedência sobre persist).
    if confirm:
        # Saída: nome da confirmação para (janela, múltiplo, tol, k).
        return f"alto_volume_w{window}_m{mult}_t{tol}_confirm{confirm}"
    # persist>0: nome dedicado da dummy de persistência de k dias.
    if persist:
        # Saída: nome da persistência para (janela, múltiplo, tol, k).
        return f"alto_volume_w{window}_m{mult}_t{tol}_persist{persist}"
    # Saída: nome do onset.
    return f"alto_volume_w{window}_m{mult}_t{tol}_signal"


# Acrescenta média de volume, estado, onset e (opcionais) persistência/confirmação ao df-fundação.
def add_columns(df: pd.DataFrame, window: int, mult: float, tol: float = 0.0, persist: int = 0, confirm: int = 0) -> pd.DataFrame:
    """
    Por quê: PLUG-IN de pico de volume. Estado bullish = volume anormalmente alto
    (≥ mult·média·(1−tol)) num dia em que o Close subiu (compra com convicção).
    `tol` reproduz o tolerancia_erro do legado (0.005) — suaviza o limiar.
    `confirm` responde: depois do pico, o PREÇO segurou por k dias?

    Lógica (Entrada → Saída):
      Entrada: df com Close e Volume; janela, múltiplo, tol, persist e confirm (0 = desligados).
      Fase 1: média móvel do volume (min_periods=window) em volma_w{window}.
      Fase 2: pico = Volume ≥ mult·média·(1−tol); alta = Close > Close[ontem].
      Fase 3: estado = pico E alta em *_state.
      Fase 4: onset = transição 0→1 em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset + k dias no estado) em *_persist{k}.
      Fase 6: se confirm>0, dummy de confirmação de PREÇO (evento + Close[t+1..t+k] ≥ Close[t],
        one-shot no dia t+k, só passado/presente) em *_confirm{k}.
      Saída: df-fundação com as colunas anexadas (3 fixas; +1 por opcional ativo).
    """
    # Fase 1: média móvel do volume (NaN até janela cheia).
    vol_ma = df["Volume"].rolling(window, min_periods=window).mean()
    # Fase 1: grava a média de volume.
    df[value_col(window)] = vol_ma
    # Fase 2: pico de volume relativo à média, com o limiar suavizado pelo tol do legado.
    high_vol = df["Volume"] >= mult * vol_ma * (1 - tol)
    # Fase 2: dia de alta do Close (shift traz o dia anterior).
    up = df["Close"] > df["Close"].shift(1)
    # Fase 3: estado = pico E alta.
    state = high_vol & up
    # Fase 3: grava o estado como Int8.
    df[f"alto_volume_w{window}_m{mult}_t{tol}_state"] = state.astype("Int8")
    # Fase 4: onset = transição 0→1 do estado.
    onset = state & ~state.shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(window, mult, tol)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: acende só quando state=1 e a sequência tem exatamente k+1 dias (sem vazamento).
        df[signal_col(window, mult, tol, persist)] = (state & (streak == persist + 1)).astype("Int8")
    # Fase 6: confirmação de PREÇO opcional (evento + Close segurando o nível por k dias).
    if confirm:
        # Fase 6: candidato à confirmação = o dia k após um onset.
        held = onset.shift(confirm, fill_value=False)
        # Fase 6: exige o Close de CADA um dos k dias ≥ Close do dia do evento (só passado/presente).
        for j in range(1, confirm + 1):
            # Fase 6: Close do (evento+j) comparado ao Close do dia do evento.
            held = held & (df["Close"].shift(confirm - j) >= df["Close"].shift(confirm))
        # Fase 6: grava a dummy one-shot no dia da confirmação.
        df[signal_col(window, mult, tol, persist, confirm)] = held.astype("Int8")
    # Saída: df enriquecido.
    return df
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_alto_volume.py -v`
Expected: PASS (7 testes).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/indicators/alto_volume.py tests/test_alto_volume.py
git commit -m "feat(alto_volume): volume-spike-on-up-day onset plug-in"
```

---

## Task 9: Indicador `exaustao_atr` (dia de range gigante)

**Files:**
- Create: `src/robusta/indicators/exaustao_atr.py`
- Create: `tests/test_exaustao_atr.py`

**Interfaces:**
- Produces: `exaustao_atr.NAME="exaustao_atr"`; `exaustao_atr.value_col(atr_period)->"atr_p{atr_period}"`; `exaustao_atr.signal_col(atr_period, mult, tol=0.0, persist=0, confirm=0)` → `"exaustao_atr_p{atr_period}_m{mult}_t{tol}_signal"` / `..._persist{k}` / `..._confirm{k}` (precedência: confirm > persist > onset); `exaustao_atr.add_columns(df, atr_period, mult, tol=0.0, persist=0, confirm=0)->df` (colunas: valor, `*_state`, `*_signal`, +`*_persist{k}`/`*_confirm{k}` opcionais). `tol` reproduz o `tolerancia_erro` do legado — SUAVIZA o limiar: `TR ≥ mult·ATR₋₁·(1−tol)`. `confirm=k` = evento + Close segurando ≥ Close do evento por k dias (one-shot no dia t+k). O grid do config usa `persist=[0]` e `confirm=[0..4]`.

**Nota semântica:** provavelmente **contrária** (um dia de range enorme costuma preceder reversão). `lift < 1` aqui é o achado, não bug. Mantido como sinal bullish; os dados decidem.

- [ ] **Step 1: Escrever `tests/test_exaustao_atr.py`**

```python
# pandas para casos pequenos controlados.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import exaustao_atr as ea


# Teste: cria ATR, estado e onset.
def test_ea_creates_columns(synthetic_prices_volume):
    """
    Por quê: estado = TR do dia ≥ mult·ATR(ontem) E Close subiu; onset = 1º dia disso.

    Lógica: Entrada (preços) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: ATR de 14, mult 1,5.
    out = ea.add_columns(synthetic_prices_volume.copy(), atr_period=14, mult=1.5)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert ea.value_col(14) in out.columns
    scol = ea.signal_col(14, 1.5)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and ea.NAME == "exaustao_atr"


# Teste: onset = transição 0→1 do estado.
def test_ea_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset acende só no 1º dia de um range-gigante-de-alta.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1.
    out = ea.add_columns(synthetic_prices_volume.copy(), atr_period=14, mult=1.5)
    # Fase 2: invariante.
    state = out["exaustao_atr_p14_m1.5_t0.0_state"]
    sig = out[ea.signal_col(14, 1.5)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: só acende num dia de range GIGANTE de alta; dias normais não.
def test_ea_fires_only_on_big_up_range():
    """
    Por quê: a definição exige TR do dia bem acima do ATR recente E Close subindo.
    Dias de range normal não podem acender.

    Lógica: Entrada (dias calmos + 1 dia de range enorme em alta) → Fase 1 → Fase 2 → Saída.
    """
    # Entrada: 5 dias calmos (range 1) e um 6º dia com range enorme e Close subindo forte.
    df = pd.DataFrame({
        "High": [10.5, 10.5, 10.5, 10.5, 10.5, 20.0],
        "Low":  [9.5, 9.5, 9.5, 9.5, 9.5, 11.0],
        "Close": [10, 10, 10, 10, 10, 19],
    })
    # Fase 1: ATR de 3, mult 2.
    out = ea.add_columns(df.copy(), atr_period=3, mult=2.0)
    # Fase 2: acende só no dia 5 (o de range gigante em alta), 1 evento no total.
    sig = out[ea.signal_col(3, 2.0)]
    assert int(sig.sum()) == 1 and int(sig.iloc[5]) == 1


# Teste: janela > série → ATR NaN → zero eventos.
def test_ea_window_larger_than_series_zero_events():
    """
    Por quê: atr_period grande num df curto → ATR NaN → estado False → sem evento.

    Lógica: Entrada (3 dias, atr_period=14) → Fase 1 → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"High": [11.0, 12.0, 13.0], "Low": [9.0, 10.0, 11.0], "Close": [10.0, 11.0, 12.0]})
    # Fase 1: ATR de 14.
    out = ea.add_columns(df.copy(), atr_period=14, mult=1.5)
    # Fase 2/Saída: zero eventos.
    assert int(out[ea.signal_col(14, 1.5)].sum()) == 0


# Teste: persist confirma dias CONSECUTIVOS de range gigante em alta (one-shot).
def test_ea_persist_confirms_consecutive_big_days():
    """
    Por quê: o módulo suporta persist como os demais (mesmo bloco de streak), ainda
    que o grid do config use [0] — dois dias seguidos de exaustão é raríssimo. Aqui
    provamos a mecânica com um caso construído.

    Lógica: Entrada (2 dias seguidos de range gigante em alta) → Fase 1
    add_columns(persist=1) → Fase 2 confirmação uma única vez, no 2º dia → Saída.
    """
    # Entrada: 4 dias calmos (range 1) e DOIS dias seguidos de range gigante em alta.
    df = pd.DataFrame({
        "High":  [10.5, 10.5, 10.5, 10.5, 20.0, 30.0],
        "Low":   [9.5, 9.5, 9.5, 9.5, 11.0, 21.0],
        "Close": [10, 10, 10, 10, 19, 29],
    })
    # Fase 1: ATR de 2, mult 2, persist=1.
    out = ea.add_columns(df.copy(), atr_period=2, mult=2.0, persist=1)
    # Fase 2: estado ligado no idx4 (onset: TR=10 ≥ 2·ATR=2) e no idx5 (TR=11 ≥ 2·5.5).
    p = out[ea.signal_col(2, 2.0, persist=1)]
    # Fase 2/Saída: uma única confirmação, no idx5, dtype Int8.
    assert int(p.sum()) == 1 and int(p.iloc[5]) == 1 and str(p.dtype) == "Int8"


# Teste: o tol do legado SUAVIZA o limiar — range de fronteira só conta com tol=0.005.
def test_ea_tol_softens_threshold():
    """
    Por quê: o legado usa tolerancia_erro=0.005 no limiar (TR ≥ mult·ATR₋₁·(1−tol));
    aqui o fator vira o param `tol` varrível. Sentido do botão: tol MAIOR → limiar
    MENOR → MAIS eventos.

    Lógica: Entrada (dia de range de fronteira) → Fase 1 add_columns com tol 0 e
    0.005 → Fase 2 o evento só conta com a tolerância → Saída.
    """
    # Entrada: 4 dias calmos (TR=1 → ATR2=1) e um dia de fronteira em alta:
    # TR = 11.5−9.51 = 1.99 (limiar exato = 2·1 = 2; suave = 2·0.995 = 1.99).
    df = pd.DataFrame({
        "High":  [10.5, 10.5, 10.5, 10.5, 11.5],
        "Low":   [9.5, 9.5, 9.5, 9.5, 9.51],
        "Close": [10, 10, 10, 10, 11],
    })
    # Fase 1: sem tolerância (limiar exato) e com a tolerância do legado.
    strict = ea.add_columns(df.copy(), atr_period=2, mult=2.0, tol=0.0)[ea.signal_col(2, 2.0, 0.0)].sum()
    soft = ea.add_columns(df.copy(), atr_period=2, mult=2.0, tol=0.005)[ea.signal_col(2, 2.0, 0.005)].sum()
    # Fase 2/Saída: 1.99 < 2 (exato, não conta) e 1.99 ≥ 1.99 (suave, conta).
    assert int(strict) == 0 and int(soft) == 1


# Teste: confirm_k = evento + preço SEGURANDO o nível por k dias (some se devolver).
def test_ea_confirm_price_hold_after_event():
    """
    Por quê: persist não se aplica a evento pontual (ranges gigantes consecutivos são
    raros e o ATR sobe); a pergunta certa é — depois da exaustão, o PREÇO segurou?
    confirm_k = evento no dia t e Close[t+1..t+k] ≥ Close[t]; dummy 1 one-shot em t+k.

    Lógica: Entrada (exaustão com preço segurando vs devolvendo) → Fase 1
    add_columns(confirm=2) → Fase 2 confirma só quando o preço segurou → Saída.
    """
    # Entrada A: exaustão no idx4 (Close=19) e o preço SEGURA (19.5 e 20 ≥ 19).
    segura = pd.DataFrame({
        "High":  [10.5, 10.5, 10.5, 10.5, 20.0, 20.0, 20.5],
        "Low":   [9.5, 9.5, 9.5, 9.5, 11.0, 19.0, 19.5],
        "Close": [10, 10, 10, 10, 19, 19.5, 20],
    })
    # Entrada B: mesma exaustão, mas o preço DEVOLVE no dia seguinte (18 < 19).
    devolve = pd.DataFrame({
        "High":  [10.5, 10.5, 10.5, 10.5, 20.0, 19.0, 20.5],
        "Low":   [9.5, 9.5, 9.5, 9.5, 11.0, 17.5, 19.5],
        "Close": [10, 10, 10, 10, 19, 18, 20],
    })
    # Fase 1: ATR de 2, mult 2, confirm=2 (evento só no idx4 nos dois cenários).
    out_a = ea.add_columns(segura.copy(), atr_period=2, mult=2.0, confirm=2)
    out_b = ea.add_columns(devolve.copy(), atr_period=2, mult=2.0, confirm=2)
    ca = out_a[ea.signal_col(2, 2.0, confirm=2)]
    cb = out_b[ea.signal_col(2, 2.0, confirm=2)]
    # Fase 2: no cenário que segura, confirma UMA vez, no idx6 (evento idx4 + 2 dias).
    assert int(ca.sum()) == 1 and int(ca.iloc[6]) == 1 and str(ca.dtype) == "Int8"
    # Fase 2/Saída: no cenário que devolve, nenhuma confirmação.
    assert int(cb.sum()) == 0
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_exaustao_atr.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Criar `src/robusta/indicators/exaustao_atr.py`**

```python
# pandas para concat/rolling/shift e Int8.
import pandas as pd

# Nome do indicador.
NAME = "exaustao_atr"


# Nome canônico da coluna de valor (ATR).
def value_col(atr_period: int) -> str:
    """
    Por quê: centralizar o nome do ATR.

    Lógica: Entrada (período) → Saída (`atr_p{atr_period}`).
    """
    # Saída: nome do ATR.
    return f"atr_p{atr_period}"


# Nome canônico da coluna-dummy (onset puro, persistência ou confirmação de preço).
def signal_col(atr_period: int, mult: float, tol: float = 0.0, persist: int = 0, confirm: int = 0) -> str:
    """
    Por quê: o sweep descobre o nome pela (período do ATR, múltiplo, tol, persist, confirm);
    um mesmo (período, mult, tol) pode gerar o onset puro, a persistência do estado
    (persist=k) OU a confirmação de preço (confirm=k). Precedência: confirm > persist.

    Lógica: Entrada (período, mult, tol, persist, confirm) → Saída:
      confirm=k → `..._confirm{k}`; persist=k → `..._persist{k}`;
      ambos 0 → `exaustao_atr_p{atr_period}_m{mult}_t{tol}_signal`.
    """
    # confirm>0: nome dedicado da confirmação de preço (precedência sobre persist).
    if confirm:
        # Saída: nome da confirmação para (período, múltiplo, tol, k).
        return f"exaustao_atr_p{atr_period}_m{mult}_t{tol}_confirm{confirm}"
    # persist>0: nome dedicado da dummy de persistência de k dias.
    if persist:
        # Saída: nome da persistência para (período, múltiplo, tol, k).
        return f"exaustao_atr_p{atr_period}_m{mult}_t{tol}_persist{persist}"
    # Saída: nome do onset.
    return f"exaustao_atr_p{atr_period}_m{mult}_t{tol}_signal"


# Acrescenta ATR, estado, onset e (opcionais) persistência/confirmação ao df-fundação.
def add_columns(df: pd.DataFrame, atr_period: int, mult: float, tol: float = 0.0, persist: int = 0, confirm: int = 0) -> pd.DataFrame:
    """
    Por quê: PLUG-IN de exaustão. Estado = True Range do dia bem acima do ATR recente
    (≥ mult·ATR de ONTEM·(1−tol), sem vazamento) num dia de alta. Provavelmente sinal
    contrário. `tol` reproduz o tolerancia_erro do legado (0.005) — suaviza o limiar.
    `confirm` responde: depois do dia de exaustão, o PREÇO segurou por k dias?

    Lógica (Entrada → Saída):
      Entrada: df com High, Low, Close; período do ATR, múltiplo, tol, persist e confirm (0 = desligados).
      Fase 1: True Range = max(H−L, |H−C_ontem|, |L−C_ontem|).
      Fase 2: ATR = média móvel do TR (min_periods=atr_period) em atr_p{atr_period}.
      Fase 3: range gigante = TR ≥ mult·ATR.shift(1)·(1−tol); alta = Close > Close[ontem].
      Fase 4: estado = gigante E alta em *_state; onset (transição 0→1) em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset + k dias no estado) em *_persist{k}.
      Fase 6: se confirm>0, dummy de confirmação de PREÇO (evento + Close[t+1..t+k] ≥ Close[t],
        one-shot no dia t+k, só passado/presente) em *_confirm{k}.
      Saída: df-fundação com as colunas anexadas (3 fixas; +1 por opcional ativo).
    """
    # Fase 1: Close do dia anterior (base dos gaps do TR).
    prev_close = df["Close"].shift(1)
    # Fase 1: True Range = maior das três amplitudes.
    tr = pd.concat([
        # Amplitude intradiária.
        df["High"] - df["Low"],
        # Gap de alta contra o fechamento anterior.
        (df["High"] - prev_close).abs(),
        # Gap de baixa contra o fechamento anterior.
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Fase 2: ATR = média móvel do TR (NaN até período cheio).
    atr = tr.rolling(atr_period, min_periods=atr_period).mean()
    # Fase 2: grava o ATR.
    df[value_col(atr_period)] = atr
    # Fase 3: range gigante relativo ao ATR de ONTEM (atr.shift(1) evita vazamento),
    # com o limiar suavizado pelo tol do legado.
    big = tr >= mult * atr.shift(1) * (1 - tol)
    # Fase 3: dia de alta.
    up = df["Close"] > prev_close
    # Fase 4: estado = range gigante E alta.
    state = big & up
    # Fase 4: grava o estado como Int8.
    df[f"exaustao_atr_p{atr_period}_m{mult}_t{tol}_state"] = state.astype("Int8")
    # Fase 4: onset = transição 0→1 do estado.
    onset = state & ~state.shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(atr_period, mult, tol)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: acende só quando state=1 e a sequência tem exatamente k+1 dias (sem vazamento).
        df[signal_col(atr_period, mult, tol, persist)] = (state & (streak == persist + 1)).astype("Int8")
    # Fase 6: confirmação de PREÇO opcional (evento + Close segurando o nível por k dias).
    if confirm:
        # Fase 6: candidato à confirmação = o dia k após um onset.
        held = onset.shift(confirm, fill_value=False)
        # Fase 6: exige o Close de CADA um dos k dias ≥ Close do dia do evento (só passado/presente).
        for j in range(1, confirm + 1):
            # Fase 6: Close do (evento+j) comparado ao Close do dia do evento.
            held = held & (df["Close"].shift(confirm - j) >= df["Close"].shift(confirm))
        # Fase 6: grava a dummy one-shot no dia da confirmação.
        df[signal_col(atr_period, mult, tol, persist, confirm)] = held.astype("Int8")
    # Saída: df enriquecido.
    return df
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_exaustao_atr.py -v`
Expected: PASS (7 testes).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/indicators/exaustao_atr.py tests/test_exaustao_atr.py
git commit -m "feat(exaustao_atr): big-range exhaustion onset plug-in"
```

---

## Task 10: Indicador `rsi` (saída do sobrevendido)

**Files:**
- Create: `src/robusta/indicators/rsi.py`
- Create: `tests/test_rsi.py`

**Interfaces:**
- Produces: `rsi.NAME="rsi"`; `rsi.value_col(window)->"rsi_w{window}"`; `rsi.signal_col(window, low, persist=0)` → `"rsi_w{window}_low{low}_signal"` (persist=0) / `"rsi_w{window}_low{low}_persist{k}"` (k>0); `rsi.add_columns(df, window, low, persist=0)->df` (colunas: valor, `*_state`, `*_signal`, +`*_persist{k}` se persist>0).

**Nota semântica:** RSI é reversão à média. Onset bullish = **sair do sobrevendido** (RSI cruza `low`=30 p/ cima), não "RSI alto".

- [ ] **Step 1: Escrever `tests/test_rsi.py`**

```python
# numpy para montar a rampa de preços.
import numpy as np
# pandas para o DataFrame.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import rsi


# Fixture local: cai forte e depois sobe forte (RSI mergulha < 30 e volta > 30).
def _dip_then_rally():
    # Fase 1: 20 dias caindo (RSI vai a <30) + 20 dias subindo (RSI volta a >30).
    down = np.linspace(100, 60, 20)
    up = np.linspace(60, 110, 20)
    close = np.concatenate([down, up])
    # Saída: DataFrame só com Close (RSI usa só Close).
    return pd.DataFrame({"Close": close})


# Teste: cria RSI, estado e onset.
def test_rsi_creates_columns():
    """
    Por quê: estado = RSI ≥ low (não-sobrevendido); onset = cruzar low p/ cima.

    Lógica: Entrada (dip-then-rally) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: janela 14, low 30.
    out = rsi.add_columns(_dip_then_rally(), window=14, low=30)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert rsi.value_col(14) in out.columns
    scol = rsi.signal_col(14, 30)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and rsi.NAME == "rsi"


# Teste: onset = transição 0→1 do estado.
def test_rsi_signal_equals_state_transitions():
    """
    Por quê: onset só quando o RSI passa de sobrevendido a não-sobrevendido.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1.
    out = rsi.add_columns(_dip_then_rally(), window=14, low=30)
    # Fase 2: invariante.
    state = out["rsi_w14_low30_state"]
    sig = out[rsi.signal_col(14, 30)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: cada onset é um CRUZAMENTO do low p/ cima (RSI ontem < low, hoje ≥ low).
def test_rsi_onset_is_upward_cross_of_low():
    """
    Por quê: o gatilho é a saída do sobrevendido — precisa provar que todo onset
    ocorre onde o RSI cruza `low` de baixo p/ cima.

    Lógica: Entrada (dip-then-rally) → Fase 1 add_columns → Fase 2 checa cada onset → Saída.
    """
    # Fase 1: janela 14, low 30.
    out = rsi.add_columns(_dip_then_rally(), window=14, low=30)
    r = out[rsi.value_col(14)]
    sig = out[rsi.signal_col(14, 30)]
    # Fase 2: houve ao menos um onset...
    idxs = [i for i in range(1, len(out)) if int(sig.iloc[i]) == 1]
    assert len(idxs) >= 1
    # Fase 2/Saída: em cada onset, RSI ontem < 30 e RSI hoje ≥ 30.
    for i in idxs:
        assert r.iloc[i - 1] < 30 and r.iloc[i] >= 30


# Teste: janela > série → RSI NaN → zero eventos.
def test_rsi_window_larger_than_series_zero_events():
    """
    Por quê: janela grande num df curto → RSI NaN (min_periods) → sem evento.

    Lógica: Entrada (5 dias, window=14) → Fase 1 → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"Close": [10.0, 11.0, 10.0, 12.0, 11.0]})
    # Fase 1: janela 14.
    out = rsi.add_columns(df.copy(), window=14, low=30)
    # Fase 2/Saída: zero eventos.
    assert int(out[rsi.signal_col(14, 30)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_rsi_persist_fires_once_at_confirmation():
    """
    Por quê: persist confirma que a saída do sobrevendido durou — RSI cruzou 30 p/
    cima e permaneceu ≥ 30 por mais k dias. One-shot na confirmação, sem vazamento.

    Lógica: Entrada (dip-then-rally) → Fase 1 add_columns(persist=2) → Fase 2 cada
    confirmação está 2 dias após um onset, com estado ligado no intervalo → Saída.
    """
    # Fase 1: janela 14, low 30, persist=2 (rally sustentado mantém o RSI subindo).
    out = rsi.add_columns(_dip_then_rally(), window=14, low=30, persist=2)
    # Fase 2: colunas de onset, estado e persistência.
    onset = out[rsi.signal_col(14, 30)]
    state = out["rsi_w14_low30_state"]
    p = out[rsi.signal_col(14, 30, persist=2)]
    # Fase 2: há ao menos uma confirmação; dtype Int8.
    idxs = [i for i in range(len(out)) if int(p.iloc[i]) == 1]
    assert len(idxs) >= 1 and str(p.dtype) == "Int8"
    # Fase 2/Saída: cada confirmação está 2 dias após um onset, com o estado ligado no meio.
    for i in idxs:
        assert int(onset.iloc[i - 2]) == 1
        assert all(int(state.iloc[j]) == 1 for j in range(i - 2, i + 1))
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_rsi.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Criar `src/robusta/indicators/rsi.py`**

```python
# pandas para diff/ewm/shift e Int8.
import pandas as pd

# Nome do indicador.
NAME = "rsi"


# Nome canônico da coluna de valor (RSI).
def value_col(window: int) -> str:
    """
    Por quê: centralizar o nome do RSI.

    Lógica: Entrada (janela) → Saída (`rsi_w{window}`).
    """
    # Saída: nome do RSI.
    return f"rsi_w{window}"


# Nome canônico da coluna-dummy (onset puro ou persistência de k dias).
def signal_col(window: int, low: int, persist: int = 0) -> str:
    """
    Por quê: o sweep descobre o nome pela (janela, piso, persist); um mesmo
    (janela, low) pode gerar o onset puro (persist=0) OU a persistência de k dias.

    Lógica: Entrada (janela, low, persist) → Saída:
      persist=0 → `rsi_w{window}_low{low}_signal`; persist=k → `rsi_w{window}_low{low}_persist{k}`.
    """
    # persist>0: nome dedicado da dummy de persistência de k dias.
    if persist:
        # Saída: nome da persistência para (janela, low, k).
        return f"rsi_w{window}_low{low}_persist{persist}"
    # Saída: nome do onset.
    return f"rsi_w{window}_low{low}_signal"


# Acrescenta RSI (Wilder), estado, onset e (opcional) persistência ao df-fundação.
def add_columns(df: pd.DataFrame, window: int, low: int, persist: int = 0) -> pd.DataFrame:
    """
    Por quê: PLUG-IN de reversão à média. O gatilho bullish é SAIR do sobrevendido:
    estado = RSI ≥ low; onset = o dia em que o RSI cruza `low` de baixo p/ cima.

    Lógica (Entrada → Saída):
      Entrada: df com Close; janela do RSI, piso `low` e persist (0 = desligada).
      Fase 1: variação diária → ganhos e perdas separados.
      Fase 2: médias de Wilder (EMA α=1/window, min_periods=window) de ganho e perda.
      Fase 3: RS = média_ganho/média_perda; RSI = 100 − 100/(1+RS) em rsi_w{window}.
      Fase 4: estado (RSI ≥ low) em *_state; onset (transição 0→1) em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset + k dias no estado) em *_persist{k}.
      Saída: df-fundação com as colunas anexadas (3 fixas; +1 se persist>0).
    """
    # Fase 1: variação diária do Close.
    delta = df["Close"].diff()
    # Fase 1: ganhos (parte positiva) e perdas (parte negativa, em módulo).
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Fase 2: médias de Wilder via EMA (α=1/window); NaN até window pontos.
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    # Fase 3: força relativa e RSI.
    rs = avg_gain / avg_loss
    rsi_series = 100 - 100 / (1 + rs)
    # Fase 3: grava o RSI.
    df[value_col(window)] = rsi_series
    # Fase 4: estado bullish = fora do sobrevendido.
    state = rsi_series >= low
    # Fase 4: grava o estado como Int8.
    df[f"rsi_w{window}_low{low}_state"] = state.astype("Int8")
    # Fase 4: onset = transição 0→1 (cruza `low` p/ cima).
    onset = state & ~state.shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(window, low)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: acende só quando state=1 e a sequência tem exatamente k+1 dias (sem vazamento).
        df[signal_col(window, low, persist)] = (state & (streak == persist + 1)).astype("Int8")
    # Saída: df enriquecido.
    return df
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_rsi.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/indicators/rsi.py tests/test_rsi.py
git commit -m "feat(rsi): exit-from-oversold onset plug-in"
```

---

## Task 11: Indicador `macd` (cruzamento da linha de sinal)

**Files:**
- Create: `src/robusta/indicators/macd.py`
- Create: `tests/test_macd.py`

**Interfaces:**
- Produces: `macd.NAME="macd"`; `macd.value_col(fast, slow)->"macd_{fast}_{slow}"`; `macd.signal_col(fast, slow, sig, persist=0)` → `"macd_{fast}_{slow}_{sig}_signal"` (persist=0) / `"macd_{fast}_{slow}_{sig}_persist{k}"` (k>0); `macd.add_columns(df, fast, slow, sig, persist=0)->df` (colunas: `macd_{fast}_{slow}`, `*_line`, `*_state`, `*_signal`, +`*_persist{k}` se persist>0).

- [ ] **Step 1: Escrever `tests/test_macd.py`**

```python
# numpy para a rampa de preços.
import numpy as np
# pandas para o DataFrame.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import macd


# Fixture local: cai e depois sobe (MACD cruza a linha de sinal p/ cima).
def _down_then_up():
    # Fase 1: 30 dias caindo + 30 subindo (gera o cruzamento do MACD).
    close = np.concatenate([np.linspace(100, 70, 30), np.linspace(70, 120, 30)])
    # Saída: DataFrame só com Close.
    return pd.DataFrame({"Close": close})


# Teste: cria MACD, linha de sinal, estado e onset.
def test_macd_creates_columns():
    """
    Por quê: estado = MACD > linha de sinal; onset = cruzamento p/ cima.

    Lógica: Entrada (down-then-up) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: 12/26/9.
    out = macd.add_columns(_down_then_up(), fast=12, slow=26, sig=9)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert macd.value_col(12, 26) in out.columns
    scol = macd.signal_col(12, 26, 9)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and macd.NAME == "macd"


# Teste: onset = transição 0→1 do estado.
def test_macd_signal_equals_state_transitions():
    """
    Por quê: onset só quando o MACD passa de ≤ para > a linha de sinal.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1.
    out = macd.add_columns(_down_then_up(), fast=12, slow=26, sig=9)
    # Fase 2: invariante.
    state = out["macd_12_26_9_state"]
    sig = out[macd.signal_col(12, 26, 9)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: cada onset é um cruzamento MACD > sinal (antes ≤).
def test_macd_onset_is_upward_cross_of_signal():
    """
    Por quê: o gatilho é o MACD cruzar a linha de sinal p/ cima — provar em cada onset.

    Lógica: Entrada (down-then-up) → Fase 1 add_columns → Fase 2 checa cada onset → Saída.
    """
    # Fase 1.
    out = macd.add_columns(_down_then_up(), fast=12, slow=26, sig=9)
    m = out[macd.value_col(12, 26)]
    line = out["macd_12_26_9_line"]
    sig = out[macd.signal_col(12, 26, 9)]
    # Fase 2: há ao menos um onset e, em cada um, MACD sobe através do sinal.
    idxs = [i for i in range(1, len(out)) if int(sig.iloc[i]) == 1]
    assert len(idxs) >= 1
    for i in idxs:
        assert m.iloc[i] > line.iloc[i] and m.iloc[i - 1] <= line.iloc[i - 1]


# Teste: série curtíssima não quebra e dá dummy 0/1 (slow > série → sem valor → 0).
def test_macd_short_series_zero_events():
    """
    Por quê: com min_periods=slow, uma série menor que `slow` deixa o MACD NaN → sem evento.

    Lógica: Entrada (5 dias, slow=26) → Fase 1 → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 11.0, 13.0]})
    # Fase 1: 12/26/9.
    out = macd.add_columns(df.copy(), fast=12, slow=26, sig=9)
    # Fase 2/Saída: zero eventos.
    assert int(out[macd.signal_col(12, 26, 9)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_macd_persist_fires_once_at_confirmation():
    """
    Por quê: persist confirma que o cruzamento do MACD durou — MACD acima da linha
    de sinal por mais k dias. One-shot na confirmação, sem vazamento.

    Lógica: Entrada (down-then-up) → Fase 1 add_columns(persist=2) → Fase 2 cada
    confirmação está 2 dias após um onset, com estado ligado no intervalo → Saída.
    """
    # Fase 1: 12/26/9, persist=2 (rally sustentado mantém MACD acima do sinal).
    out = macd.add_columns(_down_then_up(), fast=12, slow=26, sig=9, persist=2)
    # Fase 2: colunas de onset, estado e persistência.
    onset = out[macd.signal_col(12, 26, 9)]
    state = out["macd_12_26_9_state"]
    p = out[macd.signal_col(12, 26, 9, persist=2)]
    # Fase 2: há ao menos uma confirmação; dtype Int8.
    idxs = [i for i in range(len(out)) if int(p.iloc[i]) == 1]
    assert len(idxs) >= 1 and str(p.dtype) == "Int8"
    # Fase 2/Saída: cada confirmação está 2 dias após um onset, com o estado ligado no meio.
    for i in idxs:
        assert int(onset.iloc[i - 2]) == 1
        assert all(int(state.iloc[j]) == 1 for j in range(i - 2, i + 1))
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_macd.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Criar `src/robusta/indicators/macd.py`**

```python
# pandas para ewm/shift e Int8.
import pandas as pd

# Nome do indicador.
NAME = "macd"


# Nome canônico da coluna de valor (linha MACD).
def value_col(fast: int, slow: int) -> str:
    """
    Por quê: centralizar o nome da linha MACD (diferença das EMAs).

    Lógica: Entrada (fast, slow) → Saída (`macd_{fast}_{slow}`).
    """
    # Saída: nome da linha MACD.
    return f"macd_{fast}_{slow}"


# Nome canônico da coluna-dummy (onset puro ou persistência de k dias).
def signal_col(fast: int, slow: int, sig: int, persist: int = 0) -> str:
    """
    Por quê: o sweep descobre o nome pela (fast, slow, sig, persist); um mesmo trio
    pode gerar o onset puro (persist=0) OU a persistência de k dias.

    Lógica: Entrada (fast, slow, sig, persist) → Saída:
      persist=0 → `macd_{fast}_{slow}_{sig}_signal`; persist=k → `macd_{fast}_{slow}_{sig}_persist{k}`.
    """
    # persist>0: nome dedicado da dummy de persistência de k dias.
    if persist:
        # Saída: nome da persistência para (fast, slow, sig, k).
        return f"macd_{fast}_{slow}_{sig}_persist{persist}"
    # Saída: nome do onset.
    return f"macd_{fast}_{slow}_{sig}_signal"


# Acrescenta MACD, linha de sinal, estado, onset e (opcional) persistência ao df-fundação.
def add_columns(df: pd.DataFrame, fast: int, slow: int, sig: int, persist: int = 0) -> pd.DataFrame:
    """
    Por quê: PLUG-IN de momentum. Estado bullish = linha MACD acima da linha de sinal;
    onset = o cruzamento para cima (gatilho clássico de compra do MACD).

    Lógica (Entrada → Saída):
      Entrada: df com Close; períodos fast, slow, sig e persist (0 = desligada).
      Fase 1: EMAs rápida e lenta (min_periods = span → NaN até janela cheia).
      Fase 2: MACD = EMA_fast − EMA_slow em macd_{fast}_{slow}.
      Fase 3: linha de sinal = EMA(MACD, sig) em *_line.
      Fase 4: estado (MACD > sinal) em *_state; onset (transição 0→1) em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset + k dias no estado) em *_persist{k}.
      Saída: df-fundação com as colunas anexadas (4 fixas; +1 se persist>0).
    """
    # Fase 1: EMAs (adjust=False = EMA padrão; min_periods evita valor precoce).
    ema_fast = df["Close"].ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = df["Close"].ewm(span=slow, adjust=False, min_periods=slow).mean()
    # Fase 2: linha MACD.
    macd_line = ema_fast - ema_slow
    # Fase 2: grava a linha MACD.
    df[value_col(fast, slow)] = macd_line
    # Fase 3: linha de sinal (EMA da MACD).
    signal_line = macd_line.ewm(span=sig, adjust=False, min_periods=sig).mean()
    # Fase 3: grava a linha de sinal.
    df[f"macd_{fast}_{slow}_{sig}_line"] = signal_line
    # Fase 4: estado bullish = MACD acima da linha de sinal.
    state = macd_line > signal_line
    # Fase 4: grava o estado como Int8.
    df[f"macd_{fast}_{slow}_{sig}_state"] = state.astype("Int8")
    # Fase 4: onset = transição 0→1 do estado.
    onset = state & ~state.shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(fast, slow, sig)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: acende só quando state=1 e a sequência tem exatamente k+1 dias (sem vazamento).
        df[signal_col(fast, slow, sig, persist)] = (state & (streak == persist + 1)).astype("Int8")
    # Saída: df enriquecido.
    return df
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_macd.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/indicators/macd.py tests/test_macd.py
git commit -m "feat(macd): signal-line-cross onset plug-in"
```

---

## Task 12: Indicador `donchian` (nova máxima de N dias)

**Files:**
- Create: `src/robusta/indicators/donchian.py`
- Create: `tests/test_donchian.py`

**Interfaces:**
- Produces: `donchian.NAME="donchian"`; `donchian.value_col(N)->"donchian_hh{N}"`; `donchian.signal_col(N, persist=0)` → `"donchian_N{N}_signal"` (persist=0) / `"donchian_N{N}_persist{k}"` (k>0); `donchian.add_columns(df, N, persist=0)->df` (colunas: `donchian_hh{N}`, `*_state`, `*_signal`, +`*_persist{k}` se persist>0).

- [ ] **Step 1: Escrever `tests/test_donchian.py`**

```python
# pandas para casos pequenos controlados.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import donchian as dc


# Teste: cria a máxima de N dias, estado e onset.
def test_dc_creates_columns(synthetic_prices_volume):
    """
    Por quê: estado = Close acima da máxima dos N dias ANTERIORES; onset = nova máxima.

    Lógica: Entrada (preços) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: N=20.
    out = dc.add_columns(synthetic_prices_volume.copy(), N=20)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert dc.value_col(20) in out.columns
    scol = dc.signal_col(20)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and dc.NAME == "donchian"


# Teste: onset = transição 0→1 do estado.
def test_dc_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset acende no 1º dia acima do canal (nova máxima), não em cada dia acima.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1.
    out = dc.add_columns(synthetic_prices_volume.copy(), N=20)
    # Fase 2: invariante.
    state = out["donchian_N20_state"]
    sig = out[dc.signal_col(20)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: acende exatamente quando o Close supera a máxima dos N dias anteriores.
def test_dc_fires_on_new_n_day_high():
    """
    Por quê: provar a definição do canal — o Close rompe a máxima de N=3 dias num
    índice conhecido.

    Lógica: Entrada (platô e depois um novo topo) → Fase 1 add_columns → Fase 2 → Saída.
    """
    # Entrada: High/Close estáveis em 10 e um salto para 12 no idx5.
    df = pd.DataFrame({
        "High":  [10, 10, 10, 10, 10, 12],
        "Close": [10, 10, 10, 10, 10, 12],
    })
    # Fase 1: N=3 (máxima dos 3 dias anteriores).
    out = dc.add_columns(df.copy(), N=3)
    # Fase 2/Saída: acende só no idx5 (novo topo acima da máxima anterior = 10).
    sig = out[dc.signal_col(3)]
    assert int(sig.sum()) == 1 and int(sig.iloc[5]) == 1


# Teste: janela > série → máxima NaN → zero eventos.
def test_dc_window_larger_than_series_zero_events():
    """
    Por quê: N grande num df curto → rolling max NaN → sem evento.

    Lógica: Entrada (3 dias, N=55) → Fase 1 → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"High": [10.0, 11.0, 12.0], "Close": [10.0, 11.0, 12.0]})
    # Fase 1: N=55.
    out = dc.add_columns(df.copy(), N=55)
    # Fase 2/Saída: zero eventos.
    assert int(out[dc.signal_col(55)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_dc_persist_fires_once_at_confirmation():
    """
    Por quê: persist confirma que o rompimento do canal durou — novas máximas por
    mais k dias seguidos. One-shot na confirmação, sem vazamento.

    Lógica: Entrada (platô, depois novas máximas todo dia) → Fase 1 add_columns(persist=2)
    → Fase 2 onset no idx3, estado segue ligado → confirmação única no idx5 → Saída.
    """
    # Entrada: platô de 3 dias e depois novas máximas todo dia (estado permanece ligado).
    df = pd.DataFrame({
        "High":  [10, 10, 10, 11, 12, 13, 14, 15],
        "Close": [10, 10, 10, 11, 12, 13, 14, 15],
    })
    # Fase 1: N=3, persist=2.
    out = dc.add_columns(df.copy(), N=3, persist=2)
    # Fase 2: onset no idx3 (rompe o teto=10); streak=3 no idx5 → confirmação única.
    p = out[dc.signal_col(3, persist=2)]
    # Fase 2/Saída: uma única confirmação, no idx5, dtype Int8.
    assert int(p.sum()) == 1 and int(p.iloc[5]) == 1 and str(p.dtype) == "Int8"
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_donchian.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Criar `src/robusta/indicators/donchian.py`**

```python
# pandas para rolling/shift e Int8.
import pandas as pd

# Nome do indicador.
NAME = "donchian"


# Nome canônico da coluna de valor (máxima de N dias anteriores).
def value_col(N: int) -> str:
    """
    Por quê: centralizar o nome do teto do canal de Donchian.

    Lógica: Entrada (N) → Saída (`donchian_hh{N}`).
    """
    # Saída: nome da máxima de N dias.
    return f"donchian_hh{N}"


# Nome canônico da coluna-dummy (onset puro ou persistência de k dias).
def signal_col(N: int, persist: int = 0) -> str:
    """
    Por quê: o sweep descobre o nome por (N, persist); um mesmo N pode gerar o onset
    puro (persist=0) OU a persistência de k dias.

    Lógica: Entrada (N, persist) → Saída:
      persist=0 → `donchian_N{N}_signal`; persist=k → `donchian_N{N}_persist{k}`.
    """
    # persist>0: nome dedicado da dummy de persistência de k dias.
    if persist:
        # Saída: nome da persistência para (N, k).
        return f"donchian_N{N}_persist{persist}"
    # Saída: nome do onset.
    return f"donchian_N{N}_signal"


# Acrescenta o teto do canal, estado, onset e (opcional) persistência ao df-fundação.
def add_columns(df: pd.DataFrame, N: int, persist: int = 0) -> pd.DataFrame:
    """
    Por quê: PLUG-IN de rompimento de canal. Estado bullish = Close acima da máxima
    dos N dias ANTERIORES (shift(1) evita usar o próprio dia → sem vazamento);
    onset = a nova máxima de N dias.

    Lógica (Entrada → Saída):
      Entrada: df com High e Close; janela N do canal e persist (0 = desligada).
      Fase 1: máxima móvel do High em N dias, deslocada 1 dia (min_periods=N) em donchian_hh{N}.
      Fase 2: estado (Close > teto anterior) em *_state.
      Fase 3: onset (transição 0→1) em *_signal.
      Fase 4: se persist>0, dummy de persistência (onset + k dias no estado) em *_persist{k}.
      Saída: df-fundação com as colunas anexadas (3 fixas; +1 se persist>0).
    """
    # Fase 1: teto do canal = máxima dos N dias anteriores (shift(1) exclui o dia atual).
    hh = df["High"].rolling(N, min_periods=N).max().shift(1)
    # Fase 1: grava o teto.
    df[value_col(N)] = hh
    # Fase 2: estado bullish = Close rompeu o teto anterior.
    state = df["Close"] > hh
    # Fase 2: grava o estado como Int8.
    df[f"donchian_N{N}_state"] = state.astype("Int8")
    # Fase 3: onset = transição 0→1 do estado.
    onset = state & ~state.shift(1, fill_value=False)
    # Fase 3: grava o onset como Int8.
    df[signal_col(N)] = onset.astype("Int8")
    # Fase 4: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 4: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 4: acende só quando state=1 e a sequência tem exatamente k+1 dias (sem vazamento).
        df[signal_col(N, persist)] = (state & (streak == persist + 1)).astype("Int8")
    # Saída: df enriquecido.
    return df
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_donchian.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/indicators/donchian.py tests/test_donchian.py
git commit -m "feat(donchian): N-day-high breakout onset plug-in"
```

---

## Task 13: Indicador `bollinger` (rompimento da banda superior)

**Files:**
- Create: `src/robusta/indicators/bollinger.py`
- Create: `tests/test_bollinger.py`

**Interfaces:**
- Produces: `bollinger.NAME="bollinger"`; `bollinger.value_col(window)->"boll_mid{window}"`; `bollinger.signal_col(window, n_std, persist=0)` → `"bollinger_w{window}_s{n_std}_signal"` (persist=0) / `"bollinger_w{window}_s{n_std}_persist{k}"` (k>0); `bollinger.add_columns(df, window, n_std, persist=0)->df` (colunas: `boll_mid{window}`, `boll_upper_w{window}_s{n_std}`, `*_state`, `*_signal`, +`*_persist{k}` se persist>0).

- [ ] **Step 1: Escrever `tests/test_bollinger.py`**

```python
# pandas para casos pequenos controlados.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import bollinger as bb


# Teste: cria banda média, banda superior, estado e onset.
def test_bb_creates_columns(synthetic_prices_volume):
    """
    Por quê: estado = Close acima da banda superior (mid + n_std·σ); onset = rompimento.

    Lógica: Entrada (preços) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: janela 20, 2 desvios.
    out = bb.add_columns(synthetic_prices_volume.copy(), window=20, n_std=2.0)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert bb.value_col(20) in out.columns
    scol = bb.signal_col(20, 2.0)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and bb.NAME == "bollinger"


# Teste: onset = transição 0→1 do estado.
def test_bb_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset acende no 1º dia acima da banda, não em cada dia acima.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1.
    out = bb.add_columns(synthetic_prices_volume.copy(), window=20, n_std=2.0)
    # Fase 2: invariante.
    state = out["bollinger_w20_s2.0_state"]
    sig = out[bb.signal_col(20, 2.0)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: um salto de preço acima da banda acende; n_std maior exige salto maior (≤ eventos).
def test_bb_wider_band_suppresses(synthetic_prices_volume):
    """
    Por quê: bandas mais largas (n_std maior) são mais difíceis de romper → menos ou
    igual nº de onsets.

    Lógica: Entrada → Fase 1 dois n_std → Fase 2 wide ≤ narrow → Saída.
    """
    # Fase 1: eventos com 2 e com 3 desvios.
    narrow = bb.add_columns(synthetic_prices_volume.copy(), window=20, n_std=2.0)[bb.signal_col(20, 2.0)].sum()
    wide = bb.add_columns(synthetic_prices_volume.copy(), window=20, n_std=3.0)[bb.signal_col(20, 3.0)].sum()
    # Fase 2/Saída.
    assert wide <= narrow


# Teste: janela > série → banda NaN → zero eventos.
def test_bb_window_larger_than_series_zero_events():
    """
    Por quê: janela grande num df curto → média/σ NaN → banda NaN → sem evento.

    Lógica: Entrada (3 dias, window=20) → Fase 1 → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0]})
    # Fase 1: janela 20.
    out = bb.add_columns(df.copy(), window=20, n_std=2.0)
    # Fase 2/Saída: zero eventos.
    assert int(out[bb.signal_col(20, 2.0)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_bb_persist_fires_once_at_confirmation():
    """
    Por quê: persist confirma que o rompimento da banda durou k dias — a banda
    alarga aos poucos após um salto, então o estado dura alguns dias e desliga.
    One-shot na confirmação, sem vazamento.

    Lógica: Entrada (19 dias parado + salto mantido) → Fase 1 add_columns(persist=2)
    → Fase 2 onset no idx19; estado dura idx19–21 → confirmação única no idx21 → Saída.
    """
    # Entrada: 19 dias parado em 10 e salto para 20 mantido (a banda alarga aos poucos).
    df = pd.DataFrame({"Close": [10.0] * 19 + [20.0] * 5})
    # Fase 1: janela 20, 2 desvios, persist=2.
    out = bb.add_columns(df.copy(), window=20, n_std=2.0, persist=2)
    # Fase 2: onset no idx19 (1º dia acima da banda superior).
    onset = out[bb.signal_col(20, 2.0)]
    assert int(onset.iloc[19]) == 1
    # Fase 2: estado dura 3 dias (idx19–21; no idx22 a banda já engoliu o salto).
    p = out[bb.signal_col(20, 2.0, persist=2)]
    # Fase 2/Saída: uma única confirmação, no idx21, dtype Int8.
    assert int(p.sum()) == 1 and int(p.iloc[21]) == 1 and str(p.dtype) == "Int8"
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_bollinger.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Criar `src/robusta/indicators/bollinger.py`**

```python
# pandas para rolling/shift e Int8.
import pandas as pd

# Nome do indicador.
NAME = "bollinger"


# Nome canônico da coluna de valor (banda média = SMA).
def value_col(window: int) -> str:
    """
    Por quê: centralizar o nome da banda média (SMA base das bandas).

    Lógica: Entrada (janela) → Saída (`boll_mid{window}`).
    """
    # Saída: nome da banda média.
    return f"boll_mid{window}"


# Nome canônico da coluna-dummy (onset puro ou persistência de k dias).
def signal_col(window: int, n_std: float, persist: int = 0) -> str:
    """
    Por quê: o sweep descobre o nome pela (janela, nº de desvios, persist); um mesmo
    (janela, n_std) pode gerar o onset puro (persist=0) OU a persistência de k dias.

    Lógica: Entrada (janela, n_std, persist) → Saída:
      persist=0 → `bollinger_w{window}_s{n_std}_signal`; persist=k → `..._persist{k}`.
    """
    # persist>0: nome dedicado da dummy de persistência de k dias.
    if persist:
        # Saída: nome da persistência para (janela, n_std, k).
        return f"bollinger_w{window}_s{n_std}_persist{persist}"
    # Saída: nome do onset.
    return f"bollinger_w{window}_s{n_std}_signal"


# Acrescenta banda média, banda superior, estado, onset e (opcional) persistência ao df-fundação.
def add_columns(df: pd.DataFrame, window: int, n_std: float, persist: int = 0) -> pd.DataFrame:
    """
    Por quê: PLUG-IN de volatilidade. Estado bullish = Close acima da banda superior
    (SMA + n_std·desvio-padrão); onset = o rompimento da banda.

    Lógica (Entrada → Saída):
      Entrada: df com Close; janela, nº de desvios e persist (0 = desligada).
      Fase 1: SMA (banda média) e desvio-padrão móvel (min_periods=window).
      Fase 2: banda superior = média + n_std·σ em boll_upper_w{window}_s{n_std}.
      Fase 3: estado (Close > banda superior) em *_state.
      Fase 4: onset (transição 0→1) em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset + k dias no estado) em *_persist{k}.
      Saída: df-fundação com as colunas anexadas (4 fixas; +1 se persist>0).
    """
    # Fase 1: banda média (SMA) e desvio-padrão móvel (NaN até janela cheia).
    mid = df["Close"].rolling(window, min_periods=window).mean()
    sd = df["Close"].rolling(window, min_periods=window).std()
    # Fase 1: grava a banda média.
    df[value_col(window)] = mid
    # Fase 2: banda superior.
    upper = mid + n_std * sd
    # Fase 2: grava a banda superior.
    df[f"boll_upper_w{window}_s{n_std}"] = upper
    # Fase 3: estado bullish = Close rompeu a banda superior.
    state = df["Close"] > upper
    # Fase 3: grava o estado como Int8.
    df[f"bollinger_w{window}_s{n_std}_state"] = state.astype("Int8")
    # Fase 4: onset = transição 0→1 do estado.
    onset = state & ~state.shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(window, n_std)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: acende só quando state=1 e a sequência tem exatamente k+1 dias (sem vazamento).
        df[signal_col(window, n_std, persist)] = (state & (streak == persist + 1)).astype("Int8")
    # Saída: df enriquecido.
    return df
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_bollinger.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add src/robusta/indicators/bollinger.py tests/test_bollinger.py
git commit -m "feat(bollinger): upper-band breakout onset plug-in"
```

---

## Task 14: `run_all.py` (entrypoint consolidado + master rankeável)

**Files:**
- Create: `src/robusta/run_all.py`
- Create: `tests/test_run_all.py`

**Interfaces:**
- Consumes: `runner.build_summary`/`write_outputs`/`summary_dictionary`; `load_prices`; `config.INDICATORS`/`PARAM_GRIDS`/`HORIZONS`/`MIN_EVENTS`/`OUTPUT_DIR`; cada módulo via `importlib.import_module(f"robusta.indicators.{name}")`.
- Produces:
  - `run_all.build_master(summaries) -> DataFrame` — concatena e ordena por `[family, sort_key]` desc (na_position="last"), com `sort_key = lift` (logit) / `coef` (ols).
  - `run_all.write_master(master, outdir="output") -> Path` — grava `summary_ALL.xlsx` (abas `ranking` + `dicionário`).
  - `run_all.run_all(prices, indicators, param_grids, horizons, min_events=5, outdir="output") -> DataFrame` (pura, sem rede).
  - `run_all.main(ticker=config.TICKER, period=config.PERIOD)` (I/O: baixa + escreve).

- [ ] **Step 1: Escrever `tests/test_run_all.py`**

```python
# pandas para reler os arquivos e checar ordenação.
import pandas as pd
# O entrypoint consolidado sob teste (função pura run_all + master).
from robusta.run_all import run_all, build_master


# Teste: run_all roda um roster pequeno, grava um par por indicador e o master.
def test_run_all_writes_per_indicator_and_master(synthetic_prices_volume, tmp_path):
    """
    Por quê: provar a consolidação — para cada indicador sai analysis_/summary_, e um
    summary_ALL.xlsx concatena tudo. Sem rede (recebe preços prontos).

    Lógica: Entrada (preços+volume, roster pequeno) → Fase 1 run_all → Fase 2 arquivos
    → Fase 3 master → Saída.
    """
    # Entrada: roster pequeno (1 trend + 1 volume) e grids mínimos.
    indicators = ["mma", "obv"]
    grids = {"mma": {"window": [20], "tol": [0.0], "persist": [0]}, "obv": {"window": [20]}}
    # Fase 1: roda a versão pura em tmp.
    master = run_all(synthetic_prices_volume, indicators, grids, [10, 20], min_events=1, outdir=tmp_path)
    # Fase 2: um par de arquivos por indicador existe.
    for nome in indicators:
        assert (tmp_path / f"analysis_{nome}.xlsx").exists()
        assert (tmp_path / f"summary_{nome}.xlsx").exists()
    # Fase 3: o master existe e tem as duas abas.
    all_path = tmp_path / "summary_ALL.xlsx"
    assert all_path.exists()
    sheets = pd.ExcelFile(all_path).sheet_names
    assert "ranking" in sheets and "dicionário" in sheets
    # Saída: o master concatena os dois indicadores.
    assert set(master["indicator"]) == {"mma", "obv"}


# Teste: o master vem ordenado pela chave de ranking, por família (na no fim).
def test_master_ranked_by_family_key(synthetic_prices_volume):
    """
    Por quê: dentro de logit ordena por lift desc; dentro de ols por coef desc; NaN
    no fim de cada família (misturar unidades é seguro porque family é a chave primária).

    Lógica: Entrada (dois summaries) → Fase 1 build_master → Fase 2 ordenação por família → Saída.
    """
    # Entrada: gera dois summaries via run_all (descarta arquivos usando outdir tmp implícito não é preciso aqui).
    from robusta.runner import build_summary
    from robusta.indicators import mma, obv
    _, s1 = build_summary(synthetic_prices_volume, mma, {"window": [20], "tol": [0.0]}, [10, 20], min_events=1)
    _, s2 = build_summary(synthetic_prices_volume, obv, {"window": [20]}, [10, 20], min_events=1)
    # Fase 1: concatena e ordena.
    master = build_master([s1, s2])
    # Fase 2: chave por família (lift no logit, coef no ols) não-crescente, NaN por último.
    for fam, keycol in [("logit", "lift"), ("ols", "coef")]:
        vals = master[master["family"] == fam][keycol].tolist()
        notna = [v for v in vals if v == v]  # remove NaN
        # Saída: a parte não-NaN está em ordem não-crescente e os NaN vêm depois.
        assert notna == sorted(notna, reverse=True)
        nan_flags = [v == v for v in vals]  # True antes de False (na_position=last)
        assert nan_flags == sorted(nan_flags, reverse=True)
```

- [ ] **Step 2: Rodar e ver FALHAR**

Run: `uv run pytest tests/test_run_all.py -v`
Expected: FAIL — `ModuleNotFoundError: robusta.run_all`.

- [ ] **Step 3: Criar `src/robusta/run_all.py`**

```python
# Path para a pasta de saída e o caminho do master.
from pathlib import Path
# importlib carrega cada módulo-indicador pelo nome (roster dirigido por config).
import importlib
# pandas para concat/sort e o ExcelWriter.
import pandas as pd
# Download de preços (único ponto de rede).
from robusta.data import load_prices
# Runner genérico: orquestração + escrita + legenda compartilhadas.
from robusta.runner import build_summary, write_outputs, summary_dictionary
# Parâmetros centralizados.
from robusta import config


# Concatena os summaries e ordena por [family, chave-de-ranking] desc.
def build_master(summaries) -> pd.DataFrame:
    """
    Por quê: o master permite rankear os indicadores entre si. Como logit e ols usam
    métricas de escalas diferentes, a chave de ranking é lift (logit) / coef (ols), e
    `family` é a chave PRIMÁRIA de ordenação → lift e coef nunca são comparados entre si.

    Lógica (Entrada → Saída):
      Entrada: lista de summaries (um por indicador; params diferentes viram NaN no concat).
      Fase 1: concatena tudo num só DataFrame.
      Fase 2: chave de ranking por linha (lift se logit, senão coef).
      Fase 3: ordena por [family asc, chave desc], NaN por último; descarta a chave temporária.
      Saída: master ordenado, pronto para o summary_ALL.
    """
    # Fase 1: concatena (união de colunas; params ausentes viram NaN).
    master = pd.concat(summaries, ignore_index=True)
    # Fase 2: chave de ranking = lift nas linhas logit; coef nas demais (ols).
    sort_key = master["lift"].where(master["family"] == "logit", master["coef"])
    # Fase 3: ordena por família (primária) e pela chave (desc), NaN no fim; chave temporária removida.
    master = (
        master.assign(_sort=sort_key)
        .sort_values(["family", "_sort"], ascending=[True, False], na_position="last")
        .drop(columns="_sort")
        .reset_index(drop=True)
    )
    # Saída: master rankeável.
    return master


# Escreve o master em disco (.xlsx) com abas 'ranking' + 'dicionário'.
def write_master(master, outdir="output") -> Path:
    """
    Por quê: entregar o summary_ALL num arquivo à parte, com a legenda ao lado.

    Lógica (Entrada → Saída):
      Entrada: master e a pasta de saída.
      Fase 1: garante a pasta.
      Fase 2: grava 'ranking' (dados) e 'dicionário' (legenda derivada das colunas).
      Saída: caminho do summary_ALL.xlsx.
    """
    # Fase 1: normaliza a pasta e cria se faltar.
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    # Fase 2: caminho do master.
    path = out / "summary_ALL.xlsx"
    # Fase 2: writer para as duas abas.
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # Fase 2: aba de dados.
        master.to_excel(writer, sheet_name="ranking", index=False)
        # Fase 2: aba de legenda (mesma função do runner, cobre params variados).
        summary_dictionary(master).to_excel(writer, sheet_name="dicionário", index=False)
    # Saída: caminho escrito.
    return path


# Orquestração pura: de um df de preços a todos os arquivos + o master (sem rede).
def run_all(prices, indicators, param_grids, horizons, min_events: int = 5, outdir="output") -> pd.DataFrame:
    """
    Por quê: separar a consolidação (testável, sem rede) do I/O da main. Itera o
    roster, roda cada indicador com seu grid, grava o par por indicador e o master.

    Lógica (Entrada → Saída):
      Entrada: df OHLCV, roster, grids por indicador, horizontes, mín. eventos e pasta.
      Fase 1: para cada nome do roster, importa o módulo e roda build_summary com seu grid.
      Fase 2: grava analysis_/summary_ do indicador; acumula o summary.
      Fase 3: concatena os summaries no master e grava o summary_ALL.
      Saída: o master (também escrito em disco).
    """
    # Acumulador dos summaries por indicador.
    summaries = []
    # Fase 1: percorre o roster na ordem de config.INDICATORS.
    for name in indicators:
        # Fase 1: importa o módulo-indicador pelo nome.
        module = importlib.import_module(f"robusta.indicators.{name}")
        # Fase 1: grid do indicador (fonte única = config.PARAM_GRIDS).
        grid = param_grids[name]
        # Fase 1: roda o pipeline do indicador (sem rede).
        analysis, summary = build_summary(prices, module, grid, horizons, min_events=min_events)
        # Fase 2: grava o par de arquivos do indicador.
        write_outputs(analysis, summary, name, outdir)
        # Fase 2: guarda o summary para o master.
        summaries.append(summary)
    # Fase 3: monta e grava o master.
    master = build_master(summaries)
    write_master(master, outdir)
    # Saída: o master consolidado.
    return master


# Entrypoint de linha de comando: baixa 1×, roda o roster e grava tudo.
def main(ticker: str = config.TICKER, period: str = config.PERIOD) -> None:
    """
    Por quê: ponto de entrada humano do multi-indicador; concentra o I/O (download +
    escrita). TODOS os parâmetros vêm de config.py.

    Lógica (Entrada → Saída):
      Entrada: ticker e janela relativa (defaults de config).
      Fase 1: baixa os preços uma única vez (rede).
      Fase 2: roda run_all com o roster e os grids do config.
      Saída: arquivos por indicador + summary_ALL.xlsx na pasta do config.
    """
    # Fase 1: download único dos preços.
    prices = load_prices(ticker, period)
    # Fase 2: consolida tudo (arquivos por indicador + master).
    master = run_all(
        prices, config.INDICATORS, config.PARAM_GRIDS, config.HORIZONS,
        min_events=config.MIN_EVENTS, outdir=config.OUTPUT_DIR,
    )
    # Saída: feedback no console.
    print(f"summary_ALL.xlsx ({len(master)} linhas) + pares por indicador salvos em {config.OUTPUT_DIR}/")


# Permite rodar como script: `python -m robusta.run_all`.
if __name__ == "__main__":
    # Chama main com os defaults do config.
    main()
```

- [ ] **Step 4: Rodar e ver PASSAR**

Run: `uv run pytest tests/test_run_all.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Rodar a suíte inteira**

Run: `uv run pytest -v`
Expected: PASS — ~94 testes (41 após a Task 2 + 1 config + 1 fixture + 7×5 + 2×7 indicadores + 2 run_all; conferir o total real — todos verdes).

- [ ] **Step 6: Commit**

```bash
git add src/robusta/run_all.py tests/test_run_all.py
git commit -m "feat(run_all): consolidated multi-indicator runner + summary_ALL ranking"
```

---

## Task 15: Verificação e2e + atualização do `PLAN.md`

**Files:**
- Modify: `planning/PLAN.md`

- [ ] **Step 1: Rodar o pipeline real de ponta a ponta (rede)**

Run (PowerShell): `$env:PYTHONPATH="src"; uv run python -m robusta.run_all`
Expected: imprime `summary_ALL.xlsx (...) + pares por indicador salvos em output/`. Conferir em `output/`: `summary_ALL.xlsx` (~1.290 linhas = 215 combos × 3 horizontes × 2 famílias) + `analysis_<nome>.xlsx`/`summary_<nome>.xlsx` para os 10 indicadores. Abrir `summary_ALL.xlsx`, aba `ranking`, e conferir que dentro de `logit` a coluna `lift` desce e dentro de `ols` a coluna `coef` desce. Conferir também que linhas com `persist` alto têm `n_eventos` menor que as do onset puro do mesmo combo (sanidade do subconjunto).

- [ ] **Step 2: Atualizar a Fase 3 no `PLAN.md`**

Em `planning/PLAN.md`, marcar os itens da "Fase 3" como `[x]` e registrar o resultado e2e (nº de indicadores, nº de linhas do master, ticker/período), no mesmo estilo das Fases 1–2. Registrar a decisão "novos módulos sem `persist`" nas "Decisões travadas".

- [ ] **Step 3: Rodar a suíte inteira uma última vez**

Run: `uv run pytest`
Expected: PASS — todos os testes verdes.

- [ ] **Step 4: Commit**

```bash
git add planning/PLAN.md
git commit -m "docs(plan): mark Phase 3 multi-indicator complete with e2e results"
```

---

## Self-Review (do autor do plano)

**Cobertura do spec (§ do design → task):**
- §2 onset = `state & ~state.shift(1)` → Global Constraints + todas as tasks 5–13.
- §2 nomes `_state`/`_signal` → Task 1 (mma) + 5–13.
- §2 ranking lift/coef por família → Task 14 `build_master`.
- §3 contrato do módulo (sem `PARAM_GRID`, grid em config) → Global Constraints + Task 3; **`persist` em todos os 10 módulos** (decisão 2026-07-08): 8 de regime varrem `PERSISTENCES=[0..4]`, os 2 de evento ficam `[0]` no config.
- §4 onset por indicador (10 linhas da tabela) → Tasks 5–13 (mme, obv, vwap, alto_volume, exaustao_atr, rsi, macd, donchian, bollinger) + mma existente.
- §4 ressalvas (vwap rolante, atr contrário, rsi sair do sobrevendido) → docstrings/notas das Tasks 7, 9, 10 + testes específicos.
- `tolerancia_erro=0.005` do legado (exaustao_atr/alto_volume) → dimensão `tol=[0.0, 0.005]` do grid desses 2 módulos (decisão 2026-07-10); as demais divergências vs legado (só bullish; onset em vez de estado) são decisões do spec.
- Confirmação de preço `confirm=[0..4]` nos 2 módulos de evento (decisão 2026-07-10): responde "o preço segurou k dias após o pico?" — a variante de persistência que faz sentido onde o persist do estado não se aplica.
- §5a runner genérico + run_mma wrapper + summary_dictionary migrado → Task 2.
- §5b run_all (baixa 1×, itera, master) → Task 14. **Saída plana** (decisão) em vez de subpastas.
- §6 ranking (chave por família, guardas n_eventos/fisher_p visíveis) → Task 14 + colunas já presentes no summary.
- §7 config INDICATORS/PARAM_GRIDS → Task 3.
- §8 testes por módulo + runner + fixture `synthetic_prices_volume` → Tasks 4–14.
- §9 riscos (duplicação, poucos eventos) → aceitos; MIN_EVENTS/guardas cobrem.

**Consistência de tipos/nomes:** `signal_col`/`value_col`/`add_columns` de cada módulo batem com o grid do `config.PARAM_GRIDS` correspondente (params idênticos) e com o que `run_sweep` chama (`indicator.NAME`, `signal_col(**params)`, `add_columns(df, **params)`). Colunas `*_state`/`*_signal` uniformes. `build_master` usa `lift`/`coef`/`family`, todas presentes no schema de `run_sweep`.

**Placeholders:** nenhum — todo step de código traz o código completo.
