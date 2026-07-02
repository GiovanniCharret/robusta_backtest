# Design — Multi-indicador: 9 novos plug-ins + summary unificado rankeável

> Spec da Fase 3. Estende a arquitetura de 1 indicador (`mma`) para vários, cada um
> testado isoladamente, com um summary por indicador **e** um summary único que
> permite rankear todos. Segue as regras do projeto (docstrings + comentário por linha).

## 1. Objetivo e escopo

Transformar o backtest de **um** indicador (`mma`) em **N** indicadores, mantendo o
princípio já validado: cada indicador vira uma **dummy de onset bullish** (variável
independente) e é avaliado contra o alvo deslocado (`y_{h}d` / `ret_{h}d`) pelas duas
famílias (logit + ols) e pela associação 2×2.

Entregáveis:
1. Um **módulo por indicador** (plug-in isolado, cópia do padrão `mma`).
2. Um **summary por indicador** (`summary_<nome>.xlsx`), como hoje.
3. Um **runner único** (`run_all.py`) que roda todos e entrega **`summary_ALL.xlsx`**,
   um summary consolidado onde dá para **rankear os indicadores** entre si.

### Roster (9 novos + o `mma` existente = 10)

`mme`, `obv`, `vwap`, `alto_volume`, `exaustao_atr`, `rsi`, `macd`, `donchian`, `bollinger`.

### Não-objetivos (YAGNI nesta fase)

- Onset **bearish** (só bullish agora; bearish é extensão futura sem retrabalho).
- Persistência (`persist_k`) **nos novos** indicadores: o código suporta, mas o
  sweep-all roda `persist=[0]` (só onset) para o master não explodir. Só o `mma`
  mantém `PERSISTENCES=[0,4]`.
- Multi-preditor / stepwise / combinação de sinais (o legado combinava gatilhos; futuro).
- Validação out-of-sample (walk-forward) — continua no backlog.

## 2. Decisões travadas (2026-07-01)

| Tema | Decisão |
|---|---|
| Sinal → dummy | **Onset do estado bullish**: cada indicador expõe um ESTADO; a dummy = transição PARA o regime de alta (`state & ~state.shift(1)`). Espelha o `break` do `mma` e o `value→gatilho` do legado. |
| Direção | **Só bullish** nesta passada. |
| Ranking do master | Dentro de cada `family`: **logit → `lift`**, **ols → `coef`** (efeitos comparáveis entre indicadores). `r2` NÃO serve para cross-ranking. |
| Organização do código | **Um módulo por indicador** (isolamento total, cópia do padrão `mma`). Trade-off aceito: a lógica de transição/persistência fica **duplicada** entre módulos. |
| Config | Painel único: `INDICATORS` (roster) + `PARAM_GRIDS` (grid de cada indicador) em `config.py`. |
| Saídas | 1 par por indicador (`analysis_<nome>.xlsx` + `summary_<nome>.xlsx`) **+** `summary_ALL.xlsx` (abas `ranking` + `dicionário`). |

## 3. Contrato do módulo-indicador (cópia do padrão `mma`)

Cada arquivo `src/robusta/indicators/<nome>.py` expõe, como o `mma` já faz:

```
NAME: str                                   # nome curto (coluna `indicator` do summary)
PARAM_GRID: dict[str, list]                 # grid natural do indicador (default; config pode sobrescrever)
value_col(**params) -> str                  # nome canônico da(s) coluna(s) de valor
signal_col(**params, persist=0) -> str      # nome da dummy de onset (persist=0) / persistência (k>0)
add_columns(df, **params, persist=0) -> df  # ACRESCENTA valor + estado + onset (+persist) ao df-fundação
```

- `add_columns` **acumula colunas** no df-fundação (nunca devolve série solta), revisável linha a linha.
- O ESTADO bullish é gravado numa coluna `*_state` (Int8) para revisão; o onset numa `*_signal`.
- O `sweep.run_sweep` **já é agnóstico** ao indicador (recebe o módulo + `param_grid` e usa
  `signal_col`/`add_columns`), então **não muda**.

## 4. Definição do onset bullish por indicador

