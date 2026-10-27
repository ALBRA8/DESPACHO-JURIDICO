"""
DOCUMENTS — generación de DOCX con tracked changes nativas (w:ins / w:del).

Módulo V2.2 — Redline DOCX.

Inspiración clean-room (no copiar código): patrón de GLAW (redline-docx) y
Lawgent (docx-redline, compare_docx_blackline blackline).
"""
from albra.documents.redline import (
    RedlineDocxGenerator,
    compare_docx_blackline,
)

__all__ = [
    "RedlineDocxGenerator",
    "compare_docx_blackline",
]
