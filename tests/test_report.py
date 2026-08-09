# =============================================================================
# MODELO DE ESTUDO — tests/test_report.py              (Dia 23)
# -----------------------------------------------------------------------------
# ESBOCO. Voce so chega aqui no Dia 23, e ate la o formato do perfil ja tera mudado.
# Trate como ponto de partida, nao como contrato.
#
# API proposta:
#     def build_report(profiles, charts=None, title="DataLens", source=None,
#                      cleaning_log=None) -> str        # HTML completo
#
# Devolve STRING, nao escreve arquivo. Motivo: quem decide o destino e quem chama —
# o app manda para o botao de download, um script manda para o disco. Funcao que
# escreve arquivo sozinha e dificil de testar e impossivel de reusar.
#
# AUTOSSUFICIENTE e o requisito central: um unico .html que a pessoa abre offline,
# sem CSS externo e sem CDN. Se depender de link externo, quebra no primeiro lugar
# onde importa — a maquina do recrutador, sem internet no aviao.
#
# O TESTE MAIS IMPORTANTE DAQUI e o de escape de HTML. Um nome de coluna com "<" vira
# tag e quebra a pagina; pior, se o dado veio de fora, vira XSS. E o mesmo bug do
# SQL injection, em outro andar: dado tratado como codigo.
#
# -----------------------------------------------------------------------------
# O QUE O FLOCO DE NEVE TROUXE
#
# 1. A PROCEDENCIA VIROU PARTE DO RELATORIO. Com 21 tabelas e 3 views, "acoes_b3.csv"
#    deixou de identificar a fonte: o mesmo banco responde `quotes`, `v_positions` e
#    `v_assets_full`, e os tres perfis sao diferentes. O `source=` passa a carregar a
#    query, e um relatorio sem ela e um relatorio que ninguem consegue refazer.
#
# 2. A QUERY E DADO DO USUARIO. Ela vai para dentro do HTML, e comeca com "SELECT",
#    nao com "<script>" — ate o dia em que alguem colar uma query com `<` num
#    comparador. Escapar o titulo e as colunas e esquecer da fonte e o buraco classico:
#    fecha-se a porta e deixa-se a janela.
# =============================================================================

"""Tests for the HTML report builder.

Not tested: whether it looks good. That is what the Bloco C of day 23 is for -
open it in a browser and fix what is ugly.
"""

from __future__ import annotations

import pandas as pd
import pytest

from datalens.profiling import profile
from datalens.report import build_report


@pytest.fixture
def sample_profiles():
    df = pd.DataFrame(
        {
            "ticker": ["PETR4.SA", "AAPL", "PETR4.SA"],
            "close": [40.0, 210.0, None],
        }
    )
    return profile(df)


# --- The output is HTML, and it is complete -----------------------------------


def test_build_report_returns_a_complete_html_document(sample_profiles):
    # Act
    html = build_report(sample_profiles)

    # Assert
    assert isinstance(html, str)
    assert "<html" in html.lower()
    assert "</html>" in html.lower()


def test_the_report_declares_utf8(sample_profiles):
    """Without it, 'preço médio' renders as 'preÃ§o mÃ©dio' in some browsers."""
    # Act
    html = build_report(sample_profiles)

    # Assert
    assert "utf-8" in html.lower()


def test_the_report_is_self_contained(sample_profiles):
    """No external stylesheet, no CDN script: it must open offline."""
    # Act
    html = build_report(sample_profiles)

    # Assert
    assert "<link" not in html.lower()
    assert "src=\"http" not in html.lower()


# --- The content is actually there --------------------------------------------


def test_every_column_appears_in_the_report(sample_profiles):
    # Act
    html = build_report(sample_profiles)

    # Assert
    for column in sample_profiles:
        assert column in html


def test_the_missing_percentage_is_shown(sample_profiles):
    """33.3% missing on `close` is the finding - it cannot be silently dropped."""
    # Act
    html = build_report(sample_profiles)

    # Assert
    assert "33" in html


