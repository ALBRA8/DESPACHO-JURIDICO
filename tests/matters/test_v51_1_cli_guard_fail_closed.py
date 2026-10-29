"""Tests V5.1.1 — CLI guard fail-closed when Settings cannot be loaded.

V5.1.1 closes the fail-open path identified in the independent audit
of V5.1. The V5.1 guard had ``try/except: return`` around ``Settings()``
which silently swallowed any initialization error and let the command
continue with NO environment check at all — an attacker who could
make ``Settings()`` raise could bypass the CLI guard entirely.

These tests verify:

  1. When ``Settings()`` raises (simulated via monkeypatch of the
     ``albra.config.settings.Settings`` symbol), every data-touching
     CLI command refuses with exit_code=2 and a clear "REFUSED"
     message.
  2. The DB file is NOT created or modified when the guard refuses
     due to a Settings failure.
  3. No data from the matter store is leaked in the refusal message
     — the audit explicitly required verifying that errors do not
     leak other tenants' data.
  4. The escape hatch ``ALBRA_CLI_ALLOW_LOCAL=1`` is NOT extended to
     the Settings-failure path — an unknown environment is refused
     unconditionally (point 4 of the V5.1.1 brief: "sin ampliarla ni
     activarla automáticamente").
  5. Regression: when ``Settings`` loads correctly, the existing V5.1
     behavior is unchanged:
       - dev mode → command runs (exit 1 = not found)
       - production without escape hatch → refused (exit 2)
       - production with escape hatch → command runs (exit 1 = not found)

All tests use Click's ``CliRunner`` to invoke the real CLI entry point
under controlled environment variables. No mocks of the CLI itself —
only ``monkeypatch.setattr`` on the ``Settings`` symbol to force the
failure mode.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

# ===== Helper: a broken Settings class that always raises in __init__ =====

class _BrokenSettings:
    """Stand-in for albra.config.settings.Settings that raises on
    construction. Used by monkeypatch.setattr to simulate a corrupted
    configuration state.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated Settings load failure (V5.1.1 test)")


# ===== Shared fixture: minimal env vars so the rest of the CLI doesn't blow up =====

