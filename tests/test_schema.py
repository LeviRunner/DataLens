# =============================================================================
# MODELO DE ESTUDO — tests/test_schema.py              (NOVO — floco de neve)
# -----------------------------------------------------------------------------
# ESTE ARQUIVO NAO TESTA PYTHON. Testa `scripts/snowflake.sql`.
#
# "Mas SQL nao e codigo de teste." E codigo, roda em producao, e quebra igual. Um
# schema com FK apontando para tabela inexistente e um bug — so que um bug que o
# SQLite guarda para depois: ele CRIA a tabela sem reclamar e so estoura no primeiro
# INSERT, com a mensagem `foreign key mismatch`, que nao diz qual coluna esta errada.
#
# Foi o que aconteceu com a primeira versao de `snowflake.sql`:
#   - 7 comandos falharam na criacao (typo de coluna, sintaxe de REFERENCES);
#   - 12 FKs apontavam para tabela ou coluna inexistente;
#   - as 3 views quebravam ao serem consultadas.
# Nada disso aparece quando voce roda o arquivo e ve o prompt voltar sem erro.
#
# ORDEM DOS TESTES DAQUI = ORDEM DE DIAGNOSTICO. O primeiro teste responde "o arquivo
# sobe?", o segundo "as FKs fecham?", o terceiro "as views consultam?". Quando o
# primeiro falha, os outros nao tem o que dizer — por isso ele vem antes, e por isso
# se roda com `-x`.
#
# TRES PRAGMAS que voce vai usar a vida inteira e quase ninguem conhece:
#   PRAGMA foreign_key_list(<tabela>)  -> as FKs declaradas naquela tabela
#   PRAGMA foreign_key_check           -> as linhas que violam alguma FK (vazio = ok)
#   PRAGMA table_info(<tabela>)        -> colunas, tipos, NOT NULL, PK
# =============================================================================

"""Tests for the snowflake schema itself.

The schema is the foundation every SQL fixture stands on. If it does not load, the
failure has to say so here - once, in Portuguese - instead of forty times as an
opaque sqlite3 error inside unrelated tests.
"""

from __future__ import annotations

import sqlite3

import pytest


# --- 1. O arquivo sobe? --------------------------------------------------------


def test_the_schema_loads_without_errors(snowflake_schema: str):
    """O teste mais barato e o mais valioso: `executescript` para no primeiro erro.

    Se este falhar, ignore todo o resto do arquivo ate consertar - os outros testes
    estarao reclamando de tabelas que nunca chegaram a existir.
    """
    # Arrange
    connection = sqlite3.connect(":memory:")

    # Act / Assert
    try:
        connection.executescript(snowflake_schema)
    finally:
        connection.close()


def test_every_table_and_view_declared_actually_exists(snowflake_db: str):
    """Conta o que o schema PROMETE contra o que ele ENTREGA.

    A lista abaixo e escrita a mao de proposito: e ela que transforma "esqueci de criar
    asset_categories" num teste vermelho em vez de num KeyError tres modulos adiante.
    """
    # Arrange
    expected = {
        # dimensoes nivel 3
        "macro_sectors", "institution_types", "frequencies", "payout_types",
        "reit_segments",
        # dimensoes nivel 2
        "countries", "currencies", "sectors", "tax_rules", "asset_categories",
        "exchanges", "issuers", "data_sources", "transaction_types", "asset_statuses",
        # dimensoes nivel 1
        "calendar", "assets", "institutions", "portfolios", "series",
        # fatos
        "quotes", "transactions", "payouts", "indicators", "financial_statements",
        # views
        "v_assets_full", "v_assets_legacy", "v_positions",
    }
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act
    found = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
    }
    connection.close()

    # Assert
    assert expected - found == set(), f"faltando no schema: {sorted(expected - found)}"


# --- 2. As chaves estrangeiras fecham? -----------------------------------------


