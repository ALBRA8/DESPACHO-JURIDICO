"""
SECURITY AUDIT — pattern-based defensive checks for untrusted inputs.

V2.5-H3 Block 8: a small, dependency-free toolkit of predicates the
agent runtime can call before reaching for an external resource or
deserializing un untrusted payload. The intent is fail-closed: any
input that LOOKS like a known-bad pattern (SSRF target, path traversal,
javascript:/data: URI, shell=True subprocess, pickle.loads) is blocked
before the call is dispatched.

Every check returns ``tuple[blocked: bool, reason: str]``:
- ``blocked=True``  → unsafe pattern detected, DO NOT proceed.
- ``blocked=False`` → no known-bad pattern matched; proceed (but the
  caller is still responsible for protocol-level validation).

These checks are pure regex / string-pattern. They are NOT a substitute
for OS-level sandboxing, network egress filtering, or signed-payload
verification. They are the FIRST line of defense so a single typo in
an untrusted string never reaches ``urllib`` / ``subprocess`` / ``pickle``.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urlparse

from albra.observability.logger import get_logger

# Schemes we never allow in any URL accepted from untrusted content.
_UNSAFE_URL_SCHEMES: frozenset[str] = frozenset(
    {"javascript", "data", "file", "vbscript", "mhtml", "about", "blob"}
)

# Path traversal sequences (Unix + Windows + URL-encoded variants).
_TRAVERSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"%2e%2e%2f", re.IGNORECASE),
    re.compile(r"%2e%2e/", re.IGNORECASE),
    re.compile(r"\.\.%2f", re.IGNORECASE),
    re.compile(r"\.\.%5c", re.IGNORECASE),
)

# Subprocess anti-patterns: shell=True, shell injection via ; | & ` $()
_SUBPROCESS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"shell\s*=\s*True", re.IGNORECASE),
    re.compile(r";\s*(rm|del|format|shutdown|reboot)", re.IGNORECASE),
    re.compile(r"\|\s*(sh|bash|cmd|powershell)", re.IGNORECASE),
    re.compile(r"&&\s*(rm|del|format)", re.IGNORECASE),
    re.compile(r"`[^`]+`"),            # backtick command substitution
    re.compile(r"\$\([^)]+\)"),      # $(...) command substitution
    re.compile(r"\|\s*"),            # any pipe
    re.compile(r">\s*/dev/(null|sd[a-z])", re.IGNORECASE),
    # Destructive commands anywhere in the string.
    re.compile(r"\brm\s+-rf?\b", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
)

# Deserialization anti-patterns: pickle, eval, exec, __import__, etc.
_DESERIALIZATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bpickle\.loads?\b", re.IGNORECASE),
    re.compile(r"\bpickle\.Unpickler\b", re.IGNORECASE),
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"\bexec\s*\(", re.IGNORECASE),
    re.compile(r"\b__import__\s*\(", re.IGNORECASE),
    re.compile(r"\bmarshal\.loads?\b", re.IGNORECASE),
    re.compile(r"\byaml\.load\s*\(", re.IGNORECASE),  # use yaml.safe_load
    re.compile(r"\bshelve\.open\b", re.IGNORECASE),
    re.compile(r"\bcpickle\.loads?\b", re.IGNORECASE),
    re.compile(r"\b_subprocess\b", re.IGNORECASE),
)


def _looks_like_internal_ip(host: str) -> bool:
    """True if host is a private / loopback / link-local / reserved IP."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_host(host: str) -> list[str]:
    """Resolve a hostname to its IPs. Empty list on failure.

    Used so an SSRF attacker can't bypass with a hostname like
    ``localhost.attacker.com`` that resolves to 127.0.0.1.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    ips: list[str] = []
    for family, _, _, _, sockaddr in infos:
        if family in (socket.AF_INET, socket.AF_INET6) and sockaddr[0]:
            ip = sockaddr[0]
            if ip not in ips:
                ips.append(ip)
    return ips


class SecurityAudit:
    """Pattern-based defensive predicates for untrusted inputs."""

    def __init__(self, *, allowed_dirs: tuple[str, ...] = ()) -> None:
        # allowed_dirs: tuple of canonical absolute path prefixes. If empty,
        # check_path_traversal still blocks ../ and absolute paths outside
        # CWD by default (fail-closed).
        self.allowed_dirs = allowed_dirs
        self.log = get_logger("albra.security.audit")

    # ===== SSRF =====

    def check_ssrf(self, url: str) -> tuple[bool, str]:
        """Block localhost, link-local (169.254.x.x), file://, and
        private/internal IPs. Returns (blocked, reason).
        """
        if not url or not isinstance(url, str):
            return True, "empty or non-string url"
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        if scheme in _UNSAFE_URL_SCHEMES:
            return True, f"unsafe scheme '{scheme}://' blocked"
        if not scheme:
            return True, "missing url scheme"
        host = (parsed.hostname or "").lower()
        if not host:
            return True, "missing host"
        if host in ("localhost", "ip6-localhost", "ip6-loopback"):
            return True, f"host '{host}' is loopback"
        if host.endswith(".localhost"):
            return True, f"host '{host}' is loopback suffix"
        if host in ("metadata.google.internal",):
            return True, f"host '{host}' is cloud metadata service"
        if _looks_like_internal_ip(host):
            return True, f"host '{host}' is internal/loopback IP"
        # Resolve hostnames to IPs so attackers can't bypass with a
        # DNS name like localhost.attacker.com -> 127.0.0.1. If DNS
        # fails we still allow the URL (DNS resolution is the caller's
        # job) but we won't have approved an internal target.
        for ip in _resolve_host(host):
            if _looks_like_internal_ip(ip):
                return True, f"host '{host}' resolves to internal IP {ip}"
        return False, "ok"

    # ===== Path traversal =====

    def check_path_traversal(self, path: str) -> tuple[bool, str]:
        """Block ../, ..\\, and absolute paths outside allowed dirs."""
        if not path or not isinstance(path, str):
            return True, "empty or non-string path"
        for pat in _TRAVERSAL_PATTERNS:
            if pat.search(path):
                return True, f"path traversal pattern matched: {pat.pattern!r}"
        # Absolute paths: allowed only if they fall under an allowed dir.
        if path.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", path):
            if not self.allowed_dirs:
                return True, "absolute path blocked (no allowed_dirs configured)"
            normalized = path.replace("\\", "/")
            for allowed in self.allowed_dirs:
                allowed_norm = allowed.replace("\\", "/").rstrip("/")
                if normalized.startswith(allowed_norm + "/") or normalized == allowed_norm:
                    return False, "ok (within allowed dir)"
            return True, f"absolute path '{path}' outside allowed dirs"
        return False, "ok"

    # ===== Unsafe URL schemes =====

    def check_unsafe_url(self, url: str) -> tuple[bool, str]:
        """Block javascript:, data:, file:, vbscript: schemes."""
        if not url or not isinstance(url, str):
            return True, "empty or non-string url"
        scheme = (urlparse(url).scheme or "").lower()
        if scheme in _UNSAFE_URL_SCHEMES:
            return True, f"unsafe url scheme '{scheme}:' blocked"
        # Also catch scheme-less but protocol-relative or javascript:
        # fragments at the start (e.g. "javascript:alert(1)").
        head = url.lstrip().lower()
        for bad in _UNSAFE_URL_SCHEMES:
            if head.startswith(bad + ":"):
                return True, f"unsafe url prefix '{bad}:' blocked"
        return False, "ok"

    # ===== Subprocess anti-patterns =====

    def check_subprocess(self, command: str) -> tuple[bool, str]:
        """Block shell=True patterns and shell injection via ; | & ` $()."""
        if not command or not isinstance(command, str):
            return True, "empty or non-string command"
        for pat in _SUBPROCESS_PATTERNS:
            if pat.search(command):
                return True, f"subprocess anti-pattern matched: {pat.pattern!r}"
        return False, "ok"

    # ===== Deserialization anti-patterns =====

    def check_deserialization(self, data: str) -> tuple[bool, str]:
        """Block pickle.loads / eval / exec in untrusted data."""
        if not isinstance(data, str):
            # Non-string input could still be a pickled bytes payload.
            return True, "non-string deserialization input blocked"
        if not data:
            return False, "ok (empty)"
        for pat in _DESERIALIZATION_PATTERNS:
            if pat.search(data):
                return True, f"deserialization anti-pattern matched: {pat.pattern!r}"
        return False, "ok"

    # ===== Full audit =====

    def run_full_audit(self) -> dict[str, Any]:
        """Run every check against known-bad and known-good patterns.

        Returns a dict keyed by check name, each value being a summary
        of how many test cases were blocked vs. allowed. Used by the
        doctor diagnostic and the security CI gate so a regression in
        any predicate is immediately visible.
        """
        ssrf_bad = [
            "http://localhost:8080/admin",
            "http://127.0.0.1/",
            "http://169.254.169.254/latest/meta-data/",
            "file:///etc/passwd",
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://metadata.google.internal/",
        ]
        ssrf_ok = [
            "https://example.com/path",
            "https://www.secretariasenado.gov.co/basedoc/ley_0100_1993.html",
        ]
        path_bad = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "%2e%2e%2fetc%2fpasswd",
            "/etc/passwd",
            "C:\\Windows\\System32\\config\\SAM",
        ]
        path_ok = [
            "documents/demanda.docx",
            "data/matters/M-001/filings/cargo.pdf",
        ]
        url_bad = [
            "javascript:alert(document.cookie)",
            "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            "file:///etc/passwd",
            "vbscript:msgbox('xss')",
        ]
        url_ok = [
            "https://example.com/path",
            "http://example.com/path",
        ]
        sub_bad = [
            "subprocess.run(cmd, shell=True)",
            "rm -rf /; ls",
            "cat file | sh",
            "echo $(whoami)",
            "ls `whoami`",
            "cat file | less",
        ]
        sub_ok = [
            "ls -la /tmp",
            "echo hello world",
            "git status",
        ]
        deser_bad = [
            "pickle.loads(payload)",
            "eval('1+1')",
            "exec(code_string)",
            "__import__('os').system('id')",
            "yaml.load(stream)",
            "marshal.loads(b'\\x80\\x04')",
        ]
        deser_ok = [
            '{"key": "value"}',
            "plain text content",
            "",
        ]

        def _summarize(
            bad_samples: list[str],
            ok_samples: list[str],
            checker: Any,
        ) -> dict[str, Any]:
            blocked_bad = sum(1 for s in bad_samples if checker(s)[0])
            blocked_ok = sum(1 for s in ok_samples if checker(s)[0])
            return {
                "bad_total": len(bad_samples),
                "bad_blocked": blocked_bad,
                "ok_total": len(ok_samples),
                "ok_falsely_blocked": blocked_ok,
                "all_bad_blocked": blocked_bad == len(bad_samples),
                "no_ok_falsely_blocked": blocked_ok == 0,
            }

        return {
            "ssrf": _summarize(ssrf_bad, ssrf_ok, self.check_ssrf),
            "path_traversal": _summarize(path_bad, path_ok, self.check_path_traversal),
            "unsafe_url": _summarize(url_bad, url_ok, self.check_unsafe_url),
            "subprocess": _summarize(sub_bad, sub_ok, self.check_subprocess),
            "deserialization": _summarize(
                deser_bad, deser_ok, self.check_deserialization
            ),
        }
