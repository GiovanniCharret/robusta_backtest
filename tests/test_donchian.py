# pandas para casos pequenos controlados.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import donchian as dc


# Teste: cria a máxima de N dias, estado e onset.
def test_dc_creates_columns(synthetic_prices_volume):
    """
    Por quê: estado = Close acima da máxima dos N dias ANTERIORES; onset = nova máxima.

    Lógica: Entrada (preços) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: N=20.
    out = dc.add_columns(synthetic_prices_volume.copy(), N=20)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert dc.value_col(20) in out.columns
    scol = dc.signal_col(20)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and dc.NAME == "donchian"


# Teste: onset = transição 0→1 do estado.
def test_dc_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset acende no 1º dia acima do canal (nova máxima), não em cada dia acima.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1.
    out = dc.add_columns(synthetic_prices_volume.copy(), N=20)
    # Fase 2: invariante, exigindo referência (o teto do canal) válida ontem — o
    # fim do warm-up não conta como transição real (Task 16).
    state = out["donchian_N20_state"]
    sig = out[dc.signal_col(20)]
    ref = out[dc.value_col(20)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)
                   & ref.notna().shift(1, fill_value=False)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: acende exatamente quando o Close supera a máxima dos N dias anteriores.
def test_dc_fires_on_new_n_day_high():
    """
    Por quê: provar a definição do canal — o Close rompe a máxima de N=3 dias num
    índice conhecido.

    Lógica: Entrada (platô e depois um novo topo) → Fase 1 add_columns → Fase 2 → Saída.
    """
    # Entrada: High/Close estáveis em 10 e um salto para 12 no idx5.
    df = pd.DataFrame({
        "High":  [10, 10, 10, 10, 10, 12],
        "Close": [10, 10, 10, 10, 10, 12],
    })
    # Fase 1: N=3 (máxima dos 3 dias anteriores).
    out = dc.add_columns(df.copy(), N=3)
    # Fase 2/Saída: acende só no idx5 (novo topo acima da máxima anterior = 10).
    sig = out[dc.signal_col(3)]
    assert int(sig.sum()) == 1 and int(sig.iloc[5]) == 1


# Teste: janela > série → máxima NaN → zero eventos.
def test_dc_window_larger_than_series_zero_events():
    """
    Por quê: N grande num df curto → rolling max NaN → sem evento.

    Lógica: Entrada (3 dias, N=55) → Fase 1 → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"High": [10.0, 11.0, 12.0], "Close": [10.0, 11.0, 12.0]})
    # Fase 1: N=55.
    out = dc.add_columns(df.copy(), N=55)
    # Fase 2/Saída: zero eventos.
    assert int(out[dc.signal_col(55)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_dc_persist_fires_once_at_confirmation():
    """
    Por quê: persist confirma que o rompimento do canal durou — novas máximas por
    mais k dias seguidos. One-shot na confirmação, sem vazamento.

    Lógica: Entrada (platô, depois novas máximas todo dia) → Fase 1 add_columns(persist=2)
    → Fase 2 onset no idx4, estado segue ligado → confirmação única no idx6 → Saída.
    """
    # Entrada: platô de 4 dias (Task 16: precisa de 1 dia a mais que a versão
    # original — o teto só fica válido no idx3, e ali o Close ainda está no platô,
    # dando um "não-acima" REAL observado; sem esse dia extra o onset do idx3 seria
    # o artefato fantasma do 1º dia de warm-up, hoje suprimido) e depois novas
    # máximas todo dia (estado permanece ligado).
    df = pd.DataFrame({
        "High":  [10, 10, 10, 10, 11, 12, 13, 14, 15],
        "Close": [10, 10, 10, 10, 11, 12, 13, 14, 15],
    })
    # Fase 1: N=3, persist=2.
    out = dc.add_columns(df.copy(), N=3, persist=2)
    # Fase 2: teto válido desde o idx3 (10, com Close=10 → estado False real); onset
    # genuíno no idx4 (rompe o teto=10); streak=3 no idx6 → confirmação única.
    p = out[dc.signal_col(3, persist=2)]
    # Fase 2/Saída: uma única confirmação, no idx6, dtype Int8.
    assert int(p.sum()) == 1 and int(p.iloc[6]) == 1 and str(p.dtype) == "Int8"


# Task 16 (review final da Fase 3): onset fantasma no 1º dia válido do warm-up.
def test_dc_no_phantom_onset_at_warmup():
    """
    Por quê: no 1º dia em que o teto do canal fica calculável (fim do warm-up de
    NaN), se o Close já está acima dele, o onset antigo disparava — o "abaixo de
    ontem" usado na comparação era um NaN coerido para False, não uma observação
    real. Este teste prova que uma série sempre subindo (Close rompe o teto já no
    1º dia válido) NÃO gera onset nem persistência fantasma.

    Lógica: Entrada (High=Close sempre subindo) → Fase 1 add_columns(N=3, persist=2)
    → Fase 2 confirma que o cenário é real (estado já True no 1º dia válido, idx3)
    → Fase 3 nem o onset nem a persistência disparam (nenhuma transição genuína) →
    Saída.
    """
    # Entrada: High=Close sobem 1 ponto por dia.
    df = pd.DataFrame({"High": [10, 11, 12, 13, 14, 15], "Close": [10, 11, 12, 13, 14, 15]})
    # Fase 1: N=3, persist=2 (confirmaria 2 dias após o onset).
    out = dc.add_columns(df.copy(), N=3, persist=2)
    # Fase 2: 1º dia válido do teto é idx3 (rolling(3).max().shift(1) → min_periods=3
    # mais 1 dia do shift); estado já True ali (Close=13 > teto=12) — confirma que o
    # cenário é real.
    state = out["donchian_N3_state"]
    assert int(state.iloc[3]) == 1
    # Fase 3: nem o onset nem a persistência podem disparar — não há transição
    # genuína, só o fim do warm-up.
    assert int(out[dc.signal_col(3)].sum()) == 0
    # Saída: a persistência (ancorada num onset genuíno) também fica silenciosa.
    assert int(out[dc.signal_col(3, persist=2)].sum()) == 0
