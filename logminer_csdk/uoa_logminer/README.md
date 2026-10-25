# Oracle LogMiner connector for Fivetran Connector SDK

Replicate multiple primary-keyed Oracle tables through a direct connection or an
SSH bastion. Historical loads use one consistent Flashback SCN and resumable
primary-key pages. Incremental syncs use bounded, commit-aware LogMiner windows.

Select destination columns explicitly. All primary-key columns are included.
LOB, LONG, BFILE and XML payloads are excluded. A primary-key value change
soft-deletes the old key and upserts a complete row at the new key.

Source DDL schedules a historical reconciliation of **all selected tables**.
The connector soft-truncates those destination tables, reloads them at one new
SCN and catches up subsequent commits. The selected destination columns remain
fixed. This can temporarily mark rows deleted while a reload is in progress.
Selected-column removal, incompatible types, changed primary-key definitions
and replaced source tables stop replication for a reviewed resync.

This is a tested development connector, not a production certification. Read
[validation](docs/validation.md) and [limitations](docs/limitations.md) before use.

## Setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp configuration.example.json configuration.json
```

Fill in the ignored local configuration. Use exactly one of `sid` or
`service_name`. [Configuration](docs/configuration.md) documents all settings;
[Oracle setup](docs/oracle_setup.md) covers permissions and retention.
For tunnelling, follow [SSH setup](docs/ssh.md).

## Test

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy --ignore-missing-imports connector.py configuration.py errors.py identifiers.py oracle_client.py runtime_budget.py schema_models.py selection.py snapshot.py state.py type_mapping.py ssh_tunnel.py logminer schema_evolution
.venv/bin/pytest -q -m "not oracle"
.venv/bin/fivetran debug --configuration configuration.json
```

The local SDK tester stores its destination and state under `files/`. Local
reset is destructive to that tester's state; preserve it when testing replay.
Run read-only Oracle pytest integration tests separately with the documented
environment variables, or `ORACLE_TEST_CONFIGURATION=configuration.json` for
the same source/SSH settings. Live mutation tests require dedicated test tables.

## Deploy

Deploy from this directory using the official Fivetran plugin or installed CLI.
Confirm account, group, destination and connection before deployment. Create a runtime-only staging folder first:

```bash
.venv/bin/python tools/stage_deployment.py
cd .deploy
.venv/bin/fivetran deploy --destination DESTINATION_NAME --connection CONNECTION_NAME --python 3.13 --configuration configuration.json
```

For the official plugin, target `.deploy` and use its `--connection-id` option
for an existing connection. The installed SDK CLI uses destination/connection
**names** instead. Staging keeps tests and
development tools out of the deployment. Test first and explicitly choose a
schedule after validation. See [deployment](docs/deployment_profiles.md) and
[operations](docs/operational_runbook.md).

[Architecture](docs/architecture.md) · [State](docs/state_model.md) ·
[DDL policy](docs/schema_evolution.md) · [SDK assumptions](docs/sdk_assumptions.md)
