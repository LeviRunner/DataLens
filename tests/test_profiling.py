# =============================================================================
# MODELO DE ESTUDO — tests/test_profiling.py           (Dias 15-16)
# -----------------------------------------------------------------------------
# ★ ESTE E O NUCLEO DO PROJETO. E a peca que voce mostra em entrevista.
#
# API proposta:
#     @dataclass(frozen=True)
#     class ColumnProfile:
#         column: str
#         type: str
#         count: int            # nao-nulos
#         missing: int
#         missing_pct: float
#         stats: dict           # varia por tipo (ver abaixo)
#
#     def profile(df, types=None) -> dict[str, ColumnProfile]
#
# A DECISAO DE DESIGN DO DIA 16: "estrutura de saida unica para todos os tipos".
# Os campos de cima sao IGUAIS para qualquer coluna; o que varia fica em `stats`:
#     numeric  -> mean, median, std, min, max, q1, q3
#     date     -> min, max, range_days
#     boolean  -> true_count, false_count
#     category -> unique, top_values
#     text     -> unique, avg_length
# Assim a tela e o relatorio iteram sem `if tipo == ...` espalhado por toda parte.
#
# ATENCAO: `boolean` entrou nesta lista depois. O `detector.detect()` devolve
# numeric|date|boolean|category|text, e a versao original desta tabela tinha quatro
# tipos, nao cinco — uma coluna booleana cairia num `stats` vazio sem ninguem notar.
# A licao vale mais que a correcao: quando um modulo consome o vocabulario de outro,
# os dois vocabularios precisam ser a MESMA lista, nao duas listas parecidas.
#
# `types` e opcional de proposito: `profile(df)` chama o detector por dentro,
# `profile(df, types)` aceita o palpite ja corrigido pelo usuario na tela.
#
# ATENCAO ao Bloco C do Dia 15: calcule media/mediana/desvio A MAO numa amostra
# pequena e confira. Os numeros deste arquivo foram escolhidos para isso ser facil.
#
# -----------------------------------------------------------------------------
# O QUE O SCHEMA EM FLOCO DE NEVE ACRESCENTOU (bloco final do arquivo)
#
# Um `SELECT *` numa tabela do floco nao se parece com um CSV. Ele traz tres coisas
# que o profiling original nunca viu, e cada uma vira um `stats` novo:
#
#   1. BOOLEANO GUARDADO COMO INTEIRO. `is_cash`, `is_taxable`, `is_fixed_income`,
#      `is_tradable`, `is_business_day`, `is_holiday` — o SQLite nao tem BOOLEAN, e o
#      schema usa `INTEGER CHECK (x IN (0,1))`. O detector diz `numeric`, e esta certo
#      (0 e 1 sao numeros ate alguem dizer o contrario). Media de flag e 0,83 — um
#      numero que nao significa nada. -> `is_binary_flag`.
#
#   2. CHAVE ESTRANGEIRA NUMERICA. `sector_id`, `currency_id`, `exchange_id`,
#      `data_source_id`. Sao inteiros, entao entram em qualquer conta — e correlacionar
#      `sector_id` com `close` produz um numero bonito e sem sentido. -> `is_identifier`,
#      que e o que `statistics.correlation_matrix` usa para excluir a coluna.
#
#   3. CHAVE COMPOSTA. `quotes` tem PK `(ticker, date)`; `indicators`, `(code, date)`.
#      NENHUMA das duas colunas e unica sozinha, entao `is_probable_key` tem que
#      continuar FALSO nas duas. O teste existe para ninguem "consertar" isso.
# =============================================================================

"""Tests for the profiling engine - the core of DataLens.

It must run on ANY dataset. That is the claim the project makes, so the tests end
with the awkward cases: empty frames, all-null columns, single rows.
"""

from __future__ import annotations

import pandas as pd
import pytest

from datalens.detector import DetectedType
from datalens.profiling import ColumnProfile, profile


# --- The shared shape ---------------------------------------------------------


