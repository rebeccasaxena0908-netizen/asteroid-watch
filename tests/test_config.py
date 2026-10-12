from pipeline.config import load_settings
from pipeline.db import connection_args


def write_env(tmp_path, text):
    env = tmp_path / ".env"
    env.write_text(text)
    return env


def test_reads_values_from_env_file(tmp_path, monkeypatch):
    for name in ["NASA_API_KEY", "DB_HOST", "DB_PORT", "DB_SOCKET", "DB_USER", "DB_PASSWORD", "DB_NAME"]:
        monkeypatch.delenv(name, raising=False)
    env = write_env(tmp_path, "NASA_API_KEY=abc123\nDB_PORT=3307\nDB_USER=tester\nDB_PASSWORD=pw\n")

    s = load_settings(env)

    assert s.nasa_api_key == "abc123"
    assert s.db_port == 3307
    assert s.db_user == "tester"
    assert s.db_name == "asteroid_watch"  # default
    assert s.has_real_api_key


def test_environment_variable_overrides_file(tmp_path, monkeypatch):
    env = write_env(tmp_path, "DB_NAME=from_file\n")
    monkeypatch.setenv("DB_NAME", "from_env")

    assert load_settings(env).db_name == "from_env"


def test_placeholder_key_is_not_a_real_key(tmp_path, monkeypatch):
    monkeypatch.delenv("NASA_API_KEY", raising=False)
    env = write_env(tmp_path, "NASA_API_KEY=your_key_here\n")

    assert not load_settings(env).has_real_api_key


def test_secrets_are_hidden_from_repr(tmp_path, monkeypatch):
    monkeypatch.delenv("NASA_API_KEY", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    env = write_env(tmp_path, "NASA_API_KEY=supersecretkey\nDB_PASSWORD=supersecretpw\n")

    text = repr(load_settings(env))

    assert "supersecretkey" not in text
    assert "supersecretpw" not in text


def test_uses_socket_when_it_exists_else_tcp(tmp_path, monkeypatch):
    sock = tmp_path / "mysql.sock"
    sock.touch()
    monkeypatch.setenv("DB_SOCKET", str(sock))
    with_socket = connection_args(load_settings(tmp_path / "missing.env"))
    assert with_socket["unix_socket"] == str(sock)
    assert "host" not in with_socket

    monkeypatch.setenv("DB_SOCKET", str(tmp_path / "nope.sock"))
    without_socket = connection_args(load_settings(tmp_path / "missing.env"))
    assert "unix_socket" not in without_socket
    assert without_socket["port"] == 3306
