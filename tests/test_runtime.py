"""Tests de runtime y reasoning."""
import asyncio

from albra.config.settings import Settings
from albra.reasoning.engine import ReasoningEngine
from albra.runtime.engine import Runtime


def test_runtime_initialization():
    settings = Settings()
    rt = Runtime(settings)
    assert rt.settings is settings


def test_runtime_run_loop():
    settings = Settings()
    rt = Runtime(settings)
    calls = []

    async def plan_fn(task, ctx):
        calls.append(("plan", ctx.iteration))
        if ctx.iteration >= 2:
            return {"done": True}
        return {"actions": [f"action_{ctx.iteration}"]}

    async def act_fn(action, ctx):
        calls.append(("act", action))

    result = asyncio.run(rt.run("test task", plan_fn=plan_fn, act_fn=act_fn))
    assert result["ok"] is True
    assert result["iterations"] >= 2


def test_runtime_max_iter():
    settings = Settings()
    settings.runtime_loop_max_iter = 3
    rt = Runtime(settings)

    async def plan_fn(task, ctx):
        return {"actions": ["action"]}  # never done

    async def act_fn(action, ctx):
        pass

    result = asyncio.run(rt.run("test", plan_fn=plan_fn, act_fn=act_fn))
    assert result["ok"] is False
    assert result["iterations"] >= 3


def test_reasoning_detects_greeting():
    eng = ReasoningEngine(Settings())
    plan = asyncio.run(eng.plan("hola, qué más"))
    assert plan["intent"]["name"] == "greeting"


def test_reasoning_detects_legal_question():
    eng = ReasoningEngine(Settings())
    plan = asyncio.run(eng.plan("¿qué dice la ley sobre contratos?"))
    assert plan["intent"]["name"] == "legal_question"


def test_reasoning_does_not_invent_legal_doctrine():
    eng = ReasoningEngine(Settings())
    plan = asyncio.run(eng.plan("¿qué dice el artículo 25 del código civil?"))
    response = asyncio.run(eng.respond("test", plan=plan, tool_results=[]))
    # No debe contener doctrina inventada
    assert "no ha sido cargado" in response["text"].lower() or "no inventa" in response["text"].lower()


def test_reasoning_layers_separation():
    """Verifica separación de capas DATOS/FUENTES/EVIDENCIA/INFERENCIAS/CONCLUSIONES/ACCIONES."""
    eng = ReasoningEngine(Settings())
    plan = asyncio.run(eng.plan("hola"))
    layers = plan["layers"]
    for layer in ("data", "sources", "evidence", "inferences", "conclusions", "actions"):
        assert layer in layers, f"Falta capa {layer}"
