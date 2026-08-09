"""Messages in three languages, without freezing any of them into the code.

THE DESIGN DECISION: an error identifies itself, it does not write itself.

`Message` carries a code and its parameters - never a sentence. The sentence is only
produced at the edge, by `translate()`, in whatever language the caller wants. Three
things follow from that, and each one is a bug the obvious approach would have:

  1. The dashboard can switch language AFTER an error happened and the message
     re-renders. Translating at raise time freezes the sentence in one language.
  2. Tests assert on `error.message.code`, which survives a reworded sentence. Asserting
     on text means every copy edit is a red test - and a test that fails for the wrong
     reason gets ignored.
  3. `str(error)` stays English on purpose (see below), so a log file never ends up
     with three languages mixed into it.

THE LANGUAGE IS PER SESSION, NOT PER PROCESS. Streamlit runs every user session in ONE
Python process, one thread each. A module-level global would be shared by all of them:
two users on different languages, and whoever picked last wins for both - silently, and
only when two people are online at once, which is never while you develop locally.
`ContextVar` is the stdlib answer: it reads like a global and is per execution context.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

DEFAULT_LANGUAGE = "en"

SUPPORTED_LANGUAGES = ("en", "pt_BR", "es")

# For the dashboard selector - the endonym, because a Spanish speaker looks for
# "Español" in the list, not for "Spanish".
LANGUAGE_NAMES = {
    "en": "English",
    "pt_BR": "Português (BR)",
    "es": "Español",
}

_language: ContextVar[str] = ContextVar("datalens_language", default=DEFAULT_LANGUAGE)


@dataclass(frozen=True)
class Message:
    """A problem identified, not yet written in any language.

    `params` fills the placeholders of the template. Keys must be the same in every
    language, which is what `test_i18n` checks.
    """

    code: str
    params: dict[str, Any] = field(default_factory=dict)


# --- The catalog --------------------------------------------------------------
# One entry per code, one block per language. English is the reference: a code missing
# from pt_BR or es falls back to it rather than showing the raw code to the user.
#
# Style rule for every message: say what happened AND what to do about it. "Invalid
# type" is useless; "Invalid type 'parquet'; use csv, excel, json, sql or api" tells
# the reader what to type next.

CATALOG: dict[str, dict[str, str]] = {
    "en": {
        # base.py
        "empty_path": "Empty file path - the connector doesn't know what to read.",
        "file_not_found": (
            "File not found: {path}. Check the path in the config (relative to {cwd})."
        ),
        "path_is_directory": "{path} is a directory, not a data file.",
        # csv_connector.py
        "csv_encoding_failed": (
            "I couldn't read {path} with encoding {encoding}. If the file came from "
            "Excel on Windows, try 'latin-1' in the configuration."
        ),
        "csv_empty_file": "The file {path} is empty - there is no data to read.",
        "csv_parse_failed": (
            "I couldn't interpret the structure of {path} using the separator "
            "{separator}. Check if the file uses ';' or tabulation."
        ),
        # excel_connector.py
        "excel_all_sheets_refused": (
            "The tab needs to be a name or an index - you can't load them all at once, "
            "because the system works with one table per source."
        ),
        "excel_sheet_not_found": "I couldn't open the {sheet} tab in {path}: {detail}",
        "excel_missing_library": (
            "The Excel reader library is missing to open {path}. "
            "Install it with: pip install openpyxl"
        ),
        # sql_connector.py
        "sql_empty_connection": "Empty connection string.",
        "sql_empty_query": (
            "Empty query - the SQL connector needs to know what to query."
        ),
        "sql_invalid_connection": (
            "Invalid connection string: {connection}. Use the SQLAlchemy format, "
            "e.g., 'sqlite:///path/database.db'."
        ),
        "sql_query_failed": "Failed to execute query in {connection}: {detail}",
        # cleaning.py
        "unknown_strategy": (
            "Unknown missing-value strategy {strategy} for column {column}. "
            "Use one of: {valid}."
        ),
        # config_loader.py
        "config_file_not_found": (
            "Config file not found: {path}. Create it, or point --config at the right one."
        ),
        "config_unreadable": (
            "I couldn't parse the YAML in {path}: {detail}. Check the indentation and "
            "the brackets."
        ),
        "config_empty": "The config file {path} is empty - there is nothing to configure.",
        "config_missing_section": (
            "The {section} section is missing from the config - without it there is no "
            "data to read."
        ),
        "config_unknown_key": "Unknown key {key} in the config. Use one of: {valid}.",
        "config_invalid_source_type": "Invalid source type {type}; use one of: {valid}.",
        "config_missing_field": (
            "A source of type {type} requires {field} - add it to the config."
        ),
        "config_conflicting_fields": (
            "A source of type {type} takes only one of {fields}, and the config has more "
            "than one. Delete the line you don't want."
        ),
        "config_unknown_column_type": (
            "Unknown type {type} for column {column}. Use one of: {valid}."
        ),
        "config_missing_query_parameter": (
            "The query uses :{parameter}, but no value was given for it. Add it under "
            "`parameters:` - never paste the value into the query."
        ),
        # api_connector.py
        "api_missing_env_key": (
            "The environment variable {variable} is not set. The API key is read from "
            "the environment, never from the config file."
        ),
        "api_timeout": (
            "The API did not answer within {timeout}s. Try again, or raise `timeout` "
            "in the configuration."
        ),
        "api_http_error": (
            "The API answered with status {status}. Check the address in the config."
        ),
        "api_rate_limited": (
            "The API is refusing requests for now (429): too many in too little time. "
            "Wait a moment before trying again."
        ),
        "api_connection_failed": (
            "I couldn't reach {host}. Check the address and your connection."
        ),
        "api_not_json": (
            "The answer from {host} is not JSON - the server probably returned an error "
            "page. Check the address."
        ),
        "api_records_path_not_found": (
            "I couldn't find the records at {records_path} in the answer. "
            "Available keys: {available}."
        ),
        # json_connector.py
        "json_invalid": (
            "I couldn't read the JSON in {path}: {detail}. The file is not valid JSON."
        ),
        "json_lines_expected": (
            "{path} looks like JSON Lines - one object per line, not one enclosing "
            "list. Set `lines: true` in the configuration."
        ),
        "json_not_tabular": (
            "The JSON in {path} is not a table: {found}. A table is a list of objects, "
            "or one object holding such a list."
        ),
        # sql_connector.py
        "sql_foreign_key_violation": (
            "The operation breaks a foreign key in {connection}: {detail}. Load the "
            "dimension row before the fact row."
        ),
        # statistics.py
        "trend_series_too_short": (
            "{count} point(s) is not a trend in {column} - at least {minimum} are needed."
        ),
        # i18n.py itself
        "unsupported_language": (
            "Unsupported language {language}. Use one of: {valid}."
        ),
    },
    "pt_BR": {
        "empty_path": "Caminho de arquivo vazio - o conector não sabe o que ler.",
        "file_not_found": (
            "Arquivo não encontrado: {path}. Confira o caminho na config "
            "(relativo a {cwd})."
        ),
        "path_is_directory": "{path} é um diretório, não um arquivo de dados.",
        "csv_encoding_failed": (
            "Não consegui ler {path} com a codificação {encoding}. Se o arquivo veio "
            "do Excel no Windows, tente 'latin-1' na configuração."
        ),
        "csv_empty_file": "O arquivo {path} está vazio - não há dado para ler.",
        "csv_parse_failed": (
            "Não consegui interpretar a estrutura de {path} usando o separador "
            "{separator}. Verifique se o arquivo usa ';' ou tabulação."
        ),
        "excel_all_sheets_refused": (
            "A aba precisa ser um nome ou um índice - não dá para carregar todas de "
            "uma vez, porque o sistema trabalha com uma tabela por fonte."
        ),
        "excel_sheet_not_found": "Não consegui abrir a aba {sheet} em {path}: {detail}",
        "excel_missing_library": (
            "Falta a biblioteca de leitura de Excel para abrir {path}. "
            "Instale com: pip install openpyxl"
        ),
        "sql_empty_connection": "String de conexão vazia.",
        "sql_empty_query": (
            "Consulta vazia - o conector SQL precisa saber o que consultar."
        ),
        "sql_invalid_connection": (
            "String de conexão inválida: {connection}. Use o formato do SQLAlchemy, "
            "por exemplo 'sqlite:///caminho/banco.db'."
        ),
        "sql_query_failed": "Falha ao executar a consulta em {connection}: {detail}",
        "unknown_strategy": (
            "Estratégia de faltantes desconhecida {strategy} para a coluna {column}. "
            "Use uma destas: {valid}."
        ),
        "config_file_not_found": (
            "Arquivo de configuração não encontrado: {path}. Crie o arquivo, ou aponte "
            "--config para o caminho certo."
        ),
        "config_unreadable": (
            "Não consegui interpretar o YAML em {path}: {detail}. Confira a indentação "
            "e os colchetes."
        ),
        "config_empty": "O arquivo de configuração {path} está vazio - não há o que configurar.",
        "config_missing_section": (
            "Falta a seção {section} na configuração - sem ela não há dado para ler."
        ),
        "config_unknown_key": "Chave desconhecida {key} na configuração. Use uma destas: {valid}.",
        "config_invalid_source_type": "Tipo de fonte inválido {type}; use um destes: {valid}.",
        "config_missing_field": (
            "Uma fonte do tipo {type} exige {field} - acrescente na configuração."
        ),
        "config_conflicting_fields": (
            "Uma fonte do tipo {type} aceita apenas um entre {fields}, e a configuração "
            "tem mais de um. Apague a linha que você não quer."
        ),
        "config_unknown_column_type": (
            "Tipo desconhecido {type} para a coluna {column}. Use um destes: {valid}."
        ),
        "config_missing_query_parameter": (
            "A consulta usa :{parameter}, mas nenhum valor foi informado. Acrescente em "
            "`parameters:` - nunca cole o valor dentro da consulta."
        ),
        "api_missing_env_key": (
            "A variável de ambiente {variable} não está definida. A chave da API é lida "
            "do ambiente, nunca do arquivo de configuração."
        ),
        "api_timeout": (
            "A API não respondeu em {timeout}s. Tente de novo, ou aumente o `timeout` "
            "na configuração."
        ),
        "api_http_error": (
            "A API respondeu com status {status}. Confira o endereço na configuração."
        ),
        "api_rate_limited": (
            "A API está recusando as chamadas agora (429): pedidos demais em tempo de "
            "menos. Espere um momento antes de tentar outra vez."
        ),
        "api_connection_failed": (
            "Não consegui alcançar {host}. Confira o endereço e a sua conexão."
        ),
        "api_not_json": (
            "A resposta de {host} não é JSON - o servidor provavelmente devolveu uma "
            "página de erro. Confira o endereço."
        ),
        "api_records_path_not_found": (
            "Não encontrei os registros em {records_path} na resposta. "
            "Chaves disponíveis: {available}."
        ),
        "json_invalid": (
            "Não consegui ler o JSON em {path}: {detail}. O arquivo não é JSON válido."
        ),
        "json_lines_expected": (
            "{path} parece ser JSON Lines - um objeto por linha, sem lista externa "
            "envolvendo tudo. Defina `lines: true` na configuração."
        ),
        "json_not_tabular": (
            "O JSON em {path} não é uma tabela: {found}. Uma tabela é uma lista de "
            "objetos, ou um objeto que contenha essa lista."
        ),
        "sql_foreign_key_violation": (
            "A operação viola uma chave estrangeira em {connection}: {detail}. Carregue "
            "a linha da dimensão antes da linha do fato."
        ),
        "trend_series_too_short": (
            "{count} ponto(s) não é tendência em {column} - são necessários pelo menos "
            "{minimum}."
        ),
        "unsupported_language": (
            "Idioma não suportado {language}. Use um destes: {valid}."
        ),
    },
    "es": {
        "empty_path": "Ruta de archivo vacía - el conector no sabe qué leer.",
        "file_not_found": (
            "Archivo no encontrado: {path}. Revisa la ruta en la config "
            "(relativa a {cwd})."
        ),
        "path_is_directory": "{path} es un directorio, no un archivo de datos.",
        "csv_encoding_failed": (
            "No pude leer {path} con la codificación {encoding}. Si el archivo viene "
            "de Excel en Windows, prueba 'latin-1' en la configuración."
        ),
        "csv_empty_file": "El archivo {path} está vacío - no hay datos que leer.",
        "csv_parse_failed": (
            "No pude interpretar la estructura de {path} usando el separador "
            "{separator}. Comprueba si el archivo usa ';' o tabulación."
        ),
        "excel_all_sheets_refused": (
            "La pestaña debe ser un nombre o un índice - no puedes cargarlas todas a "
            "la vez, porque el sistema trabaja con una tabla por fuente."
        ),
        "excel_sheet_not_found": "No pude abrir la pestaña {sheet} en {path}: {detail}",
        "excel_missing_library": (
            "Falta la biblioteca de lectura de Excel para abrir {path}. "
            "Instálala con: pip install openpyxl"
        ),
        "sql_empty_connection": "Cadena de conexión vacía.",
        "sql_empty_query": (
            "Consulta vacía - el conector SQL necesita saber qué consultar."
        ),
        "sql_invalid_connection": (
            "Cadena de conexión inválida: {connection}. Usa el formato de SQLAlchemy, "
            "por ejemplo 'sqlite:///ruta/base.db'."
        ),
        "sql_query_failed": "Falló la ejecución de la consulta en {connection}: {detail}",
        "unknown_strategy": (
            "Estrategia de faltantes desconocida {strategy} para la columna {column}. "
            "Usa una de estas: {valid}."
        ),
        "config_file_not_found": (
            "Archivo de configuración no encontrado: {path}. Créalo, o apunta --config "
            "a la ruta correcta."
        ),
        "config_unreadable": (
            "No pude interpretar el YAML en {path}: {detail}. Revisa la indentación y "
            "los corchetes."
        ),
        "config_empty": "El archivo de configuración {path} está vacío - no hay nada que configurar.",
        "config_missing_section": (
            "Falta la sección {section} en la configuración - sin ella no hay datos que leer."
        ),
        "config_unknown_key": "Clave desconocida {key} en la configuración. Usa una de estas: {valid}.",
        "config_invalid_source_type": "Tipo de fuente inválido {type}; usa uno de estos: {valid}.",
        "config_missing_field": (
            "Una fuente de tipo {type} exige {field} - agrégalo a la configuración."
        ),
        "config_conflicting_fields": (
            "Una fuente de tipo {type} acepta solo uno entre {fields}, y la configuración "
            "tiene más de uno. Borra la línea que no quieras."
        ),
        "config_unknown_column_type": (
            "Tipo desconocido {type} para la columna {column}. Usa uno de estos: {valid}."
        ),
        "config_missing_query_parameter": (
            "La consulta usa :{parameter}, pero no se dio ningún valor. Agrégalo en "
            "`parameters:` - nunca pegues el valor dentro de la consulta."
        ),
        "api_missing_env_key": (
            "La variable de entorno {variable} no está definida. La clave de la API se "
            "lee del entorno, nunca del archivo de configuración."
        ),
        "api_timeout": (
            "La API no respondió en {timeout}s. Inténtalo de nuevo, o sube el `timeout` "
            "en la configuración."
        ),
        "api_http_error": (
            "La API respondió con estado {status}. Revisa la dirección en la configuración."
        ),
        "api_rate_limited": (
            "La API está rechazando las llamadas ahora (429): demasiadas peticiones en "
            "muy poco tiempo. Espera un momento antes de reintentar."
        ),
        "api_connection_failed": (
            "No pude alcanzar {host}. Revisa la dirección y tu conexión."
        ),
        "api_not_json": (
            "La respuesta de {host} no es JSON - el servidor probablemente devolvió una "
            "página de error. Revisa la dirección."
        ),
        "api_records_path_not_found": (
            "No encontré los registros en {records_path} en la respuesta. "
            "Claves disponibles: {available}."
        ),
        "json_invalid": (
            "No pude leer el JSON en {path}: {detail}. El archivo no es JSON válido."
        ),
        "json_lines_expected": (
            "{path} parece ser JSON Lines - un objeto por línea, sin una lista externa "
            "que lo envuelva. Define `lines: true` en la configuración."
        ),
        "json_not_tabular": (
            "El JSON en {path} no es una tabla: {found}. Una tabla es una lista de "
            "objetos, o un objeto que contenga esa lista."
        ),
        "sql_foreign_key_violation": (
            "La operación viola una clave foránea en {connection}: {detail}. Carga la "
            "fila de la dimensión antes que la del hecho."
        ),
        "trend_series_too_short": (
            "{count} punto(s) no es una tendencia en {column} - se necesitan al menos "
            "{minimum}."
        ),
        "unsupported_language": (
            "Idioma no soportado {language}. Usa uno de estos: {valid}."
        ),
    },
}


def get_language() -> str:
    """The language of the current execution context."""
    return _language.get()


def set_language(language: str) -> None:
    """Sets the language for the current execution context.

    In Streamlit, call this once at the top of every rerun from the session state. Each
    session runs in its own thread, so each one keeps its own value.
    """
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            translate(
                Message(
                    "unsupported_language",
                    {"language": repr(language), "valid": ", ".join(SUPPORTED_LANGUAGES)},
                ),
                DEFAULT_LANGUAGE,
            )
        )
    _language.set(language)


def translate(message: Message, language: str | None = None) -> str:
    """Writes the message out, in `language` or in the current context's language.

    An unknown language or a code missing a translation both fall back to English: a
    half-translated catalog must degrade into a readable sentence, never into a raw
    code on the user's screen.
    """
    catalog = CATALOG.get(language or _language.get(), CATALOG[DEFAULT_LANGUAGE])
    template = catalog.get(message.code) or CATALOG[DEFAULT_LANGUAGE].get(message.code)

    if template is None:
        # An unknown code is a bug in our code, not in the user's data. Say so plainly
        # instead of raising and masking the original error being reported.
        return f"[{message.code}] {message.params}"

    try:
        return template.format(**message.params)
    except KeyError as error:
        # A translation with a placeholder the code never fills. Same reasoning.
        return f"[{message.code}: missing parameter {error}] {message.params}"


class DataLensError(Exception):
    """Base for every error the user is meant to read.

    `str(error)` is ALWAYS English - it is what lands in logs and tracebacks, and a log
    file with three languages in it is a log file nobody can grep. The translated text
    comes from `translate(error.message)` at the point of display.
    """

    def __init__(self, code: str, **params: Any) -> None:
        self.message = Message(code, params)
        super().__init__(translate(self.message, DEFAULT_LANGUAGE))
