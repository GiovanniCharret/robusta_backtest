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
    # Fase 2: invariante.
    state = out["bollinger_w20_s2.0_state"]
    sig = out[bb.signal_col(20, 2.0)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
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

    Lógica: Entrada (19 dias parado + salto mantido) → Fase 1 add_columns(persist=2)
    → Fase 2 onset no idx19; estado dura idx19–21 → confirmação única no idx21 → Saída.
    """
    # Entrada: 19 dias parado em 10 e salto para 20 mantido (a banda alarga aos poucos).
    df = pd.DataFrame({"Close": [10.0] * 19 + [20.0] * 5})
    # Fase 1: janela 20, 2 desvios, persist=2.
    out = bb.add_columns(df.copy(), window=20, n_std=2.0, persist=2)
    # Fase 2: onset no idx19 (1º dia acima da banda superior).
    onset = out[bb.signal_col(20, 2.0)]
    assert int(onset.iloc[19]) == 1
    # Fase 2: estado dura 3 dias (idx19–21; no idx22 a banda já engoliu o salto).
    p = out[bb.signal_col(20, 2.0, persist=2)]
    # Fase 2/Saída: uma única confirmação, no idx21, dtype Int8.
    assert int(p.sum()) == 1 and int(p.iloc[21]) == 1 and str(p.dtype) == "Int8"
