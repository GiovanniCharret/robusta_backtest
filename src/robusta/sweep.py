# itertools.product expande o grid de parâmetros em combinações.
from itertools import product
# pandas para montar o DataFrame de summary.
import pandas as pd
# As duas famílias de ajuste + a associação 2×2 (complementa o logit).
from robusta.modeling import fit_logit, fit_ols, contingency_metrics


# Percorre o grid, acumula colunas no df-fundação e resume cada modelo (2 famílias).
def run_sweep(df, indicator, param_grid, horizons, min_events=5):
    """
    Por quê: orquestrar o backtest sem conhecer o indicador — recebe o MÓDULO do
    indicador por injeção e usa sua interface (NAME/signal_col/add_columns). Mantém
    o princípio de "um df-fundação que acumula colunas" e entrega as duas saídas.

    Lógica (Entrada → Saída):
      Entrada: df já rotulado, o módulo do indicador, o grid {param: [valores]},
        a lista de horizontes e o mínimo de eventos.
      Fase 1: expande o grid em todas as combinações de parâmetros.
      Fase 2: para cada combinação, ACRESCENTA as colunas do indicador ao df.
      Fase 3: por horizonte, ajusta logit (+associação 2×2) e ols → DUAS linhas.
      Fase 4: monta o summary e ordena por [family, r2] (r2 desc, NaN no fim).
      Saída: (analysis_df enriquecido, summary_df).
    """
    # Molde NaN da associação 2×2 para a linha ols (não se aplica a alvo contínuo).
    nan_cont = {"odds_ratio": float("nan"), "lift": float("nan"), "fisher_p": float("nan")}
    # Fase 1: nomes dos parâmetros e listas de valores, na mesma ordem.
    names = list(param_grid.keys())
    # Fase 1: todas as combinações cartesianas dos valores.
    combos = list(product(*[param_grid[k] for k in names]))
    # df-fundação que vamos enriquecer ao longo do laço (sweep é dono dele).
    analysis = df
    # Acumulador das linhas do summary.
    rows = []
    # Fase 2: itera cada combinação de parâmetros.
    for combo in combos:
        # Fase 2: mapeia nome→valor desta combinação.
        params = dict(zip(names, combo))
        # Fase 2: ACRESCENTA as colunas do indicador ao df-fundação.
        analysis = indicator.add_columns(analysis, **params)
        # Fase 2: nome canônico da coluna-dummy desta combinação.
        x_col = indicator.signal_col(**params)
        # Fase 3: ajusta as duas famílias por horizonte.
        for h in horizons:
            # Fase 3: bloco de identificação compartilhado pelas duas linhas.
            ident = {"indicator": indicator.NAME, **params, "horizon": h}
            # Fase 3: logística sobre o alvo binário y_{h}d.
            logit = fit_logit(analysis, y_col=f"y_{h}d", x_cols=[x_col], min_events=min_events)
            # Fase 3: associação 2×2 (rompimento × alta) — complementa o logit.
            cont = contingency_metrics(analysis, y_col=f"y_{h}d", x_cols=[x_col], min_events=min_events)
            # Fase 3: OLS sobre o retorno contínuo ret_{h}d.
            ols = fit_ols(analysis, y_col=f"ret_{h}d", x_cols=[x_col], min_events=min_events)
            # Fase 3: linha logit = identificação + métricas do fit + associação 2×2.
            rows.append({**ident, **logit, **cont})
            # Fase 3: linha ols = identificação + métricas do fit + associação NaN.
            rows.append({**ident, **ols, **nan_cont})
    # Fase 4: DataFrame com todas as linhas de modelo.
    summary = pd.DataFrame(rows)
    # Fase 4: ordena por família e r2 desc; na_position='last' joga NaN pro fim.
    summary = summary.sort_values(["family", "r2"], ascending=[True, False], na_position="last").reset_index(drop=True)
    # Saída: o df-fundação enriquecido e o summary.
    return analysis, summary