def test_profile_returns_one_entry_per_column():
    # Arrange
    df = pd.DataFrame({"ticker": ["AAPL"], "close": [210.0]})

    # Act
    result = profile(df)

    # Assert
    assert set(result) == {"ticker", "close"}
    assert all(isinstance(value, ColumnProfile) for value in result.values())


def test_every_profile_reports_counts_and_missing_percentage():
    """These four fields exist for every column regardless of type - that is what
    lets the screen render any dataset with one loop.
    """
    # Arrange - 4 rows, 1 missing
    df = pd.DataFrame({"value": [10.0, 20.0, 30.0, None]})

    # Act
    result = profile(df)["value"]

    # Assert
    assert result.count == 3
    assert result.missing == 1
    assert result.missing_pct == 25.0


# --- Numeric (Dia 15) ---------------------------------------------------------


def test_numeric_statistics_are_correct_on_a_hand_checkable_sample():
    """[10, 20, 30, 40]: mean 25, median 25, min 10, max 40.

    Work these out on paper first - that is the Bloco C of day 15.
    """
    # Arrange
    df = pd.DataFrame({"value": [10.0, 20.0, 30.0, 40.0]})

    # Act
    stats = profile(df)["value"].stats

    # Assert
    assert stats["mean"] == 25.0
    assert stats["median"] == 25.0
    assert stats["min"] == 10.0
    assert stats["max"] == 40.0


def test_quartiles_are_reported_for_numeric_columns():
    """Mean alone lies about skewed data - and financial data is always skewed."""
    # Arrange
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0, 5.0]})

    # Act
    stats = profile(df)["value"].stats

    # Assert
    assert stats["q1"] == 2.0
    assert stats["q3"] == 4.0


def test_nulls_are_excluded_from_the_statistics():
    """Treating a missing price as zero would drag the mean down and invent a crash."""
    # Arrange
    df = pd.DataFrame({"value": [10.0, None, 30.0]})

    # Act
    stats = profile(df)["value"].stats

    # Assert
    assert stats["mean"] == 20.0
    assert stats["min"] == 10.0


# --- Dates (Dia 15) -----------------------------------------------------------


def test_a_date_column_reports_its_range():
    # Arrange
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-31", "2026-01-15"])})

    # Act
    result = profile(df)["date"]

    # Assert
    assert result.type == "date"
    assert result.stats["range_days"] == 30


# --- Categories and text (Dia 16) ---------------------------------------------


def test_a_category_column_reports_cardinality_and_top_values():
    # Arrange - Finance appears 3x, Retail 2x, Energy 1x
    df = pd.DataFrame({"sector": ["Finance"] * 3 + ["Retail"] * 2 + ["Energy"]})

    # Act
    stats = profile(df)["sector"].stats

    # Assert
    assert stats["unique"] == 3
    assert stats["top_values"][0] == ("Finance", 3)


def test_an_almost_unique_column_is_flagged_as_a_probable_key():
    """One distinct value per row is an ID, not data. Averaging it is meaningless,
    and the screen should say so instead of drawing a histogram of primary keys.
    """
    # Arrange
    df = pd.DataFrame({"id": [f"ID{n}" for n in range(50)]})

    # Act
    result = profile(df)["id"]

    # Assert
    assert result.stats.get("is_probable_key") is True


def test_an_almost_constant_column_is_flagged_as_useless():
    """One value in 50 rows carries no information - it is noise in a report."""
    # Arrange
    df = pd.DataFrame({"currency": ["BRL"] * 50})

    # Act
    result = profile(df)["currency"]

    # Assert
    assert result.stats.get("is_almost_constant") is True


# --- "It must run on ANY dataset" ---------------------------------------------


def test_an_empty_dataframe_returns_an_empty_profile():
    assert profile(pd.DataFrame()) == {}


def test_an_all_null_column_does_not_crash():
    """No statistics are possible, but 100% missing IS the finding."""
    # Act
    result = profile(pd.DataFrame({"empty": [None, None, None]}))["empty"]

    # Assert
    assert result.missing_pct == 100.0
    assert result.count == 0


