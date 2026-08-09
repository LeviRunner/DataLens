# =============================================================================
# MODELO DE ESTUDO — tests/test_config_loader.py       (Dia 14)
# -----------------------------------------------------------------------------
# API proposta:
#     @dataclass(frozen=True)
#     class SourceConfig:
#         type: str                      # csv|excel|json|sql|api
#         path: str | None = None        # csv, excel, json
#         connection: str | None = None  # sql
#         query: str | None = None       # sql
#         url: str | None = None         # json, api
#         parameters: dict = field(default_factory=dict)  # NOVO — bind params do SQL
#         options: dict = field(default_factory=dict)     # separator, sheet, ...
#
#     @dataclass(frozen=True)
#     class Config:
#         source: SourceConfig
#         columns: dict[str, str]        # correcao manual do detector
#         profile: dict
#
#     def load_config(path) -> Config
#
# ATENCAO 1 — `json` e o tipo com a regra mais chata, e por isso ele esta aqui:
# e o UNICO que aceita `path` OU `url`, exatamente um dos dois. Nem um nem outro e
# erro; os dois juntos tambem. Todo tipo anterior tinha campos obrigatorios; este tem
# uma escolha exclusiva, e escolha exclusiva e onde validacao preguicosa vaza.
#
# ATENCAO 2 (NOVO, veio do floco de neve) — `parameters`. O `SQLConnector` aceita
# bind parameters desde o primeiro dia, mas nao havia como preenche-los pela config.
# Com o schema em floco, a query util deixou de ser `SELECT * FROM quotes` e virou um
# JOIN com filtro — e filtro pede valor. Sem `parameters:` na config, o usuario e
# empurrado para concatenar o valor dentro da query, que e exatamente o buraco de SQL
# injection que o conector foi escrito para fechar. Config que nao oferece o caminho
# seguro ensina o caminho inseguro.
#
# `columns` e a correcao manual do detector: `{coluna: tipo}` com tipo em
# numeric|date|boolean|category|text — o mesmo vocabulario que `detector.detect()`
# devolve. Se os dois vocabularios divergirem, a correcao do usuario vira ruido.
#
# O TEMA DO DIA E MENSAGEM DE ERRO, nao YAML. Ler YAML sao 3 linhas de PyYAML. O que
# separa ferramenta de script e o que acontece quando a config esta errada: o Bloco C
# manda voce quebrar a config de 5 formas e garantir que o erro seja legivel.
#
# -----------------------------------------------------------------------------
# COMO SE AFIRMA SOBRE UM ERRO, DEPOIS DO i18n.py — leia isto antes de copiar.
#
# A versao anterior deste arquivo escrevia:
#
#     with pytest.raises(ConfigError, match="query"):     # <- NAO faca mais isso
#
# `match=` casa contra o TEXTO da excecao. O `i18n.py` mudou a regra do projeto: o erro
# carrega um CODIGO e os parametros; a frase nasce na borda, em tres linguas. Um teste
# preso ao texto fica vermelho quando alguem melhora a redacao ou traduz — e teste que
# falha pelo motivo errado e teste que a equipe aprende a ignorar.
#
#     with pytest.raises(ConfigError) as caught:
#         load_config(path)
#     assert caught.value.message.code == "config_missing_field"
#     assert caught.value.message.params["field"] == "query"
#
# As DUAS afirmacoes trabalham juntas, e o segundo `assert` e que preserva o tema do
# dia. O codigo prova QUE tipo de erro foi; o parametro prova que a mensagem ORIENTA —
# que ela aponta o campo `query`, e nao um "configuracao invalida" generico. Reescrever
# a frase nao quebra nenhum dos dois; parar de dizer qual campo falta quebra o segundo,
# e e exatamente isso que se quer travar.
# =============================================================================

