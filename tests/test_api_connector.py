# =============================================================================
# MODELO DE ESTUDO — tests/test_api_connector.py       (Dia 18)
# -----------------------------------------------------------------------------
# ATENCAO: ja existe um `.private_docs/test_model/test_api_connector.py`, que e o
# MODELO DO FONTE (a classe APIConnector). Este aqui e o modelo dos TESTES dela.
#
# API proposta:
#     class APIConnector:
#         def __init__(self, url, records_path=None, api_key_env=None,
#                      timeout=30, params=None): ...
#         def load(self) -> pd.DataFrame
#
# DUAS COISAS QUE SAO ELIMINATORIAS NUM CODE REVIEW E QUE ESTE ARQUIVO COBRA:
#
#   1. CHAVE DE API NUNCA NO CODIGO. Por isso o parametro e `api_key_env` — o NOME
#      da variavel de ambiente, nao a chave. O teste garante que a chave nunca
#      aparece na mensagem de erro (e o vazamento classico: erro logado com a URL
#      inteira, chave inclusa, indo parar no log de producao).
#
#   2. TESTE DE REDE NAO FAZ REDE. Um teste que chama a API de verdade e lento,
#      falha no aviao, e quebra quando a API muda. Aqui usamos `monkeypatch` para
#      substituir `requests.get` por uma resposta falsa — assim da para testar 429,
#      timeout e JSON torto sem depender de ninguem.
#
# `monkeypatch` e fixture nativa do pytest: troca um atributo durante o teste e
# desfaz sozinha no fim.
#
# -----------------------------------------------------------------------------
# ASSERCAO POR CODIGO, NAO POR FRASE (mudou depois do i18n.py)
#
# A versao anterior escrevia `pytest.raises(ConnectorError, match="429|limite|rate")`.
# Aquele `match` com tres alternativas separadas por `|` era o sintoma: o teste ja
# nao sabia em que lingua a mensagem ia sair, e tentava adivinhar todas.
#
# Com o catalogo, some a adivinhacao: o codigo e `api_rate_limited`, em qualquer
# lingua. E os PARAMETROS continuam cobrando que a mensagem oriente — `status` tem
# que valer 429, senao a frase nao diz ao usuario o que aconteceu.
#
# -----------------------------------------------------------------------------
# O QUE O FLOCO DE NEVE TROUXE
#
# A tabela `data_sources` guarda de onde cada numero veio (`name`, `base_url`,
# `status`, `last_loaded_at`), e `series` + `indicators` sao alimentadas pelo SGS do
# Banco Central. O conector de API e o comeco dessa esteira — e a esteira so funciona
# se ele NAO converter nada. Ver `test_the_connector_does_not_convert_anything`.
# =============================================================================

