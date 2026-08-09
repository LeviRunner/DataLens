# =============================================================================
# MODELO DE ESTUDO — tests/test_ranking.py
# -----------------------------------------------------------------------------
# O QUE ESTE ARQUIVO PROTEGE: o unico modulo do projeto que produz uma RECOMENDACAO.
#
# Perfil, correlacao e tendencia descrevem o passado. Um Top 10 diz "compre esta".
# A diferenca importa no teste: um erro no profiling mostra um numero feio na tela;
# um erro aqui manda alguem colocar dinheiro no lugar errado com a nossa assinatura
# embaixo. Por isso os testes daqui sao de VALOR CONFERIVEL A MAO, nao de "roda sem
# estourar" — cada cenario tem o resultado calculado no comentario.
#
# OS TRES ERROS CLASSICOS QUE ESTES TESTES EXISTEM PARA PEGAR:
#
#   1. Comparar retorno com CDI SEM COMPOR. Selic vem em "% ao dia" (0,052). Somar
#      252 dias da 13,1%; compor da 13,98%. Quem soma entrega um premio inflado em
#      quase um ponto para TODA acao — o ranking ate sobrevive, o numero na tela nao.
#   2. Anualizar volatilidade multiplicando por 252 em vez de por sqrt(252). O erro
#      infla o risco em 15x e derruba o Sharpe de todo mundo igualmente: o ranking
#      continua "certo" e o numero continua absurdo. Teste com valor exato ou nada.
#   3. Alinhar preco e CDI por POSICAO em vez de por DATA. Feriado no Brasil que nao
#      e feriado nos EUA desloca a serie inteira, e o premio da AAPL passa a ser
#      medido contra o CDI de outro dia. `join(how="inner")` na data, sempre.
#
# O QUE NAO SE TESTA AQUI: se WEGE3 e uma boa compra. Isso nao e afirmacao de
# software, e o modulo nao tem opiniao sobre isso — ele ordena por Sharpe e DIZ que
# ordenou por Sharpe. Um teste que fixasse o vencedor esperado seria um teste sobre
# o mercado, e o mercado nao esta no controle de versao.
# =============================================================================

