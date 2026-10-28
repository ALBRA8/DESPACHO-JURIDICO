"""Tests for albra.security.audit (HARDENING-3 Block 8).

Covers the SecurityAudit class:
- check_ssrf (blocks localhost, internal IPs, file://, allows https)
- check_path_traversal (blocks ../, allows normal paths)
- check_unsafe_url (blocks javascript:, data:)
- check_subprocess (blocks shell=True, pipe injection)
- check_deserialization (blocks pickle/eval/exec)
- run_full_audit (returns dict summarizing all checks)
"""
from __future__ import annotations

import pytest

from albra.security.audit import SecurityAudit


@pytest.fixture
def auditor() -> SecurityAudit:
    return SecurityAudit(allowed_dirs=("/home/albra/data", "/tmp/albra"))


# ===== check_ssrf =====


def test_ssrf_blocks_localhost(auditor: SecurityAudit):
    blocked, reason = auditor.check_ssrf("http://localhost:8080/admin")
    assert blocked is True
    assert "localhost" in reason.lower() or "loopback" in reason.lower()


def test_ssrf_blocks_internal_ip(auditor: SecurityAudit):
    blocked, _ = auditor.check_ssrf("http://127.0.0.1/")
    assert blocked is True
    blocked, _ = auditor.check_ssrf("http://10.0.0.1/")
    assert blocked is True
    blocked, _ = auditor.check_ssrf("http://192.168.1.1/")
    assert blocked is True
    blocked, _ = auditor.check_ssrf("http://169.254.169.254/latest/meta-data/")
    assert blocked is True


def test_ssrf_blocks_file_scheme(auditor: SecurityAudit):
    blocked, reason = auditor.check_ssrf("file:///etc/passwd")
    assert blocked is True
    assert "file" in reason.lower()


def test_ssrf_allows_https(auditor: SecurityAudit):
    blocked, _ = auditor.check_ssrf("https://example.com/path")
    assert blocked is False
    blocked, _ = auditor.check_ssrf(
        "https://www.secretariasenado.gov.co/basedoc/ley_0100_1993.html"
    )
    assert blocked is False


def test_ssrf_blocks_metadata_endpoint(auditor: SecurityAudit):
    blocked, _ = auditor.check_ssrf("http://metadata.google.internal/")
    assert blocked is True


def test_ssrf_blocks_empty_url(auditor: SecurityAudit):
    blocked, _ = auditor.check_ssrf("")
    assert blocked is True


# ===== check_path_traversal =====


def test_path_traversal_blocks_dotdot(auditor: SecurityAudit):
    blocked, reason = auditor.check_path_traversal("../../../etc/passwd")
    assert blocked is True
    assert "traversal" in reason.lower()
    blocked, _ = auditor.check_path_traversal("..\\..\\windows\\system32")
    assert blocked is True
    blocked, _ = auditor.check_path_traversal("%2e%2e%2fetc%2fpasswd")
    assert blocked is True


def test_path_traversal_allows_normal_path(auditor: SecurityAudit):
    blocked, _ = auditor.check_path_traversal("documents/demanda.docx")
    assert blocked is False
    blocked, _ = auditor.check_path_traversal("data/matters/M-001/cargo.pdf")
    assert blocked is False


def test_path_traversal_blocks_absolute_outside_allowed(auditor: SecurityAudit):
    blocked, _ = auditor.check_path_traversal("/etc/passwd")
    assert blocked is True
    blocked, _ = auditor.check_path_traversal("/var/log/auth.log")
    assert blocked is True


def test_path_traversal_allows_absolute_in_allowed_dir(auditor: SecurityAudit):
    blocked, _ = auditor.check_path_traversal("/home/albra/data/matters/M-001/cargo.pdf")
    assert blocked is False
    blocked, _ = auditor.check_path_traversal("/tmp/albra/scratch.txt")
    assert blocked is False


# ===== check_unsafe_url =====


def test_unsafe_url_blocks_javascript(auditor: SecurityAudit):
    blocked, reason = auditor.check_unsafe_url("javascript:alert(document.cookie)")
    assert blocked is True
    assert "javascript" in reason.lower()


