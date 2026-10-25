# AGENTS.md

Sanitized instructions for AI-assisted development of an Oracle LogMiner
connector built for Fivetran Connector SDK. Private access details have been
replaced with placeholders. The implementation workflow, SDK verification,
safety requirements and test expectations are preserved for review.

## Primary instruction

Before making any changes, read `PLAN.md` in full.

Treat `PLAN.md` as the authoritative implementation specification for the Oracle LogMiner Fivetran Connector SDK connector. Follow its phases, architecture, correctness requirements, runtime constraints, checkpointing rules, schema-evolution requirements, and test expectations.

Do not begin implementation until you have:

1. Read all of `PLAN.md`.
2. Inspected the existing repository.
3. Installed and verified the official Fivetran Connector SDK Codex plugin described in `PLAN.md`.
4. Verified the installed Fivetran Connector SDK APIs rather than assuming API names or behavior.
5. Written material SDK assumptions to `docs/sdk_assumptions.md`.

## Security requirements

Any credentials supplied separately are restricted to authorized local development
and integration testing.

You must:

- Never commit credentials or credential-bearing local instruction files to Git.
- Ensure `AGENTS.local.md`, `.env`, `.env.local`, generated configuration files containing secrets, and test artifacts containing secrets are listed in `.gitignore`.
- Never print passwords, API secrets, Basic Authentication values, or full connection strings.
- Never include secrets in exceptions, structured logs, snapshots, fixtures, screenshots, test reports, generated documentation, or commit messages.
- Redact secrets from subprocess output before displaying it.
- Prefer injecting credentials through environment variables.
- Do not place real credentials in source code.
- Do not write secrets into Connector SDK state.
- Do not send these credentials to services other than the Fivetran and Oracle endpoints required for this task.
- Do not rotate, revoke, modify, or delete credentials.
- Do not modify unrelated Fivetran connections, destinations, groups, or Oracle objects.
- Keep private access details in ignored `AGENTS.local.md` or local configuration; commit only sanitized repository instructions.

Before running tests, verify that Git ignores local secret-bearing files:

```bash
git check-ignore AGENTS.local.md .env .env.local
```

If any file is not ignored, update `.gitignore` before proceeding.

## Fivetran Connector SDK credentials

Obtain credentials from the authorized operator only when the Connector SDK CLI
or API requires authentication. No working credentials are included here.

- Verify the authentication format in the installed CLI and official SDK docs.
- Use the exact environment-variable names required by the installed tooling.
- Do not assume plain-text key/secret pairs and base64 values are interchangeable.
- Do not decode or regenerate credentials unless the documented workflow requires it.
- Store authenticated profiles outside the repository.
- Stop and report a rejected credential; do not retry with unrelated credentials.

## Fivetran test target

Before any creation or deployment, obtain and verify the authorized sandbox:

```text
Account: <AUTHORIZED_SANDBOX_ACCOUNT>
Destination: <AUTHORIZED_TEST_DESTINATION>
Destination Group ID: <AUTHORIZED_TEST_GROUP_ID>
```

Do not guess these values or deploy until the intended target is confirmed.
Use a unique development connection name. Do not overwrite an existing connector
unless it was created for the current task. Record created IDs in ignored local
results. Do not delete unrelated destination tables; treat the destination as
shared infrastructure.

## Oracle source

Obtain the authorized integration-test endpoint and credentials from the operator.
The following are placeholders, not working connection details:

```text
Host: oracle.example.com
Port: 1521
Service name or SID: <AUTHORIZED_ORACLE_SERVICE_OR_SID>
Username: <AUTHORIZED_TEST_USERNAME>
Password: <INJECT_LOCALLY>
Schema: APP
Initial test table: ORDERS
```

Inject credentials through environment variables or ignored local configuration.
Determine whether the supplied connect identifier is a service name or SID; do
not guess. Use exactly the configured mode. If it cannot be determined, report
the blocker while completing work that does not need a database connection.
Use python-oracledb thin mode unless the plan and verified runtime documentation
establish another supported approach.

## Source safety

The initial source scope is:

```text
APP.ORDERS
```

Start by limiting discovery, snapshots, LogMiner filters, and tests to this table.

Before issuing DDL or DML:

1. Inspect the table definition.
2. Inspect its primary key.
3. Check the current row count.
4. Identify whether it is a dedicated test table.
5. Capture enough metadata to restore the original schema and test rows.
6. Prefer creating separate test tables in `APP` when permissions allow and doing so is safer than changing `ORDERS`.

Do not:

- Drop `ORDERS`.
- Truncate `ORDERS`.
- Delete existing rows.
- Change its primary key.
- Perform destructive type narrowing.
- Make irreversible changes.
- Modify unrelated tables.
- Change database-wide logging or retention settings without explicit approval.

If online DDL tests must use `ORDERS`, use only reversible, uniquely named test columns and compatible widening changes.

Restore the original schema after each test when safe and practical.

Example temporary column naming pattern:

```text
FT_SDK_TEST_<timestamp_or_unique_suffix>
```

Before cleanup, ensure the connector has processed the DDL and post-DDL DML required by the test.

## Required implementation workflow

Follow the implementation phases in `PLAN.md`.

At minimum:

1. Install and verify the Fivetran Codex plugin.
2. Verify Connector SDK APIs and runtime limits.
3. Implement the bounded scheduled `update()` model.
4. Implement versioned state and replay-safe checkpoints.
5. Implement the single-SCN Flashback Query snapshot.
6. Implement bounded LogMiner mining windows.
7. Implement commit-aware transaction buffering.
8. Implement cross-invocation replay.
9. Implement online `ADD COLUMN` support.
10. Implement compatible data-type change support.
11. Implement Connector SDK schema publication or the verified schema-refresh workflow.
12. Add unit, contract, restart, and Oracle integration tests.
13. Document every unsupported or unproven behavior.

