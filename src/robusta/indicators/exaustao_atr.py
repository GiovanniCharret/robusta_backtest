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
