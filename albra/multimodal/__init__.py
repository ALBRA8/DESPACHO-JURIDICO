"""Multimodalidad ALBRA - los sentidos del agente."""
from albra.multimodal.audio import AudioHandler
from albra.multimodal.document import DocumentHandler
from albra.multimodal.image import ImageHandler
from albra.multimodal.text import TextHandler

__all__ = ["AudioHandler", "DocumentHandler", "ImageHandler", "TextHandler"]
