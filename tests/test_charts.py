# =============================================================================
# MODELO DE ESTUDO — tests/test_charts.py              (Dia 17)
# -----------------------------------------------------------------------------
# API proposta:
#     def distribution_chart(df, column, column_type) -> go.Figure
#     def time_series_chart(df, date_column, value_column, group_by=None) -> go.Figure
#
# O QUE SE TESTA NUM GRAFICO — e o que NAO se testa:
#
#   NAO: cor, fonte, margem, posicao da legenda. Isso e design, muda toda semana, e
#        um teste que trava a cor so cria trabalho sem pegar bug.
#   SIM: o TIPO de grafico escolhido para cada tipo de dado. Essa e a regra de negocio
#        do Dia 17 ("qual grafico para qual pergunta"), e trocar histograma por linha
#        num dado categorico e um erro de analise, nao de estilo.
#   SIM: que os dados chegaram ao grafico, e que ele nao mente.
#
# `go.Figure` guarda os dados em `figure.data` (tuplas de traces). Um trace tem
# `.type` ("histogram", "bar", "scatter"), e os valores em `.x` / `.y`. E so isso que
# os testes daqui olham.
#
# -----------------------------------------------------------------------------
# O QUE O FLOCO DE NEVE TROUXE: **NAO EXISTE TIPO DATE NO SQLITE.**
#
# `calendar.date`, `quotes.date`, `payouts.ex_date` sao todos `TEXT`. O pandas le
# `TEXT` como `object`, e o Plotly, ao receber object, trata o eixo como CATEGORIA.
#
# O grafico sai parecido — ISO ordena alfabeticamente, entao a ordem ate acerta — e e
# por isso que o bug sobrevive a revisao. O que quebra e a DISTANCIA: 02/01 e 03/03
# aparecem lado a lado, igualmente espacados, e a serie inteira passa a mentir sobre
# o tempo. Zoom por periodo e media movel param de fazer sentido junto.
#
# Regra que sai daqui: `time_series_chart` converte a coluna de data para datetime
# antes de plotar. E a UNICA conversao que um modulo de grafico tem direito de fazer,
# e existe porque o eixo temporal e uma propriedade do grafico, nao do dado.
# =============================================================================

