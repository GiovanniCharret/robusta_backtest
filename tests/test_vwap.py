# pandas para o caso pequeno de robustez.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import vwap


# Teste: cria VWAP rolante, estado e onset.
def test_vwap_creates_columns(synthetic_prices_volume):
    """
    Por quê: VWAP rolante = Σ(Close·Vol)/Σ(Vol) na janela; o estado é Close acima do VWAP.

    Lógica: Entrada (preços+volume) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: janela 20, sem tolerância.
    out = vwap.add_columns(synthetic_prices_volume.copy(), window=20, tol=0.0)
    # Fase 2: valor e sinal presentes; 0/1; Int8; NAME.
    assert vwap.value_col(20) in out.columns
    scol = vwap.signal_col(20, 0.0)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and vwap.NAME == "vwap"


# Teste: onset = transição 0→1 do estado.
def test_vwap_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset só quando Close cruza o VWAP p/ cima.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1: janela 20.
    out = vwap.add_columns(synthetic_prices_volume.copy(), window=20, tol=0.0)
    # Fase 2: invariante, exigindo referência (o VWAP) válida ontem — o fim do
    # warm-up não conta como transição real (Task 16).
    state = out["vwap_w20_t0.0_state"]
    sig = out[vwap.signal_col(20, 0.0)]
    ref = out[vwap.value_col(20)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)
                   & ref.notna().shift(1, fill_value=False)).sum()
    assert int(sig.sum()) == int(transitions) and sig.sum() >= 1


# Teste: tolerância suprime cruzamentos marginais.
def test_vwap_tolerance_suppresses_marginal(synthetic_prices_volume):
    """
    Por quê: com tol maior, cruzamentos fracos do Close sobre o VWAP não contam.

    Lógica: Entrada → Fase 1 dois tol → Fase 2 loose ≤ strict → Saída.
    """
    # Fase 1: eventos sem tolerância e com 1,5%.
    strict = vwap.add_columns(synthetic_prices_volume.copy(), window=20, tol=0.0)[vwap.signal_col(20, 0.0)].sum()
    loose = vwap.add_columns(synthetic_prices_volume.copy(), window=20, tol=0.015)[vwap.signal_col(20, 0.015)].sum()
    # Fase 2/Saída.
    assert loose <= strict


# Teste: janela > série → VWAP NaN → zero eventos.
def test_vwap_window_larger_than_series_zero_events():
    """
    Por quê: janela grande num df curto → Σ rolante NaN → sem evento.

    Lógica: Entrada (3 dias, window=50) → Fase 1 add_columns → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0], "Volume": [100, 200, 300]})
    # Fase 1: janela 50.
    out = vwap.add_columns(df.copy(), window=50, tol=0.0)
    # Fase 2/Saída: zero eventos.
    assert int(out[vwap.signal_col(50, 0.0)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_vwap_persist_fires_once_at_confirmation():
    """
    Por quê: é o caso motivador do persist — fechar acima do vwap E os k dias
    seguintes persistirem acima é sinal diferente de fechar acima e devolver no
    dia seguinte. One-shot na confirmação, sem vazamento.

    Lógica: Entrada (parado, depois sobe firme) → Fase 1 add_columns(persist=2) →
    Fase 2 confirmação 2 dias após o onset, estado ligado no intervalo → Saída.
    """
    # Entrada: 5 dias parado (Close = vwap) e depois sobe firme (fica acima do vwap).
    df = pd.DataFrame({"Close": [10, 10, 10, 10, 10, 11, 12, 13, 14, 15],
                       "Volume": [100] * 10})
    # Fase 1: janela 3, persist=2.
    out = vwap.add_columns(df.copy(), window=3, tol=0.0, persist=2)
    # Fase 2: colunas de onset, estado e persistência.
    onset = out[vwap.signal_col(3, 0.0)]
    state = out["vwap_w3_t0.0_state"]
    p = out[vwap.signal_col(3, 0.0, persist=2)]
    # Fase 2: há ao menos uma confirmação; dtype Int8.
    idxs = [i for i in range(len(out)) if int(p.iloc[i]) == 1]
    assert len(idxs) >= 1 and str(p.dtype) == "Int8"
    # Fase 2/Saída: cada confirmação está 2 dias após um onset, com o estado ligado no meio.
    for i in idxs:
        assert int(onset.iloc[i - 2]) == 1
        assert all(int(state.iloc[j]) == 1 for j in range(i - 2, i + 1))


# Task 16 (review final da Fase 3): onset fantasma no 1º dia válido do warm-up.
def test_vwap_no_phantom_onset_at_warmup():
    """
    Por quê: no 1º dia em que o VWAP fica calculável (fim do warm-up de NaN), se o
    Close já está acima dele, o onset antigo disparava — o "abaixo de ontem" usado
    na comparação era um NaN coerido para False, não uma observação real. Este teste
    prova que uma série que já nasce "acima" desde o 1º dia válido NÃO gera onset
    nem persistência fantasma.

    Lógica: Entrada (Close sobe 1 ponto por dia, volume constante → o VWAP rolante
    de 3 dias fica sempre abaixo do Close do dia) → Fase 1 add_columns(window=3,
    tol=0.0, persist=2) → Fase 2 confirma que o cenário é real (estado já True no
    1º dia válido, idx2) → Fase 3 nem o onset nem a persistência disparam → Saída.
    """
    # Entrada: Close sobe 1 ponto por dia, volume constante.
    df = pd.DataFrame({"Close": [10, 11, 12, 13, 14, 15], "Volume": [100] * 6})
    # Fase 1: janela 3, tol=0.0, persist=2 (confirmaria 2 dias após o onset).
    out = vwap.add_columns(df.copy(), window=3, tol=0.0, persist=2)
    # Fase 2: 1º dia válido do VWAP é idx2 (min_periods=3); estado já True ali
    # (Close=12 > vwap3=11) — confirma que o cenário é real.
    state = out["vwap_w3_t0.0_state"]
    assert int(state.iloc[2]) == 1
    # Fase 3: nem o onset nem a persistência podem disparar — não há transição
    # genuína, só o fim do warm-up.
    assert int(out[vwap.signal_col(3, 0.0)].sum()) == 0
    # Saída: a persistência (ancorada num onset genuíno) também fica silenciosa.
    assert int(out[vwap.signal_col(3, 0.0, persist=2)].sum()) == 0
