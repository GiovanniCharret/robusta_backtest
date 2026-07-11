# pandas para reler os arquivos e checar ordenação.
import pandas as pd
# O entrypoint consolidado sob teste (função pura run_all + master).
from robusta.run_all import run_all, build_master


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
