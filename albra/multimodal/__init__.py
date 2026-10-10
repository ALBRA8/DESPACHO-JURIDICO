"""Multimodalidad ALBRA - los sentidos del agente."""
from albra.multimodal.text import TextHandler
from albra.multimodal.image import ImageHandler
from albra.multimodal.audio import AudioHandler
from albra.multimodal.document import DocumentHandler

__all__ = ["TextHandler", "ImageHandler", "AudioHandler", "DocumentHandler"]
