# Oracle LogMiner connector for Fivetran Connector SDK

An attempt to leverage Oracle Logminer to replicate data Fivetran Connector SDK. Historical loads use one
consistent Oracle Flashback SCN and resumable primary-key pages. Incremental
syncs use bounded, commit-aware Oracle LogMiner windows.

The connector source, tests, setup instructions and operational documentation
are in [logminer_connector](logminer_connector/README.md).
Read the [validation report](logminer_connector/docs/validation.md) and
[limitations](logminer_connector/docs/limitations.md) before use.

## AI-assisted development

Start with the [AI implementation review guide](AI_REVIEW.md).

[AGENTS.md](AGENTS.md) records the instructions given to the AI assistant,
including official SDK/plugin verification, implementation phases, security
constraints, testing order and failure/restart expectations.
[PLAN.md](PLAN.md) records the implementation specification and current scope.
The published instructions use generic examples and omit private access details.
SDK findings are recorded in
[SDK assumptions](logminer_connector/docs/sdk_assumptions.md).

## Client archive

```bash
python3 logminer_connector/tools/package_client.py
```

The archive is written to `.dist/oracle-logminer-connector-client.zip` and
contains source, tests, placeholder configuration and documentation.
Credentials, SSH keys, SDK state, raw test evidence and virtual environments
remain outside version control.
