# As peças que o sweep orquestra.
from robusta.target import add_labels
from robusta.indicators import mma
from robusta.sweep import run_sweep


# Teste: o sweep acumula colunas no df e gera o summary com as DUAS famílias.
def test_run_sweep_accumulates_columns_and_two_families(synthetic_prices):
    """
    Por quê: validar as DUAS saídas — o df-fundação enriquecido (colunas
    acumuladas) e o summary (duas linhas por modelo: logit + ols) com schema correto.

    Lógica: Entrada (preços rotulados + grid) → Fase 1 run_sweep → Fase 2 summary
    → Fase 3 analysis acumulado → Saída.
    """
    # Entrada: rótulos para dois horizontes.
    horizons = [10, 20]
    df = add_labels(synthetic_prices, horizons=horizons)
    # Grid pequeno: 2 janelas × 2 tolerâncias.
    grid = {"window": [5, 20], "tol": [0.0, 0.01]}
    # Fase 1: roda o sweep passando o MÓDULO do indicador.
    analysis, summary = run_sweep(df, mma, grid, horizons)
    # Fase 2: 2×2×2 combinações×horizontes × 2 famílias = 16 linhas.
    assert len(summary) == 2 * 2 * 2 * 2
    # Fase 2: ambas as famílias presentes.
    assert set(summary["family"]) == {"logit", "ols"}
    # Fase 2: colunas-chave do summary presentes.
    for col in ["indicator", "window", "tol", "horizon", "family", "r2", "p_value", "status"]:
        assert col in summary.columns
    # Fase 2: indicador correto.
    assert (summary["indicator"] == "mma").all()
    # Fase 3: o df-fundação ganhou as colunas de valor e dummy acumuladas.
    assert mma.value_col(5) in analysis.columns
    assert mma.signal_col(20, 0.01) in analysis.columns
    # Saída: analysis continua com 1 linha por dia (mesmo tamanho da entrada).
    assert len(analysis) == len(synthetic_prices)


# Teste: ordenação do summary por r2 desc DENTRO de cada família, NaN no fim.
def test_run_sweep_sorted_within_family(synthetic_prices):
    """
    Por quê: o usuário compara modelos dentro de cada família; o r2 do logit
    (pseudo) e do ols (clássico) não estão na mesma escala, então cada família é
    rankeada em separado e NaN afunda.

    Lógica: Entrada (preços) → Fase 1 sweep → Fase 2 confere ordenação por família → Saída.
    """
    # Entrada/Fase 1: um horizonte, grid mínimo.
    df = add_labels(synthetic_prices, horizons=[10])
    analysis, summary = run_sweep(df, mma, {"window": [5, 200], "tol": [0.0]}, [10])
    # Fase 2: dentro de cada família, r2 dos ok em ordem não-crescente.
    for fam in ["logit", "ols"]:
        oks = summary[(summary["family"] == fam) & (summary["status"] == "ok")]["r2"].tolist()
        assert oks == sorted(oks, reverse=True)
    # Saída: 2 janelas × 1 tol × 1 horizonte × 2 famílias = 4 linhas.
    assert len(summary) == 4


# Lacuna TESTES.md #29 (ALTA): linhas com r2 NaN (sem_eventos) afundam em cada família.
def test_run_sweep_nan_last_within_family(synthetic_prices):
    """
    Por quê: o design (§7b) promete na_position="last"; um ranking com NaN no topo
    enganaria a comparação. Forçamos um NaN garantido com janela MAIOR que a série
    (mma toda NaN → 0 eventos → sem_eventos).

    Lógica: Entrada (grid com window=400 > 300) → Fase 1 sweep → Fase 2 NaN no fim.
    """
    # Entrada: window=400 sobre 300 dias garante um modelo sem eventos (r2 NaN).
    df = add_labels(synthetic_prices, horizons=[10])
    analysis, summary = run_sweep(df, mma, {"window": [5, 400], "tol": [0.0]}, [10])
    # Fase 1: deve existir pelo menos um sem_eventos (o window=400).
    assert (summary["status"] == "sem_eventos").any()
    # Fase 2/Saída: em cada família, todos os não-NaN vêm ANTES dos NaN.
    for fam in ["logit", "ols"]:
        notna_flags = summary[summary["family"] == fam]["r2"].notna().tolist()
        assert notna_flags == sorted(notna_flags, reverse=True)


# Lacuna TESTES.md #30/#34 (MÉDIA): janela grande não derruba o sweep; min_events degrada.
def test_run_sweep_large_window_robust_and_min_events(synthetic_prices):
    """
    Por quê: provar robustez ponta-a-ponta — janela grande (200) roda sem cair, e
    um min_events impossível faz TODOS os modelos virarem sem_eventos (degrade gracioso).

    Lógica: Entrada (preços) → Fase 1 grid com window=200 → Fase 2 status válidos
    → Fase 3 min_events impossível → Saída.
    """
    # Entrada: grid com janela grande.
    df = add_labels(synthetic_prices, horizons=[10])
    # Fase 1: roda sem lançar exceção.
    analysis, summary = run_sweep(df, mma, {"window": [5, 200], "tol": [0.0]}, [10], min_events=5)
    # Fase 2: todos os status pertencem ao conjunto válido; coluna acumulada presente.
    assert set(summary["status"]) <= {"ok", "sem_eventos", "separacao", "erro"}
    assert mma.value_col(200) in analysis.columns
    # Fase 3: com min_events impossível, tudo vira sem_eventos.
    df2 = add_labels(synthetic_prices, horizons=[10])
    _, summary2 = run_sweep(df2, mma, {"window": [20], "tol": [0.0]}, [10], min_events=10_000)
    # Saída: degrade gracioso confirmado.
    assert (summary2["status"] == "sem_eventos").all()


# As métricas de associação 2×2 só valem na família logit (NaN no ols).
def test_run_sweep_contingency_only_on_logit(synthetic_prices):
    """
    Por quê: odds_ratio/lift/fisher_p vêm da tabela 2×2 (rompimento × alta) — só
    fazem sentido no alvo binário (logit); no ols (alvo contínuo) ficam NaN.

    Lógica: Entrada (preços) → Fase 1 sweep → Fase 2 colunas existem → Fase 3 ols NaN,
    logit preenchido → Saída.
    """
    # Entrada/Fase 1: grid mínimo, eventos suficientes.
    df = add_labels(synthetic_prices, horizons=[10])
    _, summary = run_sweep(df, mma, {"window": [20], "tol": [0.0]}, [10], min_events=5)
    # Fase 2: as três colunas de associação existem no summary.
    for col in ["odds_ratio", "lift", "fisher_p"]:
        assert col in summary.columns
    # Fase 3: nas linhas ols, a associação 2×2 é sempre NaN.
    assert summary[summary["family"] == "ols"]["odds_ratio"].isna().all()
    # Saída: nas linhas logit que ajustaram (ok), a associação está preenchida.
    logit_ok = summary[(summary["family"] == "logit") & (summary["status"] == "ok")]
    assert logit_ok["odds_ratio"].notna().all()
