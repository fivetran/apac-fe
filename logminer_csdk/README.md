# Oracle LogMiner Connector SDK project

The active connector, tests, setup instructions and documentation are in
[uoa_logminer](uoa_logminer/README.md).

Historical loads use one consistent Flashback SCN and resumable primary-key
pages. Incremental syncs use bounded, commit-aware Oracle LogMiner windows.
Read the [validation results](uoa_logminer/docs/validation.md) and
[limitations](uoa_logminer/docs/limitations.md) before use.

To generate a client delivery archive, run:

```bash
python3 uoa_logminer/tools/package_client.py
```

The archive is written to `.dist/oracle-logminer-connector-client.zip` and
contains source, tests, placeholder configuration and documentation.
Local credentials, SSH keys, SDK state, raw test evidence, virtual environments
and local implementation instructions are excluded from version control.
