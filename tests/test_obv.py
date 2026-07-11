# pandas para construir Close/Volume determinísticos.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import obv


# Teste: cria OBV, sua média, estado e onset.
def test_obv_creates_columns(synthetic_prices_volume):
    """
    Por quê: o obv acumula volume sinalizado e compara com a própria média; precisa
    acrescentar as colunas canônicas ao df-fundação.

    Lógica: Entrada (preços+volume) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: janela 20 sobre a fixture de volume.
    out = obv.add_columns(synthetic_prices_volume.copy(), window=20)
    # Fase 2: valor e sinal presentes; dummy 0/1; Int8; NAME certo.
    assert obv.value_col(20) in out.columns
    scol = obv.signal_col(20)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and obv.NAME == "obv"


# Teste: onset = transição 0→1 do estado (OBV cruza sua média p/ cima).
def test_obv_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset deve acender só quando OBV passa de abaixo para acima da média.

    Lógica: Entrada (preços+volume) → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1: janela 20.
    out = obv.add_columns(synthetic_prices_volume.copy(), window=20)
    # Fase 2: invariante evento == transições.
    state = out["obv_w20_state"]
    sig = out[obv.signal_col(20)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions) and sig.sum() >= 1


# Teste: OBV sobe em dias de alta e cai em dias de baixa (sinal do fluxo).
def test_obv_direction_follows_close():
    """
    Por quê: OBV soma volume quando Close sobe e subtrai quando cai; provamos essa
    definição num caso pequeno e controlado.

    Lógica: Entrada (2 altas, 1 baixa) → Fase 1 add_columns → Fase 2 OBV monotônico → Saída.
    """
    # Entrada: Close sobe, sobe, cai; volume constante 100.
    df = pd.DataFrame({"Close": [10, 11, 12, 11], "Volume": [100, 100, 100, 100],
                       "Open": [10, 10, 11, 12], "High": [10, 11, 12, 12], "Low": [10, 10, 11, 11]})
    # Fase 1: janela 2.
    out = obv.add_columns(df.copy(), window=2)
    # Fase 2: OBV = [0, +100, +200, +100] (sobe nos dias de alta, cai no de baixa).
    assert out["obv"].tolist() == [0.0, 100.0, 200.0, 100.0]


# Teste: janela > série → média do OBV NaN → zero eventos.
def test_obv_window_larger_than_series_zero_events():
    """
    Por quê: o grid usa window=50; num df curto a média do OBV é NaN e a dummy não acende.

    Lógica: Entrada (3 dias, window=50) → Fase 1 add_columns → Fase 2 zero eventos → Saída.
    """
    # Entrada: série curta, janela grande.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0], "Volume": [100, 100, 100],
                       "Open": [10, 10, 11], "High": [10, 11, 12], "Low": [10, 10, 11]})
    # Fase 1: janela 50 sobre 3 linhas.
    out = obv.add_columns(df.copy(), window=50)
    # Fase 2/Saída: nenhum evento.
    assert int(out[obv.signal_col(50)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_obv_persist_fires_once_at_confirmation():
    """
    Por quê: persist generaliza o padrão do mma para o estado do obv — onset (OBV
    cruza a média p/ cima) confirmado por k dias mantendo-se acima; one-shot.

    Lógica: Entrada (OBV cai e sobe firme) → Fase 1 add_columns(persist=2) → Fase 2
    confirmação 2 dias após o onset, estado ligado no intervalo → Saída.
    """
    # Entrada: Close cai 3 dias e sobe 8 (volume constante → OBV espelha o Close).
    df = pd.DataFrame({"Close": [10, 9, 8, 7, 8, 9, 10, 11, 12, 13, 14, 15],
                       "Volume": [100] * 12})
    # Fase 1: janela 3, persist=2.
    out = obv.add_columns(df.copy(), window=3, persist=2)
    # Fase 2: colunas de onset, estado e persistência.
    onset = out[obv.signal_col(3)]
    state = out["obv_w3_state"]
    p = out[obv.signal_col(3, persist=2)]
    # Fase 2: há ao menos uma confirmação; dtype Int8.
    idxs = [i for i in range(len(out)) if int(p.iloc[i]) == 1]
    assert len(idxs) >= 1 and str(p.dtype) == "Int8"
    # Fase 2/Saída: cada confirmação está 2 dias após um onset, com o estado ligado no meio.
    for i in idxs:
        assert int(onset.iloc[i - 2]) == 1
        assert all(int(state.iloc[j]) == 1 for j in range(i - 2, i + 1))