def test_a_single_row_does_not_crash_on_standard_deviation():
    """std of one value is undefined - pandas returns NaN, and NaN must not reach
    the screen as 'nan'. Decide here what the user sees.
    """
    # Act
    stats = profile(pd.DataFrame({"value": [42.0]}))["value"].stats

    # Assert
    assert stats["mean"] == 42.0
    assert stats["std"] is None


def test_a_column_name_with_spaces_and_accents_survives():
    # Arrange
    df = pd.DataFrame({"preço médio": [1.0, 2.0]})

    # Act
    result = profile(df)

    # Assert
    assert "preço médio" in result


def test_profile_does_not_modify_the_dataframe():
    # Arrange
    df = pd.DataFrame({"value": [1.0, None, 3.0]})
    before = df.copy(deep=True)

    # Act
    profile(df)

    # Assert
    pd.testing.assert_frame_equal(df, before)


# --- The claim the project is built on ----------------------------------------


@pytest.mark.parametrize(
    "df",
    [
        pd.DataFrame({"a": [1, 2, 3]}),
        pd.DataFrame({"a": ["x", "y"], "b": [1.0, 2.0]}),
        pd.DataFrame({"d": pd.to_datetime(["2026-01-01", "2026-06-01"])}),
        pd.DataFrame({"mixed": [1, "two", None, 4.0]}),
    ],
)
def test_the_same_engine_profiles_any_shape_of_data(df):
    """The versatility claim, as an executable assertion."""
    # Act
    result = profile(df)

    # Assert
    assert len(result) == len(df.columns)


# =============================================================================
# O QUE O FLOCO DE NEVE TROUXE
# =============================================================================

# --- 1. Booleano guardado como INTEGER 0/1 ------------------------------------


def test_a_zero_one_integer_column_is_flagged_as_a_binary_flag():
    """`is_business_day` vem do SQLite como 0/1. Media 0,66 nao e informacao.

    O profiling NAO converte - converter e trabalho do cleaning, e o detector nem
    opinou "boolean". Ele so marca a bandeira, para a tela poder oferecer "corrigir
    para boolean" em vez de desenhar um histograma de dois valores.
    """
    # Arrange - 2 dias uteis, 1 fim de semana
    df = pd.DataFrame({"is_business_day": [1, 1, 0]})

    # Act
    result = profile(df)["is_business_day"]

    # Assert
    assert result.type == "numeric"
    assert result.stats.get("is_binary_flag") is True


def test_a_numeric_column_with_more_than_two_values_is_not_a_binary_flag():
    """O contra-exemplo que impede a bandeira de virar falso positivo.

    `direction` em `transaction_types` vale -1, 0 ou 1: tres valores, nao e flag. Sem
    este teste, uma heuristica preguicosa ("so tem inteiros pequenos") passaria.
    """
    # Arrange
    df = pd.DataFrame({"direction": [1, -1, 0, 1]})

    # Act
    result = profile(df)["direction"]

    # Assert
    assert result.stats.get("is_binary_flag") is not True


def test_the_user_correction_turns_the_flag_into_a_real_boolean_profile():
    """★ Para que serve o parametro `types`.

    O usuario viu "is_holiday: numeric" na tela e corrigiu para boolean. A correcao
    entra por aqui, e o `stats` muda de forma: sai media/mediana, entram as contagens.

    Repare no tipo: `DetectedType`, o MESMO que `detector.detect()` devolve e que
    `cleaning.clean()` consome. A config entrega string (`is_holiday: boolean`); quem
    converte string em DetectedType e a borda - o app -, nao este modulo. Um formato
    interno so, tres portas de entrada.
    """
    # Arrange
    df = pd.DataFrame({"is_holiday": [1, 0, 0, 1, 1]})
    corrected = {"is_holiday": DetectedType("is_holiday", "boolean", 1.0)}

    # Act
    result = profile(df, types=corrected)["is_holiday"]

    # Assert
    assert result.type == "boolean"
    assert result.stats["true_count"] == 3
    assert result.stats["false_count"] == 2
    assert "mean" not in result.stats


# --- 2. Chave estrangeira numerica --------------------------------------------