def _set_minimal_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Set the minimal environment variables needed by the CLI.

    These are set so that, IF the guard somehow let the command through,
    the command's own Settings() call would also succeed (i.e. we want
    the test to specifically exercise the guard's fail-closed path, not
    a downstream failure). The broken-Settings monkeypatch still wins
    because the guard's local import resolves to the patched symbol.
    """
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "development")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-production-32chars-x")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    monkeypatch.delenv("ALBRA_CLI_ALLOW_LOCAL", raising=False)
    db_path = tmp_path / "matters.db"
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(db_path))
    monkeypatch.setenv("ALBRA_MATTER_DATA_DIR", str(tmp_path / "matters"))
    return db_path


# ===== 1. matter_show refused when Settings fails to load =====

def test_cli_matter_show_refused_when_settings_load_fails(tmp_path, monkeypatch):
    """When Settings() raises, `albra matter show` refuses with exit_code=2
    and does NOT create the DB file.

    V5.1.1: replaces V5.1's `try/except: return` fail-open path. The
    audit identified that an attacker who could corrupt Settings loading
    could bypass the CLI guard entirely. Now the guard fails closed.
    """
    db_path = _set_minimal_env(monkeypatch, tmp_path)
    # Replace Settings with a broken class AFTER setting env vars
    monkeypatch.setattr("albra.config.settings.Settings", _BrokenSettings)

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["matter", "show", "any-matter-id"])

    assert result.exit_code == 2, (
        f"matter show should refuse (exit 2) when Settings fails to load. "
        f"Got exit={result.exit_code}, output={result.output!r}"
    )
    assert "REFUSED" in result.output
    assert "configuration could not be loaded" in result.output, (
        f"Refusal message should explain the configuration failure. "
        f"Got: {result.output!r}"
    )
    # The DB file MUST NOT have been created
    assert not db_path.exists(), (
        "DB file must NOT be created when Settings fails to load — "
        "the guard must refuse BEFORE the MatterStore is constructed."
    )


# ===== 2. matter_advance refused when Settings fails to load =====

def test_cli_matter_advance_refused_when_settings_load_fails(tmp_path, monkeypatch):
    """Same fail-closed behavior for `albra matter advance`."""
    db_path = _set_minimal_env(monkeypatch, tmp_path)
    monkeypatch.setattr("albra.config.settings.Settings", _BrokenSettings)

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(
        main, ["matter", "advance", "any-id", "INTAKE", "--by", "ab1"],
    )

    assert result.exit_code == 2, (
        f"matter advance should refuse when Settings fails. "
        f"Got exit={result.exit_code}, output={result.output!r}"
    )
    assert "REFUSED" in result.output
    assert "configuration could not be loaded" in result.output
    assert not db_path.exists(), "DB file must NOT be created or modified."


# ===== 3. pending_approve refused when Settings fails to load =====

def test_cli_pending_approve_refused_when_settings_load_fails(tmp_path, monkeypatch):
    """Same fail-closed behavior for `albra pending approve`."""
    db_path = _set_minimal_env(monkeypatch, tmp_path)
    monkeypatch.setattr("albra.config.settings.Settings", _BrokenSettings)

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["pending", "approve", "any-action", "--by", "ab1", "--role", "abogado"],
    )

    assert result.exit_code == 2
    assert "REFUSED" in result.output
    assert "configuration could not be loaded" in result.output
    assert not db_path.exists()


# ===== 4. matter_new refused — guards against creating new data =====

def test_cli_matter_new_refused_when_settings_load_fails(tmp_path, monkeypatch):
    """`albra matter new` must refuse when Settings fails — never create
    a new matter under an unknown environment.
    """
    db_path = _set_minimal_env(monkeypatch, tmp_path)
    monkeypatch.setattr("albra.config.settings.Settings", _BrokenSettings)

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(
        main, ["matter", "new", "--client", "X", "--area", "civil"],
    )

    assert result.exit_code == 2
    assert "REFUSED" in result.output
    assert not db_path.exists(), (
        "matter new must NOT create the DB or any matter when Settings fails."
    )


# ===== 5. pending_list refused — no enumeration of pending actions =====

def test_cli_pending_list_refused_when_settings_load_fails(tmp_path, monkeypatch):
    """`albra pending list` must refuse when Settings fails — never
    enumerate pending actions under an unknown environment.
    """
    db_path = _set_minimal_env(monkeypatch, tmp_path)
    monkeypatch.setattr("albra.config.settings.Settings", _BrokenSettings)

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["pending", "list"])

    assert result.exit_code == 2
    assert "REFUSED" in result.output
    assert not db_path.exists()


# ===== 6. Errors do not leak seeded DB data =====

def test_cli_settings_failure_does_not_leak_data(tmp_path, monkeypatch):
    """When Settings fails AND a real DB exists with two tenants, the
    CLI guard's refusal message must NOT leak any of the seeded client
    names or tenant identifiers.

    V5.1.1 brief point: "no se filtran datos". The refusal happens
    before the MatterStore is opened, so the seeded data should be
    untouched AND invisible to the caller.
    """
    # Phase 1: seed a real DB with two tenants using a WORKING Settings
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "development")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-production-32chars-x")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    db_path = tmp_path / "matters.db"
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(db_path))
    monkeypatch.setenv("ALBRA_MATTER_DATA_DIR", str(tmp_path / "matters"))

    from albra.matters.store import MatterStore
    store = MatterStore(str(db_path))
    store.create_matter(
        client="SECRET_CLIENT_A", area="civil",
        created_by="ab1", tenant_id="tenant-A",
    )
    store.create_matter(
        client="SECRET_CLIENT_B", area="civil",
        created_by="ab2", tenant_id="tenant-B",
    )
    store.close()
    assert db_path.exists(), "Sanity: seeded DB must exist before the test"

    # Phase 2: break Settings so the guard cannot determine environment
    monkeypatch.setattr("albra.config.settings.Settings", _BrokenSettings)
    monkeypatch.delenv("ALBRA_CLI_ALLOW_LOCAL", raising=False)

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["matter", "show", "any-matter-id"])

    # The guard must refuse
    assert result.exit_code == 2
    output = result.output
    # The refusal message MUST NOT leak any seeded client name or tenant ID
    assert "SECRET_CLIENT_A" not in output, (
        f"Refusal message leaked tenant-A client name. Output: {output!r}"
    )
    assert "SECRET_CLIENT_B" not in output, (
        f"Refusal message leaked tenant-B client name. Output: {output!r}"
    )
    assert "tenant-A" not in output
    assert "tenant-B" not in output

    # The DB file must be unchanged — exactly the two seeded matters,
    # nothing added or removed.
    store2 = MatterStore(str(db_path))
    matters = store2.list_matters()
    assert len(matters) == 2, (
        f"Settings-failure refusal must not mutate the DB. "
        f"Expected 2 matters, got {len(matters)}."
    )
    store2.close()


# ===== 7. Escape hatch NOT extended to the Settings-failure path =====

def test_cli_settings_failure_not_overridden_by_escape_hatch(tmp_path, monkeypatch):
    """V5.1.1: ALBRA_CLI_ALLOW_LOCAL=1 is NOT extended to the
    Settings-failure path. When the environment cannot be determined,
    the guard refuses unconditionally — even with the escape hatch set.

    The escape hatch remains valid only when Settings loads correctly
    (V5.1 behavior preserved — see the regression tests below).

    V5.1.1 brief point 4: "sin ampliarla ni activarla automáticamente".
    """
    db_path = _set_minimal_env(monkeypatch, tmp_path)
    monkeypatch.setattr("albra.config.settings.Settings", _BrokenSettings)
    # Operator explicitly sets the escape hatch...
    monkeypatch.setenv("ALBRA_CLI_ALLOW_LOCAL", "1")
    # ...but the environment is unknown, so the guard must still refuse.
    # We also set ALBRA_ENVIRONMENT=production to make sure the test
    # would let the command through IF the escape hatch were extended —
    # proving that the refusal is due to the Settings failure, not the
    # production check.
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "production")

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["matter", "show", "any-matter-id"])

    assert result.exit_code == 2, (
        f"Settings failure must refuse even with ALBRA_CLI_ALLOW_LOCAL=1. "
        f"Got exit={result.exit_code}, output={result.output!r}"
    )
    assert "REFUSED" in result.output
    assert "configuration could not be loaded" in result.output
    assert not db_path.exists()


# ===== 8. Regression: dev mode still runs when Settings loads correctly =====

def test_cli_dev_mode_still_runs_when_settings_loads(tmp_path, monkeypatch):
    """V5.1.1 regression: when Settings loads correctly in dev mode,
    the CLI runs as before. The new fail-closed path ONLY fires when
    Settings actually fails to load.
    """
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "development")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-production-32chars-x")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    monkeypatch.delenv("ALBRA_CLI_ALLOW_LOCAL", raising=False)
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(tmp_path / "matters.db"))
    monkeypatch.setenv("ALBRA_MATTER_DATA_DIR", str(tmp_path / "matters"))

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["matter", "show", "nonexistent-id"])

    # exit 1 = the command ran and reported "Matter not found".
    # NOT exit 2 = refused. This proves the guard did NOT fire.
    assert result.exit_code == 1, (
        f"Dev mode should let the command run (exit 1 = not found). "
        f"Got exit={result.exit_code}, output={result.output!r}"
    )
    assert "Matter not found" in result.output


# ===== 9. Regression: production mode still refused when Settings loads =====

def test_cli_production_mode_still_refused_when_settings_loads(tmp_path, monkeypatch):
    """V5.1.1 regression: production refusal still fires when Settings
    loads correctly. The fail-closed path is additive, not a replacement
    — both paths refuse, but with distinguishable messages so operators
    can tell whether it was the production check or the Settings-failure
    check that fired.
    """
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "production")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-production-32chars-x")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    monkeypatch.delenv("ALBRA_CLI_ALLOW_LOCAL", raising=False)
    db_path = tmp_path / "matters.db"
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(db_path))

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["matter", "show", "any-id"])

    assert result.exit_code == 2
    assert "REFUSED" in result.output
    # The production-refusal message is distinguishable from the
    # Settings-failure message: it mentions "local-only" and the
    # ALBRA_CLI_ALLOW_LOCAL escape hatch.
    assert "local-only" in result.output, (
        f"Production refusal should mention 'local-only'. Got: {result.output!r}"
    )
    assert "configuration could not be loaded" not in result.output, (
        "Production refusal must NOT mention configuration failure — "
        "Settings loaded fine in this test."
    )
    assert not db_path.exists()


# ===== 10. Regression: escape hatch still works in production when Settings loads =====

def test_cli_production_escape_hatch_still_works_when_settings_loads(tmp_path, monkeypatch):
    """V5.1.1 regression: ALBRA_CLI_ALLOW_LOCAL=1 still works in
    production when Settings loads correctly. The escape hatch is NOT
    auto-enabled and NOT broadened — it remains a V5.1 escape hatch
    for the production path only.
    """
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "production")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-production-32chars-x")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    monkeypatch.setenv("ALBRA_CLI_ALLOW_LOCAL", "1")
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(tmp_path / "matters.db"))
    monkeypatch.setenv("ALBRA_MATTER_DATA_DIR", str(tmp_path / "matters"))

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["matter", "show", "nonexistent-id"])

    # exit 1 = command ran (matter not found), NOT 2 = refused.
    assert result.exit_code == 1, (
        f"Escape hatch should let the command run in production when "
        f"Settings loads. Got exit={result.exit_code}, output={result.output!r}"
    )
    assert "Matter not found" in result.output


# ===== 11. Different exception types all trigger fail-closed =====

@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("simulated"),
        ImportError("simulated missing module"),
        ValueError("simulated bad value"),
        TypeError("simulated type error"),
        KeyError("ALBRA_ENVIRONMENT"),
    ],
    ids=["RuntimeError", "ImportError", "ValueError", "TypeError", "KeyError"],
)
def test_cli_settings_failure_fail_closed_for_any_exception(tmp_path, monkeypatch, exc):
    """V5.1.1: the fail-closed behavior fires for ANY exception type
    raised by Settings construction. The guard does not discriminate —
    if it cannot reliably determine the environment, it refuses.
    """
    db_path = _set_minimal_env(monkeypatch, tmp_path)

    # Build a broken Settings class that raises the given exception
    class _BrokenSettingsDynamic:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise exc

    monkeypatch.setattr("albra.config.settings.Settings", _BrokenSettingsDynamic)

    from albra.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["matter", "show", "any-id"])

    assert result.exit_code == 2, (
        f"matter show should refuse for {type(exc).__name__}. "
        f"Got exit={result.exit_code}, output={result.output!r}"
    )
    assert "REFUSED" in result.output
    assert type(exc).__name__ in result.output, (
        f"Refusal message should name the exception type "
        f"({type(exc).__name__}) so operators can diagnose the failure. "
        f"Got: {result.output!r}"
    )
    assert not db_path.exists()
