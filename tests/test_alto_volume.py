# pandas para casos pequenos controlados.
import pandas as pd
# O módulo sob teste.
from robusta.indicators import alto_volume as av


# Teste: cria média de volume, estado e onset.
def test_av_creates_columns(synthetic_prices_volume):
    """
    Por quê: estado = volume ≥ mult·média E Close subiu; onset = 1º dia dessa condição.

    Lógica: Entrada (preços+volume) → Fase 1 add_columns → Fase 2 colunas/evento → Saída.
    """
    # Fase 1: janela 20, mult 1,5.
    out = av.add_columns(synthetic_prices_volume.copy(), window=20, mult=1.5)
    # Fase 2: valor e sinal; 0/1; Int8; NAME.
    assert av.value_col(20) in out.columns
    scol = av.signal_col(20, 1.5)
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert str(out[scol].dtype) == "Int8" and av.NAME == "alto_volume"


# Teste: onset = transição 0→1 do estado.
def test_av_signal_equals_state_transitions(synthetic_prices_volume):
    """
    Por quê: onset acende só no 1º dia de um pico (não em cada dia do pico).

    Lógica: Entrada → Fase 1 add_columns → Fase 2 invariante → Saída.
    """
    # Fase 1: janela 20, mult 1,5.
    out = av.add_columns(synthetic_prices_volume.copy(), window=20, mult=1.5)
    # Fase 2: invariante evento == transições.
    state = out["alto_volume_w20_m1.5_t0.0_state"]
    sig = out[av.signal_col(20, 1.5)]
    transitions = ((state == 1) & (state.shift(1, fill_value=0) == 0)).sum()
    assert int(sig.sum()) == int(transitions)


# Teste: pico de volume em dia de BAIXA não acende (precisa de Close subindo).
def test_av_high_volume_down_day_does_not_fire():
    """
    Por quê: a definição exige alta E volume; um pico de volume num dia de queda
    (típico de venda) não é sinal bullish.

    Lógica: Entrada (dia de pico com Close caindo) → Fase 1 add_columns → Fase 2 zero → Saída.
    """
    # Entrada: volume baixo e estável, depois um pico gigante num dia de QUEDA do Close.
    df = pd.DataFrame({
        "Close": [10, 10, 10, 10, 9],           # último dia cai
        "Volume": [100, 100, 100, 100, 10_000],  # último dia é pico
    })
    # Fase 1: janela 3, mult 2.
    out = av.add_columns(df.copy(), window=3, mult=2.0)
    # Fase 2/Saída: o pico em dia de queda NÃO acende a dummy.
    assert int(out[av.signal_col(3, 2.0)].iloc[4]) == 0


# Teste: janela > série → média de volume NaN → zero eventos.
def test_av_window_larger_than_series_zero_events():
    """
    Por quê: janela grande num df curto → média NaN → high_vol False → sem evento.

    Lógica: Entrada (3 dias, window=20) → Fase 1 add_columns → Fase 2 zero → Saída.
    """
    # Entrada: série curta.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0], "Volume": [100, 200, 9_000]})
    # Fase 1: janela 20.
    out = av.add_columns(df.copy(), window=20, mult=1.5)
    # Fase 2/Saída: zero eventos.
    assert int(out[av.signal_col(20, 1.5)].sum()) == 0


# Teste: persist confirma dias CONSECUTIVOS de pico+alta (one-shot na confirmação).
def test_av_persist_confirms_consecutive_spike_days():
    """
    Por quê: o módulo suporta persist como os demais (mesmo bloco de streak), ainda
    que o grid do config use [0] — o estado de evento raramente dura. Aqui provamos
    a mecânica com um caso construído de 2 dias seguidos de pico em alta.

    Lógica: Entrada (2 picos consecutivos em dias de alta) → Fase 1 add_columns(persist=1)
    → Fase 2 confirmação uma única vez, no 2º dia do estado → Saída.
    """
    # Entrada: Close sobe todo dia; volume salta no idx3 (1000) e idx4 (2000, vence a média que subiu).
    df = pd.DataFrame({"Close": [10, 11, 12, 13, 14],
                       "Volume": [100, 100, 100, 1000, 2000]})
    # Fase 1: janela 3, mult 1,5, persist=1.
    out = av.add_columns(df.copy(), window=3, mult=1.5, persist=1)
    # Fase 2: estado ligado no idx3 (onset) e no idx4 (streak=2) → persist1 confirma no idx4.
    p = out[av.signal_col(3, 1.5, persist=1)]
    # Fase 2/Saída: uma única confirmação, no idx4, dtype Int8.
    assert int(p.sum()) == 1 and int(p.iloc[4]) == 1 and str(p.dtype) == "Int8"


