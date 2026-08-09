# Tests for the JSON connector.

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from datalens.connectors.base import Connector, ConnectorError
from datalens.connectors.json_connector import JSONConnector

# Fixtures

@pytest.fixture
def json_records(tmp_path: Path) -> Path:
    """The easy shape: a list of flat objects, one per row."""
    path = tmp_path / "quotes.json"
    path.write_text(
        json.dumps(
            [
                {"ticker": "PETR4.SA", "date": "2026-01-02", "close": 40.0},
                {"ticker": "PETR4.SA", "date": "2026-01-03", "close": 41.5},
                {"ticker": "AAPL", "date": "2026-01-02", "close": 210.0},
            ]
        ),
        encoding="utf-8"
    )
    return path

@pytest.fixture
def nested_json(tmp_path: Path) -> Path:
    """The shape a real API returns: the rows are buried under keys."""
    path = tmp_path / "nested.json"
    path.write_text(
        json.dumps(
            {
                "status": "ok",
                "data": {
                    "items": [
                        {"codigo": 11, "valor": 0.05},
                        {"codigo": 11, "valor": 0.06},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return path

@pytest.fixture
def jsonl_file(tmp_path: Path) -> Path:
    """JSON Lines: one JSON object per line, no enclosing list."""
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"ticker": "PETR4.SA", "close": 40.0}\n{"ticker": "AAPL", "close": 210.0}\n',
        encoding="utf-8",
    )
    return path

@pytest.fixture
def fake_get(monkeypatch):
    """Replaces requests.get with something we control"""

    class FakeResponse:
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

    def install(payload=None, status_code=200, text="", error=None):
        def _get(*args, **kwargs):
            if error is not None:
                raise error
            return FakeResponse(payload, status_code, text)

        monkeypatch.setattr(requests, "get", _get)

    install.response = FakeResponse
    return install

# The contract

def test_jsoArrangen_connector_satisfies_the_contract_without_inheriting_from_it(json_records):
    # Arrange
    connector = JSONConnector(str(json_records))

    # Act / Assert
    assert isinstance(connector, Connector)
    assert Connector not in JSONConnector.__mro__

# Reading from disk

def test_a_list_of_objects_becomes_one_row_each(json_records):
    # Arrange
    connector = JSONConnector(str(json_records))

    # Act
    result = connector.load()

    # Assert
    assert isinstance(result, pd.DataFrame)
    assert result.shape == (3, 3)
    assert list(result.columns) == ["ticker", "date", "close"]
    assert result["close"][0] == 40.0

def test_load_accepts_a_path_object_and_not_only_a_string(json_records: Path):
    """validate_path takes'str | Path', so the connector should too."""
    # Act
    result = JSONConnector(json_records).load()

    # Assert
    assert result.shape == (3, 3)

def test_records_can_be_dug_out_of_a_nested_payload(nested_json):
    # Arrange
    connector = JSONConnector(str(nested_json), records_path="data.items")

    # Act
    result = connector.load()

    # Assert
    assert list(result.columns) == ["codigo", "valor"]
    assert result.shape == (2, 2)

def test_json_lines_are_read_when_told_so(jsonl_file):
    # Arrange
    connector = JSONConnector(str(jsonl_file), lines=True)

    # Act
    result = connector.load()

    # Assert
    assert result.shape == (2, 2)
    assert result["ticker"][1] == "AAPL"

def test_a_bare_object_becomes_a_single_row(tmp_path: Path):
    """'{"a": 1, "b": 2}' is not a list, but it is one row."""
    # Arrange
    path = tmp_path / "one.json"
    path.write_text('{"ticker": "AAPL", "close": 210.0}', encoding="utf-8")

    # Act
    result = JSONConnector(str(path)).load()

    # Assert
    assert result.shape == (1, 2)

def test_an_empty_list_is_an_empty_dataframe_not_an_error(tmp_path: Path):
    """'No rows' is a valid answer. An empty file is not - see below"""
    # Arrange
    path = tmp_path / "none.json"
    path.write_text("[]", encoding="utf-8")

    # Act
    result = JSONConnector(str(path)).load()

    # Assert
    assert result.empty

def test_missing_keys_across_records_become_missing_values(tmp_path: Path):
    """JSON has no schema: record 2 simply lacks"""
    # Arrange
    path = tmp_path / "ragged.json"
    path.write_text(
        '[{"ticker": "AAPL", "volume": 100}, {"ticker": "KO"}]', encoding="utf-8"
    )

    # Act
    result = JSONConnector(str(path)).load()

    # Assert
    assert result.shape == (2, 2)
    assert pd.isna(result["volume"][1])

# Reading from a URL

def test_a_source_starting_with_htto_is_fetched_instead_of_opened(fake_get):
    """The whole point of the two-origin design"""
    # Arrange
    fake_get(payload=[{"data": "02/01/2026", "valor": "0.05"}])

    # Act
    result = JSONConnector(
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados?formato=json"
    ).load()

    # Assert
    assert result.shape == (1, 2)

def test_records_path_works_the_same_over_the_network(fake_get):
    # Arrange
    fake_get(payload={"data": {"items": [{"codigo": 1, "valor": 5.4}]}})

    # Act
    result = JSONConnector("https://x.com", records_path="data.items").load()

    # Assert
    assert list(result.columns) == ["codigo", "valor"]

# Failures on disk

def test_a_missing_file_is_reported_as_a_connector_error(tmp_path: Path):
    # Arrange
    connector = JSONConnector(str(tmp_path / "does_not_exists.json"))

    # Act / Assert
    with pytest.raises(ConnectorError, match="File not found"):
        connector.load()

def test_a_directory_is_reported_as_a_connector_error(tmp_path: Path):
    with pytest.raises(ConnectorError, match="directory"):
        JSONConnector(str(tmp_path)).load()

def test_an_empty_file_is_reported_as_a_connector_error(tmp_path: Path):
    """Distinct from `[]`: an empty file means the download failed or the export never ran.
    Silently returning zero rows would hide that."""
    # Arrange
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ConnectorError, match="empty"):
        JSONConnector(str(path)).load()

def test_malformed_json_names_the_position_of_the_problem(tmp_path: Path):
    """json.JSONDecodeError knows the line and column. Passing that through turns
    'invalid JSON' into something the user can actually go fix."""
    # Arrange - trailing comma, the classic
    path = tmp_path / "broken_json"
    path.write_text('[{"a": 1},]', encoding="utf-8")

    # Act / Assert
    with pytest.raises(ConnectorError, match="line|linha"):
        JSONConnector(str(path)).load()

def test_the_wrong_encoding_suggests_the_fix(tmp_path: Path):
    """A latin-1 file read as utf-8 raises - the message should say what to try,
    exactly like the CSV connector does.
    """
    # Arrange
    path = tmp_path / "latin.json"
    path.write_bytes('[{"nome": "ação"}]'.encode("latin-1"))

    # Act / Assert
    with pytest.raises(ConnectorError, match="latin-1"):
        JSONConnector(str(path)).load()

def test_json_lines_read_without_the_flag_fails_clearly(jsonl_file):
    """The likeliest user mistake with .jsonl. The message must name the option."""
    # Arrange - lines defaults to False
    connector = JSONConnector(str(jsonl_file))

    # Act / Assert
    with pytest.raises(ConnectorError, match="lines"):
        connector.load()

# Failures over the network

def test_a_404_says_the_address_is_wrong(fake_get):
    # Arrange
    fake_get(payload={}, status_code=404)

    # Act / Assert
    with pytest.raises(ConnectorError, match="404"):
        JSONConnector("https://x.com/wrong").load()

def test_a_timeout_is_reported_as_a_connector_error(fake_get):
    # Arrange
    fake_get(error=requests.Timeout("timed out"))

    # Act / Assert
    with pytest.raises(ConnectorError, match="timeout|tempo"):
        JSONConnector("https://x.com", timeout=1).load()

def test_a_connection_error_is_reported_as_a_connector_error(fake_get):
    # Arrange
    fake_get(error=requests.ConnectionError("no route to host"))

    # Act / Assert
    with pytest.raises(ConnectorError):
        JSONConnector("https://x.com").load()

def test_an_html_error_page_with_status_200_is_reported_as_not_json(fake_get):
    """A captive portal or a maintenance page answers 200 with HTML. Without this
    branch the user gets 'Expecting value: line 1 column 1' and no idea why.
    """
    # Arrange
    fake_get(payload=None, text="<html>Service unavailable</html>")

    # Act / Assert
    with pytest.raises(ConnectorError, match="JSON"):
        JSONConnector("https://x.com").load()

# The failure that both origins share

def test_a_wrong_records_path_names_the_path_it_tried(nested_json):
    """'Path not found' is useless when the config has three paths in it."""
    # Arrange
    connector = JSONConnector(str(nested_json), records_path="data.results")

    # Act / Assert
    with pytest.raises(ConnectorError, match="data.results"):
        connector.load()

def test_a_payload_that_is_not_a_table_is_refused(tmp_path: Path):
    """`[1, 2, 3]` and `42` are valid JSON and are not tables. Turning them into
    a nameless one-column frame would push the confusion downstream into the
    detector, where it is much harder to explain.
    """
    # Arrange
    path = tmp_path / "scalar.json"
    path.write_text("42", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ConnectorError, match="table|tabela"):
        JSONConnector(str(path)).load()

def test_the_original_exception_is_preserved_as_the_cause(tmp_path: Path):
    """`raise ... from error` keeps the traceback. Losing it makes the friendly
    message a downgrade rather than an improvement.
    """
    # Arrange
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ConnectorError) as caught:
        JSONConnector(str(path)).load()
    assert isinstance(caught.value.__cause__, json.JSONDecodeError)

def test_the_error_message_is_the_same_kind_whatever_the_origin(tmp_path, fake_get):
    """The two-origin design only pays off if the caller never has to branch on
    where the data came from. One exception type, both universes.
    """
    # Arrange
    fake_get(error=requests.ConnectionError("no route to host"))

    # Act / Assert
    with pytest.raises(ConnectorError):
        JSONConnector("https://x.com").load()
    with pytest.raises(ConnectorError):
        JSONConnector(str(tmp_path / "nope.json")).load()
        