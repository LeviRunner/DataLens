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
        # streamlit_app.py - o banco de exemplo deixou de ser versionado
        "example_data_missing": (
            "The example warehouse is not on disk yet. Build it with: "
            "python scripts/download_data.py  (add --universo tudo for 827 assets)."
        ),
        # ranking.py - what stopped the ranking
        "ranking_missing_column": (
            "The ranking needs the column {column}, which is not in the data. "
            "Available: {available}."
        ),
        "ranking_unreadable_dates": (
            "I couldn't read {column} as dates - without a date there is no way to "
            "line the prices up with the benchmark."
        ),
        "ranking_no_prices": (
            "No readable price left in {column} - check the decimal mark of the source."
        ),
        "ranking_no_benchmark": (
            "No readable rate left in {column} - the benchmark series came back empty."
        ),
        "ranking_history_too_short": (
            "No asset has the {minimum} trading days the ranking needs. Widen the "
            "period, or load a longer history."
        ),
        # ranking.py - why an asset sits where it sits. Read on screen, next to the
        # number they explain, so each one names its own figure.
        "reason_beat_benchmark": "Beat the benchmark by {excess} over the period.",
        "reason_lost_to_benchmark": "Fell short of the benchmark by {excess}.",
        "reason_calm": "Calm ride: {volatility} annualised volatility.",
        "reason_volatile": "Bumpy ride: {volatility} annualised volatility.",
        "reason_shallow_drawdown": "Worst fall from a peak: {drawdown}.",
        "reason_deep_drawdown": (
            "Deep fall from a peak: {drawdown} - the result came with a hard ride."
        ),
        "reason_above_trend": "Trading above its {window}-day average.",
        "reason_below_trend": "Trading below its {window}-day average.",
        "reason_overbought": "RSI at {rsi}: bought heavily in the last days.",
        "reason_oversold": "RSI at {rsi}: sold off heavily in the last days.",
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
        "example_data_missing": (
            "O banco de exemplo ainda não está no disco. Gere com: "
            "python scripts/download_data.py  (use --universo tudo para 827 ativos)."
        ),
        "ranking_missing_column": (
            "O ranking precisa da coluna {column}, que não está nos dados. "
            "Disponíveis: {available}."
        ),
        "ranking_unreadable_dates": (
            "Não consegui ler {column} como datas - sem data não há como alinhar os "
            "preços com o benchmark."
        ),
        "ranking_no_prices": (
            "Nenhum preço legível sobrou em {column} - confira o separador decimal "
            "da fonte."
        ),
        "ranking_no_benchmark": (
            "Nenhuma taxa legível sobrou em {column} - a série do benchmark voltou vazia."
        ),
        "ranking_history_too_short": (
            "Nenhum ativo tem os {minimum} pregões que o ranking exige. Amplie o "
            "período, ou carregue um histórico mais longo."
        ),
        "reason_beat_benchmark": "Superou o benchmark em {excess} no período.",
        "reason_lost_to_benchmark": "Ficou {excess} abaixo do benchmark.",
        "reason_calm": "Trajeto calmo: {volatility} de volatilidade anualizada.",
        "reason_volatile": "Trajeto sacudido: {volatility} de volatilidade anualizada.",
        "reason_shallow_drawdown": "Pior queda desde um pico: {drawdown}.",
        "reason_deep_drawdown": (
            "Queda profunda desde um pico: {drawdown} - o resultado veio com solavanco."
        ),
        "reason_above_trend": "Negociando acima da média de {window} dias.",
        "reason_below_trend": "Negociando abaixo da média de {window} dias.",
        "reason_overbought": "IFR em {rsi}: comprado com força nos últimos dias.",
        "reason_oversold": "IFR em {rsi}: vendido com força nos últimos dias.",
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
        "example_data_missing": (
            "El almacén de ejemplo aún no está en disco. Genéralo con: "
            "python scripts/download_data.py  (usa --universo tudo para 827 activos)."
        ),
        "ranking_missing_column": (
            "El ranking necesita la columna {column}, que no está en los datos. "
            "Disponibles: {available}."
        ),
        "ranking_unreadable_dates": (
            "No pude leer {column} como fechas - sin fecha no hay forma de alinear "
            "los precios con el benchmark."
        ),
        "ranking_no_prices": (
            "No quedó ningún precio legible en {column} - revisa el separador decimal "
            "de la fuente."
        ),
        "ranking_no_benchmark": (
            "No quedó ninguna tasa legible en {column} - la serie del benchmark "
            "volvió vacía."
        ),
        "ranking_history_too_short": (
            "Ningún activo tiene las {minimum} ruedas que el ranking exige. Amplía el "
            "período, o carga un historial más largo."
        ),
        "reason_beat_benchmark": "Superó al benchmark en {excess} en el período.",
        "reason_lost_to_benchmark": "Quedó {excess} por debajo del benchmark.",
        "reason_calm": "Trayecto tranquilo: {volatility} de volatilidad anualizada.",
        "reason_volatile": "Trayecto agitado: {volatility} de volatilidad anualizada.",
        "reason_shallow_drawdown": "Peor caída desde un pico: {drawdown}.",
        "reason_deep_drawdown": (
            "Caída profunda desde un pico: {drawdown} - el resultado vino con sacudones."
        ),
        "reason_above_trend": "Cotizando por encima de su media de {window} días.",
        "reason_below_trend": "Cotizando por debajo de su media de {window} días.",
        "reason_overbought": "RSI en {rsi}: comprado con fuerza en los últimos días.",
        "reason_oversold": "RSI en {rsi}: vendido con fuerza en los últimos días.",
        "unsupported_language": (
            "Idioma no soportado {language}. Usa uno de estos: {valid}."
        ),
    },
}


