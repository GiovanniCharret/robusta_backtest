# pandas/numpy para plantar uma relação conhecida entre dummy e alvo.
import pandas as pd
import numpy as np
# As duas funções sob teste.
from robusta.modeling import fit_logit, fit_ols


# Teste: relação positiva plantada → coef positivo, family logit, status ok.
def test_fit_logit_recovers_positive_relationship():
    """
    Por quê: se a dummy realmente prevê o alvo binário, o coeficiente logístico
    deve ser positivo — prova de que o fit lê o sinal.

    Lógica: Entrada (alvo ≈ dummy) → Fase 1 fit → Fase 2 asserts → Saída.
    """
    # Entrada: 200 linhas; dummy alterna; alvo = dummy na maioria das vezes.
    n = 200
    x = np.tile([0, 1], n // 2)
    y = x.copy()
    # Introduz discordância determinística (a cada 10, inverte) para evitar separação perfeita.
    y[::10] = 1 - y[::10]
    df = pd.DataFrame({"y_20d": y, "mma_w20_t0.0_break": x})
    # Fase 1: ajusta a logística.
    res = fit_logit(df, y_col="y_20d", x_cols=["mma_w20_t0.0_break"])
    # Fase 2: convergiu, family correta, coeficiente positivo, contagens corretas.
    assert res["status"] == "ok" and res["family"] == "logit"
    assert res["coef"] > 0
    assert res["n"] == n and res["n_eventos"] == n // 2
    # Saída: r2 é um número (não NaN).
    assert res["r2"] == res["r2"]


# Teste: sem eventos → status sem_eventos, sem tentar ajustar.
def test_fit_logit_no_events_returns_status():
    """
    Por quê: a dummy de rompimento pode não ter nenhum 1 numa fatia; o fit deve
    degradar com elegância, não quebrar o sweep.

    Lógica: Entrada (dummy toda 0) → Fase 1 fit → Fase 2 status → Saída.
    """
    # Entrada: alvo variado, dummy constante em 0.
    df = pd.DataFrame({"y_20d": [0, 1, 0, 1, 1, 0], "x": [0, 0, 0, 0, 0, 0]})
    # Fase 1: tenta ajustar.
    res = fit_logit(df, y_col="y_20d", x_cols=["x"], min_events=5)
    # Fase 2: marcado como sem_eventos, métricas NaN.
    assert res["status"] == "sem_eventos"
    assert np.isnan(res["r2"])
    # Saída: contagem de eventos é zero.
    assert res["n_eventos"] == 0


# Teste: OLS sobre alvo contínuo → R² clássico e accuracy NaN.
def test_fit_ols_returns_classic_r2_and_nan_accuracy():
    """
    Por quê: a família OLS roda sobre o retorno contínuo (ret_{h}d) e entrega o R²
    clássico dos materiais de regressão; accuracy não se aplica.

    Lógica: Entrada (ret com efeito plantado da dummy) → Fase 1 fit_ols → Fase 2 asserts → Saída.
    """
    # Entrada: dummy alterna; retorno maior quando dummy=1 (efeito positivo) + ruído determinístico.
    n = 200
    x = np.tile([0, 1], n // 2)
    ret = 0.01 * x + 0.001 * np.sin(np.arange(n))
    df = pd.DataFrame({"ret_20d": ret, "mma_w20_t0.0_break": x})
    # Fase 1: ajusta o OLS sobre o retorno contínuo.
    res = fit_ols(df, y_col="ret_20d", x_cols=["mma_w20_t0.0_break"])
    # Fase 2: family correta, coef positivo, R² no intervalo [0,1], accuracy NaN.
    assert res["status"] == "ok" and res["family"] == "ols"
    assert res["coef"] > 0
    assert 0.0 <= res["r2"] <= 1.0
    assert np.isnan(res["accuracy"])


# Lacuna TESTES.md #20 (ALTA): separação perfeita no logit → separacao/erro, sem derrubar.
def test_fit_logit_perfect_separation():
    """
    Por quê: o design (§8) exige capturar PerfectSeparationError e NUNCA propagar
    exceção (o sweep não pode cair por um modelo ruim). Aceita 'separacao' ou
    'erro' (varia por versão do statsmodels), mas sempre com métricas NaN.

    Lógica: Entrada (y == x perfeitamente) → Fase 1 fit → Fase 2 status de borda → Saída.
    """
    # Entrada: 40 linhas, dummy prevê o alvo 100% (separação perfeita).
    x = [0] * 20 + [1] * 20
    df = pd.DataFrame({"y_20d": x, "x": x})
    # Fase 1: tenta ajustar (não pode lançar exceção para fora).
    res = fit_logit(df, y_col="y_20d", x_cols=["x"], min_events=5)
    # Fase 2: status de borda esperado e r2 NaN.
    assert res["status"] in {"separacao", "erro"}
    assert np.isnan(res["r2"])


# Lacuna TESTES.md #23 (MÉDIA): min_events na fronteira (`<` vs `<=`).
def test_fit_logit_min_events_boundary():
    """
    Por quê: a regra é `n_eventos < min_events`; travar os dois lados da fronteira
    evita um off-by-one que descartaria (ou aceitaria) modelos errados.

    Lógica: Entrada (exatamente 5 eventos) → Fase 1 dois min_events → Fase 2 compara → Saída.
    """
    # Entrada: 40 linhas, 5 eventos exatos; alvo varia e não é separável nos eventos.
    x = [1] * 5 + [0] * 35
    y = [1, 0] * 20
    df = pd.DataFrame({"y_20d": y, "x": x})
    # Fase 1: com min_events=5 (5<5 falso) NÃO bloqueia por falta de eventos.
    assert fit_logit(df, "y_20d", ["x"], min_events=5)["status"] != "sem_eventos"
    # Fase 2/Saída: com min_events=6 (5<6) bloqueia como sem_eventos.
    assert fit_logit(df, "y_20d", ["x"], min_events=6)["status"] == "sem_eventos"


# Lacuna TESTES.md #25 (MÉDIA): schema idêntico entre logit e ols (o sweep empilha as linhas).
def test_logit_and_ols_share_schema():
    """
    Por quê: o sweep empilha linhas de logit e ols num único DataFrame; as chaves
    dos dois dicionários precisam ser idênticas.

    Lógica: Entrada (df com y e ret) → Fase 1 os dois fits → Fase 2 comparar chaves → Saída.
    """
    # Entrada: dummy alterna; y binário e ret contínuo derivados dela.
    n = 40
    x = np.tile([0, 1], n // 2)
    df = pd.DataFrame({"y_20d": x, "ret_20d": 0.01 * x, "x": x})
    # Fase 1: roda as duas famílias (caminho de borda/feliz não importa para o schema).
    klogit = set(fit_logit(df, "y_20d", ["x"]).keys())
    kols = set(fit_ols(df, "ret_20d", ["x"]).keys())
    # Fase 2/Saída: mesmas chaves nos dois dicionários.
    assert klogit == kols
