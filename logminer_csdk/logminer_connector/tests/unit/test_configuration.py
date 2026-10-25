import pytest

from configuration import ConnectorConfig
from errors import ConfigurationError


def valid_mapping():
    return {
        "host": "db.example",
        "port": "1521",
        "service_name": "SERVICE",
        "username": "user",
        "password": "secret",
        "include_schema": "app",
        "include_table": "orders",
    }


def test_configuration_normalizes_scope_and_defaults():
    config = ConnectorConfig.from_mapping(valid_mapping())
    assert config.include_schema == "APP"
    assert config.include_table == "ORDERS"
    assert config.deployment_profile == "saas"
    assert (
        config.logminer_min_scn_span
        <= config.logminer_initial_scn_span
        <= config.logminer_max_scn_span
    )


def test_configuration_rejects_missing_service_name():
    mapping = valid_mapping()
    mapping["service_name"] = ""
    with pytest.raises(ConfigurationError, match="service_name"):
        ConnectorConfig.from_mapping(mapping)


def test_configuration_rejects_unbounded_transaction_configuration():
    mapping = valid_mapping()
    mapping["max_single_transaction_bytes"] = "2000"
    mapping["max_transaction_buffer_bytes"] = "1500"
    with pytest.raises(ConfigurationError, match="cannot exceed"):
        ConnectorConfig.from_mapping(mapping)


def test_sid_configuration_is_supported_without_service_name():
    mapping = valid_mapping()
    mapping.pop("service_name")
    mapping["sid"] = "DATABASE"
    config = ConnectorConfig.from_mapping(mapping)
    assert config.sid == "DATABASE"
    assert config.service_name is None
    assert mapping["password"] not in repr(config)


def test_service_and_sid_are_mutually_exclusive():
    mapping = {**valid_mapping(), "sid": "DATABASE"}
    with pytest.raises(ConfigurationError, match="exactly one"):
        ConnectorConfig.from_mapping(mapping)
