"""One session-scoped SSH direct-tcpip forwarder, bound only to loopback."""

import base64
import contextlib
import io
import logging
import select
import socket
import threading
import time
from typing import Self, cast

import paramiko

from configuration import SSHConfig
from errors import SSHConnectionError


def _private_key(config: SSHConfig) -> paramiko.PKey | None:
    if config.private_key is None:
        return None
    for key_type in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            key = key_type.from_private_key(
                io.StringIO(config.private_key), password=config.private_key_passphrase
            )
        except (ValueError, paramiko.SSHException):
            continue
        if config.public_key is not None and config.public_key.split()[:2] != [
            key.get_name(),
            key.get_base64(),
        ]:
            raise SSHConnectionError(
                "SSH public key does not match the configured private key"
            )
        return key
    raise SSHConnectionError(
        "SSH private key could not be loaded; check key format and passphrase"
    )


class SSHTunnel:
    def __init__(
        self,
        config: SSHConfig,
        remote_host: str,
        remote_port: int,
        lifetime_seconds: int,
    ):
        self.config = config
        self.remote_address = (remote_host, remote_port)
        self.lifetime_seconds = lifetime_seconds
        self.client = paramiko.SSHClient()
        self.listener: socket.socket | None = None
        self.local_socket: socket.socket | None = None
        self.channel: paramiko.Channel | None = None
        self.worker: threading.Thread | None = None
        self.stop = threading.Event()
        self.failed = threading.Event()
        self.local_port = 0

    def __enter__(self) -> Self:
        try:
            # Never trust a host key obtained from this connection automatically.
            parts = self.config.host_key.split()
            if len(parts) not in {2, 3}:
                raise ValueError("Invalid host key")
            key = paramiko.PKey.from_type_string(
                parts[0], base64.b64decode(parts[1], validate=True)
            )
            name = (
                self.config.host
                if self.config.port == 22
                else f"[{self.config.host}]:{self.config.port}"
            )
            self.client.get_host_keys().add(name, key.get_name(), key)
            self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
            # Library logs may contain untrusted server banners. Keep them out
            # of connector logs and surface only our fixed error messages.
            logger = logging.getLogger("logminer.ssh_transport")
            if not logger.handlers:
                logger.addHandler(logging.NullHandler())
            logger.propagate = False
            self.client.set_log_channel(logger.name)
            timeout = self.config.connect_timeout_seconds
            self.client.connect(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                pkey=_private_key(self.config),
                allow_agent=False,
                look_for_keys=False,
                timeout=timeout,
                banner_timeout=timeout,
                auth_timeout=timeout,
                channel_timeout=timeout,
            )
            transport = self.client.get_transport()
            if transport is None or not transport.is_active():
                raise SSHConnectionError("SSH transport is not active")
            self.channel = transport.open_channel(
                "direct-tcpip",
                dest_addr=self.remote_address,
                src_addr=("127.0.0.1", 0),
                timeout=timeout,
            )
            self.channel.settimeout(timeout)
            self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener.bind(("127.0.0.1", 0))
            self.listener.listen(1)
            self.listener.settimeout(timeout)
            self.local_port = self.listener.getsockname()[1]
            self.worker = threading.Thread(
                target=self._forward, name="oracle-ssh-forward"
            )
            self.worker.start()
            return self
        except Exception:  # noqa: BLE001 -- close partial setup and redact library errors
            self.close()
            raise SSHConnectionError(
                "SSH tunnel setup failed; check authentication, pinned host key, connectivity and TCP forwarding permission"
            ) from None

    def _forward(self) -> None:
        try:
            assert self.listener is not None and self.channel is not None
            self.local_socket, _ = self.listener.accept()
            self.local_socket.settimeout(self.config.connect_timeout_seconds)
            deadline = time.monotonic() + self.lifetime_seconds
            while not self.stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                ready, _, _ = select.select(
                    [self.local_socket, self.channel], [], [], min(0.2, remaining)
                )
                for ready_source in ready:
                    source = cast(socket.socket | paramiko.Channel, ready_source)
                    data = source.recv(65536)
                    if not data:
                        return
                    destination = (
                        self.channel
                        if source is self.local_socket
                        else self.local_socket
                    )
                    destination.sendall(data)
        except Exception:  # noqa: BLE001 -- worker failures must close sockets without logging secrets
            if not self.stop.is_set():
                self.failed.set()
        finally:
            if self.local_socket is not None:
                self.local_socket.close()
            self._close_channel()

    def _close_channel(self) -> None:
        if self.channel is not None:
            # Both the relay and owner can observe peer shutdown concurrently.
            # A close notification on an already closed transport is harmless.
            with contextlib.suppress(OSError, EOFError, paramiko.SSHException):
                self.channel.close()

    def close(self) -> None:
        self.stop.set()
        for endpoint in (self.local_socket, self.listener):
            if endpoint is not None:
                try:
                    endpoint.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                endpoint.close()
        self._close_channel()
        with contextlib.suppress(OSError, EOFError, paramiko.SSHException):
            self.client.close()
        if self.worker is not None:
            self.worker.join(timeout=self.config.connect_timeout_seconds + 1)
            if self.worker.is_alive():
                raise SSHConnectionError("SSH forwarding worker did not terminate")

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