# Teste: o tol do legado SUAVIZA o limiar — pico de fronteira só conta com tol=0.005.
def test_av_tol_softens_threshold():
    """
    Por quê: o legado usa tolerancia_erro=0.005 no limiar (Volume ≥ mult·média·(1−tol));
    aqui o fator vira o param `tol` varrível. Sentido do botão: tol MAIOR → limiar
    MENOR → MAIS eventos (oposto do tol do mma, que aperta a banda).

    Lógica: Entrada (pico de fronteira) → Fase 1 add_columns com tol 0 e 0.005 →
    Fase 2 o evento só conta com a tolerância → Saída.
    """
    # Entrada: Close subindo; volume de fronteira no idx3 (média=199 → limiar exato 398; suave 396.01).
    df = pd.DataFrame({"Close": [10, 11, 12, 13], "Volume": [100, 100, 100, 397]})
    # Fase 1: sem tolerância (limiar exato) e com a tolerância do legado.
    strict = av.add_columns(df.copy(), window=3, mult=2.0, tol=0.0)[av.signal_col(3, 2.0, 0.0)].sum()
    soft = av.add_columns(df.copy(), window=3, mult=2.0, tol=0.005)[av.signal_col(3, 2.0, 0.005)].sum()
    # Fase 2/Saída: 397 < 398 (exato, não conta) e 397 ≥ 396.01 (suave, conta).
    assert int(strict) == 0 and int(soft) == 1


# Teste: confirm_k = evento + preço SEGURANDO o nível por k dias (some se devolver).
def test_av_confirm_price_hold_after_event():
    """
    Por quê: persist não se aplica a evento pontual (picos consecutivos são raros);
    a pergunta certa aqui é outra — depois do pico, o PREÇO segurou? confirm_k =
    evento no dia t e Close[t+1..t+k] ≥ Close[t]; dummy 1 one-shot no dia t+k.

    Lógica: Entrada (pico com preço segurando vs pico que devolve) → Fase 1
    add_columns(confirm=2) → Fase 2 confirma só quando o preço segurou → Saída.
    """
    # Entrada A: pico no idx3 (Close=13) e o preço SEGURA (13 e 14 ≥ 13).
    segura = pd.DataFrame({"Close": [10, 11, 12, 13, 13, 14],
                           "Volume": [100, 100, 100, 1000, 100, 100]})
    # Entrada B: mesmo pico, mas o preço DEVOLVE no dia seguinte (12.5 < 13).
    devolve = pd.DataFrame({"Close": [10, 11, 12, 13, 12.5, 14],
                            "Volume": [100, 100, 100, 1000, 100, 100]})
    # Fase 1: janela 3, mult 1,5, confirm=2 (evento no idx3 nos dois cenários).
    out_a = av.add_columns(segura.copy(), window=3, mult=1.5, confirm=2)
    out_b = av.add_columns(devolve.copy(), window=3, mult=1.5, confirm=2)
    ca = out_a[av.signal_col(3, 1.5, confirm=2)]
    cb = out_b[av.signal_col(3, 1.5, confirm=2)]
    # Fase 2: no cenário que segura, confirma UMA vez, no idx5 (evento idx3 + 2 dias).
    assert int(ca.sum()) == 1 and int(ca.iloc[5]) == 1 and str(ca.dtype) == "Int8"
    # Fase 2/Saída: no cenário que devolve, nenhuma confirmação.
    assert int(cb.sum()) == 0
