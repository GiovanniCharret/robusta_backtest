# pandas para construir Closes com cruzamento conhecido.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import mme


# Teste: add_columns cria valor, estado e onset (evento 0/1).
def test_mme_creates_value_state_signal():
    """
    Por quê: o mme é plug-in; precisa acrescentar valor (EMA), estado (acima da
    banda) e a dummy de onset, com nomes canônicos que o sweep acha.

    Lógica: Entrada (Close em V) → Fase 1 add_columns → Fase 2 colunas → Fase 3 evento → Saída.
    """
    # Entrada: cai e volta a subir, cruzando a EMA curta.
    df = pd.DataFrame({"Close": [10, 9, 8, 7, 9, 11, 13, 14, 15, 16]})
    # Fase 1: EMA janela 3, sem tolerância.
    out = mme.add_columns(df.copy(), window=3, tol=0.0)
    # Fase 2: valor e sinal presentes.
    assert mme.value_col(3) in out.columns
    scol = mme.signal_col(3, 0.0)
    assert scol in out.columns
    # Fase 3: dummy é evento 0/1 e acende ao menos uma vez; dtype Int8; NAME certo.
    assert set(out[scol].dropna().unique()) <= {0, 1} and out[scol].sum() >= 1
    assert str(out[scol].dtype) == "Int8" and mme.NAME == "mme"


# Teste: onset é a transição 0→1 do estado (não o estado inteiro).
def test_mme_signal_equals_state_transitions():
    """
    Por quê: onset deve acender só no 1º dia da sequência bullish.

    Lógica: Entrada (sobe e fica acima) → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Entrada: cruza e permanece acima.
    df = pd.DataFrame({"Close": [10, 9, 8, 9, 12, 14, 16, 18, 20]})
    # Fase 1: EMA janela 3.
    out = mme.add_columns(df.copy(), window=3, tol=0.0)
    # Fase 2: sum(signal) == nº de transições 0→1 do estado.
    state = out[f"mme_w3_t0.0_state"]
    sig = out[mme.signal_col(3, 0.0)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: tolerância suprime cruzamentos marginais.
def test_mme_tolerance_suppresses_marginal():
    """
    Por quê: com tol alto, um cruzamento fraco não acende a dummy.

    Lógica: Entrada (cruzamento marginal) → Fase 1 dois tol → Fase 2 compara → Saída.
    """
    # Entrada: Close que sobe por margem pequena.
    df = pd.DataFrame({"Close": [10, 10, 10, 10, 10.05, 10.06, 10.07, 10.08]})
    # Fase 1: conta eventos sem tolerância e com 3%.
    strict = mme.add_columns(df.copy(), window=3, tol=0.0)[mme.signal_col(3, 0.0)].sum()
    loose = mme.add_columns(df.copy(), window=3, tol=0.03)[mme.signal_col(3, 0.03)].sum()
    # Fase 2/Saída: a tolerância reduz (ou iguala).
    assert loose <= strict


# Teste: janela > série → EMA indefinida → zero eventos.
def test_mme_window_larger_than_series_zero_events():
    """
    Por quê: o grid usa window=200; num df curto a EMA é NaN (min_periods) e a dummy
    não pode acender nem quebrar.

    Lógica: Entrada (4 closes, window=200) → Fase 1 add_columns → Fase 2 zero eventos → Saída.
    """
    # Entrada: série curta, janela enorme.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 13.0]})
    # Fase 1: EMA janela 200 sobre 4 linhas.
    out = mme.add_columns(df.copy(), window=200, tol=0.0)
    # Fase 2/Saída: nenhum evento.
    assert int(out[mme.signal_col(200, 0.0)].sum()) == 0


# Teste: persist_k acende UMA vez, k dias após o onset, com o estado ligado no meio.
def test_mme_persist_fires_once_at_confirmation():
    """
    Por quê: persist generaliza o padrão do mma — onset confirmado por k dias
    mantendo o estado; carimbado one-shot no dia da confirmação, sem vazamento.

    Lógica: Entrada (cruza a EMA e fica acima) → Fase 1 add_columns(persist=2) →
    Fase 2 cada confirmação está 2 dias após um onset, com estado ligado no meio → Saída.
    """
    # Entrada: cai e depois sobe firme, cruzando a EMA3 e permanecendo acima.
    df = pd.DataFrame({"Close": [10, 9, 8, 7, 9, 11, 13, 15, 17, 19, 21]})
    # Fase 1: persist=2 (onset + 2 dias mantendo o estado).
    out = mme.add_columns(df.copy(), window=3, tol=0.0, persist=2)
    # Fase 2: colunas de onset, estado e persistência.
    onset = out[mme.signal_col(3, 0.0)]
    state = out["mme_w3_t0.0_state"]
    p = out[mme.signal_col(3, 0.0, persist=2)]
    # Fase 2: existe ao menos uma confirmação e o dtype é Int8.
    idxs = [i for i in range(len(out)) if int(p.iloc[i]) == 1]
    assert len(idxs) >= 1 and str(p.dtype) == "Int8"
    # Fase 2/Saída: cada confirmação está 2 dias após um onset, com o estado ligado no intervalo.
    for i in idxs:
        assert int(onset.iloc[i - 2]) == 1
        assert all(int(state.iloc[j]) == 1 for j in range(i - 2, i + 1))
