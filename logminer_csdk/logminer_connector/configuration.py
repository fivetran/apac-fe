"""Compact, string-backed Connector SDK configuration."""

import hashlib
import json
from dataclasses import dataclass, field

from errors import ConfigurationError
from selection import TableSelection, parse_selections


def _required(configuration: dict, key: str) -> str:
    value = configuration.get(key)
    if value is None or not str(value).strip():
        raise ConfigurationError(f"Missing required configuration field: {key}")
    return str(value).strip()


def _secret(configuration: dict, key: str) -> str | None:
    value = configuration.get(key)
    return str(value) if value is not None and str(value) else None


@dataclass(frozen=True)
class SSHConfig:
    host: str
    port: int
    username: str
    host_key: str
    public_key: str | None = None
    password: str | None = field(default=None, repr=False)
    private_key: str | None = field(default=None, repr=False)
    private_key_passphrase: str | None = field(default=None, repr=False)
    connect_timeout_seconds: int = 10

    @classmethod
    def from_mapping(cls, configuration: dict) -> "SSHConfig | None":
        if not _boolean(configuration, "ssh_enabled", False):
            if any(
                str(configuration.get(key) or "").strip()
                for key in (
                    "ssh_host",
                    "ssh_username",
                    "ssh_host_key",
                    "ssh_password",
                )
            ):
                raise ConfigurationError("SSH settings require ssh_enabled=true")
            return None
        password = _secret(configuration, "ssh_password")
        private_key = _secret(configuration, "ssh_private_key")
        passphrase = _secret(configuration, "ssh_private_key_passphrase")
        if bool(password) == bool(private_key):
            raise ConfigurationError(
                "Specify exactly one of ssh_password or ssh_private_key"
            )
        if passphrase and not private_key:
            raise ConfigurationError(
                "ssh_private_key_passphrase requires ssh_private_key"
            )
        return cls(
            host=_required(configuration, "ssh_host"),
            port=_integer(configuration, "ssh_port", 22, 1, 65535),
            username=_required(configuration, "ssh_username"),
            host_key=_required(configuration, "ssh_host_key"),
            public_key=_secret(configuration, "ssh_public_key"),
            password=password,
            private_key=private_key,
            private_key_passphrase=passphrase,
            connect_timeout_seconds=_integer(
                configuration, "ssh_connect_timeout_seconds", 10, 1, 60
            ),
        )


def _integer(
    configuration: dict, key: str, default: int, minimum: int, maximum: int
) -> int:
    raw = configuration.get(key, str(default))
    try:
        value = int(str(raw))
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{key} must be between {minimum} and {maximum}")
    return value


def _boolean(configuration: dict, key: str, default: bool) -> bool:
    raw = str(configuration.get(key, str(default))).strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    raise ConfigurationError(f"{key} must be true or false")