"""Tests for the API connector.

Nothing here touches the network. Every scenario - success, 404, 429, timeout,
malformed JSON - is simulated, which is the only way to test them reliably.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
import requests

from datalens.connectors.api_connector import APIConnector
from datalens.connectors.base import Connector, ConnectorError


class FakeResponse:
    """The slice of requests.Response that the connector actually uses."""

    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON object could be decoded")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)


@pytest.fixture
def fake_get(monkeypatch):
    """Replaces requests.get with something we control."""

    def install(response=None, error=None):
        def _get(*args, **kwargs):
            if error is not None:
                raise error
            return response

        monkeypatch.setattr(requests, "get", _get)

    return install


def failure(connector) -> "object":
    """Carrega esperando falha e devolve a `Message`. Ver o mesmo helper em
    `test_config_loader.py` — a razao para ele existir e a mesma."""
    with pytest.raises(ConnectorError) as caught:
        connector.load()
    return caught.value.message


# --- The contract -------------------------------------------------------------


def test_api_connector_satisfies_the_contract_without_inheriting_from_it():
    # Arrange
    connector = APIConnector("https://example.com/quotes")

    # Act / Assert
    assert isinstance(connector, Connector)
    assert Connector not in APIConnector.__mro__


# --- Turning JSON into a DataFrame --------------------------------------------


def test_a_list_of_objects_becomes_a_dataframe(fake_get):
    # Arrange
    fake_get(FakeResponse([{"ticker": "AAPL", "close": 210.0}, {"ticker": "KO", "close": 60.0}]))

    # Act
    result = APIConnector("https://example.com/quotes").load()

    # Assert
    assert isinstance(result, pd.DataFrame)
    assert result.shape == (2, 2)


def test_records_can_be_dug_out_of_a_nested_payload(fake_get):
    """Real APIs bury the rows: {"data": {"items": [...]}}. Without a path the
    connector would build a one-row DataFrame containing a dict.
    """
    # Arrange
    fake_get(FakeResponse({"data": {"items": [{"ticker": "AAPL", "close": 210.0}]}}))

    # Act
    result = APIConnector("https://x.com", records_path="data.items").load()

    # Assert
    assert list(result.columns) == ["ticker", "close"]


def test_an_empty_result_is_an_empty_dataframe_not_an_error(fake_get):
    """'No results' is a valid answer from an API, not a failure."""
    # Arrange
    fake_get(FakeResponse([]))

    # Act
    result = APIConnector("https://x.com").load()

    # Assert
    assert result.empty


# --- A esteira que abastece `series` e `indicators` ---------------------------


def test_the_connector_does_not_convert_anything(fake_get):
    """★ NOVO — a resposta real do SGS do Banco Central, que alimenta `indicators`.

        [{"data": "02/01/2026", "valor": "0.052"}, ...]

    Data em dd/mm/aaaa e numero como STRING. A tentacao e o conector "arrumar" isso
    na entrada. Nao arrume: converter aqui espalha a regra de conversao por cinco
    conectores, e cada um vai errar de um jeito diferente com o `1.234,56`.

    A cadeia do projeto e uma so: conector -> detector (opina) -> cleaning (converte).
    Este teste e o que impede o conector de furar a fila.
    """
    # Arrange
    fake_get(
        FakeResponse(
            [
                {"data": "02/01/2026", "valor": "0.052"},
                {"data": "03/01/2026", "valor": "0.052"},
            ]
        )
    )

    # Act
    result = APIConnector("https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados").load()

    # Assert
    assert result["valor"].dtype == object
    assert result["valor"].iloc[0] == "0.052"
    assert result["data"].iloc[0] == "02/01/2026"


def test_query_parameters_are_sent_as_params_not_glued_into_the_url(fake_get, monkeypatch):
    """`?formato=json&dataInicial=01/01/2026` — a barra e a virgula precisam ser
    escapadas, e quem sabe escapar e o `requests`, via `params=`.

    Colar na URL a mao funciona ate o primeiro valor com espaco ou acento. E o mesmo
    raciocinio do bind parameter do SQL: valor viaja separado do texto.
    """
    # Arrange
    captured = {}

    def _get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        return FakeResponse([{"valor": "1"}])

    monkeypatch.setattr(requests, "get", _get)

    # Act
    APIConnector("https://api.bcb.gov.br/dados", params={"formato": "json"}).load()

    # Assert
    assert captured["params"] == {"formato": "json"}
    assert "formato=json" not in captured["url"]


# --- The API key ---------------------------------------------------------------


def test_the_api_key_is_read_from_the_environment(monkeypatch, fake_get):
    # Arrange
    monkeypatch.setenv("DATALENS_API_KEY", "secret-123")
    fake_get(FakeResponse([{"a": 1}]))

    # Act
    result = APIConnector("https://x.com", api_key_env="DATALENS_API_KEY").load()

    # Assert
    assert not result.empty


def test_a_missing_environment_variable_fails_with_a_clear_message(monkeypatch):
    """Fail at load time with the variable's NAME, not with a 401 from the server.

    O nome da variavel e o parametro que orienta: sem ele a mensagem vira "faltou a
    chave" e o usuario nao sabe qual `export` escrever.
    """
    # Arrange
    monkeypatch.delenv("DATALENS_API_KEY", raising=False)
    connector = APIConnector("https://x.com", api_key_env="DATALENS_API_KEY")

    # Act
    message = failure(connector)

    # Assert
    assert message.code == "api_missing_env_key"
    assert message.params["variable"] == "DATALENS_API_KEY"


def test_the_api_key_never_appears_in_an_error_message(monkeypatch, fake_get):
    """The classic leak: an error logs the full URL, key included, into production
    logs. This test is the guardrail.
    """
    # Arrange
    monkeypatch.setenv("DATALENS_API_KEY", "secret-123")
    fake_get(error=requests.Timeout("timed out"))
    connector = APIConnector("https://x.com", api_key_env="DATALENS_API_KEY")

    # Act / Assert
    with pytest.raises(ConnectorError) as caught:
        connector.load()
    assert "secret-123" not in str(caught.value)


def test_the_key_does_not_leak_through_the_message_parameters(monkeypatch, fake_get):
    """★ NOVO — o vazamento que o i18n abriu, e quase ninguem enxerga.

    `str(error)` agora e so a frase EM INGLES. Os parametros continuam vivos dentro de
    `error.message.params`, e e deles que a tela e o log estruturado montam o texto.
    Uma chave escondida ali vaza do mesmo jeito, so que por uma porta nova.

    Por isso o teste anterior nao basta: ele olha a frase, este olha os parametros.
    """
    # Arrange
    monkeypatch.setenv("DATALENS_API_KEY", "secret-123")
    fake_get(error=requests.Timeout("timed out"))
    connector = APIConnector(
        "https://x.com", api_key_env="DATALENS_API_KEY", params={"token": "secret-123"}
    )

    # Act
    message = failure(connector)

    # Assert
    assert "secret-123" not in str(message.params)


# --- Every failure mode of HTTP (Bloco C do Dia 18) ---------------------------


def test_a_timeout_is_reported_as_a_connector_error(fake_get):
    # Arrange
    fake_get(error=requests.Timeout("timed out"))

    # Act
    message = failure(APIConnector("https://x.com", timeout=1))

    # Assert
    assert message.code == "api_timeout"
    assert message.params["timeout"] == 1


def test_a_404_says_the_address_is_wrong(fake_get):
    # Arrange
    fake_get(FakeResponse({}, status_code=404))

    # Act
    message = failure(APIConnector("https://x.com/wrong"))

    # Assert
    assert message.code == "api_http_error"
    assert message.params["status"] == 404


def test_a_429_says_to_slow_down(fake_get):
    """Rate limit is not a bug - it is the API asking you to wait. The message
    must say that, or the user will keep hammering it.

    Codigo PROPRIO, separado de `api_http_error`: 404 e 429 pedem acoes opostas
    (conferir o endereco / esperar), e uma mensagem que serve para os dois nao serve
    para nenhum. O status virar parametro de uma frase generica seria justamente o
    erro que o catalogo existe para evitar.
    """
    # Arrange
    fake_get(FakeResponse({}, status_code=429))

    # Act
    message = failure(APIConnector("https://x.com"))

    # Assert
    assert message.code == "api_rate_limited"


def test_a_connection_error_is_reported_as_a_connector_error(fake_get):
    # Arrange
    fake_get(error=requests.ConnectionError("no route to host"))

    # Act
    message = failure(APIConnector("https://x.com"))

    # Assert
    assert message.code == "api_connection_failed"


def test_a_response_that_is_not_json_is_reported_clearly(fake_get):
    """An HTML error page with status 200 is a real thing that happens."""
    # Arrange
    fake_get(FakeResponse(None, text="<html>Service unavailable</html>"))

    # Act
    message = failure(APIConnector("https://x.com"))

    # Assert
    assert message.code == "api_not_json"


def test_a_wrong_records_path_names_the_path_it_tried(fake_get):
    """Sem o caminho tentado na mensagem, o usuario fica adivinhando entre `results`,
    `data`, `items` e `records` — quatro nomes que quatro APIs diferentes usam.
    """
    # Arrange
    fake_get(FakeResponse({"data": []}))

    # Act
    message = failure(APIConnector("https://x.com", records_path="results"))

    # Assert
    assert message.code == "api_records_path_not_found"
    assert message.params["records_path"] == "results"
