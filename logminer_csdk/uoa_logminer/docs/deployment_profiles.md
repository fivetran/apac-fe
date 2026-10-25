# Deployment and sizing

Current Fivetran documentation specifies **4 GB RAM** for SaaS Connector SDK.
This connector uses conservative limits: 64 MiB per transaction, 256 MiB total
transaction buffer, 16 MiB continuation bytes and 16 MiB estimated per operation.
LOB values are excluded. Python/SDK object overhead means estimated payload bytes
are not a hard process RSS ceiling; measure the actual workload.

Local validation uses Python 3.12, SDK 2.10.3, oracledb 4.0.2 and Paramiko 4.0.0.
Sandbox deployment uses Python 3.13. `requirements.txt` contains only source
runtime dependencies; Fivetran supplies the SDK. Development tools live in
`requirements-dev.txt` and are excluded from deployed code.

Deployment should package only the active Python modules, `logminer/`,
`schema_evolution/`, runtime requirements and the ignored local configuration.
The clean client archive also contains tests and documentation. Deploying an
SDK project uploads Python files; exclude `tests/` from the deployment directory.
Do not distribute a configured source project with its local secrets.

Hybrid permits larger measured limits. Long transactions require retained redo
from their first event and complete in-memory commit buffering. Large/long
transactions and large snapshots need workload-specific memory, undo, redo and
schedule sizing. Hybrid operation and production load are not yet certified.

Reference: https://fivetran.com/docs/connector-sdk/deploying-connectors
