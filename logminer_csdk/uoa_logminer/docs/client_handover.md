# Client handover

## Delivered

Active Connector SDK source, pinned runtime/development requirements, placeholder
configuration, regression tests, runtime-only deployment staging and client
packaging tools, architecture/state/Oracle/SSH/DDL/configuration guides, and the
validation report. Use explicit selected-column arrays for the fixed-schema client
contract. Multiple primary-keyed tables and composite keys are supported.

Client archive: `.dist/oracle-logminer-connector-client.zip` at the repository root.
A SHA256 file manifest is included. Rebuild with `python tools/package_client.py`
from the connector directory. It uses an explicit allowlist.

## Cleanup performed

- Archived `connector1.py`, the obsolete prototype, outside active source.
- Archived old project-local SDK destination/state and raw integration artifacts.
- Removed generated caches and Finder metadata from the active project;
  development environments remain local and are excluded from delivery.
- Restored tests to Git visibility; development and integration code is excluded
  from runtime deployment by `tools/stage_deployment.py`.
- Rewrote README, architecture, state, schema evolution, operations, Oracle setup,
  sizing, SSH and SDK assumptions; added configuration, limitations and validation.
- Kept the internal PLAN with the approved scope amendment, outside client package.
- Retained pure legacy schema classification/barrier tests as migration reference;
  the active connector no longer calls the publication-barrier workflow.

Credentials, SSH keys, configured secrets, raw evidence, virtual environments,
SDK warehouse/state, internal AGENTS/PLAN files and Git metadata are excluded from
the client archive. Local credentials/keys were preserved and not rotated/deleted.
No unrelated source or destination objects were changed.

## Client actions

Fill ignored configuration, establish Oracle/Flashback/LogMiner privileges and
retention, generate a client-specific SSH identity and pin the bastion host key.
Test on dedicated source tables. Stage runtime code, deploy to the intended
connection, query destination acceptance results, then select a schedule.

The connector is not labelled production-ready. See [validation](validation.md)
for performed tests, expected cloud counts and unproven behavior.
