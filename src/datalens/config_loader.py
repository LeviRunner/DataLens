# Tests for the YAML config loader.

from __future__ import annotations

from pathlib import Path

import pytest

from dalens.config_loader import Config, ConfigError, load_config

# Small helper: a YAML file on disk
def write_config(tmp_path: Path, body: str) -> Path:

    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path

# The happy path

def test_a_minimal_csv_config_loads(tmp_path: Path):
    # Arrange
    path = write_config(
        tmp_path,
        """ source:
                type: csv
                path: data/exemplos
        """
    )
    # Act
    config = load_config(path)

    # Assert
    assert isinstance(config, Config)
    assert config.source.type == "csv"
    assert config.source.path == "data/exemplos/acoes_b3.csv"