"""Tests for the ranking module: the cross between prices and a macro benchmark."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from datalens.i18n import DataLensError
from datalens.ranking import (
    MIN_TRADING_DAYS,
    TRADING_DAYS_PER_YEAR,
    AnalysisError,
    benchmark_series,
    extremes,
    price_panel,
    rank,
)

# --- Cenarios -----------------------------------------------------------------

DAYS = 300  # folgado acima de MIN_TRADING_DAYS, e o bastante para MA50 e IFR14


def _business_days(count: int = DAYS) -> pd.DatetimeIndex:
    """Dias uteis de verdade: a serie tem buraco no fim de semana de proposito."""
    return pd.bdate_range("2024-01-01", periods=count)


def _prices(ticker: str, daily_return: float, count: int = DAYS) -> pd.DataFrame:
    """Uma acao que sobe (ou cai) exatamente `daily_return` por dia util.

    Retorno constante quer dizer volatilidade ZERO — proposital: separa o teste do
    retorno do teste do risco. Cada numero de cada vez.
    """
    dates = _business_days(count)
    prices = [100.0 * (1 + daily_return) ** position for position in range(count)]
    return pd.DataFrame({"ticker": ticker, "date": dates, "close": prices})


def _benchmark_frame(daily_percent: float = 0.05, count: int = DAYS) -> pd.DataFrame:
    """O SGS 11 como ele chega: coluna `valor` em % AO DIA, data como texto."""
    dates = _business_days(count)
    return pd.DataFrame(
        {
            "data": [date.strftime("%d/%m/%Y") for date in dates],
            "valor": [str(daily_percent)] * count,
        }
    )


@pytest.fixture
def benchmark() -> pd.Series:
    return benchmark_series(_benchmark_frame(), date_column="data", rate_column="valor")


# --- A normalizacao da entrada ------------------------------------------------


def test_the_benchmark_arrives_as_percent_per_day_and_leaves_as_a_decimal_rate():
    """0,05 "% a.d." e 0,0005 ao dia. Errar aqui multiplica o CDI por 100."""
    # Act
    series = benchmark_series(
        _benchmark_frame(0.05), date_column="data", rate_column="valor"
    )

    # Assert
    assert series.iloc[0] == pytest.approx(0.0005)
    assert isinstance(series.index, pd.DatetimeIndex)


def test_the_benchmark_reads_the_brazilian_date_the_bcb_sends():
    """`02/01/2026` e 2 de janeiro, nunca 1 de fevereiro."""
    # Arrange
    frame = pd.DataFrame({"data": ["02/01/2026"], "valor": ["0.052"]})

    # Act
    series = benchmark_series(frame, date_column="data", rate_column="valor")

    # Assert
    assert series.index[0] == pd.Timestamp("2026-01-02")


def test_a_repeated_date_in_the_benchmark_keeps_one_row():
    """A API reenviada duas vezes nao pode dobrar o juro do dia."""
    # Arrange
    frame = pd.DataFrame(
        {"data": ["02/01/2026", "02/01/2026"], "valor": ["0.052", "0.052"]}
    )

    # Act
    series = benchmark_series(frame, date_column="data", rate_column="valor")

    # Assert
    assert len(series) == 1


def test_the_panel_refuses_a_frame_without_the_columns_it_needs():
    """Mensagem que nomeia a coluna que falta - "dados invalidos" nao e resposta."""
    # Arrange
    frame = pd.DataFrame({"ticker": ["PETR4.SA"], "preco": [40.0]})

    # Act / Assert
    with pytest.raises(AnalysisError) as raised:
        price_panel(frame)

    assert raised.value.message.code == "ranking_missing_column"
    assert isinstance(raised.value, DataLensError)


def test_the_panel_reads_prices_written_the_brazilian_way():
    """`1.234,56` e mil duzentos e trinta e quatro - o parse vem do detector."""
    # Arrange
    frame = pd.DataFrame(
        {"ticker": ["PETR4.SA"], "date": ["02/01/2026"], "close": ["1.234,56"]}
    )

    # Act
    panel = price_panel(frame)

    # Assert
    assert panel["price"].iloc[0] == pytest.approx(1234.56)


# --- O premio sobre o benchmark -----------------------------------------------


def test_the_benchmark_return_is_compounded_not_summed():
    """★ O teste do erro nº 1.

    252 dias uteis a 0,05% ao dia:
        somando:  252 * 0,0005            = 0,12600  (12,60%)
        compondo: 1,0005**252 - 1         = 0,13418  (13,42%)
    O modulo tem que devolver o segundo.
    """
    # Arrange
    panel = price_panel(_prices("FLAT", 0.0, count=253))
    series = benchmark_series(
        _benchmark_frame(0.05, count=253), date_column="data", rate_column="valor"
    )

    # Act
    score = rank(panel, series)[0]

    # Assert
    assert score.benchmark_return == pytest.approx(1.0005**252 - 1, rel=1e-9)
    assert score.benchmark_return != pytest.approx(252 * 0.0005, rel=1e-3)


def test_an_asset_that_does_not_move_loses_to_the_benchmark():
    """Preco parado com CDI positivo e premio negativo. Um ranking que nao consegue
    dizer "isto perdeu" so sabe elogiar.
    """
    # Arrange
    panel = price_panel(_prices("FLAT", 0.0))

    # Act
    score = rank(panel, benchmark_series(
        _benchmark_frame(), date_column="data", rate_column="valor"
    ))[0]

    # Assert
    assert score.total_return == pytest.approx(0.0)
    assert score.excess_return < 0


def test_the_excess_is_the_accumulated_return_minus_the_accumulated_benchmark(benchmark):
    # Arrange
    panel = price_panel(_prices("UP", 0.001))

    # Act
    score = rank(panel, benchmark)[0]

    # Assert
    assert score.excess_return == pytest.approx(
        score.total_return - score.benchmark_return
    )


# --- O risco ------------------------------------------------------------------


def test_volatility_is_annualised_by_the_square_root_of_time():
    """★ O teste do erro nº 2.

    Retornos alternando +1% e -1%: o desvio-padrao diario e conhecido, e o anual
    tem que ser ele vezes sqrt(252) - nunca vezes 252.
    """
    # Arrange
    dates = _business_days(DAYS)
    prices, price = [], 100.0
    for step in range(DAYS):
        prices.append(price)
        price *= 1.01 if step % 2 == 0 else 1 / 1.01
    frame = pd.DataFrame({"ticker": "ZIGZAG", "date": dates, "close": prices})
    daily = pd.Series(prices).pct_change().dropna()

    # Act
    score = rank(
        price_panel(frame),
        benchmark_series(
            _benchmark_frame(0.0), date_column="data", rate_column="valor"
        ),
    )[0]

    # Assert
    expected = daily.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)
    assert score.volatility == pytest.approx(expected, rel=1e-6)


def test_a_constant_return_has_no_volatility_and_no_infinite_sharpe():
    """Divisao por zero disfarcada: volatilidade zero com premio positivo daria
    infinito, e `inf` no topo do ranking e a pior recomendacao possivel.
    """
    # Arrange
    panel = price_panel(_prices("UP", 0.001))

    # Act
    score = rank(panel, benchmark_series(
        _benchmark_frame(), date_column="data", rate_column="valor"
    ))[0]

    # Assert
    assert score.volatility == pytest.approx(0.0, abs=1e-9)
    assert math.isfinite(score.sharpe)


def test_the_drawdown_is_the_worst_fall_from_a_peak(benchmark):
    """Sobe de 100 a 200, cai a 150, volta a 210: o pior tombo foi -25%, mesmo com
    o resultado final positivo. Drawdown mede o caminho, nao o destino.
    """
    # Arrange
    dates = _business_days(MIN_TRADING_DAYS + 10)
    half = len(dates) // 2
    prices = (
        list(pd.Series(range(half)).map(lambda step: 100.0 + step))
        + [200.0, 150.0]
        + [210.0] * (len(dates) - half - 2)
    )
    frame = pd.DataFrame({"ticker": "PEAK", "date": dates, "close": prices})

    # Act
    score = rank(price_panel(frame), benchmark, minimum_days=MIN_TRADING_DAYS)[0]

    # Assert
    assert score.max_drawdown == pytest.approx(-0.25)


# --- A ordenacao --------------------------------------------------------------


def test_the_ranking_puts_the_better_risk_adjusted_asset_first(benchmark):
    """Duas acoes com o MESMO retorno e riscos diferentes: quem oscilou menos ganha.

    Se este teste passar com as duas em qualquer ordem, o ranking esta ordenando por
    retorno e chamando de risco-ajustado.
    """
    # Arrange
    steady = _prices("STEADY", 0.001)
    dates, prices, price = _business_days(DAYS), [], 100.0
    for step in range(DAYS):
        prices.append(price)
        # Mesmo retorno medio composto, entregue aos trancos.
        price *= 1.021 if step % 2 == 0 else (1.001**2) / 1.021
    noisy = pd.DataFrame({"ticker": "NOISY", "date": dates, "close": prices})

    # Act
    scores = rank(price_panel(pd.concat([noisy, steady])), benchmark)

    # Assert
    assert [score.ticker for score in scores][0] == "STEADY"
    assert scores[0].sharpe > scores[1].sharpe


def test_a_negative_premium_cannot_produce_a_positive_sharpe(benchmark):
    """★ O erro que so aparece com dado real, e que nao parece erro.

    Uma acao que alterna +10% e -9,09% termina EXATAMENTE onde comecou: retorno zero,
    abaixo do CDI. Mas a MEDIA ARITMETICA dos excessos diarios dela e positiva
    (+0,45% ao dia), porque a media ignora que perder 50% exige ganhar 100% para
    voltar. Um Sharpe construido sobre essa media sai POSITIVO para quem perdeu do
    benchmark - e a tabela mostra "-37% vs CDI" na linha ordenada acima de "-11%".

    O que ordena tem que ser a mesma grandeza que a linha exibe. Dai o excesso
    geometrico: se o premio e negativo, o Sharpe e negativo.
    """
    # Arrange
    dates, prices, price = _business_days(DAYS), [], 100.0
    for step in range(DAYS):
        prices.append(price)
        price *= 1.10 if step % 2 == 0 else 1 / 1.10
    frame = pd.DataFrame({"ticker": "SWINGER", "date": dates, "close": prices})

    # Act
    score = rank(price_panel(frame), benchmark)[0]

    # Assert
    # Sobe e desce nas mesmas proporcoes: acaba perto de onde comecou, e o CDI do
    # periodo passa na frente com folga.
    assert score.total_return < score.benchmark_return
    assert score.excess_return < 0
    assert score.sharpe < 0


def test_the_ranking_returns_at_most_the_requested_number(benchmark):
    # Arrange
    frames = [_prices(f"T{index}", 0.0005 + index / 10_000) for index in range(15)]

    # Act
    scores = rank(price_panel(pd.concat(frames)), benchmark, top=10)

    # Assert
    assert len(scores) == 10


def test_a_ticker_without_enough_history_is_left_out_not_ranked_badly(benchmark):
    """★ O silencio e a resposta certa aqui.

    Uma acao com 5 dias de historico nao "vai mal no ranking": ela nao tem ranking.
    Rankeada com 5 pontos, a volatilidade dela e ruido e o Sharpe pode sair enorme -
    e uma IPO de tres dias aparece em primeiro lugar.
    """
    # Arrange
    panel = price_panel(pd.concat([_prices("LONG", 0.001), _prices("NEW", 0.05, 5)]))

    # Act
    scores = rank(panel, benchmark)

    # Assert
    assert [score.ticker for score in scores] == ["LONG"]


def test_no_ticker_with_enough_history_is_an_error_not_an_empty_table(benchmark):
    """Tabela vazia sem explicacao le-se como "nenhuma acao presta"."""
    # Arrange
    panel = price_panel(_prices("NEW", 0.01, count=5))

    # Act / Assert
    with pytest.raises(AnalysisError) as raised:
        rank(panel, benchmark)

    assert raised.value.message.code == "ranking_history_too_short"


# --- O alinhamento por data ---------------------------------------------------


def test_price_and_benchmark_are_paired_by_date_not_by_position(benchmark):
    """★ O teste do erro nº 3.

    O benchmark comeca 40 dias DEPOIS da serie de precos. Pareando por posicao, o
    premio sairia calculado contra o juro de outro dia e o resultado mudaria; pareando
    por data, so os dias em comum entram, e a conta bate com o periodo em comum.
    """
    # Arrange
    panel = price_panel(_prices("UP", 0.001))
    shifted = benchmark.iloc[40:]

    # Act
    score = rank(panel, shifted)[0]

    # Assert
    # `days` conta os dias pareados; o primeiro nao vira retorno (nao ha vespera),
    # e por isso o benchmark acumula a partir do segundo.
    assert score.days == len(shifted)
    assert score.benchmark_return == pytest.approx(
        (1 + shifted.iloc[1:]).prod() - 1, rel=1e-9
    )


# --- O porque, que e o que vai para a tela ------------------------------------


def test_every_score_explains_itself_in_message_codes_not_sentences(benchmark):
    """A razao viaja como codigo + parametros, igual a um erro. Uma frase pronta aqui
    seria uma frase em uma lingua so, na tela que tem seletor de idioma.
    """
    # Arrange
    panel = price_panel(_prices("UP", 0.001))

    # Act
    score = rank(panel, benchmark)[0]

    # Assert
    assert score.reasons
    assert all(reason.code.startswith("reason_") for reason in score.reasons)


def test_a_winner_is_told_apart_from_a_loser_in_the_reasons(benchmark):
    # Arrange
    winner = rank(price_panel(_prices("UP", 0.002)), benchmark)[0]
    loser = rank(price_panel(_prices("DOWN", -0.002)), benchmark)[0]

    # Act
    codes = {"winner": [r.code for r in winner.reasons], "loser": [r.code for r in loser.reasons]}

    # Assert
    assert "reason_beat_benchmark" in codes["winner"]
    assert "reason_lost_to_benchmark" in codes["loser"]


def test_every_reason_code_exists_in_every_language():
    """Uma razao sem traducao vira `[reason_x] {...}` na tela do usuario."""
    # Arrange
    from datalens.i18n import CATALOG

    # Act
    codes = {code for code in CATALOG["en"] if code.startswith(("reason_", "ranking_"))}

    # Assert
    assert codes, "nenhum codigo de ranking no catalogo"
    for language in ("pt_BR", "es"):
        assert not codes - set(CATALOG[language]), f"faltam traducoes em {language}"


# --- Os extremos que vao para o grafico ---------------------------------------


def test_the_extremes_take_the_best_and_the_worst(benchmark):
    """Os dois lados da tabela, na ordem do ranking."""
    # Arrange
    panel = price_panel(
        pd.concat([_prices(f"T{index}", 0.0002 * index) for index in range(10)])
    )
    scores = rank(panel, benchmark, top=10)

    # Act
    ends = extremes(scores, 4)

    # Assert
    assert [score.ticker for score in ends] == [
        scores[0].ticker, scores[1].ticker, scores[-2].ticker, scores[-1].ticker
    ]


def test_a_short_list_is_not_counted_twice(benchmark):
    """★ O bug que so aparece depois de um filtro.

    Com 6 ativos e 8 posicoes pedidas, `scores[:4] + scores[-4:]` repete os dois do
    meio. No grafico, a repeticao vira duas barras na MESMA linha, empilhadas: le-se
    como uma barra mais larga, e o ativo repetido parece maior do que e.
    """
    # Arrange
    panel = price_panel(
        pd.concat([_prices(f"T{index}", 0.0002 * index) for index in range(6)])
    )
    scores = rank(panel, benchmark, top=6)

    # Act
    ends = extremes(scores, 8)

    # Assert
    tickers = [score.ticker for score in ends]
    assert len(tickers) == len(set(tickers)), "ativo repetido na selecao"
    assert len(tickers) == 6


def test_asking_for_exactly_as_many_as_there_are_changes_nothing(benchmark):
    # Arrange
    panel = price_panel(
        pd.concat([_prices(f"T{index}", 0.0002 * index) for index in range(4)])
    )
    scores = rank(panel, benchmark, top=4)

    # Act / Assert
    assert extremes(scores, 4) == scores


# --- Tabela vazia -------------------------------------------------------------


def test_an_empty_quote_table_says_it_is_empty(benchmark):
    """★ A mensagem errada que apareceu na tela de verdade.

    Um frame sem linha nenhuma nao tem formato de data para descobrir, e a busca de
    formato devolvia "nao consegui ler a coluna como datas" — mandando o leitor
    investigar o formato de um dado que nao existe.

    Aconteceu ao abrir o app no meio de um download: as cotacoes ja estavam gravadas,
    a tabela de indicadores ainda nao. A causa era "a tabela esta vazia" e a tela
    dizia "as datas estao ilegiveis"; as duas frases mandam procurar em lugares
    diferentes, e so uma delas tinha razao.
    """
    # Arrange
    vazio = pd.DataFrame({"ticker": [], "date": [], "close": []})

    # Act / Assert
    with pytest.raises(AnalysisError) as raised:
        price_panel(vazio)

    assert raised.value.message.code == "ranking_no_prices"


def test_an_empty_benchmark_says_it_is_empty():
    # Arrange
    vazio = pd.DataFrame({"data": [], "valor": []})

    # Act / Assert
    with pytest.raises(AnalysisError) as raised:
        benchmark_series(vazio, date_column="data", rate_column="valor")

    assert raised.value.message.code == "ranking_no_benchmark"
