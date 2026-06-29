# pandas para montar um Close mínimo e checar tipos/valores.
import pandas as pd
# A função sob teste.
from robusta.target import add_labels


# Teste do caminho feliz: retorno contínuo + binário + cauda NA (sem vazamento).
def test_add_labels_adds_continuous_and_binary():
    """
    Por quê: o df-fundação precisa ganhar AMBAS as colunas — o retorno contínuo
    (para revisão) e o binário (o alvo) — e ficar sem rótulo nas últimas h linhas.

    Lógica: Entrada (Close conhecido) → Fase 1 add_labels → Fase 2 ret → Fase 3 y
    → Fase 4 cauda NA → Saída (asserts).
    """
    # Entrada: Close cresce e depois cai.
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 9.0]})
    # Fase 1: rótulos para horizonte 1.
    out = add_labels(df, horizons=[1])
    # Fase 2: ret_1d[0] = 11/10 - 1 = 0.1.
    assert round(out["ret_1d"].iloc[0], 4) == 0.1
    # Fase 3: sobe, sobe, cai → 1, 1, 0.
    assert out["y_1d"].tolist()[:3] == [1, 1, 0]
    # Fase 4: última linha sem t+1 → NA em ambas as colunas.
    assert pd.isna(out["y_1d"].iloc[-1]) and pd.isna(out["ret_1d"].iloc[-1])
    # Saída: dtype inteiro anulável no alvo.
    assert str(out["y_1d"].dtype) == "Int8"


# Teste de horizonte maior: confere quantidade de NAs na cauda.
def test_add_labels_nan_tail_length_matches_horizon():
    """
    Por quê: garantir que exatamente h linhas finais ficam sem rótulo.

    Lógica: Entrada (5 closes) → Fase 1 add_labels h=2 → Fase 2 conta NAs → Saída.
    """
    # Entrada: cinco preços.
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0, 4.0, 5.0]})
    # Fase 1: horizonte 2.
    out = add_labels(df, horizons=[2])
    # Fase 2: as 2 últimas linhas devem ser NA.
    assert out["y_2d"].isna().sum() == 2


# Lacuna TESTES.md #6 (ALTA): retorno exatamente zero deve virar 0, não 1.
def test_add_labels_zero_return_is_zero():
    """
    Por quê: a regra é `ret > 0`; o retorno exatamente zero é a fronteira do `>`
    e define o rótulo — um erro aqui contamina toda a variável dependente.

    Lógica: Entrada (Close constante) → Fase 1 add_labels → Fase 2 ret=0 → Saída y=0.
    """
    # Entrada: Close constante → retorno futuro exatamente 0.
    df = pd.DataFrame({"Close": [10.0, 10.0, 10.0]})
    # Fase 1: horizonte 1.
    out = add_labels(df, horizons=[1])
    # Fase 2: ret_1d[0] = 10/10 - 1 = 0.0.
    assert out["ret_1d"].iloc[0] == 0.0
    # Saída: 0.0 não é > 0 → rótulo 0.
    assert out["y_1d"].iloc[0] == 0


# Lacuna TESTES.md #5 (MÉDIA): múltiplos horizontes numa só chamada.
def test_add_labels_multiple_horizons():
    """
    Por quê: o uso real passa vários horizontes (a daylist [10,20,30,45,90]); uma
    só chamada deve criar todas as colunas ret/y, cada uma com sua cauda NA.

    Lógica: Entrada (10 closes) → Fase 1 add_labels [1,2,3] → Fase 2 colunas → Fase 3 caudas.
    """
    # Entrada: dez preços crescentes.
    df = pd.DataFrame({"Close": [float(i) for i in range(1, 11)]})
    # Fase 1: três horizontes de uma vez.
    out = add_labels(df, horizons=[1, 2, 3])
    # Fase 2: as 6 colunas (ret+y por horizonte) existem.
    for h in (1, 2, 3):
        assert f"ret_{h}d" in out.columns and f"y_{h}d" in out.columns
    # Fase 3: cada coluna y tem exatamente h NAs na cauda.
    for h in (1, 2, 3):
        assert out[f"y_{h}d"].isna().sum() == h


# Lacuna TESTES.md #8 (MÉDIA): não muta o df original do chamador.
def test_add_labels_does_not_mutate_input():
    """
    Por quê: efeito colateral é bug sutil; add_labels usa `out = df.copy()`, então
    o df original não pode ganhar colunas.

    Lógica: Entrada (df) → Fase 1 add_labels → Fase 2 original intacto → Saída.
    """
    # Entrada: df original só com Close.
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0]})
    # Fase 1: roda add_labels (descarta o retorno).
    add_labels(df, horizons=[1])
    # Saída: o original continua só com a coluna Close.
    assert list(df.columns) == ["Close"]
