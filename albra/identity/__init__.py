"""
ALBRA - DESPACHO JURÍDICO DIGITAL
Agente Base V1.0

Organismo completo con 30 órganos del ADN ALBRA.
El conocimiento jurídico se carga DESPUÉS (primera jurisdicción: Colombia).
"""
from albra.identity.agent import Agent, get_agent
from albra.identity.manifest import AGENT_MANIFEST, AgentIdentity

__all__ = ["AGENT_MANIFEST", "Agent", "AgentIdentity", "get_agent"]

__version__ = "1.0.0"
