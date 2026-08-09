# =============================================================================
# MODELO DE ESTUDO — tests/test_statistics.py          (Dia 26)
# -----------------------------------------------------------------------------
# ESBOCO — Sprint 5. Trate como ponto de partida.
#
# API proposta (ATUALIZADA pelo floco de neve — ver o parametro novo):
#     def correlation_matrix(df, method="pearson", exclude_identifiers=True) -> pd.DataFrame
#     @dataclass(frozen=True)
#     class Trend:
#         column: str
#         direction: str      # rising|falling|flat
#         slope: float
#         r_squared: float
#     def detect_trend(df, date_column, value_column) -> Trend
#
# CUIDADO — "statistics.py" colide com o modulo `statistics` da biblioteca padrao do
# Python. Dentro do pacote `datalens` isso funciona (import absoluto resolve para o
# da stdlib), mas e uma armadilha classica. Se algum dia der erro estranho de import,
# lembre deste comentario. `analytics.py` teria sido um nome mais seguro.
#
# O TESTE QUE IMPORTA: correlacao alta entre coisas nao relacionadas. O Bloco C do
# dia manda voce achar uma correlacao espuria nos seus dados e escrever por que ela
# nao e causa. O codigo tem que deixar isso VISIVEL, nao esconder atras de um numero
# bonito — por isso o modulo devolve r_squared junto, e nao so a direcao.
#
# -----------------------------------------------------------------------------
# O QUE O FLOCO DE NEVE TROUXE: CHAVE ESTRANGEIRA NAO ENTRA EM CORRELACAO.
#
# A versao anterior descartava so o nao-numerico — o comentario dizia "correlacionar
# tickers seria sem sentido, nao ha ordem em 'AAPL'". Certo, e insuficiente.
#
# Num `SELECT * FROM assets` do floco vem `asset_category_id`, `asset_status_id`,
# `sector_id`, `exchange_id`, `issuer_id`, `reit_segment_id`. Sao INTEIROS. Passam
# pelo filtro de "e numerico" sem tocar a barreira, e correlacionam lindamente.
#
# E o MESMO erro de correlacionar tickers, so que disfarcado: `sector_id = 2` nao e
# "o dobro" de `sector_id = 1`, e a numeracao veio da ordem em que alguem cadastrou os
# setores. So que agora sai um `-0,87` na matriz — e um numero com duas casas decimais
# tem uma autoridade que a palavra "AAPL" nunca teve.
#
# Por isso `exclude_identifiers=True` e o DEFAULT. O caminho correto e o que voce
# ganha sem pedir; incluir os IDs continua possivel, mas exige escrever a intencao.
# =============================================================================

