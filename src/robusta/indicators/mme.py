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
