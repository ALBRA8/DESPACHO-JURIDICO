"""
ALBRA - DESPACHO JURÍDICO DIGITAL
Agente Base V1.0

Identidad del organismo.
"""
from albra.identity.agent import Agent
from albra.identity.manifest import AGENT_MANIFEST, AgentIdentity

__all__ = ["AGENT_MANIFEST", "Agent", "AgentIdentity"]

__version__ = "1.0.0"
