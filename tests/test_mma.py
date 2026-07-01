# pandas para construir Closes com cruzamento conhecido.
import pandas as pd
# O módulo-plugin sob teste (passado inteiro ao sweep).
from robusta.indicators import mma


# Teste: add_columns cria valor, estado e a dummy de evento.
def test_add_columns_creates_value_above_break():
    """
    Por quê: o indicador é o PLUG-IN; precisa ACRESCENTAR ao df-fundação o valor
    da média, o estado "acima da banda" e a dummy de rompimento (evento), tudo
    com nomes canônicos que o sweep saberá achar.

    Lógica: Entrada (Close em V) → Fase 1 add_columns → Fase 2 colunas existem
    → Fase 3 dummy é evento 0/1 → Saída.
    """
    # Entrada: cai e volta a subir, cruzando a média de janela 3.
    df = pd.DataFrame({"Close": [10, 9, 8, 7, 9, 11, 13, 14]})
    # Fase 1: adiciona as colunas do mma, janela 3, sem tolerância.
    out = mma.add_columns(df.copy(), window=3, tol=0.0)
    # Fase 2: coluna de valor da média presente.
    assert mma.value_col(3) in out.columns
    # Fase 2: coluna-dummy presente, com o nome canônico.
    scol = mma.signal_col(3, 0.0)
    assert scol in out.columns
    # Fase 3: a dummy é evento → só 0/1 e acende pelo menos uma vez.
    assert set(out[scol].dropna().unique()) <= {0, 1}
    assert out[scol].sum() >= 1
    # Saída: dtype Int8 e nome do indicador exposto.
    assert str(out[scol].dtype) == "Int8" and mma.NAME == "mma"


# Teste: tolerância suprime cruzamentos pequenos dentro da banda.
def test_tolerance_suppresses_marginal_cross():
    """
    Por quê: a tolerância existe para ignorar rompimentos fracos; com tol alto,
    um cruzamento marginal não deve acender a dummy.

    Lógica: Entrada (cruzamento marginal) → Fase 1 dois tol → Fase 2 compara → Saída.
    """
    # Entrada: Close que cruza a média por margem pequena.
    df = pd.DataFrame({"Close": [10, 10, 10, 10, 10.05, 10.06, 10.07]})
    # Fase 1: conta eventos sem tolerância e com 3%.
    strict = mma.add_columns(df.copy(), window=3, tol=0.0)[mma.signal_col(3, 0.0)].sum()
    loose = mma.add_columns(df.copy(), window=3, tol=0.03)[mma.signal_col(3, 0.03)].sum()
    # Fase 2/Saída: a tolerância reduz (ou iguala) o número de eventos.
    assert loose <= strict


# Lacuna TESTES.md #11 (ALTA): estado *_above vs evento *_break (só na transição).
def test_break_is_event_not_state():
    """
    Por quê: é o coração da dummy. `above` pode ficar 1 vários dias seguidos;
    `break` deve acender SÓ no 1º dia da sequência (transição 0→1 de above).

    Lógica: Entrada (sobe e fica acima) → Fase 1 add_columns → Fase 2 above persiste
    → Fase 3 break só na transição → Saída.
    """
    # Entrada: cruza a média e PERMANECE acima por vários dias.
    df = pd.DataFrame({"Close": [10, 9, 8, 9, 12, 14, 16, 18]})
    # Fase 1: janela 3, sem tolerância.
    out = mma.add_columns(df.copy(), window=3, tol=0.0)
    # Fase 2: o estado above fica ligado em vários dias (mais que o break).
    above = out[f"mma_w3_t0.0_above"]
    brk = out[mma.signal_col(3, 0.0)]
    assert above.sum() > brk.sum()
    # Fase 3: cada break=1 corresponde a uma transição (above hoje, não-above ontem).
    transitions = ((above == 1) & (above.shift(1, fill_value=0) == 0)).sum()
    # Saída: o nº de breaks é exatamente o nº de transições 0→1.
    assert int(brk.sum()) == int(transitions)


# Lacuna TESTES.md #12 (ALTA): não acende em dia sem cruzamento.
def test_break_silent_without_new_cross():
    """
    Por quê: depois de cruzar e ficar acima, não pode haver novo break sem voltar
    a cruzar — senão o evento vira estado.

    Lógica: Entrada (cruza uma vez, fica acima) → Fase 1 add_columns → Fase 2 1 só break.
    """
    # Entrada: cruza uma única vez e segue subindo sem novo cruzamento.
    df = pd.DataFrame({"Close": [10, 9, 8, 9, 11, 13, 15, 17, 19, 21]})
    # Fase 1: janela 3.
    out = mma.add_columns(df.copy(), window=3, tol=0.0)
    # Fase 2/Saída: exatamente um rompimento em toda a série.
    assert int(out[mma.signal_col(3, 0.0)].sum()) == 1


