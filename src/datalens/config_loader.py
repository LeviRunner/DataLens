"""Reads the YAML config and refuses everything it cannot understand.

Reading YAML is three lines of PyYAML. What makes this a module instead of a script is
what happens when the config is WRONG: every rejection carries a message code and the
name of the field at fault, so the screen can say "a source of type sql requires query"
in the user's language instead of exploding three modules later with `NoneType`.

Two rules this module exists to enforce:
  1. never guess - an unknown key is a typo, not a preference, and silently ignoring it
     is the worst kind of config bug because the tool keeps running on defaults;
  2. never sanitize - a value under `parameters:` travels to the driver as a bind
     parameter, untouched. Escaping strings is the approach that always misses a case;
     keeping the value out of the query text is the one that does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .i18n import DataLensError

# The same five words `detector.detect()` returns. One list, imported by the test that
# compares the two - two hand-kept lists drift, and the drift turns a user's correction
# into silent noise.
VALID_COLUMN_TYPES = ("numeric", "date", "boolean", "category", "text")

VALID_SOURCE_TYPES = ("csv", "excel", "json", "sql", "api")

TOP_LEVEL_KEYS = ("source", "columns", "profile")

# Required fields per source type. `json` is absent on purpose: it is the only type with
# an EXCLUSIVE choice (`path` XOR `url`), and that is validated apart.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "csv": ("path",),
    "excel": ("path",),
    "sql": ("connection", "query"),
    "api": ("url",),
}

JSON_EXCLUSIVE_FIELDS = ("path", "url")

# `:name` in a query, but not the `::` of a Postgres cast nor the `12:30` of a time.
_BIND_PARAMETER = re.compile(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)")

_SOURCE_FIELDS = ("type", "path", "connection", "query", "url", "parameters", "options")


class ConfigError(DataLensError):
    """The config cannot be used as written.

    Raised with a message code and its parameters, never with a sentence:

        raise ConfigError("config_missing_field", type="sql", field="query")
    """


@dataclass(frozen=True)
class SourceConfig:
    """Where the data comes from, in the connectors' own vocabulary.

    Frozen because the config is read once and shared; anything that can rewrite it
    mid-run turns a bug into a mystery.
    """

    type: str  # csv|excel|json|sql|api
    path: str | None = None
    connection: str | None = None
    query: str | None = None
    url: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    """The whole config file, validated.

    `columns` is the manual correction of the detector: `{column: type}` with the type
    taken from `VALID_COLUMN_TYPES`.
    """

    source: SourceConfig
    columns: dict[str, str] = field(default_factory=dict)
    profile: dict[str, Any] = field(default_factory=dict)


def load_config(path: str | Path) -> Config:
    """Reads `path` and returns the validated config, or raises `ConfigError`."""
    target = Path(path)
    raw = _read_yaml(target)

    _reject_unknown_keys(raw)
    source = _build_source(_require_section(raw, "source"))
    columns = _validate_columns(_optional_mapping(raw, "columns"))

    return Config(source=source, columns=columns, profile=_optional_mapping(raw, "profile"))


# --- Reading ------------------------------------------------------------------


def _read_yaml(target: Path) -> dict[str, Any]:
    """Loads the file into a mapping, turning every failure into a `ConfigError`."""
    if not target.is_file():
        raise ConfigError("config_file_not_found", path=target)

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        # PyYAML talks about block mappings and line numbers in parser English. Wrapping
        # it is what lets the screen show a sentence.
        raise ConfigError("config_unreadable", path=target, detail=str(error)) from error
    except OSError as error:
        raise ConfigError("config_unreadable", path=target, detail=str(error)) from error

    # PyYAML returns None for an empty file - a classic source of
    # "NoneType has no attribute get" five modules downstream.
    if raw is None:
        raise ConfigError("config_empty", path=target)
    if not isinstance(raw, dict):
        raise ConfigError("config_unreadable", path=target, detail=type(raw).__name__)

    return raw


def _reject_unknown_keys(raw: dict[str, Any]) -> None:
    """A typo like `sorce:` is an error, never a key we quietly ignore."""
    for key in raw:
        if key not in TOP_LEVEL_KEYS:
            raise ConfigError(
                "config_unknown_key", key=key, valid=", ".join(TOP_LEVEL_KEYS)
            )


def _reject_unknown_source_fields(section: dict[str, Any]) -> None:
    """Same rule one level down: `pth:` is a typo, not a field to ignore.

    Without this, a mistyped `pth: x.csv` would fall through to "a source of type csv
    requires path" - an accurate message that sends the reader to add a line that is
    already there, one letter away. Naming the typo is the difference between a
    30-second fix and an afternoon.
    """
    for key in section:
        if key not in _SOURCE_FIELDS:
            raise ConfigError(
                "config_unknown_key", key=key, valid=", ".join(_SOURCE_FIELDS)
            )


def _require_section(raw: dict[str, Any], section: str) -> dict[str, Any]:
    value = raw.get(section)
    if not isinstance(value, dict):
        raise ConfigError("config_missing_section", section=section)
    return value


def _optional_mapping(raw: dict[str, Any], section: str) -> dict[str, Any]:
    """An omitted section is an empty one - zero config by default."""
    value = raw.get(section)
    return dict(value) if isinstance(value, dict) else {}


# --- The source ---------------------------------------------------------------


def _build_source(section: dict[str, Any]) -> SourceConfig:
    source_type = _validate_source_type(section)
    _reject_unknown_source_fields(section)
    parameters = _sub_mapping(section, "parameters")

    _validate_required_fields(source_type, section)
    if source_type == "sql":
        _validate_bind_parameters(str(section.get("query", "")), parameters)

    return SourceConfig(
        type=source_type,
        path=_text(section.get("path")),
        connection=_text(section.get("connection")),
        query=_text(section.get("query")),
        url=_text(section.get("url")),
        parameters=parameters,
        options=_sub_mapping(section, "options"),
    )


def _validate_source_type(section: dict[str, Any]) -> str:
    source_type = section.get("type")
    if source_type not in VALID_SOURCE_TYPES:
        raise ConfigError(
            "config_invalid_source_type",
            type=source_type,
            valid=", ".join(VALID_SOURCE_TYPES),
        )
    return str(source_type)


def _validate_required_fields(source_type: str, section: dict[str, Any]) -> None:
    """Per-type validation: `query` is required for sql and meaningless for csv."""
    if source_type == "json":
        _validate_exclusive_choice(section)
        return

    for name in REQUIRED_FIELDS[source_type]:
        if _text(section.get(name)) is None:
            raise ConfigError("config_missing_field", type=source_type, field=name)


def _validate_exclusive_choice(section: dict[str, Any]) -> None:
    """`json` takes `path` OR `url`, exactly one - neither and both are both errors."""
    given = [name for name in JSON_EXCLUSIVE_FIELDS if _text(section.get(name)) is not None]

    if not given:
        # Naming only one of them sends the user to fix the wrong half.
        raise ConfigError(
            "config_missing_field",
            type="json",
            field=" or ".join(JSON_EXCLUSIVE_FIELDS),
        )
    if len(given) > 1:
        raise ConfigError(
            "config_conflicting_fields",
            type="json",
            fields=", ".join(JSON_EXCLUSIVE_FIELDS),
        )


def _validate_bind_parameters(query: str, parameters: dict[str, Any]) -> None:
    """Every `:name` in the query needs a value here, and no value is ever escaped.

    Failing here costs one line of code; failing at the driver costs the user an
    afternoon reading about "bind parameters" in a language they did not choose.
    """
    for name in _BIND_PARAMETER.findall(query):
        if name not in parameters:
            raise ConfigError("config_missing_query_parameter", parameter=name)


def _sub_mapping(section: dict[str, Any], key: str) -> dict[str, Any]:
    """The value is copied, never transformed - a bind parameter travels intact."""
    value = section.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    """Normalises an absent or blank scalar to None, so `path:` alone is not a path."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# --- The manual column types --------------------------------------------------


def _validate_columns(columns: dict[str, Any]) -> dict[str, str]:
    """Checks the user's correction against the detector's own five-word vocabulary."""
    for column, column_type in columns.items():
        if column_type not in VALID_COLUMN_TYPES:
            raise ConfigError(
                "config_unknown_column_type",
                column=column,
                type=column_type,
                valid=", ".join(VALID_COLUMN_TYPES),
            )
    return {str(column): str(kind) for column, kind in columns.items()}
