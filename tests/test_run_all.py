# pandas para reler os arquivos e checar ordenação.
import pandas as pd
# O entrypoint consolidado sob teste (funções puras run_all/run_all_multi + master).
from robusta.run_all import run_all, build_master, run_all_multi


# Teste: run_all roda um roster pequeno, grava um par por indicador e o master.
def test_run_all_writes_per_indicator_and_master(synthetic_prices_volume, tmp_path):
    """
    Por quê: provar a consolidação — para cada indicador sai analysis_/summary_, e um
    summary_ALL.xlsx concatena tudo. Sem rede (recebe preços prontos).

    Lógica: Entrada (preços+volume, roster pequeno) → Fase 1 run_all → Fase 2 arquivos
    → Fase 3 master → Saída.
    """
    # Entrada: roster pequeno (1 trend + 1 volume) e grids mínimos.
    indicators = ["mma", "obv"]
    grids = {"mma": {"window": [20], "tol": [0.0], "persist": [0]}, "obv": {"window": [20]}}
    # Fase 1: roda a versão pura em tmp.
    master = run_all(synthetic_prices_volume, indicators, grids, [10, 20], min_events=1, outdir=tmp_path)
    # Fase 2: um par de arquivos por indicador existe.
    for nome in indicators:
        assert (tmp_path / f"analysis_{nome}.xlsx").exists()
        assert (tmp_path / f"summary_{nome}.xlsx").exists()
    # Fase 3: o master existe e tem as duas abas.
    all_path = tmp_path / "summary_ALL.xlsx"
    assert all_path.exists()
    sheets = pd.ExcelFile(all_path).sheet_names
    assert "ranking" in sheets and "dicionário" in sheets
    # Saída: o master concatena os dois indicadores.
    assert set(master["indicator"]) == {"mma", "obv"}


# Teste: o master vem ordenado pela chave de ranking, por família (na no fim).
def test_master_ranked_by_family_key(synthetic_prices_volume):
    """
    Por quê: dentro de logit ordena por lift desc; dentro de ols por coef desc; NaN
    no fim de cada família (misturar unidades é seguro porque family é a chave primária).

    Lógica: Entrada (dois summaries) → Fase 1 build_master → Fase 2 ordenação por família → Saída.
    """
    # Entrada: gera dois summaries via run_all (descarta arquivos usando outdir tmp implícito não é preciso aqui).
    from robusta.runner import build_summary
    from robusta.indicators import mma, obv
    _, s1 = build_summary(synthetic_prices_volume, mma, {"window": [20], "tol": [0.0]}, [10, 20], min_events=1)
    _, s2 = build_summary(synthetic_prices_volume, obv, {"window": [20]}, [10, 20], min_events=1)
    # Fase 1: concatena e ordena.
    master = build_master([s1, s2])
    # Fase 2: chave por família (lift no logit, coef no ols) não-crescente, NaN por último.
    for fam, keycol in [("logit", "lift"), ("ols", "coef")]:
        vals = master[master["family"] == fam][keycol].tolist()
        notna = [v for v in vals if v == v]  # remove NaN
        # Saída: a parte não-NaN está em ordem não-crescente e os NaN vêm depois.
        assert notna == sorted(notna, reverse=True)
        nan_flags = [v == v for v in vals]  # True antes de False (na_position=last)
        assert nan_flags == sorted(nan_flags, reverse=True)


# Fase 4: o modo multi-ticker gera UM master com coluna `ticker` e nenhum par por indicador.
def test_run_all_multi_master_has_ticker_and_only_master_file(synthetic_prices_volume, tmp_path):
    """
    Por quê: com ~70 tickers, gravar 21 arquivos por ticker é inviável — o modo
    multi grava só o summary_ALL, com a coluna `ticker` na frente para permitir
    comparar o MESMO indicador entre tickers.

    Lógica: Entrada (2 tickers sintéticos + roster mínimo) → Fase 1 run_all_multi
    → Fase 2 master (ticker 1ª coluna, 2 tickers, contagem) → Fase 3 disco (1 só
    arquivo) → Fase 4 dicionário cobre `ticker` → Saída.
    """
    # Entrada: dois "tickers" com os mesmos preços sintéticos (grid mínimo do obv).
    pares = [("AAA", synthetic_prices_volume), ("BBB", synthetic_prices_volume.copy())]
    grids = {"obv": {"window": [20], "persist": [0]}}
    # Fase 1: roda o modo multi em tmp.
    master = run_all_multi(pares, ["obv"], grids, [10, 20], min_events=1, outdir=tmp_path)
    # Fase 2: `ticker` é a PRIMEIRA coluna e traz os dois nomes.
    assert list(master.columns)[0] == "ticker"
    assert set(master["ticker"]) == {"AAA", "BBB"}
    # Fase 2: 1 combo × 2 horizontes × 2 famílias × 2 tickers = 8 linhas.
    assert len(master) == 8
    # Fase 3: em disco existe SÓ o master (nenhum analysis_/summary_ por indicador).
    assert sorted(p.name for p in tmp_path.iterdir()) == ["summary_ALL.xlsx"]
    # Fase 4: a legenda do master cobre a coluna `ticker`.
    dic = pd.read_excel(tmp_path / "summary_ALL.xlsx", sheet_name="dicionário")
    # Saída: uma linha do dicionário por coluna, incluindo `ticker`.
    assert "ticker" in set(dic["coluna"])
