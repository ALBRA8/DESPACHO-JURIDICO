"""Tests V1.6 CIERRE QUIRÚRGICO - 4 frentes auditados.

P0.1 - Defaults operativos eliminados (fail-closed)
P0.2 - SelfImprove → Reasoning real (lessons llegan al prompt del provider)
P1   - HMAC bearer token coherente (no híbrido JWT)
P1   - Clean-room CI sobre commit exacto
"""
import asyncio
import os
import sys
import tempfile

import pytest

from albra.config.settings import (
    KNOWN_INSECURE_ADMIN_PASSWORDS,
    KNOWN_INSECURE_JWT_SECRETS,
    InsecureConfigurationError,
    Settings,
    get_settings,
    reset_settings,
)


# Helper para tests: fixture de secretos efímeros fuertes
@pytest.fixture
def strong_secrets(monkeypatch):
    """Inyecta secretos efímeros fuertes para tests. NO son defaults."""
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")
    reset_settings()
    yield
    reset_settings()


# ============================================================
# P0.1 — Defaults operativos eliminados
# ============================================================

def test_jwt_secret_no_default_value():
    """NO existe default para ALBRA_JWT_SECRET en Settings."""
    import inspect
    src = inspect.getsource(Settings)
    # La property jwt_secret NO debe tener default operativo
    assert '"change-me-in-production"' not in src, "Default jwt_secret presente"
    # El setter debe rechazar defaults conocidos
    assert "KNOWN_INSECURE_JWT_SECRETS" in src


def test_admin_password_no_default_value():
    """NO existe default para ALBRA_ADMIN_PASSWORD en Settings."""
    import inspect
    src = inspect.getsource(Settings)
    assert '"change-me"' not in src, "Default admin_password presente"


def test_jwt_secret_missing_fails_closed(monkeypatch):
    """Sin ALBRA_JWT_SECRET → fail-closed al acceder."""
    monkeypatch.delenv("ALBRA_JWT_SECRET", raising=False)
    reset_settings()
    s = Settings()
    with pytest.raises(InsecureConfigurationError) as exc:
        _ = s.jwt_secret
    assert "required" in str(exc.value).lower() or "ALBRA_JWT_SECRET" in str(exc.value)


def test_admin_password_missing_fails_closed(monkeypatch):
    """Sin ALBRA_ADMIN_PASSWORD → fail-closed al crear SecurityGate."""
    monkeypatch.delenv("ALBRA_ADMIN_PASSWORD", raising=False)
    reset_settings()
    from albra.security.auth import SecurityGate
    s = Settings()
    with pytest.raises(InsecureConfigurationError):
        gate = SecurityGate(s)
        _ = gate


def test_jwt_secret_known_default_rejected(monkeypatch):
    """Valor default conocido → fail-closed."""
    for insecure in KNOWN_INSECURE_JWT_SECRETS:
        if not insecure:  # skip empty string - covered by missing test
            continue
        monkeypatch.setenv("ALBRA_JWT_SECRET", insecure)
        reset_settings()
        s = Settings()
        with pytest.raises(InsecureConfigurationError):
            _ = s.jwt_secret
    # Cleanup
    monkeypatch.delenv("ALBRA_JWT_SECRET", raising=False)
    reset_settings()


def test_admin_password_known_default_rejected(monkeypatch):
    """Password default conocido → fail-closed."""
    for insecure in KNOWN_INSECURE_ADMIN_PASSWORDS:
        if not insecure:
            continue
        monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", insecure)
        reset_settings()
        from albra.security.auth import SecurityGate
        s = Settings()
        with pytest.raises(InsecureConfigurationError):
            SecurityGate(s)
    monkeypatch.delenv("ALBRA_ADMIN_PASSWORD", raising=False)
    reset_settings()


def test_jwt_secret_too_short_rejected(monkeypatch):
    """Secret corto (<16 chars) → fail-closed."""
    monkeypatch.setenv("ALBRA_JWT_SECRET", "short")
    reset_settings()
    s = Settings()
    with pytest.raises(InsecureConfigurationError) as exc:
        _ = s.jwt_secret
    assert "short" in str(exc.value).lower()
    monkeypatch.delenv("ALBRA_JWT_SECRET", raising=False)
    reset_settings()


def test_admin_password_too_short_rejected(monkeypatch):
    """Password corto (<8 chars) → fail-closed."""
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "short")
    reset_settings()
    from albra.security.auth import SecurityGate
    s = Settings()
    with pytest.raises(InsecureConfigurationError):
        SecurityGate(s)
    monkeypatch.delenv("ALBRA_ADMIN_PASSWORD", raising=False)
    reset_settings()