# Fase 2 (persistência): o nome canônico da coluna persist_k.
def test_signal_col_persist_name():
    """
    Por quê: o sweep descobre o nome da dummy só pelos parâmetros. Com persist>0,
    o nome deve mudar de *_break para *_persist{k}; com persist=0 (default), fica break.

    Lógica: Entrada (window, tol, persist) → Saída (nome canônico).
    """
    # persist>0: nome dedicado da persistência.
    assert mma.signal_col(3, 0.0, persist=3) == "mma_w3_t0.0_persist3"
    # persist=0 (default): mantém o nome da dummy de rompimento (retrocompatível).
    assert mma.signal_col(3, 0.0, persist=0) == mma.signal_col(3, 0.0)


# Fase 2 (persistência): persist_k acende UMA vez, no dia da confirmação (streak==k+1).
def test_persist_fires_once_at_confirmation():
    """
    Por quê: persist_k = rompeu E ficou above por mais k dias, carimbado one-shot
    no k-ésimo dia após o rompimento (dia da confirmação) — sem vazamento.

    Lógica: Entrada (rompe no idx4, fica above idx4..idx10) → Fase 1 add_columns
    → Fase 2 persist3 só no idx7 (rompimento+3), persist4 só no idx8 (rompimento+4) → Saída.
    """
    # Entrada: cai e depois sobe firme, cruzando a mma3 no idx4 e ficando above até o fim.
    df = pd.DataFrame({"Close": [10, 9, 8, 7, 9, 11, 13, 15, 17, 19, 21]})
    # Fase 1: rompimento (idx4) e as persistências de 3 e 4 dias.
    out3 = mma.add_columns(df.copy(), window=3, tol=0.0, persist=3)
    out4 = mma.add_columns(df.copy(), window=3, tol=0.0, persist=4)
    # Fase 2: a dummy de rompimento acende no idx4.
    assert int(out3[mma.signal_col(3, 0.0)].iloc[4]) == 1
    # Fase 2: persist3 acende exatamente uma vez, no idx7 (rompimento + 3 dias acima).
    p3 = out3[mma.signal_col(3, 0.0, persist=3)]
    assert int(p3.sum()) == 1 and int(p3.iloc[7]) == 1
    # Fase 2: persist4 acende exatamente uma vez, no idx8 (rompimento + 4 dias acima).
    p4 = out4[mma.signal_col(3, 0.0, persist=4)]
    assert int(p4.sum()) == 1 and int(p4.iloc[8]) == 1
    # Saída: dtype Int8, como as demais dummies.
    assert str(p3.dtype) == "Int8"


# Fase 2 (persistência): persist=0 preserva a dummy de rompimento intacta (regressão).
def test_persist_zero_keeps_break_unchanged():
    """
    Por quê: persist=0 é o comportamento atual (rompimento puro); não pode alterar
    a coluna *_break existente.

    Lógica: Entrada (mesma série) → Fase 1 com e sem persist → Fase 2 break idêntico → Saída.
    """
    # Entrada: série com um cruzamento conhecido.
    df = pd.DataFrame({"Close": [10, 9, 8, 9, 11, 13, 15, 17]})
    # Fase 1: caminho atual (sem persist) e caminho persist=0.
    base = mma.add_columns(df.copy(), window=3, tol=0.0)
    zero = mma.add_columns(df.copy(), window=3, tol=0.0, persist=0)
    # Fase 2/Saída: a dummy de rompimento é idêntica nos dois.
    assert base[mma.signal_col(3, 0.0)].equals(zero[mma.signal_col(3, 0.0)])


# Lacuna TESTES.md #14 (ALTA): janela maior que a série → mma NaN → zero eventos.
def test_window_larger_than_series_yields_no_events():
    """
    Por quê: o grid default usa window=200; num df curto a média é toda NaN e a
    dummy não pode acender (nem quebrar com KeyError/NaN).

    Lógica: Entrada (4 closes, window=200) → Fase 1 add_columns → Fase 2 mma NaN
    → Fase 3 zero eventos → Saída.
    """
    # Entrada: série curta com janela enorme.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 13.0]})
    # Fase 1: janela 200 sobre 4 linhas.
    out = mma.add_columns(df.copy(), window=200, tol=0.0)
    # Fase 2: o valor da média é inteiramente NaN.
    assert out[mma.value_col(200)].isna().all()
    # Fase 3/Saída: nenhum rompimento (a dummy é toda 0).
    assert int(out[mma.signal_col(200, 0.0)].sum()) == 0
