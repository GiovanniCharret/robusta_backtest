# pandas para casos pequenos controlados.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import exaustao_atr as ea


# Teste: cria ATR, estado e onset.
def test_ea_creates_columns(synthetic_prices_volume):
    """
    Por quê: estado = TR do dia ≥ mult·ATR(ontem) E Close subiu; onset = 1º dia disso.

    Lógica: Entrada (preços) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: ATR de 14, mult 1,5.
    out = ea.add_columns(synthetic_prices_volume.copy(), atr_period=14, mult=1.5)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert ea.value_col(14) in out.columns
    scol = ea.signal_col(14, 1.5)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and ea.NAME == "exaustao_atr"


# Teste: onset = transição 0→1 do estado.
def test_ea_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset acende só no 1º dia de um range-gigante-de-alta.

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1.
    out = ea.add_columns(synthetic_prices_volume.copy(), atr_period=14, mult=1.5)
    # Fase 2: invariante, exigindo referência (o ATR usado pelo estado é o de ONTEM,
    # por isso aplicamos .shift(1) antes do .notna().shift(1)) válida ontem — o fim
    # do warm-up não conta como transição real (Task 16).
    state = out["exaustao_atr_p14_m1.5_t0.0_state"]
    sig = out[ea.signal_col(14, 1.5)]
    ref = out[ea.value_col(14)].shift(1)
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)
                   & ref.notna().shift(1, fill_value=False)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: só acende num dia de range GIGANTE de alta; dias normais não.
def test_ea_fires_only_on_big_up_range():
    """
    Por quê: a definição exige TR do dia bem acima do ATR recente E Close subindo.
    Dias de range normal não podem acender.

    Lógica: Entrada (dias calmos + 1 dia de range enorme em alta) → Fase 1 → Fase 2 → Saída.
    """
    # Entrada: 5 dias calmos (range 1) e um 6º dia com range enorme e Close subindo forte.
    df = pd.DataFrame({
        "High": [10.5, 10.5, 10.5, 10.5, 10.5, 20.0],
        "Low":  [9.5, 9.5, 9.5, 9.5, 9.5, 11.0],
        "Close": [10, 10, 10, 10, 10, 19],
    })
    # Fase 1: ATR de 3, mult 2.
    out = ea.add_columns(df.copy(), atr_period=3, mult=2.0)
    # Fase 2: acende só no dia 5 (o de range gigante em alta), 1 evento no total.
    sig = out[ea.signal_col(3, 2.0)]
    assert int(sig.sum()) == 1 and int(sig.iloc[5]) == 1


# Teste: janela > série → ATR NaN → zero eventos.
def test_ea_window_larger_than_series_zero_events():
    """
    Por quê: atr_period grande num df curto → ATR NaN → estado False → sem evento.

    Lógica: Entrada (3 dias, atr_period=14) → Fase 1 → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"High": [11.0, 12.0, 13.0], "Low": [9.0, 10.0, 11.0], "Close": [10.0, 11.0, 12.0]})
    # Fase 1: ATR de 14.
    out = ea.add_columns(df.copy(), atr_period=14, mult=1.5)
    # Fase 2/Saída: zero eventos.
    assert int(out[ea.signal_col(14, 1.5)].sum()) == 0


# Teste: persist confirma dias CONSECUTIVOS de range gigante em alta (one-shot).
def test_ea_persist_confirms_consecutive_big_days():
    """
    Por quê: o módulo suporta persist como os demais (mesmo bloco de streak), ainda
    que o grid do config use [0] — dois dias seguidos de exaustão é raríssimo. Aqui
    provamos a mecânica com um caso construído.

    Lógica: Entrada (2 dias seguidos de range gigante em alta) → Fase 1
    add_columns(persist=1) → Fase 2 confirmação uma única vez, no 2º dia → Saída.
    """
    # Entrada: 4 dias calmos (range 1) e DOIS dias seguidos de range gigante em alta.
    df = pd.DataFrame({
        "High":  [10.5, 10.5, 10.5, 10.5, 20.0, 30.0],
        "Low":   [9.5, 9.5, 9.5, 9.5, 11.0, 21.0],
        "Close": [10, 10, 10, 10, 19, 29],
    })
    # Fase 1: ATR de 2, mult 2, persist=1.
    out = ea.add_columns(df.copy(), atr_period=2, mult=2.0, persist=1)
    # Fase 2: estado ligado no idx4 (onset: TR=10 ≥ 2·ATR=2) e no idx5 (TR=11 ≥ 2·5.5).
    p = out[ea.signal_col(2, 2.0, persist=1)]
    # Fase 2/Saída: uma única confirmação, no idx5, dtype Int8.
    assert int(p.sum()) == 1 and int(p.iloc[5]) == 1 and str(p.dtype) == "Int8"


