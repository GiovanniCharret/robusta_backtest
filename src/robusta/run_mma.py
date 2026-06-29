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


# Escreve as duas saídas em disco no formato .xlsx.
def write_outputs(analysis, summary, outdir="output"):
    """
    Por quê: isolar a escrita em disco (formato .xlsx, via engine openpyxl) da
    lógica e do download, para poder testá-la SEM rede e trocar o formato/local
    num só ponto.

    Lógica (Entrada → Saída):
      Entrada: df-fundação enriquecido, summary e a pasta de saída.
      Fase 1: garante a existência da pasta de saída.
      Fase 2: escreve o analysis (mantendo o índice de datas) em .xlsx.
      Fase 3: escreve o summary (sem o índice numérico) em .xlsx.
      Saída: tupla (caminho_analysis, caminho_summary).
    """
    # Fase 1: normaliza o destino em Path e cria a pasta (inclusive pais) se faltar.
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    # Fase 2: caminho e escrita do df-fundação por dia (índice de datas preservado).
    analysis_path = out / "analysis_mma.xlsx"
    analysis.to_excel(analysis_path)
    # Fase 3: caminho e escrita do summary de modelos (sem índice numérico).
    summary_path = out / "summary_mma.xlsx"
    summary.to_excel(summary_path, index=False)
    # Saída: os dois caminhos escritos.
    return analysis_path, summary_path


# Entrypoint de linha de comando: baixa, resume e salva os dois .xlsx.
def main(ticker: str = "^BVSP", start: str = "2010-01-01", end: str = "2024-12-31") -> None:
    """
    Por quê: ponto de entrada humano; concentra o I/O (download + escrita) fora da
    lógica pura para manter build_summary testável.

    Lógica (Entrada → Saída):
      Entrada: ticker e janela de datas.
      Fase 1: baixa os preços (rede).
      Fase 2: roda build_summary com o grid default.
      Fase 3: escreve as duas saídas .xlsx via write_outputs.
      Saída: output/analysis_mma.xlsx e output/summary_mma.xlsx em disco.
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
    # Fase 3: escreve os dois .xlsx (pasta default output/).
    analysis_path, summary_path = write_outputs(analysis, summary)
    # Fase 3: feedback no console de onde os arquivos foram salvos.
    print(f"{analysis_path.name} ({len(analysis)} dias) e {summary_path.name} ({len(summary)} modelos) salvos em output/")


# Permite rodar como script: `python -m robusta.run_mma`.
if __name__ == "__main__":
    # Chama main com os defaults.
    main()