"""Tests for the chart builders.

Charts are tested for the decision they encode - which chart for which question -
not for how they look.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pytest

from datalens.charts import (
    MAX_PIE_SLICES,
    distribution_chart,
    ranked_bars,
    share_pie,
    time_series_chart,
)


# --- The right chart for the right question -----------------------------------


def test_a_numeric_column_gets_a_histogram():
    """Continuous data - the question is 'how is it spread?', so: histogram."""
    # Arrange
    df = pd.DataFrame({"close": [10.0, 11.0, 12.0, 11.5, 10.5]})

    # Act
    figure = distribution_chart(df, "close", "numeric")

    # Assert
    assert isinstance(figure, go.Figure)
    assert figure.data[0].type == "histogram"


def test_a_category_column_gets_a_bar_chart():
    """Discrete data - the question is 'how many of each?', so: bar.

    A histogram of categories is the classic beginner mistake: it implies an order
    and a distance between categories that do not exist.
    """
    # Arrange
    df = pd.DataFrame({"sector": ["Finance", "Retail", "Finance"]})

    # Act
    figure = distribution_chart(df, "sector", "category")

    # Assert
    assert figure.data[0].type == "bar"


def test_a_date_column_gets_a_line_over_time():
    # Arrange
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "close": [10.0, 11.0, 12.0],
        }
    )

    # Act
    figure = time_series_chart(df, "date", "close")

    # Assert
    assert figure.data[0].type in {"scatter", "scattergl"}
    assert figure.data[0].mode == "lines"


def test_a_binary_flag_gets_a_bar_chart_not_a_histogram():
    """NOVO — as flags 0/1 do floco (`is_business_day`, `is_tradable`).

    O tipo chega como `boolean` porque o usuario corrigiu o detector. Duas barras
    ("verdadeiro" e "falso") respondem a pergunta; um histograma de dois valores
    desenha uma distribuicao onde nao ha distribuicao nenhuma.
    """
    # Arrange
    df = pd.DataFrame({"is_business_day": [True, True, False, True]})

    # Act
    figure = distribution_chart(df, "is_business_day", "boolean")

    # Assert
    assert figure.data[0].type == "bar"
    assert len(figure.data[0].x) == 2


# --- The data actually reaches the chart --------------------------------------


def test_the_series_carries_every_point():
    # Arrange
    df = pd.DataFrame(
        {"date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "close": [10.0, 11.0]}
    )

    # Act
    figure = time_series_chart(df, "date", "close")

    # Assert
    assert list(figure.data[0].y) == [10.0, 11.0]


def test_the_bar_chart_shows_the_real_counts():
    # Arrange - Finance 2, Retail 1
    df = pd.DataFrame({"sector": ["Finance", "Retail", "Finance"]})

    # Act
    figure = distribution_chart(df, "sector", "category")

    # Assert
    counts = dict(zip(figure.data[0].x, figure.data[0].y))
    assert counts["Finance"] == 2


def test_a_grouped_series_draws_one_line_per_group():
    """Two tickers on one axis is the whole point of the finance dataset."""
    # Arrange
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-01"]),
            "close": [10.0, 210.0],
            "ticker": ["PETR4.SA", "AAPL"],
        }
    )

    # Act
    figure = time_series_chart(df, "date", "close", group_by="ticker")

    # Assert
    assert len(figure.data) == 2


def test_each_group_is_named_so_the_legend_means_something():
    """NOVO. Duas linhas sem nome sao "trace 0" e "trace 1" na legenda.

    Com `group_by="ticker"` vindo de um JOIN do floco, o nome do grupo E a informacao:
    e o unico jeito de saber qual linha e a Petrobras.
    """
    # Arrange
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-02"]),
            "close": [40.0, 210.0],
            "ticker": ["PETR4.SA", "AAPL"],
        }
    )

    # Act
    figure = time_series_chart(df, "date", "close", group_by="ticker")

    # Assert
    assert {trace.name for trace in figure.data} == {"PETR4.SA", "AAPL"}


# --- The chart must not lie ---------------------------------------------------


def test_the_axes_are_labelled_with_the_column_names():
    """An unlabelled axis is a lying chart - the reader cannot tell what they see."""
    # Arrange
    df = pd.DataFrame({"close": [1.0, 2.0]})

    # Act
    figure = distribution_chart(df, "close", "numeric")

    # Assert
    assert "close" in (figure.layout.xaxis.title.text or "")


def test_missing_values_are_dropped_and_not_plotted_as_zero():
    """Plotting NaN as 0 invents a crash that never happened."""
    # Arrange
    df = pd.DataFrame(
        {"date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "close": [10.0, None]}
    )

    # Act
    figure = time_series_chart(df, "date", "close")

    # Assert
    assert 0 not in list(figure.data[0].y)


# --- A data que veio do SQLite como TEXT --------------------------------------


def test_an_iso_text_date_becomes_a_real_time_axis():
    """★ O teste que o floco de neve obrigou a existir.

    A coluna chega como string ISO, exatamente como o SQLite entrega. Se o grafico
    plotar a string crua, o eixo vira categoria e a serie mente sobre o tempo.

    Note o BURACO de dois meses entre 03/01 e 03/03: com eixo categorico, os tres
    pontos ficam igualmente espacados e o buraco desaparece do desenho.
    """
    # Arrange
    df = pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-03", "2026-03-03"],
            "close": [40.0, 41.5, 55.0],
        }
    )

    # Act
    figure = time_series_chart(df, "date", "close")

    # Assert
    assert figure.layout.xaxis.type in (None, "date")
    assert pd.api.types.is_datetime64_any_dtype(pd.Series(figure.data[0].x))


def test_text_dates_out_of_order_are_plotted_chronologically():
    """Um `SELECT` sem `ORDER BY` devolve na ordem que o banco quiser.

    Grafico de linha liga os pontos NA ORDEM DO VETOR: fora de ordem, a linha vai e
    volta no tempo e desenha um ziguezague que nunca aconteceu. Ordenar e trabalho do
    grafico, porque so o grafico depende disso.
    """
    # Arrange
    df = pd.DataFrame(
        {"date": ["2026-01-03", "2026-01-02"], "close": [41.5, 40.0]}
    )

    # Act
    figure = time_series_chart(df, "date", "close")

    # Assert
    assert list(figure.data[0].y) == [40.0, 41.5]


def test_an_unparseable_date_column_fails_instead_of_plotting_nothing():
    """Se a coluna nao e data, converter produz NaT em tudo e o grafico sai vazio —
    uma tela em branco que o usuario le como "nao tem dado".

    Errar alto e melhor: a pergunta "qual coluna e a data?" tem resposta, e quem sabe
    a resposta e o usuario.
    """
    # Arrange
    df = pd.DataFrame({"date": ["nao", "e", "data"], "close": [1.0, 2.0, 3.0]})

    # Act / Assert
    with pytest.raises((ValueError, TypeError)):
        time_series_chart(df, "date", "close")


# --- Edge cases ---------------------------------------------------------------


def test_an_empty_column_returns_an_empty_figure_instead_of_crashing():
    """An empty dataset is a normal state of the app, not an exception."""
    # Act
    figure = distribution_chart(pd.DataFrame({"close": []}), "close", "numeric")

    # Assert
    assert isinstance(figure, go.Figure)


def test_an_unknown_column_fails_loudly():
    with pytest.raises(KeyError):
        distribution_chart(pd.DataFrame({"a": [1]}), "b", "numeric")


def test_a_category_with_many_values_is_capped_to_the_top_n():
    """A bar chart with 500 bars is unreadable. Show the top N and say so."""
    # Arrange
    df = pd.DataFrame({"id": [f"ID{n}" for n in range(500)]})

    # Act
    figure = distribution_chart(df, "id", "category")

    # Assert
    assert len(figure.data[0].x) <= 20


# --- Os dois graficos da pagina inicial ---------------------------------------
# Mesma regra de sempre: aqui se testa a ESCOLHA e a HONESTIDADE do grafico, nunca
# a cor. Um ranking desordenado e um erro de analise; um azul diferente nao e.


def test_a_ranking_is_drawn_horizontally():
    """Rotulo e palavra: "Bens Industriais" no eixo vertical sai truncado ou girado
    45 graus. Deitado, le-se sem esforco."""
    # Arrange
    df = pd.DataFrame({"ticker": ["A", "B"], "premium": [0.2, 0.5]})

    # Act
    figure = ranked_bars(df, "ticker", "premium")

    # Assert
    assert figure.data[0].type == "bar"
    assert figure.data[0].orientation == "h"


def test_a_ranking_comes_out_ordered_with_the_biggest_on_top():
    """★ O teste que importa neste grafico.

    O Plotly desenha a PRIMEIRA categoria embaixo. Quem ordena decrescente e entrega
    sem inverter obtem exatamente o contrario do que quis: o maior no rodape. O erro
    nao estoura, nao aparece em teste de fumaca, e inverte a leitura da pagina.
    """
    # Arrange
    df = pd.DataFrame({"ticker": ["low", "high", "mid"], "premium": [1.0, 9.0, 5.0]})

    # Act
    figure = ranked_bars(df, "ticker", "premium")

    # Assert - de baixo para cima: low, mid, high  =>  high no topo
    assert list(figure.data[0].y) == ["low", "mid", "high"]


def test_a_ranking_keeps_the_negative_bars():
    """Numa tabela de premio sobre o CDI, as barras para a esquerda sao metade da
    resposta. Descartar negativo seria desenhar so a boa noticia."""
    # Arrange
    df = pd.DataFrame({"ticker": ["won", "lost"], "premium": [0.2, -0.4]})

    # Act
    figure = ranked_bars(df, "ticker", "premium")

    # Assert
    assert -0.4 in list(figure.data[0].x)


def test_a_ranking_is_capped_to_the_requested_size():
    # Arrange
    df = pd.DataFrame({"t": [f"T{n}" for n in range(50)], "v": list(range(50))})

    # Act
    figure = ranked_bars(df, "t", "v", top=5)

    # Assert
    assert len(figure.data[0].y) == 5


def test_the_pie_groups_the_tail_instead_of_dropping_it():
    """★ As fatias tem que somar o inteiro que o grafico diz dividir.

    Com 10 setores e 6 fatias, cortar os 4 menores produz uma pizza que afirma ser
    100% de um todo do qual faltam pedacos. Agrupar em "other" mantem a soma e diz ao
    leitor que existe uma cauda.
    """
    # Arrange
    df = pd.DataFrame({"sector": [f"S{n}" for n in range(10)] * 2})

    # Act
    figure = share_pie(df, "sector")

    # Assert
    assert sum(figure.data[0].values) == 20
    assert "other" in list(figure.data[0].labels)
    assert len(figure.data[0].labels) == MAX_PIE_SLICES + 1


def test_a_short_pie_has_no_other_slice():
    """Sem cauda, nao se inventa uma fatia vazia."""
    # Arrange
    df = pd.DataFrame({"sector": ["a", "a", "b"]})

    # Act
    figure = share_pie(df, "sector")

    # Assert
    assert "other" not in list(figure.data[0].labels)


def test_the_pie_fails_loudly_on_an_unknown_column():
    with pytest.raises(KeyError):
        share_pie(pd.DataFrame({"a": [1]}), "b")
