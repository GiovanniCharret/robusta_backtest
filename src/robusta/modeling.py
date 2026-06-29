# numpy para NaN e contagens.
import numpy as np
# pandas para manipular as colunas do df.
import pandas as pd
# statsmodels fornece Logit/OLS com pseudo-R²/R², p-valores e log-likelihood.
import statsmodels.api as sm
# Exceção específica de separação perfeita (modelo não identificável).
from statsmodels.tools.sm_exceptions import PerfectSeparationError


# Molde padrão de uma linha de métricas para os caminhos de borda (sem ajuste).
def _empty(family: str, n: int, n_eventos: int, status: str) -> dict:
    """
    Por quê: garantir que logit e ols devolvam EXATAMENTE o mesmo schema, mesmo
    quando não há ajuste — assim o sweep trata todas as linhas igual.

    Lógica: Entrada (família, n, eventos, status) → Saída (dict com métricas NaN).
    """
    # Saída: dicionário com contagens preenchidas e métricas NaN.
    return {
        # Identificação da família e contagens.
        "family": family, "n": n, "n_eventos": n_eventos,
        # Métricas indefinidas neste caminho.
        "r2": np.nan, "coef": np.nan, "p_value": np.nan,
        "llf": np.nan, "accuracy": np.nan,
        # Status do caminho de borda.
        "status": status,
    }


# Ajusta uma regressão logística de um (ou mais) preditor(es) e resume métricas.
def fit_logit(df: pd.DataFrame, y_col: str, x_cols: list[str], min_events: int = 5) -> dict:
    """
    Por quê: isolar o ajuste logístico (alvo binário) do laço do sweep, devolvendo
    uma linha plana do summary. Aceita N preditores para habilitar stepwise no futuro.

    Lógica (Entrada → Saída):
      Entrada: df + coluna-alvo binária + colunas-preditoras + mín. eventos.
      Fase 1: descarta NA no alvo/preditores.
      Fase 2: conta eventos; se poucos, alvo ou dummy constantes → sem_eventos.
      Fase 3: ajusta a Logit com constante; captura separação/erros.
      Fase 4: extrai r2 (pseudo), coef, p_value, llf e acurácia in-sample.
      Saída: dicionário (family=logit) com as métricas e o status.
    """
    # Fase 1: mantém só as colunas relevantes e remove NA (cauda do rótulo etc.).
    data = df[[y_col, *x_cols]].dropna()
    # Fase 1: tamanho amostral efetivo após limpeza.
    n = int(len(data))
    # Fase 2: nº de eventos = soma do 1º preditor (a dummy do indicador).
    n_eventos = int(data[x_cols[0]].sum()) if n else 0
    # Fase 2: poucos eventos, ou dummy/alvo constantes → não ajusta.
    if n_eventos < min_events or data[x_cols[0]].nunique() < 2 or data[y_col].nunique() < 2:
        # Retorna o molde marcado como sem_eventos.
        return _empty("logit", n, n_eventos, "sem_eventos")
    # Fase 3: matriz de preditores com constante (intercepto).
    X = sm.add_constant(data[x_cols].astype(float))
    # Fase 3: vetor-alvo como float para o statsmodels.
    y = data[y_col].astype(float)
    # Fase 3: tenta ajustar, capturando separação e quaisquer erros numéricos.
    try:
        # Ajuste silencioso (disp=0 não imprime o log de iterações).
        res = sm.Logit(y, X).fit(disp=0)
    except PerfectSeparationError:
        # Separação perfeita → modelo não identificável.
        return _empty("logit", n, n_eventos, "separacao")
    except Exception:
        # Qualquer outra falha numérica → marca erro, não derruba o sweep.
        return _empty("logit", n, n_eventos, "erro")
    # Fase 4: predição in-sample binarizada em 0.5 para a acurácia de referência.
    pred = (res.predict(X) > 0.5).astype(int)
    # Fase 4: acurácia = fração de acertos in-sample.
    accuracy = float((pred.values == y.values).mean())
    # Saída: dicionário plano com todas as métricas do modelo logístico.
    return {
        # Família e contagens.
        "family": "logit", "n": n, "n_eventos": n_eventos,
        # McFadden pseudo-R² na coluna unificada r2.
        "r2": float(res.prsquared),
        # Coeficiente e p-valor do preditor de interesse (o 1º).
        "coef": float(res.params[x_cols[0]]),
        "p_value": float(res.pvalues[x_cols[0]]),
        # Log-likelihood e acurácia in-sample.
        "llf": float(res.llf), "accuracy": accuracy,
        # Ajuste bem-sucedido.
        "status": "ok",
    }


# Ajusta um OLS de um (ou mais) preditor(es) sobre o retorno contínuo e resume métricas.
def fit_ols(df: pd.DataFrame, y_col: str, x_cols: list[str], min_events: int = 5) -> dict:
    """
    Por quê: a segunda família. Roda sobre o ret_{h}d contínuo e entrega o R²
    clássico dos materiais de regressão, no MESMO schema do fit_logit.

    Lógica (Entrada → Saída):
      Entrada: df + coluna-alvo contínua (ret) + colunas-preditoras + mín. eventos.
      Fase 1: descarta NA no alvo/preditores.
      Fase 2: conta eventos; se poucos ou dummy constante → sem_eventos.
      Fase 3: ajusta o OLS com constante; captura erros.
      Fase 4: extrai r2 (clássico), coef, p_value, llf; accuracy = NaN.
      Saída: dicionário (family=ols) com as métricas e o status.
    """
    # Fase 1: mantém só as colunas relevantes e remove NA.
    data = df[[y_col, *x_cols]].dropna()
    # Fase 1: tamanho amostral efetivo.
    n = int(len(data))
    # Fase 2: nº de eventos = soma do 1º preditor.
    n_eventos = int(data[x_cols[0]].sum()) if n else 0
    # Fase 2: poucos eventos ou dummy constante → não ajusta (x sem variância quebra o OLS).
    if n_eventos < min_events or data[x_cols[0]].nunique() < 2:
        # Retorna o molde marcado como sem_eventos.
        return _empty("ols", n, n_eventos, "sem_eventos")
    # Fase 3: matriz de preditores com constante (intercepto).
    X = sm.add_constant(data[x_cols].astype(float))
    # Fase 3: vetor-alvo contínuo como float.
    y = data[y_col].astype(float)
    # Fase 3: tenta ajustar o OLS, capturando erros numéricos.
    try:
        # OLS ordinário (sem iterações; não há disp).
        res = sm.OLS(y, X).fit()
    except Exception:
        # Falha numérica → marca erro, não derruba o sweep.
        return _empty("ols", n, n_eventos, "erro")
    # Saída: dicionário plano com as métricas do OLS.
    return {
        # Família e contagens.
        "family": "ols", "n": n, "n_eventos": n_eventos,
        # R² clássico na coluna unificada r2.
        "r2": float(res.rsquared),
        # Coeficiente e p-valor do preditor de interesse.
        "coef": float(res.params[x_cols[0]]),
        "p_value": float(res.pvalues[x_cols[0]]),
        # Log-likelihood; acurácia não se aplica ao OLS.
        "llf": float(res.llf), "accuracy": np.nan,
        # Ajuste bem-sucedido.
        "status": "ok",
    }
