# numpy para a rampa de preços.
import numpy as np
# pandas para o DataFrame.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import macd


# Fixture local: cai e depois sobe (MACD cruza a linha de sinal p/ cima).
def _down_then_up():
    # Fase 1: 45 dias caindo + 45 subindo (queda longa esgota o warm-up da linha
    # de sinal antes do cruzamento real do MACD, que só ocorre na rampa de subida).
    close = np.concatenate([np.linspace(100, 55, 45), np.linspace(55, 125, 45)])
    # Saída: DataFrame só com Close.
    return pd.DataFrame({"Close": close})


# Teste: cria MACD, linha de sinal, estado e onset.
def test_macd_creates_columns():
    """
    Por quê: estado = MACD > linha de sinal; onset = cruzamento p/ cima.

    Lógica: Entrada (down-then-up) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: 12/26/9.
    out = macd.add_columns(_down_then_up(), fast=12, slow=26, sig=9)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert macd.value_col(12, 26) in out.columns
    scol = macd.signal_col(12, 26, 9)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and macd.NAME == "macd"


# Teste: onset = transição 0→1 do estado.
def test_macd_signal_equals_state_transitions():
    """
    Por quê: onset só quando o MACD passa de ≤ para > a linha de sinal.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1.
    out = macd.add_columns(_down_then_up(), fast=12, slow=26, sig=9)
    # Fase 2: invariante.
    state = out["macd_12_26_9_state"]
    sig = out[macd.signal_col(12, 26, 9)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: cada onset é um cruzamento MACD > sinal (antes ≤).
def test_macd_onset_is_upward_cross_of_signal():
    """
    Por quê: o gatilho é o MACD cruzar a linha de sinal p/ cima — provar em cada onset.

    Lógica: Entrada (down-then-up) → Fase 1 add_columns → Fase 2 checa cada onset → Saída.
    """
    # Fase 1.
    out = macd.add_columns(_down_then_up(), fast=12, slow=26, sig=9)
    m = out[macd.value_col(12, 26)]
    line = out["macd_12_26_9_line"]
    sig = out[macd.signal_col(12, 26, 9)]
    # Fase 2: há ao menos um onset e, em cada um, MACD sobe através do sinal.
    idxs = [i for i in range(1, len(out)) if int(sig.iloc[i]) == 1]
    assert len(idxs) >= 1
    for i in idxs:
        assert m.iloc[i] > line.iloc[i] and m.iloc[i - 1] <= line.iloc[i - 1]


# Teste: série curtíssima não quebra e dá dummy 0/1 (slow > série → sem valor → 0).
def test_macd_short_series_zero_events():
    """
    Por quê: com min_periods=slow, uma série menor que `slow` deixa o MACD NaN → sem evento.

    Lógica: Entrada (5 dias, slow=26) → Fase 1 → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 11.0, 13.0]})
    # Fase 1: 12/26/9.
    out = macd.add_columns(df.copy(), fast=12, slow=26, sig=9)
    # Fase 2/Saída: zero eventos.
    assert int(out[macd.signal_col(12, 26, 9)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_macd_persist_fires_once_at_confirmation():
    """
    Por quê: persist confirma que o cruzamento do MACD durou — MACD acima da linha
    de sinal por mais k dias. One-shot na confirmação, sem vazamento.

    Lógica: Entrada (down-then-up) → Fase 1 add_columns(persist=2) → Fase 2 cada
    confirmação está 2 dias após um onset, com estado ligado no intervalo → Saída.
    """
    # Fase 1: 12/26/9, persist=2 (rally sustentado mantém MACD acima do sinal).
    out = macd.add_columns(_down_then_up(), fast=12, slow=26, sig=9, persist=2)
    # Fase 2: colunas de onset, estado e persistência.
    onset = out[macd.signal_col(12, 26, 9)]
    state = out["macd_12_26_9_state"]
    p = out[macd.signal_col(12, 26, 9, persist=2)]
    # Fase 2: há ao menos uma confirmação; dtype Int8.
    idxs = [i for i in range(len(out)) if int(p.iloc[i]) == 1]
    assert len(idxs) >= 1 and str(p.dtype) == "Int8"
    # Fase 2/Saída: cada confirmação está 2 dias após um onset, com o estado ligado no meio.
    for i in idxs:
        assert int(onset.iloc[i - 2]) == 1
        assert all(int(state.iloc[j]) == 1 for j in range(i - 2, i + 1))
