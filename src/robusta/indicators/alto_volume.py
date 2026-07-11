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
      Fase 4: onset = transição 0→1, exigindo a média de volume válida ontem (evita
        o onset fantasma no 1º dia útil do warm-up), em *_signal.
      Fase 5: se persist>0, dummy de persistência (onset GENUÍNO + k dias no estado) em *_persist{k}.
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
    # Fase 4: onset = pico+alta hoje, não hoje ontem, E a média de volume era VÁLIDA
    # ontem (o "não" de ontem foi observado, não um NaN do warm-up — evita o onset
    # fantasma no 1º dia válido).
    onset = state & ~state.shift(1, fill_value=False) & vol_ma.notna().shift(1, fill_value=False)
    # Fase 4: grava o onset como Int8.
    df[signal_col(window, mult, tol)] = onset.astype("Int8")
    # Fase 5: persistência opcional (onset + k dias mantendo o estado, one-shot na confirmação).
    if persist:
        # Fase 5: streak = nº de dias consecutivos com o MESMO valor de state, terminando em t.
        streak = state.groupby((state != state.shift()).cumsum()).cumcount() + 1
        # Fase 5: persist acende só se state=1, a sequência tem exatamente k+1 dias E a
        # corrida começou com um onset GENUÍNO k dias atrás (âncora; mata o persist
        # fantasma do warm-up).
        df[signal_col(window, mult, tol, persist)] = (state & (streak == persist + 1) & onset.shift(persist, fill_value=False)).astype("Int8")
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
