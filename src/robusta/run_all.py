# Path para a pasta de saída e o caminho do master.
from pathlib import Path
# importlib carrega cada módulo-indicador pelo nome (roster dirigido por config).
import importlib
# pandas para concat/sort e o ExcelWriter.
import pandas as pd
# Download de preços e leitura da lista de tickers (único ponto de I/O de dados).
from robusta.data import load_prices, load_tickers
# Runner genérico: orquestração + escrita + legenda compartilhadas.
from robusta.runner import build_summary, write_outputs, summary_dictionary
# Parâmetros centralizados.
from robusta import config


# Concatena os summaries e ordena por [family, chave-de-ranking] desc.
def build_master(summaries) -> pd.DataFrame:
    """
    Por quê: o master permite rankear os indicadores entre si. Como logit e ols usam
    métricas de escalas diferentes, a chave de ranking é lift (logit) / coef (ols), e
    `family` é a chave PRIMÁRIA de ordenação → lift e coef nunca são comparados entre si.

    Lógica (Entrada → Saída):
      Entrada: lista de summaries (um por indicador; params diferentes viram NaN no concat).
      Fase 1: concatena tudo num só DataFrame.
      Fase 2: chave de ranking por linha (lift se logit, senão coef).
      Fase 3: ordena por [family asc, chave desc], NaN por último; descarta a chave temporária.
      Saída: master ordenado, pronto para o summary_ALL.
    """
    # Fase 1: concatena (união de colunas; params ausentes viram NaN).
    master = pd.concat(summaries, ignore_index=True)
    # Fase 2: chave de ranking = lift nas linhas logit; coef nas demais (ols).
    sort_key = master["lift"].where(master["family"] == "logit", master["coef"])
    # Fase 3: ordena por família (primária) e pela chave (desc), NaN no fim; chave temporária removida.
    master = (
        master.assign(_sort=sort_key)
        .sort_values(["family", "_sort"], ascending=[True, False], na_position="last")
        .drop(columns="_sort")
        .reset_index(drop=True)
    )
    # Saída: master rankeável.
    return master


# Escreve o master em disco (.xlsx) com abas 'ranking' + 'dicionário'.
def write_master(master, outdir="output") -> Path:
    """
    Por quê: entregar o summary_ALL num arquivo à parte, com a legenda ao lado.

    Lógica (Entrada → Saída):
      Entrada: master e a pasta de saída.
      Fase 1: garante a pasta.
      Fase 2: grava 'ranking' (dados) e 'dicionário' (legenda derivada das colunas).
      Saída: caminho do summary_ALL.xlsx.
    """
    # Fase 1: normaliza a pasta e cria se faltar.
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    # Fase 2: caminho do master.
    path = out / "summary_ALL.xlsx"
    # Fase 2: writer para as duas abas.
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # Fase 2: aba de dados.
        master.to_excel(writer, sheet_name="ranking", index=False)
        # Fase 2: aba de legenda (mesma função do runner, cobre params variados).
        summary_dictionary(master).to_excel(writer, sheet_name="dicionário", index=False)
    # Saída: caminho escrito.
    return path


# Orquestração pura: de um df de preços a todos os arquivos + o master (sem rede).
def run_all(prices, indicators, param_grids, horizons, min_events: int = 5, outdir="output") -> pd.DataFrame:
    """
    Por quê: separar a consolidação (testável, sem rede) do I/O da main. Itera o
    roster, roda cada indicador com seu grid, grava o par por indicador e o master.

    Lógica (Entrada → Saída):
      Entrada: df OHLCV, roster, grids por indicador, horizontes, mín. eventos e pasta.
      Fase 1: para cada nome do roster, importa o módulo e roda build_summary com seu grid.
      Fase 2: grava analysis_/summary_ do indicador; acumula o summary.
      Fase 3: concatena os summaries no master e grava o summary_ALL.
      Saída: o master (também escrito em disco).
    """
    # Acumulador dos summaries por indicador.
    summaries = []
    # Fase 1: percorre o roster na ordem de config.INDICATORS.
    for name in indicators:
        # Fase 1: importa o módulo-indicador pelo nome.
        module = importlib.import_module(f"robusta.indicators.{name}")
        # Fase 1: grid do indicador (fonte única = config.PARAM_GRIDS).
        grid = param_grids[name]
        # Fase 1: roda o pipeline do indicador (sem rede).
        analysis, summary = build_summary(prices, module, grid, horizons, min_events=min_events)
        # Fase 2: grava o par de arquivos do indicador.
        write_outputs(analysis, summary, name, outdir)
        # Fase 2: guarda o summary para o master.
        summaries.append(summary)
    # Fase 3: monta e grava o master.
    master = build_master(summaries)
    write_master(master, outdir)
    # Saída: o master consolidado.
    return master