Estado bullish `s[t]` (booleano). Onset (a dummy) = `s & ~s.shift(1)` — 1 só no 1º dia da sequência.
Usa apenas passado/presente → **sem vazamento** para o alvo.

| Módulo | Valor | Estado bullish `s[t]` | Params (default) |
|---|---|---|---|
| **mme** | `ema = Close.ewm(span=w).mean()` | `Close > ema·(1+tol)` | `window ∈ {10,26,50,200}`, `tol ∈ {0,0.015,0.03}` |
| **obv** | `OBV` (volume sinalizado acumulado); `OBV_MA = OBV.rolling(w)` | `OBV > OBV_MA` | `window ∈ {20,50}` |
| **vwap** | `vwap = Σ(Close·Vol)/Σ(Vol)` **rolante** em `W` | `Close > vwap·(1+tol)` | `window ∈ {20,50}`, `tol ∈ {0,0.015}` |
| **alto_volume** | `vol_ma = Volume.rolling(w)`; `high = Volume ≥ mult·vol_ma` | `high E Close>Close[ontem]` | `window ∈ {20}`, `mult ∈ {1.5,2.0}` |
| **exaustao_atr** | `ATR = TR.rolling(p)`; `big = TR ≥ mult·ATR.shift(1)` | `big E Close>Close[ontem]` | `atr_period ∈ {14}`, `mult ∈ {1.5,2.0}` |
| **rsi** | `RSI(w)` (Wilder) | `RSI ≥ low` (saiu do sobrevendido → onset = cruzar `low` p/ cima) | `window ∈ {14}`, `low ∈ {30}` |
| **macd** | `macd = ema(fast)-ema(slow)`; `signal = ema(macd, sig)` | `macd > signal` | `fast ∈ {12}`, `slow ∈ {26}`, `sig ∈ {9}` |
| **donchian** | `hh = High.rolling(N).max().shift(1)` | `Close > hh` (nova máxima de N dias) | `N ∈ {20,55}` |
| **bollinger** | `mid = SMA(W)`; `upper = mid + n·σ_W` | `Close > upper` (rompe banda superior) | `window ∈ {20}`, `n_std ∈ {2.0}` |

### Ressalvas semânticas (aprovadas)

1. **VWAP é rolante** (janela `W`), não cumulativo desde o início — o cumulativo em 10 anos vira
   quase constante dominado pelos primeiros anos. Rolante é o padrão para sinal.
2. **Exaustão ATR é provavelmente contrária.** Um dia de alta gigante costuma preceder reversão;
   `lift < 1` aqui **é o achado**, não um bug. Mantido como sinal bullish; os dados decidem.
3. **RSI é reversão à média.** Onset bullish = **sair do sobrevendido** (cruzar `low`=30 p/ cima),
   não "RSI alto". É o gatilho clássico de compra.

## 5. Runner e saídas

### 5a. Runner genérico (refatora `build_summary`)

Hoje `run_mma.build_summary` está preso a `{window,tol,persist}` + `mma`. A versão genérica
vai para um módulo novo `src/robusta/runner.py`:

```
build_summary(prices, indicator, param_grid, horizons, min_events) -> (analysis, summary)
```

Decisão explícita: **`run_mma.py` continua existindo como wrapper fino** — sua `main`/`build_summary`
passam a delegar para `runner.build_summary` com o módulo `mma` e o grid do `mma`. Assim os testes
atuais (`test_run_mma.py`, `test_config.py`) seguem verdes sem reescrita. O `summary_dictionary` (legenda)
também migra para o `runner` (é compartilhado por todos os indicadores).

### 5b. `run_all.py` (entrypoint consolidado)

```
Entrada: config (ticker, period, INDICATORS, PARAM_GRIDS, horizons, ...).
Fase 1: baixa preços UMA vez (rede).
Fase 2: para cada indicador em INDICATORS:
          - roda build_summary com o PARAM_GRID do indicador;
          - escreve output/<nome>/analysis_<nome>.xlsx e summary_<nome>.xlsx (com dicionário).
Fase 3: concatena todos os summaries (coluna `indicator` já vem do ident);
        ordena para ranking (ver §6); escreve output/summary_ALL.xlsx (abas ranking + dicionário).
Saída: arquivos por indicador + o master rankeável.
```