"""Tests for the statistics module.

Correlation is easy to compute and easy to misread. These tests pin down the maths;
the honesty is a documentation problem, and the module must not get in its way.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from datalens.statistics import Trend, correlation_matrix, detect_trend


# --- Correlation --------------------------------------------------------------


def test_a_column_correlates_perfectly_with_itself():
    """The sanity check: the diagonal is always 1."""
    # Arrange
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [5.0, 3.0, 1.0]})

    # Act
    result = correlation_matrix(df)

    # Assert
    assert result.loc["a", "a"] == pytest.approx(1.0)


def test_an_exact_inverse_relationship_is_minus_one():
    # Arrange - b decreases exactly as a increases
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [4.0, 3.0, 2.0, 1.0]})

    # Act
    result = correlation_matrix(df)

    # Assert
    assert result.loc["a", "b"] == pytest.approx(-1.0)


def test_the_matrix_is_symmetric():
    # Arrange
    df = pd.DataFrame({"a": [1.0, 5.0, 3.0], "b": [2.0, 1.0, 9.0]})

    # Act
    result = correlation_matrix(df)

    # Assert
    assert result.loc["a", "b"] == pytest.approx(result.loc["b", "a"])


def test_non_numeric_columns_are_excluded():
    """Correlating tickers would be meaningless - there is no order in 'AAPL'."""
    # Arrange
    df = pd.DataFrame({"ticker": ["AAPL", "KO"], "close": [210.0, 60.0]})

    # Act
    result = correlation_matrix(df)

    # Assert
    assert "ticker" not in result.columns


def test_a_constant_column_produces_no_correlation():
    """Zero variance means correlation is undefined - pandas gives NaN. It must not
    surface as 0.0, which a reader would interpret as 'proven unrelated'.
    """
    # Arrange
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "constant": [7.0, 7.0, 7.0]})

    # Act
    result = correlation_matrix(df)

    # Assert
    assert np.isnan(result.loc["a", "constant"])


def test_a_high_correlation_between_unrelated_series_is_still_reported():
    """The spurious correlation, as an executable reminder.

    These two series have nothing to do with each other and correlate at ~1.0.
    The module reports it honestly; interpreting it is the analyst's job, and that
    interpretation belongs in the report text, not hidden in the code.
    """
    # Arrange
    df = pd.DataFrame({"ice_cream_sales": [1.0, 2.0, 3.0, 4.0], "drownings": [2.0, 4.0, 6.0, 8.0]})

    # Act
    result = correlation_matrix(df)

    # Assert
    assert result.loc["ice_cream_sales", "drownings"] == pytest.approx(1.0)


def test_a_dataframe_with_one_numeric_column_does_not_crash():
    # Act
    result = correlation_matrix(pd.DataFrame({"a": [1.0, 2.0]}))

    # Assert
    assert result.shape == (1, 1)


# --- As chaves estrangeiras do floco ------------------------------------------


def test_foreign_key_columns_are_excluded_by_default():
    """★ NOVO. `sector_id = 2` nao e o dobro de `sector_id = 1`.

    A numeracao saiu da ordem de cadastro dos setores. Correlacionar isso com preco
    produz um numero que descreve o INSERT, nao o mercado.
    """
    # Arrange
    df = pd.DataFrame(
        {
            "sector_id": [1, 2, 1, 2],
            "exchange_id": [1, 2, 1, 2],
            "close": [40.0, 210.0, 41.5, 209.0],
        }
    )

    # Act
    result = correlation_matrix(df)

    # Assert
    assert "sector_id" not in result.columns
    assert "exchange_id" not in result.columns
    assert "close" in result.columns


def test_the_exclusion_can_be_turned_off_on_purpose():
    """Excluir por padrao nao e proibir. Ha uso legitimo: conferir se dois IDs andam
    juntos revela redundancia no modelo (dois campos que dizem a mesma coisa).

    A diferenca entre um default e uma proibicao e quem fica no comando.
    """
    # Arrange
    df = pd.DataFrame({"sector_id": [1, 2, 1, 2], "close": [40.0, 210.0, 41.5, 209.0]})

    # Act
    result = correlation_matrix(df, exclude_identifiers=False)

    # Assert
    assert "sector_id" in result.columns


def test_a_measurement_that_ends_in_id_is_not_excluded_blindly():
    """O contra-exemplo. A heuristica olha nome E cardinalidade — nao so o sufixo.

    `bid` termina em "id" e e preco. Uma regra de sufixo ingenua comeria a coluna, e o
    usuario nunca saberia: coluna excluida simplesmente nao aparece na matriz.
    """
    # Arrange
    df = pd.DataFrame({"bid": [39.9, 209.5, 41.4, 208.8], "close": [40.0, 210.0, 41.5, 209.0]})

    # Act
    result = correlation_matrix(df)

    # Assert
    assert "bid" in result.columns


def test_a_binary_flag_is_excluded_from_the_correlation():
    """`is_business_day` vale 0 ou 1. Pearson entre uma flag e um preco tem formula,
    tem resultado, e nao tem significado - a suposicao de escala continua nao valendo.

    Correlacao com variavel binaria e outro teste (ponto-bisserial), e nao e este.
    """
    # Arrange
    df = pd.DataFrame(
        {"is_business_day": [1, 1, 0, 1], "close": [40.0, 41.5, 41.5, 42.0]}
    )

    # Act
    result = correlation_matrix(df)

    # Assert
    assert "is_business_day" not in result.columns


def test_a_real_query_against_the_warehouse_yields_a_clean_matrix(snowflake_db: str):
    """NOVO — ponta a ponta. `SELECT * FROM quotes` traz `data_source_id` junto.

    Sem a exclusao, a matriz teria uma linha sobre a PROCEDENCIA do dado no meio das
    linhas sobre PRECO. E o tipo de coisa que ninguem questiona num print de matriz.
    """
    from datalens.connectors.sql_connector import SQLConnector

    # Arrange
    df = SQLConnector(snowflake_db, "SELECT * FROM quotes").load()

    # Act
    result = correlation_matrix(df)

    # Assert
    assert "data_source_id" not in result.columns
    assert {"open", "high", "low", "close", "volume"} >= set(result.columns)


# --- Trend --------------------------------------------------------------------


def test_a_rising_series_is_detected_as_rising():
    # Arrange
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=5, freq="D"),
            "close": [10.0, 11.0, 12.0, 13.0, 14.0],
        }
    )

    # Act
    result = detect_trend(df, "date", "close")

    # Assert
    assert isinstance(result, Trend)
    assert result.direction == "rising"
    assert result.slope > 0


def test_a_falling_series_is_detected_as_falling():
    # Arrange
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=4, freq="D"),
            "close": [14.0, 13.0, 12.0, 11.0],
        }
    )

    # Act
    result = detect_trend(df, "date", "close")

    # Assert
    assert result.direction == "falling"


def test_a_flat_series_is_detected_as_flat():
    """Not every series has a story. Reporting a trend in noise is the statistical
    version of lying.
    """
    # Arrange
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=4, freq="D"),
            "close": [10.0, 10.0, 10.0, 10.0],
        }
    )

    # Act
    result = detect_trend(df, "date", "close")

    # Assert
    assert result.direction == "flat"


def test_a_perfect_line_has_r_squared_of_one():
    """r_squared says how well the line explains the data. Reporting a slope without
    it lets a trend be claimed on four random points.
    """
    # Arrange
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=4, freq="D"),
            "close": [10.0, 12.0, 14.0, 16.0],
        }
    )

    # Act
    result = detect_trend(df, "date", "close")

    # Assert
    assert result.r_squared == pytest.approx(1.0)


def test_noisy_data_has_a_low_r_squared():
    # Arrange
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=6, freq="D"),
            "close": [10.0, 50.0, 12.0, 48.0, 11.0, 49.0],
        }
    )

    # Act
    result = detect_trend(df, "date", "close")

    # Assert
    assert result.r_squared < 0.5


def test_a_series_too_short_for_a_trend_is_refused():
    """Two points always make a perfect line. Calling that a trend is nonsense."""
    # Arrange
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=1), "close": [10.0]})

    # Act / Assert
    with pytest.raises(ValueError):
        detect_trend(df, "date", "close")


def test_nulls_are_ignored_rather_than_treated_as_zero():
    # Arrange
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=4, freq="D"),
            "close": [10.0, None, 12.0, 13.0],
        }
    )

    # Act
    result = detect_trend(df, "date", "close")

    # Assert
    assert result.direction == "rising"


def test_a_text_date_column_is_accepted():
    """NOVO — mesma razao do `test_charts.py`: no SQLite a data e TEXT.

    Se `detect_trend` exigir datetime, todo uso vindo do banco quebra, e o app vai
    acabar convertendo por fora - espalhando a mesma conversao por tres lugares.
    """
    # Arrange - as strings ISO exatamente como o SQLite devolve
    df = pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"],
            "close": [10.0, 11.0, 12.0, 13.0],
        }
    )

    # Act
    result = detect_trend(df, "date", "close")

    # Assert
    assert result.direction == "rising"


def test_the_slope_is_per_day_and_not_per_row():
    """★ NOVO, e sutil. `calendar.is_business_day` existe porque a serie TEM buracos:
    o mercado nao abre no fim de semana nem no feriado.

    Se o eixo x for a POSICAO da linha (0, 1, 2, 3), a inclinacao muda de valor quando
    aparece um feriado no meio - a mesma serie de precos passa a "subir mais rapido"
    porque tem menos linhas. A inclinacao tem que ser por DIA.

    Conta na mao: de 10,00 em 02/01 a 13,00 em 05/01 sao 3 reais em 3 dias -> 1,0/dia.
    Com o feriado dia 04 removido, sobram 3 linhas, mas continuam sendo 3 dias.
    """
    # Arrange - 04/01 nao existe na serie (mercado fechado)
    df = pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-03", "2026-01-05"],
            "close": [10.0, 11.0, 13.0],
        }
    )

    # Act
    result = detect_trend(df, "date", "close")

    # Assert
    assert result.slope == pytest.approx(1.0)
