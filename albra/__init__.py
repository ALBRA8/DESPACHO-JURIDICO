"""
ALBRA - DESPACHO JURÍDICO DIGITAL
Agente Base V1.0

Identidad del organismo.
"""
from albra.identity.manifest import AGENT_MANIFEST, AgentIdentity
from albra.identity.agent import Agent

__all__ = ["AGENT_MANIFEST", "AgentIdentity", "Agent"]

__version__ = "1.0.0"
