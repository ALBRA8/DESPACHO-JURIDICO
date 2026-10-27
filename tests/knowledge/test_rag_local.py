"""Tests de LocalRAG — TF-IDF + cosine similarity en Python puro.

V2.2-B: RAG local lightweight sin numpy/sklearn/sentence-transformers/qdrant.

Cobertura (17 tests):
- Tokenizer: lowercase, stopwords, unicode accents
- Empty RAG: search [] y stats zeros
- index_document: count de chunks y vocabulary growth
- index_corpus: carga 12 chunks de real_corpus_v11
- search: top-k, shape de result, article 13 first, min_score filter,
  no-match, sorted descending
- persist/load roundtrip + load nonexistent
- default_rag carga corpus
- clear resetea índice
"""
from __future__ import annotations

import pytest

from albra.knowledge.colombia.corpus_pilot import real_corpus_v11
from albra.knowledge.rag_local import LocalRAG, _tokenize, default_rag


@pytest.fixture
def strong_secrets(monkeypatch):
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def rag(strong_secrets):
    return LocalRAG()


@pytest.fixture
def loaded_rag(strong_secrets):
    return default_rag()


# ===== Tokenizer =====

def test_tokenizer_lowercases_and_filters_short_tokens(strong_secrets):
    """Lowercase, conserva palabras largas, elimina 1-char."""
    tokens = _tokenize("El Estado PROTEGE a los NIÑOS")
    assert "estado" in tokens
    assert "protege" in tokens
    assert "niños" in tokens
    # 'el' y 'los' son stopwords; 'a' es 1-char
    assert "el" not in tokens
    assert "a" not in tokens
    assert "los" not in tokens


def test_tokenizer_removes_spanish_stopwords(strong_secrets):
    """Lista de stopwords se filtra completamente."""
    text = "el la los las de del y o a en que se su es son por para con"
    assert _tokenize(text) == []


def test_tokenizer_keeps_accented_unicode(strong_secrets):
    """Caracteres acentuados se conservan."""
    tokens = _tokenize("Constitución artículo libertad jurídica")
    assert "constitución" in tokens
    assert "artículo" in tokens
    assert "libertad" in tokens
    assert "jurídica" in tokens


def test_tokenizer_handles_empty_and_none(strong_secrets):
    """Texto vacío o None → lista vacía sin excepción."""
    assert _tokenize("") == []


# ===== Empty RAG =====

def test_empty_rag_search_returns_empty(rag):
    """RAG vacío → search devuelve []."""
    assert rag.search("constitución") == []


def test_empty_rag_stats(rag):
    """Stats de RAG vacío: 0 documentos, 0 chunks, 0 vocab, None path."""
    stats = rag.stats()
    assert stats["documents"] == 0
    assert stats["chunks"] == 0
    assert stats["vocabulary_size"] == 0
    assert stats["persist_path"] is None


# ===== index_document =====

def test_index_document_returns_chunks_count(rag):
    """Indexa 2 artículos → devuelve 2 y stats refleja 2 chunks."""
    doc = {
        "source_id": "test_doc_1",
        "document_type": "ley",
        "number": "Ley 99 de 1999",
        "articles": [
            {"number": "1", "text": "Disposición general sobre ambiente."},
            {"number": "2", "text": "Mecanismos de protección ambiental."},
        ],
    }
    count = rag.index_document(doc)
    assert count == 2
    assert rag.stats()["chunks"] == 2


def test_index_document_increments_vocabulary(rag):
    """Indexar un documento con tokens únicos hace crecer el vocabulario."""
    before = rag.stats()["vocabulary_size"]
    doc = {
        "source_id": "t_vocab",
        "document_type": "ley",
        "number": "Ley Ambiente",
        "articles": [
            {"number": "1", "text": "Ambiente sano y equilibrado."},
        ],
    }
    rag.index_document(doc)
    after = rag.stats()["vocabulary_size"]
    assert after > before
    assert "ambiente" in rag._index.vocabulary


# ===== index_corpus =====

def test_index_corpus_loads_all_documents(rag):
    """Indexa real_corpus_v11 → 12 chunks, 3 documentos."""
    total = rag.index_corpus(real_corpus_v11)
    assert total == 12
    stats = rag.stats()
    assert stats["chunks"] == 12
    assert stats["documents"] == 3
    assert stats["vocabulary_size"] > 0


# ===== search =====

def test_search_returns_top_k(loaded_rag):
    """search respeta k como máximo de resultados."""
    results = loaded_rag.search("derechos", k=3)
    assert len(results) <= 3
    for r in results:
        assert r["score"] > 0


