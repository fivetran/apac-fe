"""Typed connector failures.

Errors deliberately avoid embedding configuration values or SQL text.
"""


class ConnectorError(RuntimeError):
    retryable = False
    requires_resnapshot = False
    requires_schema_refresh = False
    requires_hybrid = False


class ConfigurationError(ConnectorError):
    pass


class OracleConnectivityError(ConnectorError):
    retryable = True


class SSHConnectionError(ConnectorError):
    retryable = True


class MissingPrivilegeError(ConnectorError):
    pass


class UnsupportedOracleVersionError(ConnectorError):
    pass


class MissingRedoLogError(ConnectorError):
    requires_resnapshot = True


class LogMinerSessionError(ConnectorError):
    retryable = True


class RedoParseError(ConnectorError):
    pass


class SchemaMismatchError(ConnectorError):
    pass


class SchemaHistoryUnavailableError(ConnectorError):
    requires_resnapshot = True


class SchemaRefreshRequiredError(ConnectorError):
    requires_schema_refresh = True


class SchemaChangeRequiresResyncError(ConnectorError):
    requires_resnapshot = True


class UnsupportedSchemaChangeError(ConnectorError):
    pass


class TransactionBufferLimitError(ConnectorError):
    requires_hybrid = True


class DeferredDdlLimitError(ConnectorError):
    pass


class OperationSizeLimitError(ConnectorError):
    pass


class UnsupportedThinModeFeatureError(ConnectorError):
    pass


class IncompatibleStateError(ConnectorError):
    pass


class ResnapshotRequiredError(ConnectorError):
    requires_resnapshot = True


class SnapshotTooOldError(ResnapshotRequiredError):
    pass


class InvocationBudgetExceededError(ConnectorError):
    retryable = True
