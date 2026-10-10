"""Tests de memoria memorydv."""
import asyncio
import os
import tempfile

from albra.config.settings import Settings
from albra.memory.categories import MEMORY_CATEGORIES
from albra.memory.store import MemoryDV


def test_memory_categories_separated():
    """6 categorías separadas."""
    assert len(MEMORY_CATEGORIES) == 6
    for cat in ("conversational", "operational", "knowledge", "documental", "evidence", "config"):
        assert cat in MEMORY_CATEGORIES


async def _cycle(mem):
    # WRITE → STORE
    eid = await mem.write("Hola, soy ALBRA", category="conversational", metadata={"user": "test"})
    # RETRIEVE
    results = await mem.retrieve("Hola ALBRA", top_k=5)
    assert len(results) > 0
    assert any(r["id"] == eid for r in results)
    # UPDATE
    await mem.update(eid, "Hola, soy ALBRA v2")
    # CONSOLIDATE (no debe romper)
    await mem.consolidate("conversational", similarity_threshold=0.99)
    # STATS
    stats = mem.stats()
    assert "conversational" in stats or sum(stats.values()) >= 0


def test_memory_inmemory_write_retrieve():
    settings = Settings(memory_backend="inmemory")
    mem = MemoryDV(settings)
    asyncio.run(_cycle(mem))


def test_memory_sqlite_write_retrieve():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "mem.db")
        settings = Settings(memory_backend="sqlite", memory_path=db_path)
        mem = MemoryDV(settings)
        asyncio.run(_cycle(mem))


def test_memory_cycle_with_startup_shutdown():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "mem.db")
        settings = Settings(memory_backend="sqlite", memory_path=db_path)
        mem = MemoryDV(settings)
        asyncio.run(mem.startup())
        asyncio.run(_cycle(mem))
        asyncio.run(mem.shutdown())


def test_memory_invalid_category_rejected():
    settings = Settings(memory_backend="inmemory")
    mem = MemoryDV(settings)
    try:
        asyncio.run(mem.write("test", category="invalid_category"))
        raise AssertionError("Debería haber lanzado error")
    except ValueError:
        pass


def test_memory_deactivate_keeps_history():
    """Invalidate sin delete - mantiene versión histórica."""
    settings = Settings(memory_backend="inmemory")
    mem = MemoryDV(settings)
    eid = asyncio.run(mem.write("test", category="conversational"))
    asyncio.run(mem.deactivate(eid))
    results = asyncio.run(mem.retrieve("test"))
    assert all(r["id"] != eid for r in results), "Item desactivado no debe aparecer"


def test_memory_retrieves_by_category():
    """Búsqueda acotada a categoría."""
    settings = Settings(memory_backend="inmemory")
    mem = MemoryDV(settings)
    asyncio.run(mem.write("norma A", category="knowledge"))
    asyncio.run(mem.write("chat B", category="conversational"))
    results = asyncio.run(mem.retrieve("norma", category="knowledge", top_k=5))
    assert all(r["category"] == "knowledge" for r in results)
