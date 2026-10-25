"""Configuration, cleanup and routing tests without external connections."""

from dataclasses import replace
from types import SimpleNamespace

import oracledb
import pytest
from test_configuration import valid_mapping

from configuration import ConnectorConfig, SSHConfig
from errors import ConfigurationError, OracleConnectivityError, SSHConnectionError
from oracle_client import OracleClient
from ssh_tunnel import SSHTunnel, _private_key


@pytest.mark.parametrize("kind", ["ed25519", "ecdsa"])
def test_openssh_private_keys_load_in_memory(kind):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519

    key = (
        ed25519.Ed25519PrivateKey.generate()
        if kind == "ed25519"
        else ec.generate_private_key(ec.SECP256R1())
    )
    contents = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.BestAvailableEncryption(b"test-passphrase"),
    ).decode()
    cfg = SSHConfig(
        "host",
        22,
        "user",
        "public",
        private_key=contents,
        private_key_passphrase="test-passphrase",
    )
    parsed = _private_key(cfg)
    assert parsed.get_name() == (
        "ssh-ed25519" if kind == "ed25519" else "ecdsa-sha2-nistp256"
    )


def ssh_mapping():
    return {
        **valid_mapping(),
        "ssh_enabled": "true",
        "ssh_host": "bastion.example",
        "ssh_username": "test",
        "ssh_host_key": "ssh-ed25519 placeholder",
        "ssh_password": "ssh-secret",
    }


def test_ssh_opt_in_and_secret_repr():
    assert ConnectorConfig.from_mapping(valid_mapping()).ssh is None
    cfg = ConnectorConfig.from_mapping(ssh_mapping())
    assert cfg.ssh.port == 22
    assert "ssh-secret" not in repr(cfg)
    key = SSHConfig(
        "host",
        22,
        "user",
        "public",
        private_key="private-secret",
        private_key_passphrase="passphrase-secret",
    )
    assert "private-secret" not in repr(key)
    assert "passphrase-secret" not in repr(key)


@pytest.mark.parametrize(
    "changes",
    [
        {"ssh_host": ""},
        {"ssh_username": ""},
        {"ssh_host_key": ""},
        {"ssh_password": ""},
        {"ssh_private_key": "private"},
        {"ssh_private_key_passphrase": "passphrase"},
        {"ssh_port": "0"},
        {"ssh_connect_timeout_seconds": "61"},
        {"ssh_enabled": "false"},
    ],
)
def test_ssh_invalid_configuration_rejected(changes):
    with pytest.raises(ConfigurationError):
        ConnectorConfig.from_mapping({**ssh_mapping(), **changes})


def test_private_key_whitespace_preserved():
    cfg = ConnectorConfig.from_mapping(
        {
            **ssh_mapping(),
            "ssh_password": "",
            "ssh_private_key": "  key\n",
            "ssh_private_key_passphrase": " pass ",
        }
    )
    assert cfg.ssh.private_key == "  key\n"
    assert cfg.ssh.private_key_passphrase == " pass "


def test_key_pair_can_be_staged_before_bastion_configuration():
    cfg = ConnectorConfig.from_mapping(
        {
            **valid_mapping(),
            "ssh_enabled": "false",
            "ssh_private_key": "staged-secret",
            "ssh_public_key": "staged-public",
        }
    )
    assert cfg.ssh is None


def test_public_key_mismatch_is_rejected():
    import io

    import paramiko

    key = paramiko.RSAKey.generate(2048)
    text = io.StringIO()
    key.write_private_key(text)
    cfg = SSHConfig(
        "host",
        22,
        "user",
        "public",
        public_key="ssh-rsa invalid",
        private_key=text.getvalue(),
    )
    with pytest.raises(SSHConnectionError, match="does not match"):
        _private_key(cfg)


@pytest.mark.parametrize("failure", [False, True])
def test_oracle_routes_through_loopback_and_closes_tunnel(monkeypatch, failure):
    tunnels = []
    calls = []
    closed = []

    class Tunnel:
        local_port = 12345
        failed = SimpleNamespace(is_set=lambda: False)

        def __init__(self, *args):
            self.args = args
            tunnels.append(self)

        def __enter__(self):
            return self

        def close(self):
            closed.append("tunnel")

    def connect(**kwargs):
        calls.append(kwargs)
        if failure:
            raise oracledb.DatabaseError("sensitive-driver-secret")
        return SimpleNamespace(close=lambda: closed.append("oracle"))

    monkeypatch.setattr("ssh_tunnel.SSHTunnel", Tunnel)
    monkeypatch.setattr(oracledb, "connect", connect)
    cfg = replace(
        ConnectorConfig.from_mapping(ssh_mapping()), service_name=None, sid="DATABASE"
    )
    if failure:
        with pytest.raises(OracleConnectivityError) as error, OracleClient(cfg):
            pass
        assert error.value.__suppress_context__
        assert "sensitive-driver-secret" not in str(error.value)
        assert closed == ["tunnel"]
    else:
        with OracleClient(cfg):
            pass
        assert closed == ["oracle", "tunnel"]
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 12345
    assert calls[0]["sid"] == "DATABASE"
    assert calls[0]["service_name"] is None
    assert calls[0]["disable_oob"] is True
    assert tunnels[0].args[1:3] == ("db.example", 1521)


def test_malformed_host_key_fails_before_network_and_is_redacted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "paramiko.SSHClient.connect", lambda *args, **kwargs: calls.append(kwargs)
    )
    tunnel = SSHTunnel(
        SSHConfig("host", 22, "user", "invalid-secret", password="password-secret"),
        "db",
        1521,
        30,
    )
    with pytest.raises(SSHConnectionError) as error:
        tunnel.__enter__()
    assert not calls
    assert tunnel.worker is None
    assert "invalid-secret" not in str(error.value)
    assert "password-secret" not in str(error.value)
    assert error.value.__suppress_context__


def test_peer_shutdown_during_channel_close_still_closes_client(monkeypatch):
    closed = []
    tunnel = SSHTunnel(
        SSHConfig("host", 22, "user", "public", password="test"), "db", 1521, 30
    )

    def close_channel():
        raise EOFError()

    tunnel.channel = SimpleNamespace(close=close_channel)
    monkeypatch.setattr(tunnel.client, "close", lambda: closed.append("client"))
    tunnel.close()
    assert closed == ["client"]
