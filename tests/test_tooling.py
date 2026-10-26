import tomllib

from scripts import check_secrets, gen_requirements
from scripts.check_secrets import env_secrets, find_secrets

FAKE_KEY = "abcdEFGH1234ijklMNOP5678qrstUVWX9012abcd"


def test_requirements_txt_matches_pyproject():
    pyproject = tomllib.loads(gen_requirements.PYPROJECT.read_text())
    assert gen_requirements.REQUIREMENTS.read_text() == gen_requirements.render(pyproject)


def test_env_secrets_keeps_only_real_secret_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        f"NASA_API_KEY={FAKE_KEY}\n"
        "DB_PASSWORD=change_me\n"          # placeholder
        "DASHBOARD_DB_PASSWORD=s3cret-Pass-99\n"
        "DB_USER=asteroid_user\n"          # not a secret name
        "JWT_SECRET=short\n"               # too short to search for safely
    )
    assert env_secrets(env) == {"NASA_API_KEY": FAKE_KEY, "DASHBOARD_DB_PASSWORD": "s3cret-Pass-99"}
    assert env_secrets(tmp_path / "missing.env") == {}


def test_find_secrets_by_value_and_by_pattern():
    secrets = {"DB_PASSWORD": "s3cret-Pass-99"}
    assert find_secrets("password = s3cret-Pass-99", secrets) == ["DB_PASSWORD"]
    assert find_secrets(f"https://api.nasa.gov/neo/rest/v1/feed?api_key={FAKE_KEY}", {}) == ["api_key in a URL"]
    assert find_secrets("-----BEGIN OPENSSH " + "PRIVATE KEY-----", {}) == ["private key"]
    assert find_secrets("token ghp_" + "a1" * 18, {}) == ["GitHub token"]


def test_find_secrets_allows_redacted_and_placeholder_urls():
    for text in ["?api_key=REDACTED", "?api_key=DEMO_KEY", "NASA_API_KEY=your_key_here", "plain text"]:
        assert find_secrets(text, {"DB_PASSWORD": "s3cret-Pass-99"}) == []


def test_main_refuses_and_never_prints_the_secret(tmp_path, monkeypatch, capsys):
    (tmp_path / ".env").write_text(f"NASA_API_KEY={FAKE_KEY}\n")
    (tmp_path / "leak.py").write_text(f'KEY = "{FAKE_KEY}"\n')
    (tmp_path / "clean.py").write_text("x = 1\n")
    monkeypatch.setattr(check_secrets, "ROOT", tmp_path)

    assert check_secrets.main(["clean.py"]) == 0
    assert check_secrets.main(["leak.py"]) == 1
    out = capsys.readouterr().out
    assert "leak.py: contains NASA_API_KEY" in out
    assert FAKE_KEY not in out