# --- The interface ------------------------------------------------------------
# The catalog above is about the DATA (an error in a file, a column that cannot be
# read). This one is about the SCREEN: every label, title and caption the dashboard
# prints. They are kept in separate blocks because they change for different reasons -
# a new connector adds error codes, a new panel adds interface codes - and merged into
# one catalog at import time so `translate()` keeps its single lookup and its single
# fallback rule.
#
# The convention: `ui_` prefix, and the ENGLISH text is the reference. A code missing
# from pt_BR or es shows the English sentence, never the raw code.

UI: dict[str, dict[str, str]] = {
    "en": {
        # streamlit_app.py - chrome
        "ui_brand_note": "Investment intelligence terminal",
        "ui_main_menu": "Main menu",
        "ui_reload_data": "Reload data",
        "ui_reload_data_help": (
            "Drops the cache and reads the database again. Press it after running "
            "scripts/download_data.py - the page keeps what it read when it opened."
        ),
        "ui_page": "Page:",
        "ui_page_Home": "Home",
        "ui_page_Explore": "Explore",
        "ui_page_Terminal": "Terminal",
        # streamlit_app.py - the source picker
        "ui_source": "Source",
        "ui_source_example": "example",
        "ui_source_csv": "csv",
        "ui_source_excel": "excel",
        "ui_source_sql": "sql",
        "ui_source_api": "api",
        "ui_clean_first": "Clean the data before profiling",
        "ui_pick_a_source": "Choose a file or fill in the source fields on the left.",
        "ui_csv_file": "CSV file",
        "ui_separator": "Separator",
        "ui_encoding": "Encoding",
        "ui_decimal": "Decimal mark",
        "ui_excel_file": "Excel workbook",
        "ui_sheet": "Sheet (name or index)",
        "ui_header_row": "Header row",
        "ui_connection_string": "Connection string",
        "ui_ready_made_view": "Ready-made view",
        "ui_own_query": "(write my own query)",
        "ui_query": "Query",
        "ui_endpoint_url": "Endpoint URL",
        "ui_records_path": "Records path (optional)",
        "ui_api_key_env": "API key environment variable (optional)",
        # streamlit_app.py - the profiling screen
        "ui_rows_columns": "{rows} rows, {columns} columns",
        "ui_column_types": "Column types - correct any wrong guess",
        "ui_guessed": "{column} - guessed {type} ({confidence})",
        "ui_cleaning_changed": "What cleaning changed",
        "ui_nothing_to_clean": (
            "Nothing to clean: no duplicates, no conversions, no missing values."
        ),
        "ui_profile": "Profile",
        "ui_distribution": "Distribution",
        "ui_distribution_of": "Distribution of",
        "ui_over_time": "Over time",
        "ui_column_statistics": "Column statistics",
        "ui_date_column": "Date column",
        "ui_value_column": "Value column",
        "ui_one_line_per": "One line per",
        "ui_none": "(none)",
        "ui_all": "(all)",
        "ui_th_column": "column",
        "ui_th_type": "type",
        "ui_th_values": "values",
        "ui_th_missing": "missing",
        "ui_th_missing_pct": "missing %",
        "ui_th_statistic": "statistic",
        "ui_th_value": "value",
        "ui_th_action": "action",
        "ui_th_rows": "rows",
        "ui_th_detail": "detail",
        # home.py
        "ui_chip_benchmark": "Benchmark",
        "ui_chip_best": "Best premium",
        "ui_chip_worst": "Worst premium",
        "ui_chip_volatility": "Volatility",
        "ui_chip_coverage": "Coverage",
        "ui_data_source": "Data source",
        "ui_example_warehouse": (
            "Example warehouse - {quotes} daily closes, {assets} assets"
        ),
        "ui_data_source_help": (
            "The home page reads the bundled warehouse so it can answer on the first "
            "frame, without asking anything first. Load your own data in Explore, or "
            "cross it against a live benchmark in Terminal."
        ),
        "ui_please_filter": "Please filter",
        "ui_region": "Region",
        "ui_sector": "Sector",
        "ui_all_regions": "All regions",
        "ui_all_sectors": "All sectors",
        "ui_card_selic": "Selic, period",
        "ui_card_vs_selic": "{ticker} vs Selic",
        "ui_card_calmest": "Calmest: {ticker}",
        "ui_card_assets": "Assets",
        "ui_count_of": "{count} of {total}",
        "ui_panel_benchmark": "Benchmark over time (Selic, % per day)",
        "ui_panel_premium": "Premium over the benchmark, by asset",
        "ui_panel_universe": "Universe by sector",
        # terminal.py
        "ui_search_ingest": "Search and ingest",
        "ui_filter_assets": "Filter assets",
        "ui_filter_assets_help": (
            "Filters the loaded universe by ticker or name before ranking. Leave it "
            "empty to rank everything."
        ),
        "ui_add_files": "Add local files",
        "ui_add_files_help": (
            "CSV and JSON join the workspace as tables. An SVG is drawn as an image - "
            "it is a picture, and no ranking can be computed from it."
        ),
        "ui_sources_form": "Data sources - what gets downloaded, and from where",
        "ui_prices": "Prices",
        "ui_prices_help": (
            "The warehouse holds five years of daily closes for the example assets. "
            "The other option ranks whatever table the Explore page has open - your "
            "own CSV, your own query."
        ),
        "ui_prices_warehouse": "Example warehouse (5 years of daily closes)",
        "ui_prices_loaded": "The table open in the Explore page",
        "ui_nothing_loaded": (
            "Nothing is loaded in Explore yet - pick a source there first."
        ),
        "ui_from": "From",
        "ui_from_help": (
            "Start of the window. Both the prices and the benchmark are cut to it, so "
            "the excess is measured over one single period."
        ),
        "ui_to": "To",
        "ui_benchmark": "Benchmark",
        "ui_benchmark_help": (
            "The rate the shares are measured against. Only daily rates qualify: a "
            "monthly series cannot be compounded day by day."
        ),
        "ui_live_download": "Download the benchmark from the Banco Central",
        "ui_live_download_help": (
            "On: one HTTP call to the BCB, cached for an hour. Off: the same series "
            "already stored in the example database - works offline."
        ),
        "ui_context_series": "Also download (context only)",
        "ui_context_series_help": (
            "Downloaded into the workspace below for you to read and export. They do "
            "NOT enter the ranking - see the label of each one."
        ),
        "ui_how_many": "How many assets in the table",
        "ui_how_the_cross_works": (
            "How the cross works: the Selic arrives as a percentage **per day** "
            "(`{url}`), and gets compounded over the period - not summed. Each share "
            "is then paired with it **by date**, and what is left over is the premium "
            "it paid for the risk it took."
        ),
        "ui_submit": "Download and cross the data",
        "ui_set_period_first": (
            "Set the period and the benchmark above, then press the button."
        ),
        "ui_ticker_column": "Ticker column",
        "ui_price_column": "Price column",
        "ui_workspace": "Workspace",
        "ui_workspace_caption": (
            "Edit anything you need to correct, then export. Changes live in this "
            "session only - neither the API nor the database is written back to."
        ),
        "ui_table_rows": "{name} - {rows} rows",
        "ui_export": "Export {name} (CSV)",
        "ui_benchmark_period": "Benchmark, period",
        "ui_best_premium": "Best premium",
        "ui_assets_ranked": "Assets ranked",
        "ui_trading_days": "Trading days",
        "ui_vs_benchmark_delta": "{value} vs benchmark",
        "ui_top": "Top {count}",
        "ui_why_first": "Why {ticker} is first",
        "ui_why_caption": (
            "Ordered by Sharpe: excess over the benchmark per unit of risk taken. The "
            "moving average and the RSI describe today and are reported, not scored."
        ),
        "ui_th_ticker": "ticker",
        "ui_th_sector": "sector",
        "ui_th_return": "return",
        "ui_th_vs_benchmark": "vs benchmark",
        "ui_th_volatility": "volatility",
        "ui_th_sharpe": "sharpe",
        "ui_th_worst_fall": "worst fall",
        "ui_th_above_avg": "above {window}d avg",
        "ui_yes": "yes",
        "ui_no": "no",
    },
    "pt_BR": {
        "ui_brand_note": "Terminal de inteligência de investimentos",
        "ui_main_menu": "Menu principal",
        "ui_reload_data": "Recarregar dados",
        "ui_reload_data_help": (
            "Descarta o cache e lê o banco de novo. Use depois de rodar "
            "scripts/download_data.py — a página mantém o que leu ao abrir."
        ),
        "ui_page": "Página:",
        "ui_page_Home": "Início",
        "ui_page_Explore": "Explorar",
        "ui_page_Terminal": "Terminal",
        "ui_source": "Fonte",
        "ui_source_example": "exemplo",
        "ui_source_csv": "csv",
        "ui_source_excel": "excel",
        "ui_source_sql": "sql",
        "ui_source_api": "api",
        "ui_clean_first": "Limpar os dados antes de perfilar",
        "ui_pick_a_source": (
            "Escolha um arquivo ou preencha os campos da fonte à esquerda."
        ),
        "ui_csv_file": "Arquivo CSV",
        "ui_separator": "Separador",
        "ui_encoding": "Codificação",
        "ui_decimal": "Separador decimal",
        "ui_excel_file": "Planilha Excel",
        "ui_sheet": "Aba (nome ou índice)",
        "ui_header_row": "Linha do cabeçalho",
        "ui_connection_string": "String de conexão",
        "ui_ready_made_view": "Visão pronta",
        "ui_own_query": "(escrever minha própria consulta)",
        "ui_query": "Consulta",
        "ui_endpoint_url": "URL do endpoint",
        "ui_records_path": "Caminho dos registros (opcional)",
        "ui_api_key_env": "Variável de ambiente da chave de API (opcional)",
        "ui_rows_columns": "{rows} linhas, {columns} colunas",
        "ui_column_types": "Tipos das colunas - corrija qualquer palpite errado",
        "ui_guessed": "{column} - palpite {type} ({confidence})",
        "ui_cleaning_changed": "O que a limpeza mudou",
        "ui_nothing_to_clean": (
            "Nada a limpar: sem duplicatas, sem conversões, sem valores faltantes."
        ),
        "ui_profile": "Perfil",
        "ui_distribution": "Distribuição",
        "ui_distribution_of": "Distribuição de",
        "ui_over_time": "Ao longo do tempo",
        "ui_column_statistics": "Estatísticas da coluna",
        "ui_date_column": "Coluna de data",
        "ui_value_column": "Coluna de valor",
        "ui_one_line_per": "Uma linha por",
        "ui_none": "(nenhum)",
        "ui_all": "(todas)",
        "ui_th_column": "coluna",
        "ui_th_type": "tipo",
        "ui_th_values": "valores",
        "ui_th_missing": "faltantes",
        "ui_th_missing_pct": "% faltante",
        "ui_th_statistic": "estatística",
        "ui_th_value": "valor",
        "ui_th_action": "ação",
        "ui_th_rows": "linhas",
        "ui_th_detail": "detalhe",
        "ui_chip_benchmark": "Referência",
        "ui_chip_best": "Melhor prêmio",
        "ui_chip_worst": "Pior prêmio",
        "ui_chip_volatility": "Volatilidade",
        "ui_chip_coverage": "Cobertura",
        "ui_data_source": "Fonte de dados",
        "ui_example_warehouse": (
            "Armazém de exemplo - {quotes} fechamentos diários, {assets} ativos"
        ),
        "ui_data_source_help": (
            "A página inicial lê o armazém que vem junto para responder já no primeiro "
            "quadro, sem perguntar nada antes. Carregue seus próprios dados em "
            "Explorar, ou cruze-os com uma referência ao vivo no Terminal."
        ),
        "ui_please_filter": "Filtre aqui",
        "ui_region": "Região",
        "ui_sector": "Setor",
        "ui_all_regions": "Todas as regiões",
        "ui_all_sectors": "Todos os setores",
        "ui_card_selic": "Selic, período",
        "ui_card_vs_selic": "{ticker} vs Selic",
        "ui_card_calmest": "Mais calmo: {ticker}",
        "ui_card_assets": "Ativos",
        "ui_count_of": "{count} de {total}",
        "ui_panel_benchmark": "Referência ao longo do tempo (Selic, % ao dia)",
        "ui_panel_premium": "Prêmio sobre a referência, por ativo",
        "ui_panel_universe": "Universo por setor",
        "ui_search_ingest": "Buscar e carregar",
        "ui_filter_assets": "Filtrar ativos",
        "ui_filter_assets_help": (
            "Filtra o universo carregado por código ou nome antes do ranking. Deixe "
            "vazio para ranquear tudo."
        ),
        "ui_add_files": "Adicionar arquivos locais",
        "ui_add_files_help": (
            "CSV e JSON entram no workspace como tabelas. Um SVG é desenhado como "
            "imagem - é uma figura, e nenhum ranking pode ser calculado a partir dela."
        ),
        "ui_sources_form": "Fontes de dados - o que é baixado, e de onde",
        "ui_prices": "Preços",
        "ui_prices_help": (
            "O armazém guarda cinco anos de fechamentos diários dos ativos de exemplo. "
            "A outra opção ranqueia a tabela que estiver aberta na página Explorar - "
            "seu próprio CSV, sua própria consulta."
        ),
        "ui_prices_warehouse": "Armazém de exemplo (5 anos de fechamentos diários)",
        "ui_prices_loaded": "A tabela aberta na página Explorar",
        "ui_nothing_loaded": (
            "Nada carregado em Explorar ainda - escolha uma fonte lá primeiro."
        ),
        "ui_from": "De",
        "ui_from_help": (
            "Início da janela. Tanto os preços quanto a referência são cortados nela, "
            "para que o excesso seja medido sobre um único período."
        ),
        "ui_to": "Até",
        "ui_benchmark": "Referência",
        "ui_benchmark_help": (
            "A taxa contra a qual as ações são medidas. Só taxas diárias servem: uma "
            "série mensal não pode ser capitalizada dia a dia."
        ),
        "ui_live_download": "Baixar a referência do Banco Central",
        "ui_live_download_help": (
            "Ligado: uma chamada HTTP ao BCB, em cache por uma hora. Desligado: a mesma "
            "série já guardada no banco de exemplo - funciona offline."
        ),
        "ui_context_series": "Baixar também (apenas contexto)",
        "ui_context_series_help": (
            "Baixadas para o workspace abaixo, para você ler e exportar. Elas NÃO "
            "entram no ranking - veja o rótulo de cada uma."
        ),
        "ui_how_many": "Quantos ativos na tabela",
        "ui_how_the_cross_works": (
            "Como o cruzamento funciona: a Selic chega como percentual **ao dia** "
            "(`{url}`), e é capitalizada ao longo do período - não somada. Cada ação é "
            "então pareada com ela **por data**, e o que sobra é o prêmio que ela pagou "
            "pelo risco que correu."
        ),
        "ui_submit": "Baixar e cruzar os dados",
        "ui_set_period_first": (
            "Defina o período e a referência acima, depois aperte o botão."
        ),
        "ui_ticker_column": "Coluna do código",
        "ui_price_column": "Coluna do preço",
        "ui_workspace": "Workspace",
        "ui_workspace_caption": (
            "Edite o que precisar corrigir, depois exporte. As mudanças vivem só nesta "
            "sessão - nem a API nem o banco são gravados de volta."
        ),
        "ui_table_rows": "{name} - {rows} linhas",
        "ui_export": "Exportar {name} (CSV)",
        "ui_benchmark_period": "Referência, período",
        "ui_best_premium": "Melhor prêmio",
        "ui_assets_ranked": "Ativos ranqueados",
        "ui_trading_days": "Pregões",
        "ui_vs_benchmark_delta": "{value} vs referência",
        "ui_top": "Top {count}",
        "ui_why_first": "Por que {ticker} está em primeiro",
        "ui_why_caption": (
            "Ordenado por Sharpe: excesso sobre a referência por unidade de risco "
            "assumido. A média móvel e o RSI descrevem o hoje e são informados, não "
            "pontuados."
        ),
        "ui_th_ticker": "código",
        "ui_th_sector": "setor",
        "ui_th_return": "retorno",
        "ui_th_vs_benchmark": "vs referência",
        "ui_th_volatility": "volatilidade",
        "ui_th_sharpe": "sharpe",
        "ui_th_worst_fall": "pior queda",
        "ui_th_above_avg": "acima da média de {window}d",
        "ui_yes": "sim",
        "ui_no": "não",
    },
    "es": {
        "ui_brand_note": "Terminal de inteligencia de inversiones",
        "ui_main_menu": "Menú principal",
        "ui_reload_data": "Recargar datos",
        "ui_reload_data_help": (
            "Descarta la caché y vuelve a leer la base. Úsalo tras ejecutar "
            "scripts/download_data.py: la página conserva lo que leyó al abrir."
        ),
        "ui_page": "Página:",
        "ui_page_Home": "Inicio",
        "ui_page_Explore": "Explorar",
        "ui_page_Terminal": "Terminal",
        "ui_source": "Fuente",
        "ui_source_example": "ejemplo",
        "ui_source_csv": "csv",
        "ui_source_excel": "excel",
        "ui_source_sql": "sql",
        "ui_source_api": "api",
        "ui_clean_first": "Limpiar los datos antes de perfilar",
        "ui_pick_a_source": (
            "Elige un archivo o completa los campos de la fuente a la izquierda."
        ),
        "ui_csv_file": "Archivo CSV",
        "ui_separator": "Separador",
        "ui_encoding": "Codificación",
        "ui_decimal": "Marca decimal",
        "ui_excel_file": "Libro de Excel",
        "ui_sheet": "Hoja (nombre o índice)",
        "ui_header_row": "Fila de encabezado",
        "ui_connection_string": "Cadena de conexión",
        "ui_ready_made_view": "Vista lista para usar",
        "ui_own_query": "(escribir mi propia consulta)",
        "ui_query": "Consulta",
        "ui_endpoint_url": "URL del endpoint",
        "ui_records_path": "Ruta de los registros (opcional)",
        "ui_api_key_env": "Variable de entorno de la clave de API (opcional)",
        "ui_rows_columns": "{rows} filas, {columns} columnas",
        "ui_column_types": "Tipos de columna - corrige cualquier suposición errónea",
        "ui_guessed": "{column} - supuesto {type} ({confidence})",
        "ui_cleaning_changed": "Qué cambió la limpieza",
        "ui_nothing_to_clean": (
            "Nada que limpiar: sin duplicados, sin conversiones, sin valores faltantes."
        ),
        "ui_profile": "Perfil",
        "ui_distribution": "Distribución",
        "ui_distribution_of": "Distribución de",
        "ui_over_time": "A lo largo del tiempo",
        "ui_column_statistics": "Estadísticas de la columna",
        "ui_date_column": "Columna de fecha",
        "ui_value_column": "Columna de valor",
        "ui_one_line_per": "Una línea por",
        "ui_none": "(ninguno)",
        "ui_all": "(todas)",
        "ui_th_column": "columna",
        "ui_th_type": "tipo",
        "ui_th_values": "valores",
        "ui_th_missing": "faltantes",
        "ui_th_missing_pct": "% faltante",
        "ui_th_statistic": "estadística",
        "ui_th_value": "valor",
        "ui_th_action": "acción",
        "ui_th_rows": "filas",
        "ui_th_detail": "detalle",
        "ui_chip_benchmark": "Referencia",
        "ui_chip_best": "Mejor prima",
        "ui_chip_worst": "Peor prima",
        "ui_chip_volatility": "Volatilidad",
        "ui_chip_coverage": "Cobertura",
        "ui_data_source": "Fuente de datos",
        "ui_example_warehouse": (
            "Almacén de ejemplo - {quotes} cierres diarios, {assets} activos"
        ),
        "ui_data_source_help": (
            "La página de inicio lee el almacén incluido para responder en el primer "
            "cuadro, sin preguntar nada antes. Carga tus propios datos en Explorar, o "
            "crúzalos con una referencia en vivo en Terminal."
        ),
        "ui_please_filter": "Filtra aquí",
        "ui_region": "Región",
        "ui_sector": "Sector",
        "ui_all_regions": "Todas las regiones",
        "ui_all_sectors": "Todos los sectores",
        "ui_card_selic": "Selic, período",
        "ui_card_vs_selic": "{ticker} vs Selic",
        "ui_card_calmest": "Más tranquilo: {ticker}",
        "ui_card_assets": "Activos",
        "ui_count_of": "{count} de {total}",
        "ui_panel_benchmark": "Referencia a lo largo del tiempo (Selic, % por día)",
        "ui_panel_premium": "Prima sobre la referencia, por activo",
        "ui_panel_universe": "Universo por sector",
        "ui_search_ingest": "Buscar e ingerir",
        "ui_filter_assets": "Filtrar activos",
        "ui_filter_assets_help": (
            "Filtra el universo cargado por símbolo o nombre antes del ranking. Déjalo "
            "vacío para rankear todo."
        ),
        "ui_add_files": "Agregar archivos locales",
        "ui_add_files_help": (
            "CSV y JSON entran al workspace como tablas. Un SVG se dibuja como imagen - "
            "es una figura, y ningún ranking puede calcularse a partir de ella."
        ),
        "ui_sources_form": "Fuentes de datos - qué se descarga, y de dónde",
        "ui_prices": "Precios",
        "ui_prices_help": (
            "El almacén guarda cinco años de cierres diarios de los activos de ejemplo. "
            "La otra opción rankea la tabla que esté abierta en la página Explorar - tu "
            "propio CSV, tu propia consulta."
        ),
        "ui_prices_warehouse": "Almacén de ejemplo (5 años de cierres diarios)",
        "ui_prices_loaded": "La tabla abierta en la página Explorar",
        "ui_nothing_loaded": (
            "Todavía no hay nada cargado en Explorar - elige una fuente allí primero."
        ),
        "ui_from": "Desde",
        "ui_from_help": (
            "Inicio de la ventana. Tanto los precios como la referencia se recortan a "
            "ella, para que el exceso se mida sobre un único período."
        ),
        "ui_to": "Hasta",
        "ui_benchmark": "Referencia",
        "ui_benchmark_help": (
            "La tasa contra la que se miden las acciones. Solo califican las tasas "
            "diarias: una serie mensual no puede capitalizarse día a día."
        ),
        "ui_live_download": "Descargar la referencia del Banco Central",
        "ui_live_download_help": (
            "Activado: una llamada HTTP al BCB, en caché por una hora. Desactivado: la "
            "misma serie ya guardada en la base de ejemplo - funciona sin conexión."
        ),
        "ui_context_series": "Descargar también (solo contexto)",
        "ui_context_series_help": (
            "Se descargan al workspace de abajo para que las leas y exportes. NO entran "
            "en el ranking - mira la etiqueta de cada una."
        ),
        "ui_how_many": "Cuántos activos en la tabla",
        "ui_how_the_cross_works": (
            "Cómo funciona el cruce: la Selic llega como porcentaje **por día** "
            "(`{url}`), y se capitaliza a lo largo del período - no se suma. Cada acción "
            "se empareja con ella **por fecha**, y lo que queda es la prima que pagó por "
            "el riesgo que tomó."
        ),
        "ui_submit": "Descargar y cruzar los datos",
        "ui_set_period_first": (
            "Define el período y la referencia arriba, luego presiona el botón."
        ),
        "ui_ticker_column": "Columna del símbolo",
        "ui_price_column": "Columna del precio",
        "ui_workspace": "Workspace",
        "ui_workspace_caption": (
            "Edita lo que necesites corregir, luego exporta. Los cambios viven solo en "
            "esta sesión - ni la API ni la base se reescriben."
        ),
        "ui_table_rows": "{name} - {rows} filas",
        "ui_export": "Exportar {name} (CSV)",
        "ui_benchmark_period": "Referencia, período",
        "ui_best_premium": "Mejor prima",
        "ui_assets_ranked": "Activos rankeados",
        "ui_trading_days": "Ruedas",
        "ui_vs_benchmark_delta": "{value} vs referencia",
        "ui_top": "Top {count}",
        "ui_why_first": "Por qué {ticker} está primero",
        "ui_why_caption": (
            "Ordenado por Sharpe: exceso sobre la referencia por unidad de riesgo "
            "asumido. La media móvil y el RSI describen el hoy y se informan, no se "
            "puntúan."
        ),
        "ui_th_ticker": "símbolo",
        "ui_th_sector": "sector",
        "ui_th_return": "retorno",
        "ui_th_vs_benchmark": "vs referencia",
        "ui_th_volatility": "volatilidad",
        "ui_th_sharpe": "sharpe",
        "ui_th_worst_fall": "peor caída",
        "ui_th_above_avg": "sobre la media de {window}d",
        "ui_yes": "sí",
        "ui_no": "no",
    },
}