def test_unsafe_url_blocks_data_uri(auditor: SecurityAudit):
    blocked, reason = auditor.check_unsafe_url("data:text/html;base64,PHNjcmlwdD4=")
    assert blocked is True
    assert "data" in reason.lower()


def test_unsafe_url_blocks_file_scheme(auditor: SecurityAudit):
    blocked, _ = auditor.check_unsafe_url("file:///etc/passwd")
    assert blocked is True


def test_unsafe_url_allows_https(auditor: SecurityAudit):
    blocked, _ = auditor.check_unsafe_url("https://example.com/path")
    assert blocked is False


# ===== check_subprocess =====


def test_subprocess_blocks_shell_true(auditor: SecurityAudit):
    blocked, reason = auditor.check_subprocess("subprocess.run(cmd, shell=True)")
    assert blocked is True
    assert "shell" in reason.lower()


def test_subprocess_blocks_pipe_injection(auditor: SecurityAudit):
    blocked, _ = auditor.check_subprocess("cat file | sh")
    assert blocked is True
    blocked, _ = auditor.check_subprocess("echo $(whoami)")
    assert blocked is True
    blocked, _ = auditor.check_subprocess("ls `whoami`")
    assert blocked is True
    blocked, _ = auditor.check_subprocess("rm -rf / ; ls")
    assert blocked is True


def test_subprocess_allows_safe_command(auditor: SecurityAudit):
    blocked, _ = auditor.check_subprocess("git status")
    assert blocked is False
    blocked, _ = auditor.check_subprocess("echo hello world")
    assert blocked is False


# ===== check_deserialization =====


def test_deserialization_blocks_pickle(auditor: SecurityAudit):
    blocked, reason = auditor.check_deserialization("pickle.loads(payload)")
    assert blocked is True
    assert "pickle" in reason.lower()


def test_deserialization_blocks_eval(auditor: SecurityAudit):
    blocked, _ = auditor.check_deserialization("eval('1+1')")
    assert blocked is True
    blocked, _ = auditor.check_deserialization("exec(code_string)")
    assert blocked is True


def test_deserialization_blocks_import(auditor: SecurityAudit):
    blocked, _ = auditor.check_deserialization("__import__('os').system('id')")
    assert blocked is True


def test_deserialization_blocks_yaml_unsafe_load(auditor: SecurityAudit):
    blocked, _ = auditor.check_deserialization("yaml.load(stream)")
    assert blocked is True


def test_deserialization_allows_safe_data(auditor: SecurityAudit):
    blocked, _ = auditor.check_deserialization('{"key": "value"}')
    assert blocked is False
    blocked, _ = auditor.check_deserialization("plain text content")
    assert blocked is False
    blocked, _ = auditor.check_deserialization("")
    assert blocked is False


def test_deserialization_blocks_non_string(auditor: SecurityAudit):
    blocked, _ = auditor.check_deserialization(b"\x80\x04pickle")  # type: ignore[arg-type]
    assert blocked is True


# ===== run_full_audit =====


def test_full_audit_returns_dict(auditor: SecurityAudit):
    summary = auditor.run_full_audit()
    assert isinstance(summary, dict)
    expected_keys = {
        "ssrf",
        "path_traversal",
        "unsafe_url",
        "subprocess",
        "deserialization",
    }
    assert set(summary.keys()) == expected_keys
    for check_name, info in summary.items():
        assert "bad_total" in info
        assert "bad_blocked" in info
        assert "ok_total" in info
        assert "ok_falsely_blocked" in info
        assert "all_bad_blocked" in info
        assert "no_ok_falsely_blocked" in info
        # Every check must block all known-bad samples.
        assert info["all_bad_blocked"] is True, (
            f"{check_name} failed to block a known-bad sample: {info}"
        )
        # No known-good sample should be falsely blocked.
        assert info["no_ok_falsely_blocked"] is True, (
            f"{check_name} falsely blocked a known-good sample: {info}"
        )


def test_full_audit_bad_counts_positive(auditor: SecurityAudit):
    """Every check has at least 1 known-bad sample."""
    summary = auditor.run_full_audit()
    for check_name, info in summary.items():
        assert info["bad_total"] > 0, f"{check_name} has no bad samples"
