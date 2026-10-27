"""Tests del CitationGraph (SQLite + treatment labels)."""
from __future__ import annotations

import pytest

from albra.knowledge.citation_graph import CitationGraph


@pytest.fixture
def graph(tmp_path):
    g = CitationGraph(str(tmp_path / "citation_graph.db"))
    yield g
    g.close()


@pytest.fixture
def populated_graph(graph):
    """Bootstrap con corpus V1.1 + algunos edges sintéticos."""
    graph.index_corpus_v11()
    return graph


# ===== Bootstrap =====

def test_index_corpus_v11_creates_12_nodes(populated_graph):
    """3 documentos × articles sum: Constitución 6 + Ley 100 3 + Ley 80 3 = 12."""
    stats = populated_graph.stats()
    assert stats["total_nodes"] == 12


def test_index_corpus_v11_is_idempotent(graph):
    graph.index_corpus_v11()
    count1 = graph.stats()["total_nodes"]
    graph.index_corpus_v11()
    count2 = graph.stats()["total_nodes"]
    assert count1 == count2 == 12


# ===== Nodes CRUD =====

def test_add_node_idempotent(graph):
    graph.add_node(
        node_id="test_node_1",
        document_type="legislacion",
        document_name="Test Ley 1",
        article_number="1",
    )
    # Add again — should not duplicate
    graph.add_node(
        node_id="test_node_1",
        document_type="legislacion",
        document_name="Test Ley 1",
        article_number="1",
    )
    assert graph.stats()["total_nodes"] == 1


def test_get_node_returns_dict(graph):
    graph.add_node(
        node_id="t1",
        document_type="legislacion",
        document_name="Test",
        article_number="1",
        source_url="http://example.com",
    )
    node = graph.get_node("t1")
    assert node is not None
    assert node["id"] == "t1"
    assert node["document_name"] == "Test"
    assert node["article_number"] == "1"


def test_get_nonexistent_node_returns_none(graph):
    assert graph.get_node("nonexistent") is None


def test_list_nodes_filter_by_document_type(populated_graph):
    # V1.1 corpus usa document_type "ley" (no "legislacion")
    leyes = populated_graph.list_nodes(document_type="ley")
    constitucion = populated_graph.list_nodes(document_type="constitucion")
    assert len(leyes) == 6  # Ley 100 (3) + Ley 80 (3)
    assert len(constitucion) == 6  # Constitución arts 1,2,5,13,25,29


# ===== Edges =====

def test_add_edge_creates_relationship(populated_graph):
    """Sentencia X cita artículo 1 de la Constitución con treatment='followed'."""
    # Add sentencia node
    populated_graph.add_node(
        node_id="sentencia_test_001",
        document_type="jurisprudencia",
        document_name="Sentencia Test 001",
    )
    # Add edge
    edge_id = populated_graph.add_edge(
        source_node_id="sentencia_test_001",
        target_node_id="constitucion_constitucion_politica_de_1991_art_1",
        treatment="followed",
        citing_text="aplicando el mismo criterio del artículo 1",
        confidence=1.0,
    )
    assert edge_id
    assert populated_graph.stats()["total_edges"] == 1


def test_add_edge_invalid_treatment_raises(populated_graph):
    populated_graph.add_node(
        node_id="s1", document_type="jurisprudencia", document_name="S1"
    )
    with pytest.raises(ValueError):
        populated_graph.add_edge(
            source_node_id="s1",
            target_node_id="constitucion_constitucion_politica_de_1991_art_1",
            treatment="invalid_treatment",
        )


def test_add_edge_nonexistent_source_raises(populated_graph):
    with pytest.raises(KeyError):
        populated_graph.add_edge(
            source_node_id="nonexistent",
            target_node_id="constitucion_constitucion_politica_de_1991_art_1",
            treatment="followed",
        )


def test_add_edge_nonexistent_target_raises(populated_graph):
    populated_graph.add_node(
        node_id="s1", document_type="jurisprudencia", document_name="S1"
    )
    with pytest.raises(KeyError):
        populated_graph.add_edge(
            source_node_id="s1",
            target_node_id="nonexistent_target",
            treatment="followed",
        )


# ===== Citation network =====

def test_get_citation_network_for_target_node(populated_graph):
    """Artículo 1 de la Constitución es citado por 2 sentencias."""
    populated_graph.add_node(
        node_id="s1", document_type="jurisprudencia", document_name="S1"
    )
    populated_graph.add_node(
        node_id="s2", document_type="jurisprudencia", document_name="S2"
    )
    populated_graph.add_edge(
        source_node_id="s1",
        target_node_id="constitucion_constitucion_politica_de_1991_art_1",
        treatment="followed",
    )
    populated_graph.add_edge(
        source_node_id="s2",
        target_node_id="constitucion_constitucion_politica_de_1991_art_1",
        treatment="distinguished",
    )
    network = populated_graph.get_citation_network(
        "constitucion_constitucion_politica_de_1991_art_1"
    )
    assert network["node_id"] == "constitucion_constitucion_politica_de_1991_art_1"
    assert len(network["cited_by_in"]) == 2
    assert len(network["cites_out"]) == 0  # el artículo no cita a otros