Do not implement an infinite loop, background process, daemon, or sleeping poller.

## Testing sequence

Run tests in increasing order of risk.

### 1. Static and unit validation

Run:

- formatting;
- linting;
- type checking;
- unit tests;
- state serialization tests;
- watermark tests;
- schema-diff tests;
- type-compatibility tests;
- transaction-buffer tests;
- DDL-barrier tests.

Do not access Fivetran or Oracle for tests that can be completed locally.

### 2. Oracle read-only validation

Connect to Oracle and verify:

- connectivity;
- thin mode;
- Oracle version;
- current SCN access;
- ARCHIVELOG mode;
- supplemental logging;
- required views;
- required packages;
- schema and table discovery;
- primary-key discovery;
- Flashback Query against `APP.ORDERS`;
- LogMiner prerequisites;
- redo coverage.

Initially perform only read-only queries.

### 3. Historical-sync test

Run a bounded historical snapshot of:

```text
APP.ORDERS
```

Verify:

- one consistent snapshot SCN;
- explicit column projection;
- primary-key pagination;
- bounded `update()` termination;
- checkpoint resume;
- no unbounded memory growth.

### 4. Incremental DML test

Use non-destructive test rows with unique primary-key values.

Test:

- insert;
- update;
- explicit null;
- delete and Fivetran soft-delete behavior;
- rollback;
- transaction spanning multiple mining windows;
- replay after failure;
- replay after checkpoint.

Clean up only rows created by this test, and only after confirming the connector observed the required changes.

### 5. Online ADD COLUMN test

Prefer a dedicated test table.

If `ORDERS` must be used:

1. Add a uniquely named nullable column with no default.
2. Confirm the connector detects the DDL.
3. Confirm the Connector SDK schema gains the column through the verified schema-evolution mechanism.
4. Insert or update a test row using the new column.
5. Confirm post-DDL DML is decoded with the new schema.
6. Confirm absent and explicit-null values remain distinct.
7. Confirm no post-DDL operation was emitted before schema publication.
8. Restore the table only after all required assertions are complete.

### 6. Compatible type-change test

Prefer a dedicated test table and a reversible widening change.

Test a change such as:

```text
VARCHAR2(n) -> VARCHAR2(larger_n)
```

Verify:

- DDL detection;
- old and new schema versions;
- type-compatibility classification;
- Connector SDK schema publication when required;
- correct decoding before and after the DDL boundary;
- checkpoint safety;
- restart and replay around the DDL.

Do not test narrowing or destructive type changes against shared data.

### 7. Fivetran deployment test

Deploy only to:

```text
Account: <AUTHORIZED_SANDBOX_ACCOUNT>
Destination: <AUTHORIZED_TEST_DESTINATION>
Group ID: <AUTHORIZED_TEST_GROUP_ID>
```

Verify:

- connector creation;
- setup and schema discovery;
- first historical sync;
- subsequent incremental sync;
- soft deletes;
- checkpoint continuation;
- schema-change propagation;
- destination row correctness.

Use a unique development connector name.

Do not promote the connector or label it production-ready.

## Required failure and restart tests

Test failures at these boundaries:

```text
after reading redo
during continuation assembly
during transaction buffering
after yielding some operations
after yielding all transaction operations
before checkpoint
after checkpoint
immediately before DDL
immediately after DDL detection
after schema publication
before post-DDL checkpoint
between scheduled update() invocations
```

Verify:

- no committed source change is missed;
- replay may produce duplicates;
- upserts remain idempotent;
- deletes remain idempotent soft deletes;
- unresolved transactions pin the low watermark;
- unresolved DDL pins the low watermark;
- post-DDL DML is never decoded with stale schema metadata.

## Test-result recording

Store test results in ignored local files, for example:

```text
.local-test-results/
.local-test-results/oracle-validation.json
.local-test-results/fivetran-deployment.json
.local-test-results/integration-summary.md
```

Redact all secrets.

Record:

- connector name and ID;
- test timestamps;
- Oracle version;
- SDK version;
- plugin commit;
- snapshot SCN;
- streaming low watermark;
- processed-through SCN;
- high-watermark commit SCN;
- tested DDL SCNs;
- schema fingerprints;
- test outcomes;
- remaining limitations.

## Stop conditions

Stop and report clearly instead of guessing when:

- the Oracle service name cannot be determined;
- required Oracle privileges are missing;
- required redo has aged out;
- Flashback Query cannot access the original SCN;
- a transaction exceeds safe memory limits;
- Connector SDK schema-publication behavior is unavailable or ambiguous;
- an Oracle type change is not proven compatible;
- required schema history is missing;
- the Fivetran target does not match the specified sandbox destination;
- a proposed test could damage shared data;
- a credential is rejected.

Do not work around a safety or correctness failure by:

- advancing the checkpoint;
- skipping data;
- suppressing errors;
- weakening assertions;
- silently changing the requested source or destination.

## Completion criteria

Do not call the connector production-ready until all requirements in `PLAN.md` pass, including:

```text
snapshot consistency tests
cross-invocation transaction tests
restart and replay tests
missing-redo tests
transaction memory-limit tests
LOB and operation-size tests
ADD COLUMN integration tests
data-type-change integration tests
schema-publication failure tests
real Oracle LogMiner integration tests
```

At completion, provide:

1. A summary of implemented functionality.
2. Verified Connector SDK API behavior.
3. Plugin installation details.
4. Test commands run.
5. Fivetran connector and destination identifiers used.
6. Oracle tests performed.
7. DDL tests performed.
8. Data-loss and duplication risk assessment.
9. Unsupported Oracle types or DDL.
10. Unproven assumptions.
11. Clear next steps before production use.