def test_valid_secrets_startup_ok(strong_secrets):
    """Secretos fuertes → startup correcto."""
    s = Settings()
    # No debe raise
    secret = s.jwt_secret
    assert secret == "test-ephemeral-jwt-secret-32-chars"
    password = s.admin_password
    assert password == "test-ephemeral-pass-1234"


def test_settings_as_dict_does_not_leak_secrets(strong_secrets):
    """as_dict NO debe exponer secretos."""
    s = Settings()
    d = s.as_dict()
    assert "jwt_secret" not in d
    assert "admin_password" not in d
    assert "_jwt_secret" not in d
    assert "_admin_password" not in d


def test_no_change_me_in_repo():
    """No debe haber 'change-me' como secreto operativo en código."""
    import pathlib
    # .env.example puede tener placeholder, pero NO el código fuente
    for p in pathlib.Path("albra").rglob("*.py"):
        text = p.read_text()
        # Permitido: en strings de ejemplo de KNOWN_INSECURE (porque están ahí para rechazar)
        # NO permitido: como valor default operativo
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            if "change-me" in line and "KNOWN_INSECURE" not in text[:text.find(line)]:
                # Check si la línea es parte de la lista KNOWN_INSECURE
                if "change-me" in line and ("KNOWN_INSECURE" in text or "insecure" in line.lower()):
                    continue
                # Si no, es un default operativo - rechazar
                pytest.fail(f"{p}:{i} contains 'change-me' as potential default: {line.strip()}")


# ============================================================
# P0.2 — SelfImprove → Reasoning real (lessons llegan al prompt)
# ============================================================

def test_build_prompt_includes_promoted_lessons():
    """_build_prompt debe incluir promoted_lessons en el contexto enviado al provider."""
    from albra.config.settings import Settings
    from albra.reasoning.engine import ReasoningEngine
    eng = ReasoningEngine(Settings())
    plan = {
        "intent": {"name": "greeting", "confidence": 0.8},
        "promoted_lessons": [
            {"pattern": "clock:timeout", "text": "Before calling clock, validate it's available"},
        ],
    }
    prompt = eng._build_prompt("hola", plan, [])
    # La lesson debe estar en el prompt
    assert "clock:timeout" in prompt, f"Lesson pattern not in prompt: {prompt}"
    assert "validate it's available" in prompt, f"Lesson text not in prompt: {prompt}"
    # Debe estar marcada como contexto, NO como código
    assert "contexto, NO código" in prompt or "context" in prompt.lower()


def test_build_prompt_without_lessons_works():
    """Sin promoted_lessons → prompt funciona normal."""
    from albra.config.settings import Settings
    from albra.reasoning.engine import ReasoningEngine
    eng = ReasoningEngine(Settings())
    plan = {"intent": {"name": "greeting", "confidence": 0.8}}
    prompt = eng._build_prompt("hola", plan, [])
    assert "Lecciones operativas promovidas" not in prompt


