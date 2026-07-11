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