def test_an_id_column_is_flagged_as_an_identifier():
    """`sector_id` e inteiro, entao entra em qualquer conta - e nao deveria.

    A bandeira e o que permite `statistics.correlation_matrix` excluir a coluna sem
    reimplementar a mesma heuristica do outro lado. Uma decisao, um lugar.
    """
    # Arrange
    df = pd.DataFrame({"sector_id": [1, 2, 1, 2, 1], "close": [40.0, 210.0, 41.5, 209.0, 40.2]})

    # Act
    result = profile(df)

    # Assert
    assert result["sector_id"].stats.get("is_identifier") is True
    assert result["close"].stats.get("is_identifier") is not True


def test_a_column_named_like_data_is_not_an_identifier_just_for_being_integer():
    """`volume` e inteiro e nao e identificador. A heuristica olha o NOME (`*_id`) e a
    unicidade - nao "e inteiro".

    Heuristica que erra para o lado de excluir dado esconde analise; e pior que
    heuristica que erra para o lado de incluir ruido, porque ninguem ve o que sumiu.
    """
    # Arrange
    df = pd.DataFrame({"volume": [1000000, 850000, 500000]})

    # Act
    result = profile(df)["volume"]

    # Assert
    assert result.stats.get("is_identifier") is not True


# --- 3. Chave composta --------------------------------------------------------


def test_neither_half_of_a_composite_key_is_flagged_as_a_key():
    """`quotes` tem PK (ticker, date). Sozinha, nenhuma das duas e unica.

    Este teste existe para travar o comportamento CERTO contra um "conserto" futuro:
    quem olhar so a tabela vai sentir vontade de marcar as duas como chave.
    """
    # Arrange - a mesma forma da fixture snowflake_db
    df = pd.DataFrame(
        {
            "ticker": ["PETR4.SA", "PETR4.SA", "AAPL"],
            "date": ["2026-01-02", "2026-01-03", "2026-01-02"],
            "close": [40.0, 41.5, 210.0],
        }
    )

    # Act
    result = profile(df)

    # Assert
    assert result["ticker"].stats.get("is_probable_key") is not True
    assert result["date"].stats.get("is_probable_key") is not True


# --- 4. Um SELECT de verdade, ponta a ponta -----------------------------------


def test_the_profile_survives_a_real_query_against_the_warehouse(snowflake_db: str):
    """★ O teste de integracao do nucleo: conector -> DataFrame -> perfil.

    Nao ha mock nenhum aqui. E o unico teste do arquivo que toca banco, e ele paga
    por si: a forma que o SQLite devolve (data como TEXT, flag como int, REAL com
    NULL) e diferente da forma que voce montaria a mao num `pd.DataFrame`.
    """
    from datalens.connectors.sql_connector import SQLConnector

    # Arrange
    df = SQLConnector(snowflake_db, "SELECT * FROM quotes").load()

    # Act
    result = profile(df)

    # Assert
    assert set(result) == {
        "ticker", "date", "open", "high", "low", "close", "volume", "data_source_id"
    }
    # AAPL entrou sem abertura: 1 faltante em 3 linhas.
    assert result["open"].missing == 1
    assert result["open"].missing_pct == pytest.approx(33.33, abs=0.01)
    # `close` e NOT NULL no schema, e o perfil tem que refletir isso.
    assert result["close"].missing == 0
    assert result["data_source_id"].stats.get("is_identifier") is True


def test_a_wide_view_profiles_every_column_including_the_empty_ones(snowflake_db: str):
    """`v_assets_full` tem 12 colunas e varias vem NULL para quem nao e FII.

    Dataset largo com buraco e o caso REAL do floco: o LEFT JOIN preenche o que existe
    e deixa o resto nulo. 100% faltante nao e falha do perfil - e o achado.
    """
    from datalens.connectors.sql_connector import SQLConnector

    # Arrange
    df = SQLConnector(snowflake_db, "SELECT * FROM v_assets_full").load()

    # Act
    result = profile(df)

    # Assert
    assert len(result) == len(df.columns)
    assert result["reit_segment"].missing_pct == 100.0
    assert result["ticker"].stats.get("is_probable_key") is True