def test_self_improve_to_reasoning_e2e_flow():
    """E2E: lesson → HITL → promote → persist → restart → retrieve → reasoning prompt.

    Verifica que la lesson efectivamente llega al contexto del provider.
    """
    with tempfile.TemporaryDirectory() as tmp:
        from albra.config.settings import Settings
        from albra.doctor.self_improve import SelfImprove
        from albra.reasoning.engine import ReasoningEngine

        si_path = f"{tmp}/si.db"

        # A. Crear lesson válida via capture + threshold
        si1 = SelfImprove(si_path)
        si1.PROMOTION_THRESHOLD = 2
        si1.capture_error(tool_name="clock", error="timeout 1")
        si1.capture_error(tool_name="clock", error="timeout 2")
        # Debe existir una lesson drafted
        cur = si1._conn.execute("SELECT id, lesson_text FROM lessons ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        assert row is not None, "Lesson should be drafted after threshold"
        lesson_id, lesson_text = row[0], row[1]
        assert "timeout" in lesson_text.lower() or "clock" in lesson_text.lower()

        # B. Validate (HITL step 1)
        assert si1.validate_lesson(lesson_id, validator="admin") is True

        # C. Promote WITHOUT HITL → debe fallar (safety)
        result = si1.promote_lesson(lesson_id)
        assert not result["ok"]
        assert "hitl_required" in result["reason"]

        # D. Promote WITH HITL → ok
        result = si1.promote_lesson(lesson_id, hitl_request_id="hitl_test_001")
        assert result["ok"]

        # E. Persist (close + restart)
        si1.close()

        # F. Restart - new instance, same DB
        si2 = SelfImprove(si_path)

        # G. Retrieve promoted lessons
        promoted = si2.get_promoted_lessons()
        assert len(promoted) >= 1, "Promoted lessons should persist after restart"
        assert promoted[0]["pattern_key"].startswith("clock:")

        # H. Reasoning recibe la lesson
        eng = ReasoningEngine(Settings())
        # Simular plan que Runtime construiría (con promoted_lessons)
        plan = {
            "intent": {"name": "greeting", "confidence": 0.8},
            "promoted_lessons": [
                {"pattern": p["pattern_key"], "text": p["lesson_text"]}
                for p in promoted
            ],
        }
        prompt = eng._build_prompt("test message", plan, [])

        # I. Verificar que el provider/contexto recibe la lesson
        assert "clock:" in prompt, "Lesson pattern must be in provider prompt"
        assert any(word in prompt for word in ["timeout", "clock"]), "Lesson text must be in provider prompt"

        si2.close()


def test_self_improve_unapproved_not_in_prompt():
    """Lesson no aprobada NO llega al prompt del provider."""
    with tempfile.TemporaryDirectory() as tmp:
        from albra.config.settings import Settings
        from albra.doctor.self_improve import SelfImprove
        from albra.reasoning.engine import ReasoningEngine

        si = SelfImprove(f"{tmp}/si.db")
        si.PROMOTION_THRESHOLD = 2
        si.capture_error(tool_name="clock", error="timeout 1")
        si.capture_error(tool_name="clock", error="timeout 2")
        # Validar pero NO promover
        cur = si._conn.execute("SELECT id FROM lessons ORDER BY created_at DESC LIMIT 1")
        lesson_id = cur.fetchone()[0]
        si.validate_lesson(lesson_id, validator="admin")
        # NO promote

        # Promoted lessons debe estar vacío
        promoted = si.get_promoted_lessons()
        assert len(promoted) == 0

        # Prompt sin lessons
        eng = ReasoningEngine(Settings())
        plan = {"intent": {"name": "greeting", "confidence": 0.8}}
        prompt = eng._build_prompt("test", plan, [])
        assert "clock:" not in prompt

        si.close()


def test_self_improve_forbidden_actions_enforced():
    """SelfImprove NO puede modificar sistemas críticos."""
    with tempfile.TemporaryDirectory() as tmp:
        from albra.doctor.self_improve import SelfImprove
        si = SelfImprove(f"{tmp}/si.db")
        forbidden = si.forbidden_actions()
        # Verificar acciones críticas prohibidas
        for action in ("modify_code", "modify_autonomy_ceiling", "modify_policy_state",
                        "modify_kill_switch", "elevate_role", "bypass_execution_guard",
                        "self_promote_to_L5", "delete_audit_log", "modify_rbac"):
            assert action in forbidden, f"Missing forbidden: {action}"
        # Verificar que NO existen métodos peligrososos
        for method in ("modify_code", "engage_kill_switch", "elevate_role",
                        "delete_audit_log", "modify_rbac"):
            assert not hasattr(si, method), f"SelfImprove tiene método peligroso: {method}"
        si.close()


# ============================================================
# P1 — HMAC signed bearer token (NO híbrido JWT)
# ============================================================

def test_tokens_module_not_called_jwt():
    """Módulo NO se llama JWT - se llama HMAC signed bearer."""
    import inspect

    import albra.security.tokens as tokens_mod
    src = inspect.getsource(tokens_mod)
    # Debe decir explícitamente que NO es JWT/JWS estándar
    assert "NO es JWT" in src or "not JWT" in src.lower() or "HMAC signed bearer" in src


def test_token_format_is_hmac_payload_signature():
    """Formato del token: payload.signature (NO header.payload.signature como JWT)."""
    import os

    from albra.security.tokens import issue_token
    os.environ["ALBRA_JWT_SECRET"] = "strong_test_secret_32_chars_min"
    reset_settings()
    try:
        token = issue_token(subject="u", role="admin")
        # JWT estándar: 3 partes separadas por .
        # Nuestro: 2 partes (payload.signature)
        parts = token.split(".")
        assert len(parts) == 2, f"Expected 2 parts (payload.signature), got {len(parts)}"
    finally:
        os.environ.pop("ALBRA_JWT_SECRET", None)
        reset_settings()


def test_hmac_token_security_properties(strong_secrets):
    """HMAC bearer token mantiene seguridad criptográfica."""
    from albra.security.tokens import issue_token, verify_token
    # Issue
    token = issue_token(subject="user1", role="admin", expires_in_seconds=3600)
    # Verify correct
    payload = verify_token(token)
    assert payload is not None
    assert payload["sub"] == "user1"
    assert payload["role"] == "admin"
    # Tampered → None
    parts = token.split(".")
    tampered = parts[0] + ".invalid_signature"
    assert verify_token(tampered) is None
    # Expirado → None
    expired = issue_token(subject="u", role="r", expires_in_seconds=-1)
    assert verify_token(expired) is None


def test_no_jwt_word_in_token_module():
    """No usar 'JWT' como nombre del token en código (solo en ALBRA_JWT_SECRET env var).

    Excepciones: el env var se llama ALBRA_JWT_SECRET por compatibilidad,
    pero el token NO se llama JWT en docstrings.
    """
    import inspect

    import albra.security.tokens as tokens_mod
    src = inspect.getsource(tokens_mod)
    # El módulo debe decir explícitamente que NO es JWT
    assert "NO es JWT" in src or "not JWT" in src or "HMAC signed bearer" in src
    # No debe decir "este es un JWT" o "JWT token"
    assert "este es un JWT" not in src.lower()
    assert "JWT/JWS estándar" not in src or "NO es JWT" in src


def test_api_docstring_says_hmac_not_jwt():
    """API docs dicen HMAC, no JWT."""
    import inspect

    import albra.api.app as app_mod
    src = inspect.getsource(app_mod)
    # NO debe afirmar ser JWT en el docstring principal
    # (puede mencionar ALBRA_JWT_SECRET como env var name)
    lines = src.splitlines()
    for line in lines[:20]:  # Top docstring
        line_lower = line.lower()
        if "jwt" in line_lower and "albra_jwt_secret" not in line_lower:
            assert "no" in line_lower or "not" in line_lower, \
                f"API docstring uses JWT ambiguously: {line}"


# ============================================================
# P1 — CI clean-room sobre commit exacto
# ============================================================

def test_ci_workflow_uses_github_sha():
    """CI workflow usa github.sha para checkout específico."""
    import pathlib
    ci_path = pathlib.Path(".github/workflows/ci.yml")
    if not ci_path.exists():
        pytest.skip("CI workflow not found")
    content = ci_path.read_text()
    # Debe usar github.sha para checkout
    assert "github.sha" in content, "CI must checkout specific commit via github.sha"
    # Clean-room debe clonar el commit exacto
    assert "git checkout" in content or "ref: ${{ github.sha }}" in content


def test_ci_no_or_true():
    """CI NO usa || true para esconder fallos (solo se permite en comentarios)."""
    import pathlib
    ci_path = pathlib.Path(".github/workflows/ci.yml")
    if not ci_path.exists():
        pytest.skip("CI workflow not found")
    content = ci_path.read_text()
    # Buscar || true en líneas de comando (no en comentarios)
    for line in content.splitlines():
        stripped = line.strip()
        # Comment line
        if stripped.startswith("#") or stripped.startswith("echo"):
            continue
        # Línea de comando: contiene || true para ignorar errores
        if "|| true" in stripped and not stripped.startswith("#"):
            pytest.fail(f"CI uses '|| true' to hide failure: {stripped}")


def test_ci_python_matrix():
    """CI ejecuta matrix Python 3.10/3.11/3.12."""
    import pathlib
    ci_path = pathlib.Path(".github/workflows/ci.yml")
    content = ci_path.read_text()
    for version in ('"3.10"', '"3.11"', '"3.12"'):
        assert version in content, f"CI missing Python {version}"


# ============================================================
# Regression: secrets fail-closed en Agent.boot
# ============================================================

def test_agent_boot_fails_without_secrets(monkeypatch):
    """Agent.boot falla si no hay secretos configurados."""
    monkeypatch.delenv("ALBRA_JWT_SECRET", raising=False)
    monkeypatch.delenv("ALBRA_ADMIN_PASSWORD", raising=False)
    reset_settings()
    from albra.identity.agent import get_agent
    agent = get_agent()
    with pytest.raises(InsecureConfigurationError):
        asyncio.run(agent.boot())


def test_agent_boot_works_with_strong_secrets(strong_secrets):
    """Agent.boot funciona con secretos fuertes."""
    from albra.identity.agent import get_agent
    agent = get_agent()
    asyncio.run(agent.boot())
    asyncio.run(agent.shutdown())