Cada indicador tem seu próprio `analysis_<nome>.xlsx` (as colunas de cálculo diferem entre indicadores;
não faz sentido fundir num df só).

## 6. Ranking do master

O `summary_ALL` tem as duas famílias empilhadas. A ordenação usa uma **chave por família**:

- `sort_key = lift` nas linhas `logit`; `sort_key = coef` nas linhas `ols`.
- Ordena por `[family, sort_key]` desc. Como `family` é a chave primária, os valores de `sort_key`
  só são comparados **dentro** da mesma family → misturar unidades (lift × coef) é seguro.

Colunas-guarda visíveis: `n_eventos` (amostra) e `fisher_p` (significância). O leitor filtra por
`n_eventos ≥ MIN_EVENTS` e checa `fisher_p` antes de confiar num `lift` alto de amostra pequena.

## 7. Config (painel único)

`config.py` ganha:

```python
# Roster de indicadores a rodar no run_all (nomes dos módulos).
INDICATORS = ["mma", "mme", "obv", "vwap", "alto_volume",
              "exaustao_atr", "rsi", "macd", "donchian", "bollinger"]

# Grid de parâmetros por indicador (ajuste manual). persist só no mma.
PARAM_GRIDS = {
    "mma":          {"window": [10, 26, 50, 200], "tol": [0.0, 0.015, 0.03], "persist": [0, 4]},
    "mme":          {"window": [10, 26, 50, 200], "tol": [0.0, 0.015, 0.03]},
    "obv":          {"window": [20, 50]},
    "vwap":         {"window": [20, 50], "tol": [0.0, 0.015]},
    "alto_volume":  {"window": [20], "mult": [1.5, 2.0]},
    "exaustao_atr": {"atr_period": [14], "mult": [1.5, 2.0]},
    "rsi":          {"window": [14], "low": [30]},
    "macd":         {"fast": [12], "slow": [26], "sig": [9]},
    "donchian":     {"N": [20, 55]},
    "bollinger":    {"window": [20], "n_std": [2.0]},
}
```

Compartilhados continuam: `TICKER, PERIOD, HORIZONS, MIN_EVENTS, OUTPUT_DIR` (e `PERSISTENCES` do mma).

## 8. Testes (TDD)

Por módulo (espelhando `test_mma.py`):
- onset é **evento**, não estado (acende só na transição 0→1 do estado);
- não acende sem nova transição;
- limiar/tolerância suprime sinais fracos;
- janela > série → estado indefinível → **zero eventos** (sem quebrar);
- **1 teste específico** do indicador (ex.: `rsi` acende ao cruzar 30 p/ cima; `macd` ao cruzar o
  sinal; `donchian` ao fazer nova máxima de N dias; `exaustao_atr` só em dia de alta gigante).

Runner:
- `run_all` roda o registry, escreve um par de arquivos por indicador e o `summary_ALL`;
- o master concatena e vem **ordenado** pela chave de ranking por família.

Fixture:
- `synthetic_prices` tem `Volume` constante → obv/vwap/alto_volume/exaustao_atr não geram sinal útil.
  Adicionar **`synthetic_prices_volume`** (Volume determinístico e variável) para esses testes.

## 9. Riscos e itens em aberto

- **Duplicação da lógica de transição/persistência** entre 10 módulos (trade-off aceito pela escolha
  "um módulo por indicador"). Mitigação: testes idênticos por módulo pegam divergências.
- **Exaustão ATR / alto_volume** podem ter poucos eventos e/ou serem contrários — esperado; `MIN_EVENTS`
  e as guardas do ranking cobrem.
- **VWAP rolante vs cumulativo**: escolhido rolante; registrar caso se queira comparar no futuro.

## 10. Itens futuros (fora desta fase)

- Onset bearish (dimensão `direction`) e simetria.
- Persistência nos indicadores promissores.
- Combinação de sinais (2 gatilhos), multi-preditor + stepwise.
- Validação out-of-sample (walk-forward), painel multi-ticker.
