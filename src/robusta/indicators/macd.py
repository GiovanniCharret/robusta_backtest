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
      Fase 4: estado (MACD > sinal) em *_state; onset (transição 0→1, exigindo a
        linha de sinal válida ontem — evita o onset fantasma no 1º dia útil do
        warm-up) em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset GENUÍNO + k dias no estado) em *_persist{k}.
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
    # Fase 4: onset = acima hoje, não-acima ontem, E a linha de sinal era VÁLIDA
    # ontem (o não-acima de ontem foi observado, não um NaN do warm-up — evita o
    # onset fantasma no 1º dia válido; a linha de sinal, mais tardia que a linha
    # MACD, domina o warm-up do estado).
    onset = state & ~state.shift(1, fill_value=False) & signal_line.notna().shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(fast, slow, sig)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: persist acende só se state=1, a sequência tem exatamente k+1 dias E a
        # corrida começou com um onset GENUÍNO k dias atrás (âncora; mata o persist
        # fantasma do warm-up).
        df[signal_col(fast, slow, sig, persist)] = (state & (streak == persist + 1) & onset.shift(persist, fill_value=False)).astype("Int8")
    # Saída: df enriquecido.
    return df
