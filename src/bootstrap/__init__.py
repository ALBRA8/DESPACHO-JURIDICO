"""
Bootstrap — inicialización del arnés ALBRA.

Monta el AGENTE-GENERAL sobre el arnés con:
- BridgeRegistry (ZAI SDK priority + Python fallback)
- SkillRegistry
- KnowledgeRegistry (conocimiento jurídico ALBRA)
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from src.adapters.general_adapter import GeneralAdapter
from src.adapters.types import (
    AgentAdapter,
    HarnessContext,
    ProjectConfig,
    StackType,
)
from src.bridges.types import BridgeRegistry, PythonBridge, ZaiSdkBridge
from src.harness.knowledge_registry import KnowledgeRegistry, register_builtin_knowledge
from src.harness.types import SkillRegistry


def bootstrap(
    project_name: str = "DESPACHO JURIDICO ALBRA",
    environment: str = "development",
    python_path: str = "python3",
    script_dir: str = "./scripts",
) -> HarnessContext:
    """
    Inicializa el arnés y monta el AGENTE-GENERAL.

    Returns:
        HarnessContext con bridges, skills, knowledge y agent montados.
    """
    print(f"[Bootstrap] Inicializando arnés para: {project_name}")

    # 1. Bridges
    bridges = BridgeRegistry()
    zai_bridge = ZaiSdkBridge()
    bridges.register(zai_bridge, is_priority=True)

    # Python bridge como fallback
    py_bridge = PythonBridge(
        name="ALBRA-Python",
        python_path=python_path,
        script_dir=script_dir,
    )
    bridges.register(py_bridge)

    # 2. Skills
    skills = SkillRegistry()

    # 3. Knowledge
    knowledge = KnowledgeRegistry()
    register_builtin_knowledge(knowledge)

    # 4. Config
    config = ProjectConfig(
        project_name=project_name,
        stack=StackType.PYTHON,
        environment=environment,
        bridges=[
            {"type": "zai-sdk", "enabled": True},
            {"type": "python", "enabled": True, "config": {"pythonPath": python_path, "scriptDir": script_dir}},
        ],
    )

    # 5. Montar agente
    agent = GeneralAdapter()
    context = HarnessContext(
        bridges=bridges,
        skills=skills,
        knowledge=knowledge,
        config=config,
    )

    print("[Bootstrap] Arnés listo.")
    print(f"  Agente: {agent.name} v{agent.version}")
    print(f"  Bridges: {[b['type'] for b in bridges.list()]}")
    print(f"  Skills: {len(skills.list())}")
    print(f"  Knowledge: {len(knowledge.list())} módulos ({knowledge.health_check()['valid']} válidos)")

    return context