def test_every_foreign_key_points_at_something_that_exists(snowflake_db: str):
    """A verificacao que o SQLite NAO faz por voce na hora do CREATE.

    Percorre cada FK declarada e confere se a tabela e a coluna de destino existem.
    Este e o teste que teria pego `couuntries`, `inssuers`, `calender` e
    `payout_types_id` antes de qualquer INSERT.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    # Act
    broken: list[str] = []
    for table in sorted(tables):
        for _, _, target, from_column, to_column, *_ in connection.execute(
            f'PRAGMA foreign_key_list("{table}")'
        ):
            if target not in tables:
                broken.append(f"{table}.{from_column} -> tabela '{target}' nao existe")
                continue
            target_columns = {
                row[1] for row in connection.execute(f'PRAGMA table_info("{target}")')
            }
            if to_column and to_column not in target_columns:
                broken.append(
                    f"{table}.{from_column} -> coluna '{target}.{to_column}' nao existe"
                )
    connection.close()

    # Assert
    assert broken == [], "chaves estrangeiras quebradas:\n  " + "\n  ".join(broken)


def test_the_seeded_data_violates_no_foreign_key(snowflake_db: str):
    """`PRAGMA foreign_key_check` devolve uma linha por violacao. Vazio e o esperado."""
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act
    violations = list(connection.execute("PRAGMA foreign_key_check"))
    connection.close()

    # Assert
    assert violations == []


def test_an_orphan_row_is_refused_when_the_pragma_is_on(snowflake_db: str):
    """A prova de que a integridade referencial esta VIVA, e nao so declarada.

    Sem `PRAGMA foreign_keys = ON`, este INSERT passa e o warehouse ganha uma cotacao
    de um ativo que nao existe. O pragma e por CONEXAO - e por isso que o
    `sql_connector` precisa liga-lo em toda conexao nova, e nao uma vez so.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))
    connection.execute("PRAGMA foreign_keys = ON")

    # Act / Assert
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO quotes (ticker, date, close) VALUES ('NAOEXISTE', '2026-01-02', 1.0)"
        )
    connection.close()


def test_without_the_pragma_the_same_orphan_slips_in(snowflake_db: str):
    """O teste incomodo: mostra o que acontece quando alguem esquece o pragma.

    Ele existe para voce SENTIR o problema uma vez. Um banco que aceita orfao nao
    avisa nada - o estrago aparece semanas depois, como um JOIN que perde linhas.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))
    connection.execute("PRAGMA foreign_keys = OFF")

    # Act
    connection.execute(
        "INSERT INTO quotes (ticker, date, close) VALUES ('NAOEXISTE', '2026-01-02', 1.0)"
    )
    violations = list(connection.execute("PRAGMA foreign_key_check"))
    connection.close()

    # Assert
    assert violations, "o orfao entrou e o banco nao reclamou - esse e o ponto"


# --- 3. As views consultam? ----------------------------------------------------


@pytest.mark.parametrize("view", ["v_assets_full", "v_assets_legacy", "v_positions"])
def test_every_view_can_actually_be_queried(snowflake_db: str, view: str):
    """View no SQLite tambem e preguicosa: o CREATE VIEW aceita nomes inexistentes.

    O erro so aparece no primeiro SELECT - possivelmente em producao, possivelmente na
    tela do app durante a demo.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act / Assert
    try:
        connection.execute(f"SELECT * FROM {view} LIMIT 1").fetchall()
    finally:
        connection.close()


def test_v_assets_full_flattens_the_whole_branch(snowflake_db: str):
    """A view existe para poupar 8 JOINs. Se ela nao trouxer o setor e o pais, ela
    nao esta poupando nada e o app vai acabar escrevendo os JOINs de novo.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))
    connection.row_factory = sqlite3.Row

    # Act
    row = connection.execute(
        "SELECT * FROM v_assets_full WHERE ticker = 'PETR4.SA'"
    ).fetchone()
    connection.close()

    # Assert
    assert row["sector"] == "Petroleo e Gas"
    assert row["macro_sector"] == "Materiais Basicos"
    assert row["exchange_country"] == "Brasil"
    assert row["currency"] == "BRL"


def test_the_legacy_view_still_answers_the_old_flat_queries(snowflake_db: str):
    """`v_assets_legacy` e a promessa de compatibilidade: as queries escritas contra o
    `assets` plano do `schema.sql` seguem rodando. Se as colunas mudarem de nome, a
    promessa quebra - e este teste e quem cobra.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act
    columns = [
        row[1] for row in connection.execute("PRAGMA table_info(v_assets_legacy)")
    ]
    connection.close()

    # Assert
    assert columns == ["ticker", "name", "type", "country", "currency", "sector", "exchange"]


def test_v_positions_computes_the_quantity_from_the_direction(snowflake_db: str):
    """100 compradas, 40 vendidas -> 60. A posicao nasce do SINAL do tipo de
    transacao, nao de uma coluna 'quantidade atual' que alguem teria que manter.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act
    quantity = connection.execute(
        "SELECT quantity FROM v_positions WHERE ticker = 'PETR4.SA'"
    ).fetchone()[0]
    connection.close()

    # Assert
    assert quantity == 60


def test_net_cost_adds_fees_instead_of_multiplying(snowflake_db: str):
    """★ O teste mais importante deste arquivo.

    Conta na mao:  100 * 40,00 + 5,00  -  40 * 41,50 + 3,00  =  2348,00

    A primeira versao da view escrevia `* t.fees`. Como `fees` tem DEFAULT 0, TODO
    net_cost saia 0,00 - e um zero nao parece erro, parece dado. Erro que estoura
    voce conserta; erro que roda vai para o relatorio.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act
    net_cost = connection.execute(
        "SELECT net_cost FROM v_positions WHERE ticker = 'PETR4.SA'"
    ).fetchone()[0]
    connection.close()

    # Assert
    assert net_cost == pytest.approx(2348.00)


