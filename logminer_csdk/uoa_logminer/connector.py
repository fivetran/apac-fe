"""Oracle Flashback historical load and bounded LogMiner SDK connector."""

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

from configuration import ConnectorConfig
from errors import (
    MissingPrivilegeError,
    SchemaMismatchError,
)
from logminer.sync import run_logminer_sync
from oracle_client import OracleClient
from runtime_budget import RuntimeBudget
from schema_models import TableSchema
from snapshot import run_snapshot
from state import ConnectorState


def validate_configuration(configuration: dict) -> ConnectorConfig:
    """Validate and normalize the compact connector configuration."""
    return ConnectorConfig.from_mapping(configuration)


def schema(configuration: dict):
    """Discover selected tables and their complete primary keys."""
    config = validate_configuration(configuration)
    with OracleClient(config) as client:
        tables = client.discover_tables()
    return [table.sdk_definition() for table in tables]


def _validate_streaming_prerequisites(client: OracleClient) -> None:
    validation = client.basic_validation()
    if validation["log_mode"] != "ARCHIVELOG":
        raise MissingPrivilegeError(
            "Oracle database must use ARCHIVELOG mode for LogMiner CDC"
        )
    if validation["supplemental_log_data_min"] not in {"YES", "IMPLICIT"}:
        raise MissingPrivilegeError(
            "Oracle minimal supplemental logging is required for LogMiner CDC"
        )


def update(configuration: dict, state: dict):
    """Perform one finite snapshot or LogMiner catch-up invocation."""
    config = validate_configuration(configuration)
    parsed_state = ConnectorState.load(state)
    runtime = RuntimeBudget.start(config.max_invocation_seconds)

    with OracleClient(config) as client:
        if parsed_state.scope_fingerprint not in {None, config.scope_fingerprint}:
            raise SchemaMismatchError(
                "Source/selection changed; explicit connection resync required"
            )
        identity = client.source_identity()
        if parsed_state.source_identity not in {None, identity}:
            raise SchemaMismatchError(
                "Source database/incarnation changed; explicit connection resync required"
            )
        parsed_state.scope_fingerprint = config.scope_fingerprint
        parsed_state.source_identity = identity
        if parsed_state.pending_schema_change:
            parsed_state.request_resnapshot(
                "Migration of pending DDL to historical reconciliation"
            )
        if parsed_state.phase == "snapshot":
            log.info(
                f"Starting bounded snapshot for "
                f"{config.include_schema}.{config.include_table}"
            )
            run_snapshot(client, config, parsed_state, runtime)
            log.info("Bounded snapshot invocation completed")
            return

        _validate_streaming_prerequisites(client)
        saved = parsed_state.table_schemas()
        current = {table.source_key: table for table in client.discover_tables()}
        if set(saved) != set(current):
            raise SchemaMismatchError(
                "Selected tables changed; explicit connection resync required"
            )
        for key, value in saved.items():
            previous = TableSchema.from_dict(value)
            refreshed = current[key].retain_contract(previous)
            if refreshed.fingerprint != previous.fingerprint:
                parsed_state.request_resnapshot(f"Source metadata changed for {key}")
                op.checkpoint(state=parsed_state.to_dict())
                return
        log.info(
            f"Starting bounded LogMiner catch-up from SCN "
            f"{parsed_state.streaming.low_watermark_scn}"
        )
        run_logminer_sync(client, config, parsed_state, runtime)
        log.info("Bounded LogMiner invocation completed")


connector = Connector(update=update, schema=schema)


if __name__ == "__main__":
    connector.debug()
