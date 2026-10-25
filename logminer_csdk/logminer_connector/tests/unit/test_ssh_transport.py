"""Real SSH handshake and forwarding tests with an ephemeral loopback server."""

import io
import select
import socket
import threading
from contextlib import contextmanager
from dataclasses import replace

import paramiko
import pytest

from configuration import SSHConfig
from errors import SSHConnectionError
from ssh_tunnel import SSHTunnel

pytestmark = pytest.mark.ssh_local


class Server(paramiko.ServerInterface):
    def __init__(self, client_key, reject_forward):
        self.client_key = client_key
        self.reject_forward = reject_forward
        self.destination = None

    def get_allowed_auths(self, username):
        return "password,publickey"

    def check_auth_password(self, username, password):
        return (
            paramiko.AUTH_SUCCESSFUL
            if (username, password) == ("test", "test-only-password")
            else paramiko.AUTH_FAILED
        )

    def check_auth_publickey(self, username, key):
        return (
            paramiko.AUTH_SUCCESSFUL
            if username == "test" and key == self.client_key
            else paramiko.AUTH_FAILED
        )

    def check_channel_direct_tcpip_request(self, chanid, origin, destination):
        self.destination = destination
        return (
            paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
            if self.reject_forward
            else paramiko.OPEN_SUCCEEDED
        )


@contextmanager
def ssh_server(reject_forward=False, target_address=None):
    host_key = paramiko.RSAKey.generate(2048)
    client_key = paramiko.RSAKey.generate(2048)
    server = Server(client_key, reject_forward)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)
    transports = []
    finished = threading.Event()

    def serve():
        target = None
        try:
            sock, _ = listener.accept()
            transport = paramiko.Transport(sock)
            transports.append(transport)
            transport.set_log_channel("logminer.ssh_transport")
            transport.add_server_key(host_key)
            transport.start_server(server=server)
            channel = transport.accept(5)
            if channel is not None:
                channel.settimeout(5)
                if target_address is not None:
                    assert server.destination == target_address
                    target = socket.create_connection(target_address, timeout=10)
                    while True:
                        readable, _, _ = select.select([channel, target], [], [], 5)
                        if not readable:
                            continue
                        for endpoint in readable:
                            data = endpoint.recv(65536)
                            if not data:
                                return
                            (target if endpoint is channel else channel).sendall(data)
                while True:
                    data = channel.recv(65536)
                    if not data:
                        break
                    channel.sendall(data)
        except (OSError, EOFError, paramiko.SSHException):
            pass
        finally:
            if target is not None:
                target.close()
            for transport in transports:
                transport.close()
            finished.set()

    worker = threading.Thread(target=serve, name="test-ssh-server")
    worker.start()
    config = SSHConfig(
        "127.0.0.1",
        listener.getsockname()[1],
        "test",
        f"{host_key.get_name()} {host_key.get_base64()}",
        password="test-only-password",
        connect_timeout_seconds=2,
    )
    try:
        yield config, client_key, server
    finally:
        listener.close()
        for transport in transports:
            transport.close()
        worker.join(timeout=6)
        assert not worker.is_alive()
        assert finished.is_set()


@pytest.mark.parametrize("authentication", ["password", "key", "encrypted-key"])
def test_actual_ssh_authentication_forwarding_and_cleanup(authentication):
    with ssh_server() as (cfg, key, server):
        if authentication != "password":
            contents = io.StringIO()
            passphrase = (
                "test-only-passphrase" if authentication == "encrypted-key" else None
            )
            key.write_private_key(contents, password=passphrase)
            cfg = replace(
                cfg,
                password=None,
                private_key=contents.getvalue(),
                private_key_passphrase=passphrase,
            )
        tunnel = SSHTunnel(cfg, "oracle.internal", 1521, 30)
        with tunnel:
            assert tunnel.listener.getsockname()[0] == "127.0.0.1"
            with socket.create_connection(
                ("127.0.0.1", tunnel.local_port), timeout=3
            ) as connection:
                payload = b"oracle-test-bytes" * 8192
                connection.sendall(payload)
                received = bytearray()
                while len(received) < len(payload):
                    received.extend(connection.recv(65536))
                assert received == payload
            assert server.destination == ("oracle.internal", 1521)
        assert not tunnel.worker.is_alive()
        assert tunnel.client.get_transport() is None
        tunnel.close()


@pytest.mark.parametrize("failure", ["host-key", "password", "forwarding"])
def test_actual_ssh_failure_is_closed_and_redacted(failure):
    with ssh_server(reject_forward=failure == "forwarding") as (cfg, _, _):
        if failure == "host-key":
            wrong = paramiko.RSAKey.generate(2048)
            cfg = replace(cfg, host_key=f"{wrong.get_name()} {wrong.get_base64()}")
        if failure == "password":
            cfg = replace(cfg, password="sensitive-test-secret")
        tunnel = SSHTunnel(cfg, "oracle.internal", 1521, 30)
        with pytest.raises(SSHConnectionError) as error:
            tunnel.__enter__()
        assert "sensitive-test-secret" not in str(error.value)
        assert error.value.__suppress_context__
        assert tunnel.worker is None
        assert tunnel.client.get_transport() is None


def test_active_tunnel_closes_when_callback_raises():
    with ssh_server() as (cfg, _, _):
        tunnel = SSHTunnel(cfg, "oracle.internal", 1521, 30)
        with (
            pytest.raises(RuntimeError),
            tunnel,
            socket.create_connection(("127.0.0.1", tunnel.local_port), timeout=3),
        ):
            raise RuntimeError("test callback failure")
        assert not tunnel.worker.is_alive()


def test_forwarding_lifetime_is_bounded():
    with ssh_server() as (cfg, _, _):
        tunnel = SSHTunnel(cfg, "oracle.internal", 1521, 0)
        with tunnel:
            with socket.create_connection(
                ("127.0.0.1", tunnel.local_port), timeout=3
            ) as connection:
                assert connection.recv(1) == b""
            assert tunnel.failed.wait(2)
        assert not tunnel.worker.is_alive()
