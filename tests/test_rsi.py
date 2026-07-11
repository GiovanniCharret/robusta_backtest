# numpy para montar a rampa de preços.
import numpy as np
# pandas para o DataFrame.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import rsi


# Fixture local: cai forte e depois sobe forte (RSI mergulha < 30 e volta > 30).
def _dip_then_rally():
    # Fase 1: 20 dias caindo (RSI vai a <30) + 20 dias subindo (RSI volta a >30).
    down = np.linspace(100, 60, 20)
    up = np.linspace(60, 110, 20)
    close = np.concatenate([down, up])
    # Saída: DataFrame só com Close (RSI usa só Close).
    return pd.DataFrame({"Close": close})


# Teste: cria RSI, estado e onset.
def test_rsi_creates_columns():
    """
    Por quê: estado = RSI ≥ low (não-sobrevendido); onset = cruzar low p/ cima.

    Lógica: Entrada (dip-then-rally) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: janela 14, low 30.
    out = rsi.add_columns(_dip_then_rally(), window=14, low=30)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert rsi.value_col(14) in out.columns
    scol = rsi.signal_col(14, 30)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and rsi.NAME == "rsi"


# Teste: onset = transição 0→1 do estado.
def test_rsi_signal_equals_state_transitions():
    """
    Por quê: onset só quando o RSI passa de sobrevendido a não-sobrevendido.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1.
    out = rsi.add_columns(_dip_then_rally(), window=14, low=30)
    # Fase 2: invariante.
    state = out["rsi_w14_low30_state"]
    sig = out[rsi.signal_col(14, 30)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: cada onset é um CRUZAMENTO do low p/ cima (RSI ontem < low, hoje ≥ low).
def test_rsi_onset_is_upward_cross_of_low():
    """
    Por quê: o gatilho é a saída do sobrevendido — precisa provar que todo onset
    ocorre onde o RSI cruza `low` de baixo p/ cima.

    Lógica: Entrada (dip-then-rally) → Fase 1 add_columns → Fase 2 checa cada onset → Saída.
    """
    # Fase 1: janela 14, low 30.
    out = rsi.add_columns(_dip_then_rally(), window=14, low=30)
    r = out[rsi.value_col(14)]
    sig = out[rsi.signal_col(14, 30)]
    # Fase 2: houve ao menos um onset...
    idxs = [i for i in range(1, len(out)) if int(sig.iloc[i]) == 1]
    assert len(idxs) >= 1
    # Fase 2/Saída: em cada onset, RSI ontem < 30 e RSI hoje ≥ 30.
    for i in idxs:
        assert r.iloc[i - 1] < 30 and r.iloc[i] >= 30


# Teste: janela > série → RSI NaN → zero eventos.
def test_rsi_window_larger_than_series_zero_events():
    """
    Por quê: janela grande num df curto → RSI NaN (min_periods) → sem evento.

    Lógica: Entrada (5 dias, window=14) → Fase 1 → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"Close": [10.0, 11.0, 10.0, 12.0, 11.0]})
    # Fase 1: janela 14.
    out = rsi.add_columns(df.copy(), window=14, low=30)
    # Fase 2/Saída: zero eventos.
    assert int(out[rsi.signal_col(14, 30)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_rsi_persist_fires_once_at_confirmation():
    """
    Por quê: persist confirma que a saída do sobrevendido durou — RSI cruzou 30 p/
    cima e permaneceu ≥ 30 por mais k dias. One-shot na confirmação, sem vazamento.

    Lógica: Entrada (dip-then-rally) → Fase 1 add_columns(persist=2) → Fase 2 cada
    confirmação está 2 dias após um onset, com estado ligado no intervalo → Saída.
    """
    # Fase 1: janela 14, low 30, persist=2 (rally sustentado mantém o RSI subindo).
    out = rsi.add_columns(_dip_then_rally(), window=14, low=30, persist=2)
    # Fase 2: colunas de onset, estado e persistência.
    onset = out[rsi.signal_col(14, 30)]
    state = out["rsi_w14_low30_state"]
    p = out[rsi.signal_col(14, 30, persist=2)]
    # Fase 2: há ao menos uma confirmação; dtype Int8.
    idxs = [i for i in range(len(out)) if int(p.iloc[i]) == 1]
    assert len(idxs) >= 1 and str(p.dtype) == "Int8"
    # Fase 2/Saída: cada confirmação está 2 dias após um onset, com o estado ligado no meio.
    for i in idxs:
        assert int(onset.iloc[i - 2]) == 1
        assert all(int(state.iloc[j]) == 1 for j in range(i - 2, i + 1))