def test_a_fully_sold_position_disappears_from_the_view(snowflake_db: str):
    """O `HAVING <> 0` da view: quem zerou a posicao nao aparece na carteira.

    Sem ele, a tela lista dezenas de ativos com quantidade 0 - ruido que esconde o
    que importa.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        "INSERT INTO transactions VALUES (3, 'PETR4.SA', '2026-01-03', 1, 1, 2, 60, 41.50, 0.0)"
    )

    # Act
    rows = connection.execute(
        "SELECT * FROM v_positions WHERE ticker = 'PETR4.SA'"
    ).fetchall()
    connection.close()

    # Assert
    assert rows == []


# --- 4. As regras de negocio que viraram CHECK ---------------------------------
# Um CHECK e uma regra de negocio escrita no lugar onde ela nao pode ser esquecida.
# Validar so no Python significa que o script de carga, o notebook e o DBeaver podem
# furar a regra. Estes testes provam que a regra esta no banco, nao so na intencao.


def test_a_negative_quantity_is_refused(snowflake_db: str):
    """`CHECK (quantity > 0)`: a direcao da operacao vive em `transaction_types`.

    Quantidade negativa seria uma SEGUNDA forma de dizer 'venda' - e duas formas de
    dizer a mesma coisa e como nasce um relatorio que nao bate.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act / Assert
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO transactions VALUES (9, 'PETR4.SA', '2026-01-02', 1, 1, 1, -10, 40.0, 0.0)"
        )
    connection.close()


def test_a_payment_before_the_ex_date_is_refused(snowflake_db: str):
    """`CHECK (payment_date >= ex_date)`: nao se paga dividendo antes da data-com."""
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act / Assert
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO payouts VALUES "
            "(9, 'PETR4.SA', 1, 1, 1, '2026-01-03', '2026-01-02', 10.0, 0.0)"
        )
    connection.close()


def test_a_high_below_the_low_is_refused(snowflake_db: str):
    """`CHECK (high >= low)`: a maxima abaixo da minima e dado corrompido na origem.

    Barrar no banco e barato; descobrir depois, num grafico torto, e caro.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act / Assert
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO quotes VALUES ('AAPL', '2026-01-03', 200, 190, 210, 205, 1, 1)"
        )
    connection.close()


def test_an_unknown_data_source_status_is_refused(snowflake_db: str):
    """`CHECK (status IN ('active','inactive','error'))`: um vocabulario fechado no
    banco e o que impede 'ativo', 'ACTIVE' e 'ok' conviverem na mesma coluna.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act / Assert
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO data_sources VALUES (9, 'fonte nova', NULL, 'ligada', NULL)"
        )
    connection.close()


def test_an_iso_code_with_the_wrong_length_is_refused(snowflake_db: str):
    """`CHECK (length(iso_code) = 3)`: 'BR' e ISO 3166-1 alpha-2, e o schema decidiu
    alpha-3. Misturar os dois padroes na mesma coluna quebra todo JOIN por pais.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act / Assert
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO countries VALUES (9, 'Portugal', 'PT', 100)")
    connection.close()


# --- 5. Os indices ------------------------------------------------------------


def test_every_index_the_schema_promises_exists(snowflake_db: str):
    """O SQLite nao indexa FK automaticamente - e o floco vive de JOIN por FK.

    Sem indice, cada JOIN vira varredura completa. Com 3 linhas nao se nota; com
    300 mil cotacoes, a tela demora 4 segundos e ninguem sabe por que.
    """
    # Arrange
    expected = {
        "idx_assets_sector", "idx_assets_category", "idx_assets_issuer",
        "idx_assets_exchange", "idx_quotes_date", "idx_indicators_date",
        "idx_tx_ticker", "idx_tx_date", "idx_tx_portfolio_date",
        "idx_payouts_ticker", "idx_payouts_payment", "idx_statements_period",
    }
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act
    found = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'"
        )
    }
    connection.close()

    # Assert
    assert expected - found == set(), f"indices faltando: {sorted(expected - found)}"


def test_the_date_index_is_actually_used_by_a_date_query(snowflake_db: str):
    """`EXPLAIN QUERY PLAN` diz se o indice foi usado. Criar indice que o otimizador
    ignora e trabalho jogado fora - e acontece mais do que parece.
    """
    # Arrange
    connection = sqlite3.connect(snowflake_db.replace("sqlite:///", ""))

    # Act
    plan = " ".join(
        str(row)
        for row in connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM quotes WHERE date = '2026-01-02'"
        )
    )
    connection.close()

    # Assert
    assert "idx_quotes_date" in plan or "USING INDEX" in plan
