import sys
from contextlib import nullcontext

from scripts import provision_super_admin as provisioner


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, existing_admin=None):
        self.existing_admin = existing_admin
        self.inserted = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=None):
        if "WHERE role='super_admin'" in query:
            return FakeCursor(self.existing_admin)
        if "WHERE lower(email)=lower(%s)" in query:
            return FakeCursor(None)
        if "INSERT INTO app_users" in query:
            self.inserted = True
            return FakeCursor({"id": 42, "email": params[0]})
        raise AssertionError(f"Unexpected SQL in provisioning test: {query}")


class FakeSsm:
    def __init__(self, password="a-test-password-that-is-long-enough"):
        self.password = password
        self.deleted_parameters = []

    def get_parameter(self, *, Name, WithDecryption):
        assert WithDecryption is True
        return {"Parameter": {"Type": "SecureString", "Value": self.password}}

    def delete_parameter(self, *, Name):
        self.deleted_parameters.append(Name)


def configure_noninteractive(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("SB_SUPER_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("SB_SUPER_ADMIN_FULL_NAME", "Test Admin")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)


def test_noninteractive_run_without_secure_parameter_fails_closed(monkeypatch, capsys):
    configure_noninteractive(monkeypatch)
    monkeypatch.delenv("SB_SUPER_ADMIN_PASSWORD_PARAMETER", raising=False)
    monkeypatch.setattr(
        provisioner.psycopg,
        "connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Database must not be touched without a password source")
        ),
    )

    result = provisioner.main()

    captured = capsys.readouterr()
    assert result == 2
    assert "non-interactive" in captured.err.lower()
    assert "securestring" in captured.err.lower()


def test_secure_parameter_provisions_admin_and_deletes_secret_after_success(monkeypatch, capsys):
    configure_noninteractive(monkeypatch)
    parameter_name = "/superbajaar/bootstrap/super-admin-password"
    monkeypatch.setenv("SB_SUPER_ADMIN_PASSWORD_PARAMETER", parameter_name)
    ssm = FakeSsm()
    connection = FakeConnection()
    monkeypatch.setattr(provisioner.boto3, "client", lambda service: ssm)
    monkeypatch.setattr(provisioner.psycopg, "connect", lambda *args, **kwargs: connection)
    monkeypatch.setattr(provisioner, "_password_hash", lambda password: "hashed-password")

    result = provisioner.main()

    assert result == 0
    assert connection.inserted is True
    assert ssm.deleted_parameters == [parameter_name]
    output = capsys.readouterr().out
    assert "admin@example.com" in output
    assert ssm.password not in output


def test_existing_super_admin_refuses_provisioning_and_keeps_secret(monkeypatch):
    configure_noninteractive(monkeypatch)
    parameter_name = "/superbajaar/bootstrap/super-admin-password"
    monkeypatch.setenv("SB_SUPER_ADMIN_PASSWORD_PARAMETER", parameter_name)
    ssm = FakeSsm()
    connection = FakeConnection(existing_admin={"id": 7})
    monkeypatch.setattr(provisioner.boto3, "client", lambda service: ssm)
    monkeypatch.setattr(provisioner.psycopg, "connect", lambda *args, **kwargs: connection)

    result = provisioner.main()

    assert result == 3
    assert ssm.deleted_parameters == []
    assert connection.inserted is False
