import json
import os
from pathlib import Path

import pytest

from configuration import ConnectorConfig
from oracle_client import OracleClient


def integration_config():
    config_path = os.environ.get("ORACLE_TEST_CONFIGURATION")
    if config_path:
        return ConnectorConfig.from_mapping(json.loads(Path(config_path).read_text()))
    required = {
        "host": os.environ.get("ORACLE_HOST"),
        "port": os.environ.get("ORACLE_PORT", "1521"),
        "service_name": os.environ.get("ORACLE_SERVICE_NAME"),
        "username": os.environ.get("ORACLE_USERNAME"),
        "password": os.environ.get("ORACLE_PASSWORD"),
        "include_schema": os.environ.get("ORACLE_SCHEMA"),
        "include_table": os.environ.get("ORACLE_TABLE"),
    }
    if os.environ.get("ORACLE_SID"):
        required.pop("service_name")
        required["sid"] = os.environ["ORACLE_SID"]
    missing = [name for name, value in required.items() if not value]
    if missing:
        pytest.skip(
            "Oracle integration environment is incomplete: " + ", ".join(missing)
        )
    return ConnectorConfig.from_mapping(required)


@pytest.mark.oracle
def test_oracle_prerequisites_and_historical_query_are_readable():
    config = integration_config()
    with OracleClient(config) as client:
        validation = client.basic_validation()
        tables = client.discover_tables()
        capture_boundary_scn, oldest_transaction_scn = client.capture_boundary()
        for table in tables:
            rows = client.fetch_historical_page(
                table, [], 1, snapshot_scn=capture_boundary_scn
            )
            assert table.primary_key
            assert len(rows) <= 1
    assert validation["current_scn"]
    assert capture_boundary_scn > 0
    assert oldest_transaction_scn is None or oldest_transaction_scn > 0
