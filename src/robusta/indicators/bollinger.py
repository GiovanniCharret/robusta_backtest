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