# One catalog from here on: `translate()` keeps a single lookup and a single fallback.
for _language_code, _entries in UI.items():
    CATALOG[_language_code].update(_entries)


def text(code: str, **params: Any) -> str:
    """The interface string for `code`, in the current context's language.

    The shorthand the screens use. `translate(Message(...))` is the same call written
    out; this exists so a label reads `text("ui_profile")` and not four nested calls.
    """
    return translate(Message(code, params))


def translator(language: str | None = None):
    """`text()` with the language FROZEN, for anything called back later.

    THIS IS NOT A CONVENIENCE, IT IS THE FIX FOR A REAL BUG. `text()` reads the
    language from a ContextVar, so it answers correctly only while the caller is inside
    the execution context that set it. A Streamlit `format_func` is not: it is a
    closure Streamlit keeps and may run outside the script run - and outside it, the
    ContextVar is back to its default, so a Spanish page came out with one English
    option in the middle of it.

    So a widget whose labels are translated binds the language WHEN IT IS DRAWN:

        label = translator()
        st.radio("Page", PAGES, format_func=lambda name: label(f"ui_page_{name}"))

    The values stay stable and the sentences stay in one language, whenever and
    wherever the callback happens to run.
    """
    fixed = language or _language.get()

    def render(code: str, **params: Any) -> str:
        return translate(Message(code, params), fixed)

    return render


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