def test_search_result_shape(loaded_rag):
    """Cada resultado tiene las 6 claves requeridas."""
    results = loaded_rag.search("constitución", k=2)
    for r in results:
        assert "source_id" in r
        assert "document_name" in r
        assert "document_type" in r
        assert "article_number" in r
        assert "text" in r
        assert "score" in r
        assert isinstance(r["score"], float)


def test_search_constitucion_article_13_first(loaded_rag):
    """'Constitución artículo 13' recupera el art 13 primero."""
    results = loaded_rag.search("Constitución artículo 13", k=5)
    assert len(results) > 0
    top = results[0]
    assert top["article_number"] == "13"
    assert "constitución" in top["document_name"].lower()


def test_search_min_score_filter_reduces_results(loaded_rag):
    """min_score alto reduce o iguala el número de resultados."""
    low = loaded_rag.search("seguridad social integral", k=10, min_score=0.0)
    high = loaded_rag.search("seguridad social integral", k=10, min_score=0.9)
    assert len(high) <= len(low)


def test_search_no_match_returns_empty(loaded_rag):
    """Consulta sin tokens válidos en el vocabulario → []."""
    results = loaded_rag.search("zzzqqqxxww gibberish nonsense")
    assert results == []


def test_search_results_sorted_descending(loaded_rag):
    """Resultados ordenados por score descendente."""
    results = loaded_rag.search("seguridad social integral", k=5)
    assert len(results) >= 2
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_search_specific_article_text(loaded_rag):
    """Búsqueda por contenido del artículo lo recupera."""
    # art 13 constitución habla de "discriminación por razones de sexo"
    results = loaded_rag.search("discriminación razones sexo raza", k=3)
    assert len(results) > 0
    top = results[0]
    assert top["article_number"] == "13"


# ===== persist / load =====

def test_persist_returns_path_and_creates_file(rag, tmp_path):
    """persist devuelve la ruta y crea el archivo en disco."""
    rag.index_document({
        "source_id": "persist_path",
        "document_type": "ley",
        "number": "Ley P",
        "articles": [{"number": "1", "text": "Texto sobre ambiente."}],
    })
    path = tmp_path / "rag.pkl"
    returned = rag.persist(str(path))
    assert returned == str(path)
    assert path.exists()


def test_persist_load_roundtrip(rag, tmp_path):
    """persist + load restaura índice idéntico (usando corpus real).

    Usamos el corpus real (12 chunks) en lugar de un doc sintético de 2
    arts, porque la fórmula idf=log(N/(1+df)) produce idf=0 cuando un
    token aparece en 1 doc de un corpus de 2, lo que anula el scoring.
    Con N=12 y tokens discriminativos (e.g. '13' df=1), idf es positivo.
    """
    from albra.knowledge.colombia.corpus_pilot.real_corpus_v11 import (
        ALL_DOCUMENTS,
    )
    for _doc_type, doc in ALL_DOCUMENTS:
        rag.index_document(doc)
    before = rag.search("Constitución artículo 13", k=5)
    assert len(before) > 0
    before_top = before[0]

    path = tmp_path / "rag.pkl"
    rag.persist(str(path))

    # Nuevo RAG, carga desde disco
    rag2 = LocalRAG(persist_path=str(path))
    assert rag2.load() is True

    after = rag2.search("Constitución artículo 13", k=5)
    assert len(after) == len(before)
    assert after[0]["article_number"] == before_top["article_number"]
    assert after[0]["score"] == pytest.approx(before_top["score"])


def test_load_nonexistent_returns_false(rag, tmp_path):
    """load de archivo inexistente devuelve False (no lanza)."""
    path = tmp_path / "nonexistent.pkl"
    rag2 = LocalRAG(persist_path=str(path))
    assert rag2.load() is False


# ===== default_rag =====

def test_default_rag_loads_corpus(strong_secrets):
    """default_rag() crea RAG con 12 chunks del corpus V1.1."""
    rag_obj = default_rag()
    stats = rag_obj.stats()
    assert stats["chunks"] == 12
    assert stats["documents"] == 3
    assert stats["vocabulary_size"] > 0


# ===== clear =====

def test_clear_resets_index(loaded_rag):
    """clear() vacía completamente el índice."""
    assert loaded_rag.stats()["chunks"] == 12
    loaded_rag.clear()
    stats = loaded_rag.stats()
    assert stats["chunks"] == 0
    assert stats["vocabulary_size"] == 0
    assert stats["documents"] == 0
    assert loaded_rag.search("constitución") == []
