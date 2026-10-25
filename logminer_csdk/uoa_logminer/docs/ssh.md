# SSH tunnelling

SSH is optional and disabled by default. It applies to both `schema()` and
`update()` because each uses the same Oracle client. Each client session opens
one SSH connection and one `direct-tcpip` channel to the configured Oracle host
and port. The SSH server resolves that database hostname.

## Configuration

Configuration remains a flat JSON object with string values. Keep Oracle
credentials and exactly one of `sid` or `service_name` as usual. Add:

| Field | Meaning |
| --- | --- |
| `ssh_enabled` | Set to `"true"` to enable the tunnel; default `"false"`. |
| `ssh_host` | Bastion hostname reachable from the connector runtime. |
| `ssh_port` | Bastion port; default `"22"`. |
| `ssh_username` | SSH login account. |
| `ssh_host_key` | Trusted public host key as `key-type base64-key`, optionally followed by a single comment token. |
| `ssh_password` | Password authentication secret; use this or `ssh_private_key`. |
| `ssh_private_key` | Complete private key text with actual newlines, serialized using JSON escapes. RSA, ECDSA and Ed25519 are supported. |
| `ssh_public_key` | Optional matching public key to copy into the bastion's authorized_keys. When supplied, it must match the private key. |
| `ssh_private_key_passphrase` | Optional decryption secret for `ssh_private_key`. |
| `ssh_connect_timeout_seconds` | TCP/banner/auth/channel and forwarding-write timeout; default `"10"`, allowed range 1–60. |

Use exactly one authentication method. The key pair can be staged with
`ssh_enabled=false` while preparing the bastion. Active bastion/authentication
settings with SSH disabled are rejected to prevent accidental direct connections.
Missing or mismatched
host keys fail before Oracle authentication. The connector never learns a key
automatically, searches local private-key files, or uses the SSH agent.

An illustrative key-authentication configuration fragment:

```json
{
  "ssh_enabled": "true",
  "ssh_host": "bastion.example.com",
  "ssh_port": "22",
  "ssh_username": "connector",
  "ssh_host_key": "ssh-ed25519 <trusted-public-key-base64>",
  "ssh_private_key": "<complete-private-key-text>",
  "ssh_connect_timeout_seconds": "10"
}
```

Replace placeholders locally; obtain the public host key through a trusted
channel. Put secrets in ignored local configuration or the official plugin's
configuration-entry flow. Fivetran supplies configuration securely at runtime.
Private keys are parsed in memory and never written by the tunnel to disk,
logs or connector state. Secret fields are excluded from configuration repr.

## Lifecycle and requirements

Install dependencies from `requirements.txt`; Paramiko 4.0.0 is pinned. No system
SSH executable or Oracle Instant Client is required. The bastion must permit
TCP forwarding to the Oracle endpoint and have network/DNS access to it. The
connector runtime must reach the bastion.

The local listener binds only to `127.0.0.1` on an automatically allocated port.
Oracle thin mode connects to that port using the original SID or service name.
Out-of-band Oracle breaks are disabled because SSH forwards the ordinary byte
stream. There is no automatic direct-connection fallback after an SSH failure.

The user-requested SSH transport uses a session-scoped forwarding thread plus
Paramiko's transport thread. These are a transport-only exception to PLAN's
original prohibition on background threads; they do not schedule or poll for
redo. There is no persistent tunnel daemon. The forwarding lifetime is bounded
by `max_invocation_seconds` after local connection acceptance, with bounded I/O
timeouts. Oracle closes first, followed by sockets, the SSH client and a joined
forwarding worker. Partial startup and callback failures also release resources.
Each later invocation creates a fresh tunnel and resumes normal saved state.

One Oracle TCP connection per client is supported. Connection pools, nested
bastions, SSH agents, and Oracle listener redirects/RAC paths are not supported
or verified by this implementation. DDL historical reconciliation and normal checkpoint rules apply through SSH.

## Verification

Run the configuration/lifecycle suite and local SSH integration tests:

```bash
.venv/bin/pytest tests/unit/test_ssh.py tests/unit/test_ssh_transport.py -q
```

Tests exercise real SSH authentication with passwords, plain/encrypted RSA
keys, host-key mismatch and rejected forwarding, binary round trips larger than
one relay buffer, bounded lifetime, and cleanup after callback failure. ECDSA
and Ed25519 encrypted key parsing is tested against the installed library.
Oracle routing, secret redaction and entry-failure cleanup have unit coverage.

Live validation on 2026-10-01 passed against an ephemeral local server and the
authorized bastion, using Oracle 19.32 thin mode. Historical, LogMiner CDC and
checkpoint replay were tested through SSH. Current results are recorded in
[validation](validation.md); earlier single-table runs are retained locally.

### Generate connection keys

Generate a distinct key pair for each client connection, outside delivered code:

```bash
umask 077
ssh-keygen -t ed25519 -f /secure/path/connector_ed25519 -C oracle-logminer-connector
```

Copy the `.pub` contents to the bastion user's `~/.ssh/authorized_keys`. Ensure
`.ssh` is owned by that user with mode 700 and `authorized_keys` mode 600. Store
the complete private key in the connection's secret configuration as
`ssh_private_key`, and the matching public key as `ssh_public_key`. An encrypted
key also needs `ssh_private_key_passphrase`. Verify the bastion's public host
key through a trusted administrator before setting `ssh_host_key`.

Key generation/provisioning is a one-time administrative step, outside sync
callbacks. The connector never creates a new identity during replication.

## References

- https://docs.paramiko.org/en/4.0/api/client.html
- https://docs.paramiko.org/en/4.0/api/transport.html
- https://python-oracledb.readthedocs.io/en/v4.0.0/api_manual/module.html