@dataclass(frozen=True)
class ConnectorConfig:
    host: str
    port: int
    service_name: str | None
    username: str
    password: str = field(repr=False)
    include_schema: str
    include_table: str
    snapshot_fetch_size: int
    snapshot_rows_per_invocation: int
    logminer_initial_scn_span: int
    logminer_min_scn_span: int
    logminer_max_scn_span: int
    max_mining_windows_per_invocation: int
    max_invocation_seconds: int
    archive_log_only: bool
    max_open_transactions: int
    max_transaction_events: int
    max_transaction_buffer_bytes: int
    max_single_transaction_bytes: int
    max_lob_bytes: int
    max_operation_bytes: int
    deployment_profile: str
    sid: str | None = None
    ssh: SSHConfig | None = None
    selected_tables: tuple[TableSelection, ...] = ()
    oracle_call_timeout_seconds: int = 20
    max_continuation_bytes: int = 16 * 1024 * 1024
    max_continuation_fragments: int = 8192

    @property
    def scope_fingerprint(self) -> str:
        payload = {
            "host": self.host,
            "port": self.port,
            "service_name": self.service_name,
            "sid": self.sid,
            "tables": [
                (table.source_key, table.columns) for table in self.selected_tables
            ],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_mapping(cls, configuration: dict) -> "ConnectorConfig":
        allowed = set(cls.__dataclass_fields__) - {"ssh", "selected_tables"}
        allowed.update(
            {
                "tables",
                "ssh_enabled",
                "ssh_host",
                "ssh_port",
                "ssh_username",
                "ssh_host_key",
                "ssh_password",
                "ssh_private_key",
                "ssh_public_key",
                "ssh_private_key_passphrase",
                "ssh_connect_timeout_seconds",
            }
        )
        if set(configuration) - allowed:
            raise ConfigurationError(
                "Unknown configuration field; consult docs/configuration.md"
            )
        selections = parse_selections(configuration)
        password = _secret(configuration, "password")
        if password is None:
            raise ConfigurationError("Missing required configuration field: password")
        profile = str(configuration.get("deployment_profile", "saas")).lower()
        if profile not in {"saas", "hybrid"}:
            raise ConfigurationError("deployment_profile must be either saas or hybrid")
        service_name = str(configuration.get("service_name") or "").strip() or None
        sid = str(configuration.get("sid") or "").strip() or None
        if bool(service_name) == bool(sid):
            raise ConfigurationError("Specify exactly one of service_name or sid")
        result = cls(
            host=_required(configuration, "host"),
            port=_integer(configuration, "port", 1521, 1, 65535),
            service_name=service_name,
            sid=sid,
            username=_required(configuration, "username"),
            password=password,
            include_schema=selections[0].owner,
            include_table=selections[0].name,
            selected_tables=selections,
            oracle_call_timeout_seconds=_integer(
                configuration, "oracle_call_timeout_seconds", 20, 1, 120
            ),
            max_continuation_bytes=_integer(
                configuration,
                "max_continuation_bytes",
                16 * 1024 * 1024,
                4096,
                64 * 1024 * 1024,
            ),
            max_continuation_fragments=_integer(
                configuration, "max_continuation_fragments", 8192, 1, 65536
            ),
            snapshot_fetch_size=_integer(
                configuration, "snapshot_fetch_size", 500, 1, 10_000
            ),
            snapshot_rows_per_invocation=_integer(
                configuration,
                "snapshot_rows_per_invocation",
                25_000,
                1,
                1_000_000,
            ),
            logminer_initial_scn_span=_integer(
                configuration,
                "logminer_initial_scn_span",
                50_000,
                1,
                100_000_000,
            ),
            logminer_min_scn_span=_integer(
                configuration, "logminer_min_scn_span", 1_000, 1, 100_000_000
            ),
            logminer_max_scn_span=_integer(
                configuration,
                "logminer_max_scn_span",
                1_000_000,
                1,
                100_000_000,
            ),
            max_mining_windows_per_invocation=_integer(
                configuration,
                "max_mining_windows_per_invocation",
                10,
                1,
                10_000,
            ),
            max_invocation_seconds=_integer(
                configuration, "max_invocation_seconds", 600, 30, 86_400
            ),
            archive_log_only=_boolean(configuration, "archive_log_only", True),
            max_open_transactions=_integer(
                configuration, "max_open_transactions", 1_000, 1, 100_000
            ),
            max_transaction_events=_integer(
                configuration, "max_transaction_events", 100_000, 1, 10_000_000
            ),
            max_transaction_buffer_bytes=_integer(
                configuration,
                "max_transaction_buffer_bytes",
                256 * 1024 * 1024,
                1024,
                768 * 1024 * 1024,
            ),
            max_single_transaction_bytes=_integer(
                configuration,
                "max_single_transaction_bytes",
                64 * 1024 * 1024,
                1024,
                512 * 1024 * 1024,
            ),
            max_lob_bytes=_integer(
                configuration, "max_lob_bytes", 8 * 1024 * 1024, 0, 64 * 1024 * 1024
            ),
            max_operation_bytes=_integer(
                configuration,
                "max_operation_bytes",
                16 * 1024 * 1024,
                1024,
                64 * 1024 * 1024,
            ),
            deployment_profile=profile,
            ssh=SSHConfig.from_mapping(configuration),
        )
        if not (
            result.logminer_min_scn_span
            <= result.logminer_initial_scn_span
            <= result.logminer_max_scn_span
        ):
            raise ConfigurationError(
                "LogMiner SCN spans must satisfy min <= initial <= max"
            )
        if result.max_single_transaction_bytes > result.max_transaction_buffer_bytes:
            raise ConfigurationError(
                "max_single_transaction_bytes cannot exceed "
                "max_transaction_buffer_bytes"
            )
        return result
