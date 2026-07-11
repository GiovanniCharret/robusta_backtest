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
      Fase 4: estado (OBV > média) em *_state e onset (transição 0→1, exigindo a
        média válida ontem — evita o onset fantasma no 1º dia útil do warm-up) em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset GENUÍNO + k dias no estado) em *_persist{k}.
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
    # Fase 4: onset = acima hoje, não-acima ontem, E a média era VÁLIDA ontem (o
    # não-acima de ontem foi observado, não um NaN do warm-up — evita o onset
    # fantasma no 1º dia válido).
    onset = state & ~state.shift(1, fill_value=False) & ma.notna().shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(window)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: persist acende só se state=1, a sequência tem exatamente k+1 dias E a
        # corrida começou com um onset GENUÍNO k dias atrás (âncora; mata o persist
        # fantasma do warm-up).
        df[signal_col(window, persist)] = (state & (streak == persist + 1) & onset.shift(persist, fill_value=False)).astype("Int8")
    # Saída: df enriquecido.
    return df
