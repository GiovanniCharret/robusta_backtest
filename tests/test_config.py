# O módulo de configuração centralizada sob teste.
from robusta import config
# A orquestração pura, para provar que os grids do config alimentam o pipeline.
from robusta.run_mma import build_summary


# Teste: o config expõe todos os parâmetros, bem formados.
def test_config_is_wellformed():
    """
    Por quê: o config é o painel de ajustes manual; se um parâmetro sumir ou vier
    com tipo errado, o run_mma quebra. Este teste trava o contrato do config.

    Lógica: Entrada (config) → Fase 1 dados → Fase 2 grids → Fase 3 modelagem/saída → Saída.
    """
    # Fase 1: ticker e period são strings não-vazias.
    assert isinstance(config.TICKER, str) and config.TICKER
    assert isinstance(config.PERIOD, str) and config.PERIOD
    # Fase 2: os quatro grids são listas não-vazias.
    for grid in (config.MMA_WINDOWS, config.TOLERANCES, config.HORIZONS, config.PERSISTENCES):
        assert isinstance(grid, list) and len(grid) >= 1
    # Fase 2: persistências incluem 0 (o rompimento puro) — comportamento base preservado.
    assert 0 in config.PERSISTENCES
    # Fase 3: min_events é inteiro >= 1 e a pasta de saída é string não-vazia.
    assert isinstance(config.MIN_EVENTS, int) and config.MIN_EVENTS >= 1
    assert isinstance(config.OUTPUT_DIR, str) and config.OUTPUT_DIR


# Teste: os grids do config geram o nº esperado de modelos (integração, sem rede).
def test_config_grids_drive_build_summary(synthetic_prices):
    """
    Por quê: garantir que os grids do config são válidos e atravessam o pipeline —
    nº de linhas = |windows|×|tols|×|persists|×|horizons|×2 famílias.

    Lógica: Entrada (config + preços sintéticos) → Fase 1 build_summary → Fase 2 contagem.
    """
    # Fase 1: roda o pipeline com EXATAMENTE os grids do config.
    _, summary = build_summary(
        synthetic_prices,
        windows=config.MMA_WINDOWS,
        tols=config.TOLERANCES,
        horizons=config.HORIZONS,
        persists=config.PERSISTENCES,
        min_events=config.MIN_EVENTS,
    )
    # Fase 2/Saída: contagem bate com o produto do grid × 2 famílias.
    esperado = (
        len(config.MMA_WINDOWS) * len(config.TOLERANCES)
        * len(config.PERSISTENCES) * len(config.HORIZONS) * 2
    )
    assert len(summary) == esperado


# Teste: o roster e os grids do multi-indicador estão bem formados e casados.
def test_indicators_and_param_grids_wellformed():
    """
    Por quê: o run_all itera INDICATORS e busca PARAM_GRIDS[nome]; se o roster e os
    grids desalinharem, o run_all quebra com KeyError. Este teste trava o contrato.

    Lógica: Entrada (config) → Fase 1 roster → Fase 2 grids → Fase 3 casamento → Saída.
    """
    # Fase 1: INDICATORS é lista não-vazia de strings, com o mma incluído.
    assert isinstance(config.INDICATORS, list) and config.INDICATORS
    assert all(isinstance(n, str) and n for n in config.INDICATORS)
    assert "mma" in config.INDICATORS
    # Fase 2: PARAM_GRIDS é dict; cada grid é dict de listas não-vazias.
    assert isinstance(config.PARAM_GRIDS, dict)
    for nome, grid in config.PARAM_GRIDS.items():
        assert isinstance(grid, dict) and grid
        for valores in grid.values():
            assert isinstance(valores, list) and len(valores) >= 1
    # Fase 3: todo indicador do roster tem um grid, e vice-versa.
    assert set(config.INDICATORS) == set(config.PARAM_GRIDS)
    # Fase 4: persist existe em TODO grid; regimes varrem PERSISTENCES, eventos ficam em [0].
    for grid in config.PARAM_GRIDS.values():
        assert "persist" in grid
    assert config.PERSISTENCES == [0, 1, 2, 3, 4]
    assert config.PARAM_GRIDS["mma"]["persist"] == config.PERSISTENCES
    # Fase 4: os dois indicadores de evento pontual não varrem persistência...
    assert config.PARAM_GRIDS["alto_volume"]["persist"] == [0]
    assert config.PARAM_GRIDS["exaustao_atr"]["persist"] == [0]
    # Fase 4/Saída: ...mas varrem a confirmação de PREÇO (o preço segurou k dias após o evento?).
    assert config.PARAM_GRIDS["alto_volume"]["confirm"] == [0, 1, 2, 3, 4]
    assert config.PARAM_GRIDS["exaustao_atr"]["confirm"] == [0, 1, 2, 3, 4]
