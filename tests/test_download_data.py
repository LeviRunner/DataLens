# =============================================================================
# MODELO DE ESTUDO — tests/test_download_data.py
# -----------------------------------------------------------------------------
# O QUE SE TESTA NUM SCRIPT QUE SO BAIXA COISA: a unica parte dele que DECIDE.
#
# `baixar_cotacoes` fala com o Yahoo, `baixar_indicador` fala com o Banco Central.
# Testar isso exigiria simular as duas APIs, e o teste passaria a garantir a minha
# imitacao delas, nao elas. Fica de fora de proposito.
#
# O que sobra e uma regra so, e ela vale ouro: QUAL TICKER E UMA ACAO. A brapi
# devolve 1.821 codigos da B3, e so 324 sao acao. Os outros sao fundo imobiliario,
# ETF e BDR — e cada um deles entrando no ranking e um erro diferente:
#
#   FII no ranking de acoes   -> compara imovel com empresa, e o Sharpe sai
#   ETF no ranking de acoes   -> compara uma CESTA com um componente dela
#   BDR no ranking de acoes   -> a mesma empresa entra DUAS vezes, uma em real e
#                                outra em dolar, e a que subiu mais e so a moeda
#
# Nenhum desses tres estoura nada. Todos produzem numero bonito. Por isso a regra
# esta numa funcao pura, separada da requisicao — regra que precisa de rede para ser
# testada e regra que ninguem testa.
#
# IMPORTACAO POR CAMINHO: `scripts/` nao e pacote e nao esta no sys.path. O
# `importlib` carrega o arquivo direto, que e o preco de manter o script executavel
# por `python scripts/download_data.py` sem instalar nada.
# =============================================================================

"""Tests for the one rule inside the download script: what counts as a share."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "download_data.py"
_spec = importlib.util.spec_from_file_location("download_data", _SCRIPT)
download_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(download_data)


# --- Quem entra ---------------------------------------------------------------


def test_ordinary_and_preferred_shares_are_kept():
    """3, 4, 5 e 6: ON, PN e as classes B e C. Sao acoes, e e isso que se rankeia."""
    # Arrange
    tickers = ["PETR3", "PETR4", "BRDT5", "AZUL6"]

    # Act
    kept = download_data.filtrar_acoes_b3(tickers)

    # Assert
    assert kept == sorted(tickers)


def test_the_result_is_sorted_and_without_repeats():
    """A brapi ja repetiu ticker. Repetido vira ativo duplicado no banco, e a chave
    primaria de `assets` derruba a carga no meio."""
    # Act
    kept = download_data.filtrar_acoes_b3(["VALE3", "ABEV3", "VALE3"])

    # Assert
    assert kept == ["ABEV3", "VALE3"]


# --- Quem fica de fora, e o erro que cada um causaria --------------------------


def test_real_estate_funds_and_etfs_are_left_out():
    """★ Terminacao 11.

    Sao 565 codigos na B3, quase todos FII. Um fundo imobiliario tem retorno,
    volatilidade e Sharpe — todos calculaveis, todos sem sentido ao lado de uma acao.
    O ranking nao quebraria; ele responderia outra pergunta sem avisar.

    O preco de excluir: units legitimas (BPAC11, TAEE11) saem junto. Nao ha como
    separa-las de um FII pelo codigo, e incluir 550 fundos para salvar 15 units e o
    lado errado da troca.
    """
    # Act
    kept = download_data.filtrar_acoes_b3(["ALZR11", "ACWI11", "BPAC11", "PETR4"])

    # Assert
    assert kept == ["PETR4"]


def test_bdrs_are_left_out():
    """★ Terminacao 32 a 39.

    BDR e recibo de acao estrangeira. ROXO34 e a Nubank; a Nubank tambem esta no
    S&P 500 como NU. Deixar os dois entrarem poe a MESMA empresa duas vezes no Top 10,
    e a diferenca entre as duas linhas e a variacao do dolar, nao o desempenho dela.
    """
    # Act
    kept = download_data.filtrar_acoes_b3(["ROXO34", "AAPL34", "MSFT34", "ITUB4"])

    # Assert
    assert kept == ["ITUB4"]


def test_codes_that_are_not_four_letters_are_left_out():
    """Indice, fracionario e o que mais a lista trouxer."""
    # Act
    kept = download_data.filtrar_acoes_b3(["IBOV", "PETR4F", "ABC3", "PETRO3", "VALE3"])

    # Assert
    assert kept == ["VALE3"]


# --- O catalogo do S&P 500 ----------------------------------------------------


def test_the_sp500_csv_becomes_rows_for_the_assets_table():
    """O CSV ja traz o setor GICS - e por isso que as 503 acoes americanas nao custam
    503 consultas de perfil ao Yahoo, ao contrario das brasileiras."""
    # Arrange
    csv_texto = (
        "Symbol,Security,GICS Sector,GICS Sub-Industry,Headquarters Location,"
        "Date added,CIK,Founded\n"
        "MMM,3M,Industrials,Industrial Conglomerates,\"Saint Paul, Minnesota\","
        "1957-03-04,66740,1902\n"
    )

    # Act
    linhas = download_data.catalogo_sp500(csv_texto)

    # Assert - a ordem das colunas e a da tabela `assets`, nao a do arquivo
    assert linhas == [
        ("MMM", "3M", "acao", "EUA", "USD", "Industrials", "NYSE/NASDAQ")
    ]


def test_a_row_without_a_sector_is_labelled_unknown_not_empty():
    """String vazia no setor vira uma fatia sem nome na rosca da tela inicial.
    "Desconhecido" e uma etiqueta; "" e um buraco."""
    # Arrange
    csv_texto = (
        "Symbol,Security,GICS Sector\n"
        "XYZ,Empresa Sem Setor,\n"
    )

    # Act
    linhas = download_data.catalogo_sp500(csv_texto)

    # Assert
    assert linhas[0][5] == download_data.SETOR_DESCONHECIDO


def test_a_row_without_a_symbol_is_skipped():
    """Linha em branco no fim do arquivo e o caso comum."""
    # Arrange
    csv_texto = "Symbol,Security,GICS Sector\nMMM,3M,Industrials\n,,\n"

    # Act
    linhas = download_data.catalogo_sp500(csv_texto)

    # Assert
    assert len(linhas) == 1


# --- O limite -----------------------------------------------------------------


def test_the_limit_is_applied_to_the_curated_catalogue():
    """`--limite` existe para provar a rodada em segundos em vez de 20 minutos."""
    # Act
    catalogo = download_data.montar_catalogo("exemplo", pausa=0, limite=3)

    # Assert
    assert len(catalogo) == 3


@pytest.mark.parametrize("universo", download_data.UNIVERSOS)
def test_every_advertised_universe_is_a_real_option(universo):
    """O `--universo` do argparse e a lista lida por `montar_catalogo` sao a mesma
    tupla. Um nome anunciado na ajuda e nao tratado no codigo devolveria uma lista
    vazia sem explicar por que."""
    # Assert
    assert universo in ("exemplo", "b3", "sp500", "tudo")
