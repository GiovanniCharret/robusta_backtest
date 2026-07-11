# pandas para casos pequenos controlados.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import bollinger as bb


# Teste: cria banda média, banda superior, estado e onset.
def test_bb_creates_columns(synthetic_prices_volume):
    """
    Por quê: estado = Close acima da banda superior (mid + n_std·σ); onset = rompimento.

    Lógica: Entrada (preços) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: janela 20, 2 desvios.
    out = bb.add_columns(synthetic_prices_volume.copy(), window=20, n_std=2.0)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert bb.value_col(20) in out.columns
    scol = bb.signal_col(20, 2.0)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and bb.NAME == "bollinger"


# Teste: onset = transição 0→1 do estado.
def test_bb_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset acende no 1º dia acima da banda, não em cada dia acima.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1.
    out = bb.add_columns(synthetic_prices_volume.copy(), window=20, n_std=2.0)
    # Fase 2: invariante, exigindo referência (a banda superior) válida ontem — o
    # fim do warm-up não conta como transição real (Task 16).
    state = out["bollinger_w20_s2.0_state"]
    sig = out[bb.signal_col(20, 2.0)]
    ref = out["boll_upper_w20_s2.0"]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)
                   & ref.notna().shift(1, fill_value=False)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: um salto de preço acima da banda acende; n_std maior exige salto maior (≤ eventos).
def test_bb_wider_band_suppresses(synthetic_prices_volume):
    """
    Por quê: bandas mais largas (n_std maior) são mais difíceis de romper → menos ou
    igual nº de onsets.

    Lógica: Entrada → Fase 1 dois n_std → Fase 2 wide ≤ narrow → Saída.
    """
    # Fase 1: eventos com 2 e com 3 desvios.
    narrow = bb.add_columns(synthetic_prices_volume.copy(), window=20, n_std=2.0)[bb.signal_col(20, 2.0)].sum()
    wide = bb.add_columns(synthetic_prices_volume.copy(), window=20, n_std=3.0)[bb.signal_col(20, 3.0)].sum()
    # Fase 2/Saída.
    assert wide <= narrow


# Teste: janela > série → banda NaN → zero eventos.
def test_bb_window_larger_than_series_zero_events():
    """
    Por quê: janela grande num df curto → média/σ NaN → banda NaN → sem evento.

    Lógica: Entrada (3 dias, window=20) → Fase 1 → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0]})
    # Fase 1: janela 20.
    out = bb.add_columns(df.copy(), window=20, n_std=2.0)
    # Fase 2/Saída: zero eventos.
    assert int(out[bb.signal_col(20, 2.0)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_bb_persist_fires_once_at_confirmation():
    """
    Por quê: persist confirma que o rompimento da banda durou k dias — a banda
    alarga aos poucos após um salto, então o estado dura alguns dias e desliga.
    One-shot na confirmação, sem vazamento.

    Lógica: Entrada (20 dias parado + salto mantido) → Fase 1 add_columns(persist=2)
    → Fase 2 onset no idx20; estado dura idx20–22 → confirmação única no idx22 → Saída.
    """
    # Entrada: 20 dias parado em 10 (Task 16: precisa de 1 dia a mais que a versão
    # original — a banda só fica válida no idx19, e ali o Close ainda está no
    # platô, dando um "não-acima" REAL observado; sem esse dia extra o onset do
    # idx19 seria o artefato fantasma do 1º dia de warm-up, hoje suprimido) e
    # salto para 20 mantido (a banda alarga aos poucos).
    df = pd.DataFrame({"Close": [10.0] * 20 + [20.0] * 5})
    # Fase 1: janela 20, 2 desvios, persist=2.
    out = bb.add_columns(df.copy(), window=20, n_std=2.0, persist=2)
    # Fase 2: banda válida desde o idx19 (Close=10 → estado False real); onset
    # genuíno no idx20 (1º dia acima da banda superior).
    onset = out[bb.signal_col(20, 2.0)]
    assert int(onset.iloc[20]) == 1
    # Fase 2: estado dura 3 dias (idx20–22; no idx23 a banda já engoliu o salto).
    p = out[bb.signal_col(20, 2.0, persist=2)]
    # Fase 2/Saída: uma única confirmação, no idx22, dtype Int8.
    assert int(p.sum()) == 1 and int(p.iloc[22]) == 1 and str(p.dtype) == "Int8"


# Task 16 (review final da Fase 3): onset fantasma no 1º dia válido do warm-up.
def test_bb_no_phantom_onset_at_warmup():
    """
    Por quê: no 1º dia em que a banda superior fica calculável (fim do warm-up de
    NaN), se o Close já está acima dela, o onset antigo disparava — o "abaixo de
    ontem" usado na comparação era um NaN coerido para False, não uma observação
    real. Este teste prova que uma série que dobra a cada dia (Close já rompe a
    banda desde o 1º dia válido e permanece acima) NÃO gera onset nem persistência
    fantasma. Usa n_std=1.0 (com n_std=2.0 e janela 3 é matematicamente impossível
    o 3º ponto exceder a banda — o máximo de 3 pontos fica a ≤1,155σ da média).

    Lógica: Entrada (Close dobra a cada dia) → Fase 1 add_columns(window=3,
    n_std=1.0, persist=2) → Fase 2 confirma que o cenário é real (estado já True no
    1º dia válido, idx2) → Fase 3 nem o onset nem a persistência disparam (nenhuma
    transição genuína) → Saída.
    """
    # Entrada: Close dobra a cada dia.
    df = pd.DataFrame({"Close": [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]})
    # Fase 1: janela 3, n_std=1.0, persist=2 (confirmaria 2 dias após o onset).
    out = bb.add_columns(df.copy(), window=3, n_std=1.0, persist=2)
    # Fase 2: 1º dia válido da banda superior é idx2 (min_periods=3); estado já
    # True ali (Close=4 > banda≈3,86 = média 2,33 + 1·σ 1,53) — confirma que o
    # cenário é real.
    state = out["bollinger_w3_s1.0_state"]
    assert int(state.iloc[2]) == 1
    # Fase 3: nem o onset nem a persistência podem disparar — não há transição
    # genuína, só o fim do warm-up.
    assert int(out[bb.signal_col(3, 1.0)].sum()) == 0
    # Saída: a persistência (ancorada num onset genuíno) também fica silenciosa.
    assert int(out[bb.signal_col(3, 1.0, persist=2)].sum()) == 0