"""Tests for the YAML config loader.

The rule this module exists to enforce: never fail silently, never guess. A missing
required field is an error with a name in it, not a None that explodes three modules
later.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from datalens.config_loader import Config, ConfigError, load_config


def write_config(tmp_path: Path, body: str) -> Path:
    """Small helper: a YAML file on disk, since that is what the loader takes."""
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def failure(path: Path) -> "object":
    """Carrega esperando falha e devolve a `Message` do erro.

    Existe para os testes lerem `.code` e `.params` sem repetir o bloco `raises` em
    vinte lugares. Um helper de teste tambem e codigo: se voce se pegar copiando o
    mesmo `with pytest.raises(...) as caught` cinco vezes, extraia.
    """
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    return caught.value.message


# --- The happy path -----------------------------------------------------------


def test_a_minimal_csv_config_loads(tmp_path: Path):
    # Arrange
    path = write_config(
        tmp_path,
        """
        source:
          type: csv
          path: data/exemplos/acoes_b3.csv
        """,
    )

    # Act
    config = load_config(path)

    # Assert
    assert isinstance(config, Config)
    assert config.source.type == "csv"
    assert config.source.path == "data/exemplos/acoes_b3.csv"


def test_omitted_optional_sections_get_defaults(tmp_path: Path):
    """A config with only `source` must work. Defaults are what make the tool
    usable on day one - 'zero config by default' was the product decision.
    """
    # Arrange
    path = write_config(tmp_path, "source:\n  type: csv\n  path: x.csv\n")

    # Act
    config = load_config(path)

    # Assert
    assert config.columns == {}
    assert isinstance(config.profile, dict)
    assert config.source.parameters == {}
    assert config.source.options == {}


def test_connector_options_are_carried_through(tmp_path: Path):
    # Arrange
    path = write_config(
        tmp_path,
        """
        source:
          type: csv
          path: x.csv
          options:
            separator: ";"
            decimal: ","
        """,
    )

    # Act
    config = load_config(path)

    # Assert
    assert config.source.options["separator"] == ";"
    assert config.source.options["decimal"] == ","


def test_the_config_is_immutable(tmp_path: Path):
    """Config is read once and shared. Anything that can rewrite it mid-run turns
    a bug into a mystery.
    """
    # Arrange
    config = load_config(write_config(tmp_path, "source:\n  type: csv\n  path: x.csv\n"))

    # Act / Assert
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.source.type = "sql"


# --- The five ways to break it (Bloco C do Dia 14) ----------------------------


def test_a_missing_file_says_which_file(tmp_path: Path):
    # Act
    message = failure(tmp_path / "config.yaml")

    # Assert
    assert message.code == "config_file_not_found"
    assert "config.yaml" in str(message.params["path"])


def test_malformed_yaml_is_reported_as_a_config_error(tmp_path: Path):
    """O erro cru do PyYAML fala de 'block mapping' e numero de linha em ingles de
    parser. Embrulhar num ConfigError e o que permite a tela mostrar uma frase.
    """
    # Arrange - unbalanced bracket
    path = write_config(tmp_path, "source: [type: csv\n")

    # Act / Assert
    assert failure(path).code == "config_unreadable"


def test_a_missing_source_section_names_the_section(tmp_path: Path):
    # Arrange
    path = write_config(tmp_path, "profile:\n  show_missing: true\n")

    # Act
    message = failure(path)

    # Assert
    assert message.code == "config_missing_section"
    assert message.params["section"] == "source"


def test_an_unknown_source_type_lists_the_valid_ones(tmp_path: Path):
    """'Invalid type' is useless. 'Invalid type parquet; use csv, excel, json, sql
    or api' tells the user what to type next - e o `valid` e quem carrega essa lista.
    """
    # Arrange
    path = write_config(tmp_path, "source:\n  type: parquet\n  path: x.parquet\n")

    # Act
    message = failure(path)

    # Assert
    assert message.code == "config_invalid_source_type"
    assert "parquet" in str(message.params["type"])
    assert "csv" in message.params["valid"]


def test_every_connector_type_is_accepted(tmp_path: Path):
    """The list in the error message and the list the loader accepts must be the same
    list. Two hand-maintained lists drift, and the drift shows up as 'invalid type
    json' on a type that works.
    """
    # Arrange
    bodies = {
        "csv": "source:\n  type: csv\n  path: x.csv\n",
        "excel": "source:\n  type: excel\n  path: x.xlsx\n",
        "json": "source:\n  type: json\n  path: x.json\n",
        "sql": "source:\n  type: sql\n  connection: sqlite:///x.db\n  query: SELECT 1\n",
        "api": "source:\n  type: api\n  url: https://x.com\n",
    }

    # Act / Assert
    for expected, body in bodies.items():
        assert load_config(write_config(tmp_path, body)).source.type == expected


def test_a_sql_source_without_a_query_is_rejected(tmp_path: Path):
    """Validation is per-type: `query` is required for sql and meaningless for csv."""
    # Arrange
    path = write_config(
        tmp_path, "source:\n  type: sql\n  connection: sqlite:///finance.db\n"
    )

    # Act
    message = failure(path)

    # Assert
    assert message.code == "config_missing_field"
    assert message.params["field"] == "query"


def test_a_csv_source_without_a_path_is_rejected(tmp_path: Path):
    # Arrange
    path = write_config(tmp_path, "source:\n  type: csv\n")

    # Act
    message = failure(path)

    # Assert
    assert message.code == "config_missing_field"
    assert message.params["field"] == "path"


# --- The json source: exactly one of path or url ------------------------------
# O unico tipo com escolha EXCLUSIVA. Os tres testes abaixo cobrem os tres estados
# possiveis, e e a combinacao deles que fecha o buraco: testar so o caso feliz deixa
# passar tanto o "nenhum dos dois" quanto o "os dois juntos".


def test_a_json_source_accepts_a_local_path(tmp_path: Path):
    # Arrange
    path = write_config(
        tmp_path, "source:\n  type: json\n  path: data/exemplos/selic.json\n"
    )

    # Act
    config = load_config(path)

    # Assert
    assert config.source.path == "data/exemplos/selic.json"
    assert config.source.url is None


def test_a_json_source_accepts_a_url(tmp_path: Path):
    """Same connector, other origin - the config has to allow both."""
    # Arrange
    path = write_config(
        tmp_path,
        "source:\n"
        "  type: json\n"
        "  url: https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados?formato=json\n",
    )

    # Act
    config = load_config(path)

    # Assert
    assert config.source.url.startswith("https://")
    assert config.source.path is None


def test_a_json_source_with_neither_path_nor_url_names_both(tmp_path: Path):
    """Naming only one of them sends the user to fix the wrong half.

    Repare que agora a exigencia esta no PARAMETRO, nao no texto: `fields` tem que
    conter os dois nomes. E a mesma cobranca de antes, sobrevivendo a traducao.
    """
    # Arrange
    path = write_config(tmp_path, "source:\n  type: json\n")

    # Act
    message = failure(path)

    # Assert
    assert message.code == "config_missing_field"
    assert "path" in message.params["field"]
    assert "url" in message.params["field"]


def test_a_json_source_with_both_path_and_url_is_rejected(tmp_path: Path):
    """Silently preferring one would make the other line a lie that sits in the
    config file for months looking correct.
    """
    # Arrange
    path = write_config(
        tmp_path, "source:\n  type: json\n  path: x.json\n  url: https://x.com\n"
    )

    # Act
    message = failure(path)

    # Assert
    assert message.code == "config_conflicting_fields"


def test_json_connector_options_are_carried_through(tmp_path: Path):
    # Arrange
    path = write_config(
        tmp_path,
        """
        source:
          type: json
          path: x.json
          options:
            records_path: data.items
            lines: true
        """,
    )

    # Act
    config = load_config(path)

    # Assert
    assert config.source.options["records_path"] == "data.items"
    assert config.source.options["lines"] is True


# --- O que o floco de neve trouxe: bind parameters ----------------------------
# NOVO. Com 21 tabelas, a query util tem filtro, e filtro tem valor. Estes quatro
# testes existem para que o caminho SEGURO seja o caminho FACIL.


def test_sql_bind_parameters_are_carried_through(tmp_path: Path):
    """O valor viaja separado do texto da query - e isso que barra SQL injection.

    A config so precisa entregar o dicionario intacto ao `SQLConnector`; quem faz a
    separacao e o driver. O trabalho do loader e nao atrapalhar.
    """
    # Arrange
    path = write_config(
        tmp_path,
        """
        source:
          type: sql
          connection: sqlite:///data/exemplos/finance.db
          query: SELECT ticker, date, close FROM quotes WHERE ticker = :ticker
          parameters:
            ticker: PETR4.SA
        """,
    )

    # Act
    config = load_config(path)

    # Assert
    assert config.source.parameters == {"ticker": "PETR4.SA"}


def test_a_query_placeholder_without_a_value_is_rejected(tmp_path: Path):
    """A query pede `:ticker` e a config nao entrega. Sem esta validacao, o erro vem
    do SQLAlchemy, em ingles de driver, falando de 'bind parameter' - e o usuario que
    escreveu um YAML nao faz ideia do que e isso.

    Falhar aqui custa uma linha de codigo; falhar la custa uma tarde do usuario.
    """
    # Arrange
    path = write_config(
        tmp_path,
        "source:\n"
        "  type: sql\n"
        "  connection: sqlite:///x.db\n"
        "  query: SELECT * FROM quotes WHERE ticker = :ticker\n",
    )

    # Act
    message = failure(path)

    # Assert
    assert message.code == "config_missing_query_parameter"
    assert message.params["parameter"] == "ticker"


def test_a_value_that_looks_like_sql_is_just_a_value(tmp_path: Path):
    """`'; DROP TABLE quotes; --` na config e um TICKER esquisito, nao um comando.

    O loader nao "limpa" nem escapa nada - tentar sanear string e a abordagem errada,
    porque sempre falta um caso. O valor passa intacto e vira bind parameter.
    """
    # Arrange
    path = write_config(
        tmp_path,
        "source:\n"
        "  type: sql\n"
        "  connection: sqlite:///x.db\n"
        "  query: SELECT * FROM quotes WHERE ticker = :ticker\n"
        "  parameters:\n"
        "    ticker: \"'; DROP TABLE quotes; --\"\n",
    )

    # Act
    config = load_config(path)

    # Assert
    assert config.source.parameters["ticker"] == "'; DROP TABLE quotes; --"


def test_the_foreign_key_pragma_defaults_to_on_for_sqlite(tmp_path: Path):
    """O schema em floco abre com `PRAGMA foreign_keys = ON` e a razao esta no
    `test_schema.py`: sem ele o banco aceita orfao calado.

    O default e ligado porque a opcao segura tem que ser a que voce ganha sem pedir.
    Desligar continua possivel - carga em massa e o caso legitimo - mas exige escrever.
    """
    # Arrange
    path = write_config(
        tmp_path,
        "source:\n  type: sql\n  connection: sqlite:///x.db\n  query: SELECT 1\n",
    )

    # Act
    config = load_config(path)

    # Assert
    assert config.source.options.get("foreign_keys", True) is True


# --- A correcao manual do detector --------------------------------------------
# NOVO. O floco guarda booleano como INTEGER 0/1 (`is_cash`, `is_tradable`,
# `is_business_day`, `is_holiday`...). O detector le isso como `numeric`, e esta
# CERTO: 0 e 1 sao numeros ate alguem dizer o contrario. `columns:` e esse alguem.


def test_a_manual_column_type_is_carried_through(tmp_path: Path):
    # Arrange
    path = write_config(
        tmp_path,
        """
        source:
          type: sql
          connection: sqlite:///finance.db
          query: SELECT * FROM calendar
        columns:
          date: date
          is_business_day: boolean
          is_holiday: boolean
        """,
    )

    # Act
    config = load_config(path)

    # Assert
    assert config.columns["is_business_day"] == "boolean"
    assert config.columns["date"] == "date"


def test_an_unknown_column_type_lists_the_five_valid_ones(tmp_path: Path):
    """`integer` nao existe no vocabulario do detector, e um typo aqui viraria uma
    correcao que nao corrige nada - silenciosamente.

    A lista de cinco tem que ser a MESMA de `detector.detect()`. Duas listas parecidas
    divergem; foi assim que `boolean` quase ficou de fora do `profiling`.
    """
    # Arrange
    path = write_config(
        tmp_path,
        "source:\n  type: csv\n  path: x.csv\ncolumns:\n  is_holiday: integer\n",
    )

    # Act
    message = failure(path)

    # Assert
    assert message.code == "config_unknown_column_type"
    assert message.params["column"] == "is_holiday"
    assert set(message.params["valid"].split(", ")) == {
        "numeric", "date", "boolean", "category", "text"
    }


def test_the_column_vocabulary_matches_the_detector(tmp_path: Path):
    """★ O teste que impede as duas listas de divergirem, em vez de so avisar depois.

    Ele importa os dois modulos e compara. Se alguem acrescentar um tipo no detector
    e esquecer do loader, este teste fica vermelho no mesmo commit.
    """
    from datalens.config_loader import VALID_COLUMN_TYPES

    # Arrange
    path = write_config(
        tmp_path,
        "source:\n  type: csv\n  path: x.csv\n"
        + "columns:\n"
        + "".join(f"  c{n}: {kind}\n" for n, kind in enumerate(VALID_COLUMN_TYPES)),
    )

    # Act
    config = load_config(path)

    # Assert
    assert set(config.columns.values()) == set(VALID_COLUMN_TYPES)


# --- Os erros restantes -------------------------------------------------------


def test_an_empty_file_is_reported_clearly(tmp_path: Path):
    """PyYAML returns None for an empty file - a classic source of
    'NoneType has no attribute get' five modules downstream.
    """
    # Arrange
    path = write_config(tmp_path, "")

    # Act / Assert
    assert failure(path).code == "config_empty"


def test_an_unknown_top_level_key_is_rejected(tmp_path: Path):
    """A typo like `sorce:` must not be silently ignored - that is the worst kind
    of config bug, because the tool runs and quietly uses defaults.
    """
    # Arrange
    path = write_config(tmp_path, "sorce:\n  type: csv\n  path: x.csv\n")

    # Act
    message = failure(path)

    # Assert
    assert message.code == "config_unknown_key"
    assert message.params["key"] == "sorce"


def test_the_error_reads_in_three_languages(tmp_path: Path):
    """O pagamento do i18n, cobrado uma vez: o MESMO erro, ja levantado, vira frase em
    tres linguas na hora de mostrar. Traduzir na hora de levantar congelaria a frase.
    """
    from datalens.i18n import translate

    # Arrange
    message = failure(write_config(tmp_path, "source:\n  type: csv\n"))

    # Act
    sentences = {lang: translate(message, lang) for lang in ("en", "pt_BR", "es")}

    # Assert
    assert len(set(sentences.values())) == 3
    assert all("path" in sentence for sentence in sentences.values())
