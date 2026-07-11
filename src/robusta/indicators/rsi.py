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
      Fase 4: estado (RSI ≥ low) em *_state; onset (transição 0→1, exigindo o RSI
        válido ontem — evita o onset fantasma no 1º dia útil do warm-up) em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset GENUÍNO + k dias no estado) em *_persist{k}.
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
    # Fase 4: onset = cruza `low` p/ cima hoje, não hoje ontem, E o RSI era VÁLIDO
    # ontem (o não-acima de ontem foi observado, não um NaN do warm-up — evita o
    # onset fantasma no 1º dia válido).
    onset = state & ~state.shift(1, fill_value=False) & rsi_series.notna().shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(window, low)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: persist acende só se state=1, a sequência tem exatamente k+1 dias E a
        # corrida começou com um onset GENUÍNO k dias atrás (âncora; mata o persist
        # fantasma do warm-up).
        df[signal_col(window, low, persist)] = (state & (streak == persist + 1) & onset.shift(persist, fill_value=False)).astype("Int8")
    # Saída: df enriquecido.
    return df