# Teste: o tol do legado SUAVIZA o limiar — range de fronteira só conta com tol=0.005.
def test_ea_tol_softens_threshold():
    """
    Por quê: o legado usa tolerancia_erro=0.005 no limiar (TR ≥ mult·ATR₋₁·(1−tol));
    aqui o fator vira o param `tol` varrível. Sentido do botão: tol MAIOR → limiar
    MENOR → MAIS eventos.

    Lógica: Entrada (dia de range de fronteira) → Fase 1 add_columns com tol 0 e
    0.005 → Fase 2 o evento só conta com a tolerância → Saída.
    """
    # Entrada: 4 dias calmos (TR=1 → ATR2=1) e um dia de fronteira em alta:
    # TR = 11.5−9.51 = 1.99 (limiar exato = 2·1 = 2; suave = 2·0.995 = 1.99).
    df = pd.DataFrame({
        "High":  [10.5, 10.5, 10.5, 10.5, 11.5],
        "Low":   [9.5, 9.5, 9.5, 9.5, 9.51],
        "Close": [10, 10, 10, 10, 11],
    })
    # Fase 1: sem tolerância (limiar exato) e com a tolerância do legado.
    strict = ea.add_columns(df.copy(), atr_period=2, mult=2.0, tol=0.0)[ea.signal_col(2, 2.0, 0.0)].sum()
    soft = ea.add_columns(df.copy(), atr_period=2, mult=2.0, tol=0.005)[ea.signal_col(2, 2.0, 0.005)].sum()
    # Fase 2/Saída: 1.99 < 2 (exato, não conta) e 1.99 ≥ 1.99 (suave, conta).
    assert int(strict) == 0 and int(soft) == 1


# Teste: confirm_k = evento + preço SEGURANDO o nível por k dias (some se devolver).
def test_ea_confirm_price_hold_after_event():
    """
    Por quê: persist não se aplica a evento pontual (ranges gigantes consecutivos são
    raros e o ATR sobe); a pergunta certa é — depois da exaustão, o PREÇO segurou?
    confirm_k = evento no dia t e Close[t+1..t+k] ≥ Close[t]; dummy 1 one-shot em t+k.

    Lógica: Entrada (exaustão com preço segurando vs devolvendo) → Fase 1
    add_columns(confirm=2) → Fase 2 confirma só quando o preço segurou → Saída.
    """
    # Entrada A: exaustão no idx4 (Close=19) e o preço SEGURA (19.5 e 20 ≥ 19).
    segura = pd.DataFrame({
        "High":  [10.5, 10.5, 10.5, 10.5, 20.0, 20.0, 20.5],
        "Low":   [9.5, 9.5, 9.5, 9.5, 11.0, 19.0, 19.5],
        "Close": [10, 10, 10, 10, 19, 19.5, 20],
    })
    # Entrada B: mesma exaustão, mas o preço DEVOLVE no dia seguinte (18 < 19).
    devolve = pd.DataFrame({
        "High":  [10.5, 10.5, 10.5, 10.5, 20.0, 19.0, 20.5],
        "Low":   [9.5, 9.5, 9.5, 9.5, 11.0, 17.5, 19.5],
        "Close": [10, 10, 10, 10, 19, 18, 20],
    })
    # Fase 1: ATR de 2, mult 2, confirm=2 (evento só no idx4 nos dois cenários).
    out_a = ea.add_columns(segura.copy(), atr_period=2, mult=2.0, confirm=2)
    out_b = ea.add_columns(devolve.copy(), atr_period=2, mult=2.0, confirm=2)
    ca = out_a[ea.signal_col(2, 2.0, confirm=2)]
    cb = out_b[ea.signal_col(2, 2.0, confirm=2)]
    # Fase 2: no cenário que segura, confirma UMA vez, no idx6 (evento idx4 + 2 dias).
    assert int(ca.sum()) == 1 and int(ca.iloc[6]) == 1 and str(ca.dtype) == "Int8"
    # Fase 2/Saída: no cenário que devolve, nenhuma confirmação.
    assert int(cb.sum()) == 0


# Task 16 (review final da Fase 3): onset fantasma no 1º dia válido do warm-up.
def test_ea_no_phantom_onset_at_warmup():
    """
    Por quê: no 1º dia CALCULÁVEL do estado (o 1º dia em que o ATR de ONTEM existe),
    se o range gigante E a alta já se verificam, o onset antigo disparava — o "abaixo
    de ontem" usado na comparação era um NaN coerido para False, não uma observação
    real. Este teste prova que um cenário que já nasce "acima" desde o 1º dia
    calculável E permanece assim no dia seguinte NÃO gera onset nem persistência
    fantasma.

    Lógica: Entrada (2 dias calmos seguidos de 2 dias de range gigante em alta) →
    Fase 1 add_columns(atr_period=2, mult=2.0, persist=1) → Fase 2 confirma que o
    cenário é real (estado já True no 1º dia calculável, idx2) → Fase 3 nem o onset
    nem a persistência disparam (nenhuma transição genuína) → Saída.
    """
    # Entrada: 2 dias calmos (TR=1 → ATR2 válido só a partir do idx1) e 2 dias de
    # range gigante em alta (idx2 e idx3).
    df = pd.DataFrame({
        "High":  [10.5, 10.5, 20, 30],
        "Low":   [9.5, 9.5, 11, 21],
        "Close": [10, 10, 19, 29],
    })
    # Fase 1: ATR de 2, mult=2.0, persist=1 (confirmaria 1 dia após o onset).
    out = ea.add_columns(df.copy(), atr_period=2, mult=2.0, persist=1)
    # Fase 2: o 1º dia CALCULÁVEL do estado é idx2 (ATR.shift(1) só existe a partir
    # daqui, pois atr_p2 tem seu 1º valor no idx1); estado já True ali (TR=10 ≥
    # 2·ATR(idx1)=2) — confirma que o cenário é real.
    state = out["exaustao_atr_p2_m2.0_t0.0_state"]
    assert int(state.iloc[2]) == 1
    # Fase 3: nem o onset nem a persistência podem disparar — não há transição
    # genuína, só o fim do warm-up (mesmo com o estado ligado 2 dias seguidos).
    assert int(out[ea.signal_col(2, 2.0)].sum()) == 0
    # Saída: a persistência (ancorada num onset genuíno) também fica silenciosa.
    assert int(out[ea.signal_col(2, 2.0, persist=1)].sum()) == 0
