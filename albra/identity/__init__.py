"""
ALBRA - DESPACHO JURÍDICO DIGITAL
Agente Base V1.0

Organismo completo con 30 órganos del ADN ALBRA.
El conocimiento jurídico se carga DESPUÉS (primera jurisdicción: Colombia).
"""
from albra.identity.manifest import AGENT_MANIFEST, AgentIdentity
from albra.identity.agent import Agent, get_agent

__all__ = ["AGENT_MANIFEST", "AgentIdentity", "Agent", "get_agent"]

__version__ = "1.0.0"