# Orquestração pura do modo MULTI-TICKER: grava SÓ o master (nenhum par por indicador).
def run_all_multi(ticker_prices, indicators, param_grids, horizons, min_events: int = 5, outdir="output") -> pd.DataFrame:
    """
    Por quê: com ~70 tickers, gravar os 21 arquivos por ticker seria inviável
    (~1.470 arquivos, GBs); o estudo comparativo entre tickers precisa apenas do
    master único com a coluna `ticker`. Recebe os preços PRONTOS (sem rede) para
    ser testável com dados sintéticos.

    Lógica (Entrada → Saída):
      Entrada: pares (ticker, df OHLCV), roster, grids, horizontes, mín. eventos e pasta.
      Fase 1: para cada ticker, roda cada indicador do roster (sem gravar pares).
      Fase 2: carimba a coluna `ticker` nas linhas de cada summary.
      Fase 3: concatena tudo no master (mesma ordenação do modo único), traz
        `ticker` para a primeira coluna e grava o summary_ALL.
      Saída: o master consolidado (1 único arquivo em disco).
    """
    # Acumulador dos summaries de todos os pares (ticker, indicador).
    summaries = []
    # Fase 1: percorre os tickers na ordem recebida.
    for ticker, prices in ticker_prices:
        # Feedback de progresso no console (execuções longas: ~70 tickers × 10 indicadores).
        print(f"[{ticker}] varrendo {len(indicators)} indicadores em {len(prices)} dias...")
        # Fase 1: percorre o roster para este ticker.
        for name in indicators:
            # Importa o módulo-indicador pelo nome.
            module = importlib.import_module(f"robusta.indicators.{name}")
            # Roda o pipeline do indicador (descarta o analysis; nada é gravado aqui).
            _, summary = build_summary(prices, module, param_grids[name], horizons, min_events=min_events)
            # Fase 2: carimba o ticker nas linhas deste summary.
            summary["ticker"] = ticker
            # Guarda o summary para o master.
            summaries.append(summary)
    # Fase 3: concatena e ordena com a MESMA regra do modo único (family + lift/coef).
    master = build_master(summaries)
    # Fase 3: traz `ticker` para a primeira coluna (a leitura do master gigante começa por ela).
    master = master[["ticker"] + [c for c in master.columns if c != "ticker"]]
    # Fase 3: grava o único arquivo do modo multi.
    write_master(master, outdir)
    # Saída: o master consolidado.
    return master


# Entrypoint de linha de comando: uma rota por modo (ticker único ou lista da B3).
def main() -> None:
    """
    Por quê: ponto de entrada humano; concentra o I/O (downloads + escrita) e decide
    a rota pela flag config.MULTI_TICKER. TODOS os parâmetros vêm de config.py.

    Lógica (Entrada → Saída):
      Entrada: nenhuma (tudo vem do config).
      Fase 1 (modo único): baixa config.TICKER e roda run_all (21 arquivos + master).
      Fase 2 (modo multi): lê a lista de config.TICKERS_FILE, baixa cada ticker com o
        sufixo do yfinance — falha de download PULA o ticker e registra — e roda
        run_all_multi (só o summary_ALL, com coluna ticker).
      Saída: arquivos na pasta do config + relato no console (inclusive pulados).
    """
    # Fase 1: rota do ticker único (comportamento original, com os pares por indicador).
    if not config.MULTI_TICKER:
        # Download único dos preços.
        prices = load_prices(config.TICKER, config.PERIOD)
        # Consolida tudo (arquivos por indicador + master).
        master = run_all(
            prices, config.INDICATORS, config.PARAM_GRIDS, config.HORIZONS,
            min_events=config.MIN_EVENTS, outdir=config.OUTPUT_DIR,
        )
        # Feedback no console e fim da rota única.
        print(f"summary_ALL.xlsx ({len(master)} linhas) + pares por indicador salvos em {config.OUTPUT_DIR}/")
        return
    # Fase 2: rota multi-ticker — lê a lista mantida à mão na planilha de entrada.
    tickers = load_tickers(config.TICKERS_FILE)
    # Acumuladores dos downloads bem-sucedidos e dos tickers pulados.
    baixados, pulados = [], []
    # Fase 2: baixa cada ticker; falha (deslistado, sem histórico, rede) pula e registra.
    for i, t in enumerate(tickers, 1):
        # Protege o run inteiro contra a falha de UM ticker.
        try:
            # Download com o sufixo do yfinance para a B3 (PETR4 -> PETR4.SA).
            prices = load_prices(f"{t}{config.TICKER_SUFFIX}", config.PERIOD)
            # Planilha vazia = sem histórico utilizável -> trata como falha.
            if len(prices) == 0:
                # Sinaliza para o except registrar o pulo.
                raise ValueError("sem histórico")
            # Guarda o par (nome SEM sufixo, preços) para o sweep.
            baixados.append((t, prices))
            # Progresso do download no console.
            print(f"[{i}/{len(tickers)}] {t}: {len(prices)} dias")
        except Exception as e:
            # Registra o ticker pulado e segue para o próximo.
            pulados.append(t)
            # Aviso no console com o motivo resumido.
            print(f"[{i}/{len(tickers)}] {t}: PULADO ({e})")
    # Fase 2: roda o sweep de todos os tickers baixados e grava só o master.
    master = run_all_multi(
        baixados, config.INDICATORS, config.PARAM_GRIDS, config.HORIZONS,
        min_events=config.MIN_EVENTS, outdir=config.OUTPUT_DIR,
    )
    # Saída: relato final, incluindo a lista de pulados (se houver).
    print(f"summary_ALL.xlsx ({len(master)} linhas, {len(baixados)} tickers) salvo em {config.OUTPUT_DIR}/")
    # Lista os pulados para revisão manual da planilha (ex.: deslistados).
    if pulados:
        # Uma linha só, legível.
        print(f"Tickers pulados ({len(pulados)}): {', '.join(pulados)}")


# Permite rodar como script: `python -m robusta.run_all`.
if __name__ == "__main__":
    # Chama main com os defaults do config.
    main()
