# O módulo de configuração centralizada sob teste.
from robusta import config
# A orquestração pura genérica, para provar que os grids do config alimentam o pipeline.
from robusta.runner import build_summary
# O mma serve de indicador-cobaia (o grid dele vem de PARAM_GRIDS, como no run_all).
from robusta.indicators import mma


# Teste: o config expõe todos os parâmetros, bem formados.
def test_config_is_wellformed():
    """
    Por quê: o config é o painel de ajustes manual; se um parâmetro sumir ou vier
    com tipo errado, o run_all quebra. Este teste trava o contrato do config.

    Lógica: Entrada (config) → Fase 1 dados → Fase 2 grids → Fase 3 modelagem/saída → Saída.
    """
    # Fase 1: ticker e period são strings não-vazias.
    assert isinstance(config.TICKER, str) and config.TICKER
    assert isinstance(config.PERIOD, str) and config.PERIOD
    # Fase 2: os dois grids compartilhados são listas não-vazias.
    for grid in (config.HORIZONS, config.PERSISTENCES):
        assert isinstance(grid, list) and len(grid) >= 1
    # Fase 2: persistências incluem 0 (o rompimento puro) — comportamento base preservado.
    assert 0 in config.PERSISTENCES
    # Fase 3: min_events é inteiro >= 1 e a pasta de saída é string não-vazia.
    assert isinstance(config.MIN_EVENTS, int) and config.MIN_EVENTS >= 1
    assert isinstance(config.OUTPUT_DIR, str) and config.OUTPUT_DIR


# Teste: o grid do config gera o nº esperado de modelos (integração, sem rede).
def test_config_grids_drive_build_summary(synthetic_prices):
    """
    Por quê: garantir que o grid do config é válido e atravessa o pipeline genérico
    (o mesmo caminho do run_all) — nº de linhas = produto do PARAM_GRIDS["mma"]
    × |horizons| × 2 famílias.

    Lógica: Entrada (config + preços sintéticos) → Fase 1 build_summary genérico
    com o grid do mma → Fase 2 contagem.
    """
    # Fase 1: o grid do mma vem EXATAMENTE do painel (como o run_all o consome).
    grid = config.PARAM_GRIDS["mma"]
    # Fase 1: roda o pipeline genérico injetando o módulo mma.
    _, summary = build_summary(
        synthetic_prices, mma, grid, config.HORIZONS, min_events=config.MIN_EVENTS
    )
    # Fase 2: o esperado parte de 2 famílias × nº de horizontes.
    esperado = 2 * len(config.HORIZONS)
    # Fase 2: cada dimensão do grid multiplica o nº de combinações.
    for valores in grid.values():
        # Multiplica pela cardinalidade da dimensão.
        esperado *= len(valores)
    # Saída: contagem bate com o produto do grid × horizontes × 2 famílias.
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
