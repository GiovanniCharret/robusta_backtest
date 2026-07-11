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
      Fase 4: onset (transição 0→1, exigindo o VWAP válido ontem — evita o onset
        fantasma no 1º dia útil do warm-up) em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset GENUÍNO + k dias no estado) em *_persist{k}.
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
    # Fase 4: onset = acima hoje, não-acima ontem, E o VWAP era VÁLIDO ontem (o
    # não-acima de ontem foi observado, não um NaN do warm-up — evita o onset
    # fantasma no 1º dia válido).
    onset = state & ~state.shift(1, fill_value=False) & vwap_series.notna().shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(window, tol)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: persist acende só se state=1, a sequência tem exatamente k+1 dias E a
        # corrida começou com um onset GENUÍNO k dias atrás (âncora; mata o persist
        # fantasma do warm-up).
        df[signal_col(window, tol, persist)] = (state & (streak == persist + 1) & onset.shift(persist, fill_value=False)).astype("Int8")
    # Saída: df enriquecido.
    return df