def test_the_cleaning_log_is_included_when_given(sample_profiles):
    """This is the section that makes the report portfolio material: not just what
    the data looks like, but what was done to it.
    """
    from datalens.cleaning import CleaningAction

    # Arrange
    log = [CleaningAction("close", "filled_missing", 1, "median = 125.0")]

    # Act
    html = build_report(sample_profiles, cleaning_log=log)

    # Assert
    assert "filled_missing" in html or "median" in html


def test_the_title_and_source_appear_in_the_output(sample_profiles):
    # Act
    html = build_report(sample_profiles, title="B3 analysis", source="acoes_b3.csv")

    # Assert
    assert "B3 analysis" in html
    assert "acoes_b3.csv" in html


def test_the_sql_query_is_recorded_as_the_source(sample_profiles):
    """NOVO. Num warehouse, a fonte nao e o arquivo - e a pergunta que foi feita.

    Sem a query no relatorio, o leitor ve "30% faltante em `close`" e nao tem como
    saber se isso vale para a carteira inteira ou so para 2026. Relatorio que nao
    pode ser refeito e opiniao, nao analise.
    """
    # Arrange
    query = "SELECT ticker, date, close FROM quotes WHERE date >= '2026-01-01'"

    # Act
    html = build_report(sample_profiles, source=query)

    # Assert
    assert "FROM quotes" in html


# --- The security property ----------------------------------------------------


def test_html_in_a_column_name_is_escaped():
    """A column called '<script>' must not become a tag. Same class of bug as SQL
    injection: data being treated as code.
    """
    # Arrange
    profiles = profile(pd.DataFrame({"<script>alert(1)</script>": [1.0, 2.0]}))

    # Act
    html = build_report(profiles)

    # Assert
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_in_a_category_value_is_escaped():
    """Values are user data too - they come from whatever file was uploaded."""
    # Arrange
    profiles = profile(pd.DataFrame({"name": ["<b>bold</b>"] * 5}))

    # Act
    html = build_report(profiles)

    # Assert
    assert "<b>bold</b>" not in html


def test_html_in_the_source_and_title_is_escaped(sample_profiles):
    """NOVO — a janela que fica aberta quando so se fecha a porta.

    `title` e `source` chegam de fora tanto quanto os nomes de coluna: o titulo vem de
    um campo de texto do app, a fonte vem da query que o usuario escreveu. Um `<` num
    `WHERE preco < 10` ja basta para quebrar a pagina, sem nenhuma ma intencao.
    """
    # Act
    html = build_report(
        sample_profiles,
        title="<script>alert('titulo')</script>",
        source="SELECT * FROM quotes WHERE close < 10 AND volume > 0",
    )

    # Assert
    assert "<script>alert('titulo')</script>" not in html
    assert "close &lt; 10" in html


# --- Edge cases ---------------------------------------------------------------


def test_an_empty_profile_still_produces_a_valid_page():
    """A dataset with no columns is a weird state, not a crash."""
    # Act
    html = build_report({})

    # Assert
    assert "<html" in html.lower()


def test_charts_are_embedded_inline_when_given(sample_profiles):
    """Plotly can emit a chart as a self-contained div - use that, not a CDN link."""
    from datalens.charts import distribution_chart

    # Arrange
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    charts = {"close": distribution_chart(df, "close", "numeric")}

    # Act
    html = build_report(sample_profiles, charts=charts)

    # Assert
    assert "plotly" in html.lower()


def test_a_wide_profile_from_a_view_renders_every_column(snowflake_db: str):
    """NOVO. `v_assets_full` tem 12 colunas, varias 100% nulas.

    Um relatorio que "pula" a coluna vazia esconde exatamente o achado mais forte da
    analise. Nada a dizer sobre uma coluna E o que ha para dizer sobre ela.
    """
    from datalens.connectors.sql_connector import SQLConnector

    # Arrange
    df = SQLConnector(snowflake_db, "SELECT * FROM v_assets_full").load()
    profiles = profile(df)

    # Act
    html = build_report(profiles, source="SELECT * FROM v_assets_full")

    # Assert
    for column in profiles:
        assert column in html
    assert "100" in html  # o 100% faltante de reit_segment
