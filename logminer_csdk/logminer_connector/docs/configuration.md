# Configuration

Configuration is a flat JSON object; every value is a string. Copy
`configuration.example.json` to ignored `configuration.json` and supply secrets
locally. Unknown fields are rejected rather than silently falling back.

## Source selection

| Setting | Meaning |
| --- | --- |
| `host`, `port` | Oracle host as reachable directly or from bastion; port defaults to 1521 |
| `username`, `password` | Required Oracle credentials |
| `service_name` or `sid` | Exactly one is required |
| `tables` | JSON object **encoded as a string**, mapping `OWNER.TABLE` to explicit column arrays |

Example value: `"{\"APP.ORDERS\":[\"ID\",\"STATUS\"],\"APP.ITEMS\":[\"ORDER_ID\",\"LINE_ID\",\"AMOUNT\"]}"`.
All primary-key columns are included automatically. Identifiers are normalized
uppercase and must be simple unquoted Oracle identifiers. Select up to 100 tables
and 1000 named columns per table; ensure serialized state fits the 9 MiB limit.
Destination table names combine normalized owner and table; collisions fail.

For client use, provide explicit arrays. `"*"` and legacy `include_schema` plus
`include_table` discover all eligible scalar columns; those discovery modes are
for initial exploration/migration and cannot guarantee a fixed `schema()`
projection after source additions. Convert to explicit arrays and perform a
reviewed connection resync before handover. Do not mix `tables` with legacy fields.
LOB/complex payload columns are always excluded, even if named in a list.

## Work bounds

| Setting | Default | Allowed range |
| --- | --- | --- |
| `snapshot_fetch_size` | 500 | 1–10000 |
| `snapshot_rows_per_invocation` | 25000 | 1–1000000 |
| `logminer_initial_scn_span` | 50000 | 1–100000000 |
| `logminer_min_scn_span` | 1000 | 1–100000000 |
| `logminer_max_scn_span` | 1000000 | 1–100000000 |
| `max_mining_windows_per_invocation` | 10 | 1–10000 |
| `max_invocation_seconds` | 600 | 30–86400 |
| `oracle_call_timeout_seconds` | 20 | 1–120 |
| `archive_log_only` | true | true/false |
| `deployment_profile` | saas | saas/hybrid |

SCN spans must satisfy minimum ≤ initial ≤ maximum. Archive-only mode needs
source archives to become available; a quiet database can defer CDC until the
current redo log archives. Online-plus-archive mode was tested in the sandbox.
Invocation limits are cooperative between operations; driver timeout bounds each
Oracle call. Choose a driver timeout that fits the invocation safety margin.

## Memory limits

Sizes are bytes. Count/byte breaches fail and preserve checkpoint replay.

| Setting | Default |
| --- | --- |
| `max_open_transactions` | 1000 |
| `max_transaction_events` | 100000 |
| `max_transaction_buffer_bytes` | 268435456 (256 MiB) |
| `max_single_transaction_bytes` | 67108864 (64 MiB) |
| `max_operation_bytes` | 16777216 (16 MiB) |
| `max_continuation_bytes` | 16777216 (16 MiB) |
| `max_continuation_fragments` | 8192 |
| `max_lob_bytes` | 8388608 (legacy binary-value guard; LOBs remain excluded) |

The validator enforces common bounds and per-transaction ≤ total-buffer size.
The profile changes limit diagnostics; it does not allocate runtime resources or
select a Fivetran deployment model. Larger limits need measured workload validation
in the intended runtime; limits do not enable unsupported LOBs.
See [SSH fields](ssh.md) for optional bastion authentication and host-key pinning.