def test_get_citation_network_for_source_node(populated_graph):
    """Sentencia S1 cita a 2 articles."""
    populated_graph.add_node(
        node_id="s1", document_type="jurisprudencia", document_name="S1"
    )
    populated_graph.add_edge(
        source_node_id="s1",
        target_node_id="constitucion_constitucion_politica_de_1991_art_1",
        treatment="followed",
    )
    populated_graph.add_edge(
        source_node_id="s1",
        target_node_id="constitucion_constitucion_politica_de_1991_art_13",
        treatment="cited",
    )
    network = populated_graph.get_citation_network("s1")
    assert len(network["cites_out"]) == 2
    assert len(network["cited_by_in"]) == 0


def test_get_citation_network_nonexistent_node(populated_graph):
    network = populated_graph.get_citation_network("nonexistent")
    assert network["cites_out"] == []
    assert network["cited_by_in"] == []


# ===== Treatment stats =====

def test_get_treatment_stats(populated_graph):
    populated_graph.add_node(
        node_id="s1", document_type="jurisprudencia", document_name="S1"
    )
    populated_graph.add_node(
        node_id="s2", document_type="jurisprudencia", document_name="S2"
    )
    populated_graph.add_node(
        node_id="s3", document_type="jurisprudencia", document_name="S3"
    )
    target = "constitucion_constitucion_politica_de_1991_art_1"
    populated_graph.add_edge(source_node_id="s1", target_node_id=target, treatment="followed")
    populated_graph.add_edge(source_node_id="s2", target_node_id=target, treatment="followed")
    populated_graph.add_edge(source_node_id="s3", target_node_id=target, treatment="doubted")

    stats = populated_graph.get_treatment_stats(target)
    assert stats["followed"] == 2
    assert stats["doubted"] == 1
    assert stats["distinguished"] == 0
    assert stats["overruled"] == 0
    assert stats["total_citations"] == 3
    # Todas las treatments deben estar presentes (aunque sea 0)
    for t in ("followed", "distinguished", "doubted", "overruled",
              "per_incuriam", "affirmed", "reversed", "cited"):
        assert t in stats


# ===== Authoritative nodes =====

def test_get_authoritative_nodes_filters_by_min_citations(populated_graph):
    populated_graph.add_node(
        node_id="s1", document_type="jurisprudencia", document_name="S1"
    )
    populated_graph.add_node(
        node_id="s2", document_type="jurisprudencia", document_name="S2"
    )
    populated_graph.add_node(
        node_id="s3", document_type="jurisprudencia", document_name="S3"
    )
    target = "constitucion_constitucion_politica_de_1991_art_1"
    # Add 3 citations to target
    for src in ("s1", "s2", "s3"):
        populated_graph.add_edge(source_node_id=src, target_node_id=target, treatment="followed")
    # Other target with only 1 citation
    other_target = "constitucion_constitucion_politica_de_1991_art_2"
    populated_graph.add_edge(source_node_id="s1", target_node_id=other_target, treatment="cited")

    auth = populated_graph.get_authoritative_nodes(min_citations=2)
    assert len(auth) == 1
    assert auth[0]["node"]["article_number"] == "1"
    assert auth[0]["total_citations"] == 3


def test_get_authoritative_nodes_empty_if_no_edges(graph):
    graph.index_corpus_v11()
    auth = graph.get_authoritative_nodes(min_citations=1)
    assert auth == []


# ===== Stats =====

def test_stats_returns_counts(populated_graph):
    populated_graph.add_node(
        node_id="s1", document_type="jurisprudencia", document_name="S1"
    )
    populated_graph.add_edge(
        source_node_id="s1",
        target_node_id="constitucion_constitucion_politica_de_1991_art_1",
        treatment="followed",
    )
    stats = populated_graph.stats()
    assert stats["total_nodes"] == 13  # 12 corpus + 1 sentencia
    assert stats["total_edges"] == 1
    assert stats["by_treatment"]["followed"] == 1
    assert "db_path" in stats


def test_stats_empty_graph(graph):
    stats = graph.stats()
    assert stats["total_nodes"] == 0
    assert stats["total_edges"] == 0
    assert stats["by_treatment"] == {}


# ===== Node ID generation =====

def test_node_id_generation_is_stable(populated_graph):
    """El ID del artículo 1 de la Constitución debe ser predecible."""
    node = populated_graph.get_node(
        "constitucion_constitucion_politica_de_1991_art_1"
    )
    assert node is not None
    assert node["document_name"] == "Constitución Política de 1991"
    assert node["article_number"] == "1"
