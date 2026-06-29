# Path para criar a pasta output e escrever os CSVs.
from pathlib import Path
# pandas para o tipo do df.
import pandas as pd
# As peças do pipeline.
from robusta.data import load_prices
from robusta.target import add_labels
from robusta.indicators import mma
from robusta.sweep import run_sweep


# Orquestração pura: de um df de preços às duas saídas (sem rede).
def build_summary(prices: pd.DataFrame, *, windows, tols, horizons, min_events: int = 5):
    """
    Por quê: separar a orquestração (testável, sem rede) do I/O (main). Recebe um
    df já carregado para que o teste e2e injete preços sintéticos.

    Lógica (Entrada → Saída):
      Entrada: df OHLCV + listas de janelas, tolerâncias e horizontes.
      Fase 1: cria os rótulos ret_{h}d/y_{h}d no df-fundação.
      Fase 2: monta o grid de parâmetros do mma.
      Fase 3: roda o sweep com o módulo mma (acumula colunas + resume).
      Saída: (analysis_df, summary_df).
    """
    # Fase 1: anexa as colunas-alvo para todos os horizontes.
    labeled = add_labels(prices, horizons=horizons)
    # Fase 2: grid de parâmetros do indicador.
    grid = {"window": windows, "tol": tols}
    # Fase 3/Saída: executa o sweep injetando o módulo plug-in mma.
    return run_sweep(labeled, mma, grid, horizons, min_events=min_events)


# Entrypoint de linha de comando: baixa, resume e salva os dois CSVs.
def main(ticker: str = "^BVSP", start: str = "2010-01-01", end: str = "2024-12-31") -> None:
    """
    Por quê: ponto de entrada humano; concentra o I/O (download + escrita) fora da
    lógica pura para manter build_summary testável.

    Lógica (Entrada → Saída):
      Entrada: ticker e janela de datas.
      Fase 1: baixa os preços (rede).
      Fase 2: roda build_summary com o grid default.
      Fase 3: garante a pasta output e escreve os dois CSVs.
      Saída: output/analysis_mma.csv e output/summary_mma.csv em disco.
    """
    # Fase 1: download dos preços do ticker.
    prices = load_prices(ticker, start, end)
    # Fase 2: gera as duas saídas com os grids default do projeto.
    analysis, summary = build_summary(
        prices,
        # Janelas default do sweep.
        windows=[5, 10, 20, 50, 200],
        # Tolerâncias default do sweep.
        tols=[0.0, 0.01, 0.03],
        # Horizontes default (a daylist).
        horizons=[10, 20, 30, 45, 90],
    )
    # Fase 3: cria a pasta output se não existir.
    Path("output").mkdir(exist_ok=True)
    # Fase 3: salva o df-fundação enriquecido COM o índice de datas (para revisão).
    analysis.to_csv("output/analysis_mma.csv")
    # Fase 3: salva o summary de modelos (sem o índice numérico).
    summary.to_csv("output/summary_mma.csv", index=False)
    # Fase 3: feedback no console de onde os arquivos foram salvos.
    print(f"analysis_mma.csv ({len(analysis)} dias) e summary_mma.csv ({len(summary)} modelos) salvos em output/")


# Permite rodar como script: `python -m robusta.run_mma`.
if __name__ == "__main__":
    # Chama main com os defaults.
    main()
