# Reviewing the AI-assisted implementation

This project is an Oracle LogMiner connector built for Fivetran Connector SDK.
The repository includes the instructions and implementation specification used
to guide the AI assistant, alongside the resulting code, tests and documentation.
Private access details have been removed from the published instructions.

## Review path

1. Read [AGENTS.md](AGENTS.md) for the assistant's workflow: inspect the repository,
   verify the official plugin and installed SDK APIs, document assumptions, work
   in phases, and test in increasing order of risk.
2. Read [PLAN.md](PLAN.md), starting with its scope amendment. The amendment
   takes precedence over the original broader requirements. In particular,
   source DDL triggers historical reconciliation with fixed selected destination
   columns; destination schema evolution and LOB replication are excluded.
3. Compare those requirements with the
   [architecture](logminer_connector/docs/architecture.md),
   [SDK findings](logminer_connector/docs/sdk_assumptions.md), and
   [implementation](logminer_connector/README.md).
4. Inspect the [tests](logminer_connector/tests) and
   [validation report](logminer_connector/docs/validation.md). Separate local
   assertions, live Oracle evidence and successful cloud execution from
   destination row-level assertions that remain unproven.
5. Review [limitations](logminer_connector/docs/limitations.md) and the
   [operational runbook](logminer_connector/docs/operational_runbook.md) before
   assessing deployment suitability.

## Areas that need close review

Check the snapshot-to-CDC handoff, open transactions spanning invocations,
replay-safe low watermarks, incomplete redo continuations, partial updates and
explicit nulls, key changes, memory limits and DDL reconciliation. These determine
whether the connector can recover without skipping committed source changes.

The plan records requirements, rather than asserting that every requirement has
passed. The validation report and limitations document the evidence and remaining
work. These files preserve the development instructions and review context;
they are not a complete assistant conversation transcript.

## Reproduce local checks

Follow [setup](logminer_connector/README.md), then run its lint, formatting,
type-checking and non-Oracle test commands from `logminer_connector/`.
Live Oracle and Fivetran tests require separately authorized sandbox access.
Keep credentials and raw integration evidence in ignored local files.
