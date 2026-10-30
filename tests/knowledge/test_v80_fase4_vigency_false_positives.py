"""V8.0 Fase 4 — Candidato 2: VigencyChecker false positives fix.

Verifica que el regex _MODIFICADO_POR (y los otros 4 markers) NO
matchean usos sustantivos como "modificado por el legislador" mientras
sí matchean amendment markers reales como "modificado por el artículo N
de la Ley X de YYYY".

Disciplina:
- True positives (amendment markers estructurados) deben seguir
  detectándose como `modified`.
- False positives (texto sustantivo describiendo quién puede modificar)
  NO deben clasificarse como `modified`.
- Consistencia VigencyChecker ↔ ContradictionDetector preservada.
"""
from __future__ import annotations

import re

import pytest

from albra.knowledge.colombia.corpus_pilot.real_corpus_v14 import ALL_DOCUMENTS_V14
from albra.knowledge.contradiction import ContradictionDetector
from albra.knowledge.vigency import (
    _ADICIONADO_POR,
    _DEROGADO_POR,
    _MODIFICADO_POR,
    _SUBROGADO_POR,
    _SUSTITUIDO_POR,
    VigencyChecker,
)

# ===== 1. False positive Constitución art. 62 =====

def test_vigency_constitucion_art_62_not_modified():
    """Constitución art. 62 contiene 'modificado por el legislador' —
    texto sustantivo (el legislador NO puede modificar el destino de
    las donaciones), NO un marker de modificación real. Debe ser
    clasificado como 'vigent', no 'modified'."""
    checker = VigencyChecker()
    doc = next(d for s, d in ALL_DOCUMENTS_V14 if s == "constitucion")
    art62 = next(a for a in doc["articles"] if a["number"] == "62")
    result = checker.check(document=doc, article=art62)
    assert result.status == "vigent", (
        f"Constitución art. 62 should be 'vigent' (substantive 'modificado por "
        f"el legislador' is NOT an amendment marker). Got: {result.status}. "
        f"Reason: {result.reason}"
    )
    assert result.superseded_by == "", (
        f"superseded_by should be empty for substantive use. Got: {result.superseded_by}"
    )


# ===== 2. True positives still detected =====

def test_vigency_real_amendment_still_detected_constitucion_77():
    """Constitución art. 77 contiene 'modificado por el artículo 2 del
    Acto Legislativo 2 de 2011' — amendment marker real. Debe seguir
    clasificándose como 'modified'."""
    checker = VigencyChecker()
    doc = next(d for s, d in ALL_DOCUMENTS_V14 if s == "constitucion")
    art77 = next(a for a in doc["articles"] if a["number"] == "77")
    result = checker.check(document=doc, article=art77)
    assert result.status == "modified", (
        f"Constitución art. 77 should be 'modified' (true amendment marker). "
        f"Got: {result.status}"
    )
    assert "artículo 2" in result.superseded_by
    assert "Acto Legislativo 2 de 2011" in result.superseded_by


def test_vigency_real_amendment_still_detected_constitucion_111():
    """Constitución art. 111 tiene marker real — debe seguir modified."""
    checker = VigencyChecker()
    doc = next(d for s, d in ALL_DOCUMENTS_V14 if s == "constitucion")
    art = next(a for a in doc["articles"] if a["number"] == "111")
    result = checker.check(document=doc, article=art)
    assert result.status == "modified", (
        f"Constitución art. 111 should be 'modified'. Got: {result.status}"
    )


def test_vigency_real_amendment_still_detected_constitucion_361():
    """Constitución art. 361 tiene 'modificado por dicho Acto Legislativo' —
    referencia ambigua pero IS una modificación real (solo referencia
    al Acto ya mencionado). El negative lookahead NO excluye 'dicho Acto',
    así que debe seguir como 'modified'."""
    checker = VigencyChecker()
    doc = next(d for s, d in ALL_DOCUMENTS_V14 if s == "constitucion")
    art = next(a for a in doc["articles"] if a["number"] == "361")
    result = checker.check(document=doc, article=art)
    assert result.status == "modified", (
        f"Constitución art. 361 ('modificado por dicho Acto Legislativo') "
        f"should remain 'modified' — 'dicho Acto' is not in the exclusion list. "
        f"Got: {result.status}"
    )


# ===== 3. Exclusion phrases (synthetic) =====

@pytest.mark.parametrize(
    "phrase",
    [
        "modificado por el legislador",
        "modificado por el gobierno",
        "modificado por el reglamento",
        "modificado por la presente Ley",
        "modificado por esta Ley",
    ],
)
def test_vigency_exclusion_phrases_do_not_match(phrase: str):
    """Cada una de las 5 frases excluidas por sí sola NO debe matchear
    el regex _MODIFICADO_POR."""
    text = f"El destino de la donación no podrá ser variado ni {phrase}, a menos que el objeto desaparezca."
    match = _MODIFICADO_POR.search(text)
    assert match is None, (
        f"Phrase {phrase!r} should NOT match _MODIFICADO_POR. Got match: {match.group(0) if match else None}"
    )


@pytest.mark.parametrize(
    "phrase",
    [
        "adicionado por el legislador",
        "adicionado por el gobierno",
        "subrogado por el legislador",
        "sustituido por el legislador",
        "derogado por el legislador",
    ],
)
def test_vigency_exclusion_phrases_do_not_match_other_markers(phrase: str):
    """Same negative lookahead applies to adicionado/subrogado/sustituido/derogado."""
    text = f"Texto genérico. El artículo fue {phrase}, según el reglamento interno."
    patterns = [_ADICIONADO_POR, _SUBROGADO_POR, _SUSTITUIDO_POR, _DEROGADO_POR]
    for pat in patterns:
        match = pat.search(text)
        # Note: each pattern matches its specific marker. A pattern matches
        # only if the marker keyword (adicionado/subrogado/etc.) is in the
        # phrase AND the exclusion does not trigger.
        marker_word = pat.pattern.split(r"\s+")[0].replace("[oa]", "").replace("(?:sustituid", "").replace("(?:derogad", "")
        if marker_word in phrase:
            assert match is None, (
                f"Phrase {phrase!r} should NOT match pattern {pat.pattern[:60]!r}. "
                f"Got match: {match.group(0) if match else None}"
            )


# ===== 4. True positive patterns (synthetic) still match =====

def test_vigency_modificado_por_articulo_still_matches():
    """'modificado por el artículo N de la Ley X de YYYY' sigue matcheando."""
    text = "Este artículo fue modificado por el artículo 20 de la Ley 1453 de 2011. Texto actual."
    match = _MODIFICADO_POR.search(text)
    assert match is not None, "True amendment marker should match"
    assert "artículo 20" in match.group(0)


def test_vigency_modificado_por_articulo_acto_legislativo_still_matches():
    """'modificado por el artículo N del Acto Legislativo Y de ZZZZ' sigue matcheando."""
    text = "Modificado por el artículo 2 del Acto Legislativo 2 de 2011."
    match = _MODIFICADO_POR.search(text)
    assert match is not None, "Acto Legislativo amendment marker should match"
    assert "artículo 2" in match.group(0)


def test_vigency_adicionado_por_articulo_still_matches():
    """'adicionado por el artículo N de la Ley X' sigue matcheando."""
    text = "Artículo adicionado por el artículo 11 de la Ley 1826 de 2017."
    match = _ADICIONADO_POR.search(text)
    assert match is not None


# ===== 5. Synthetic article-level behavior =====

def test_vigency_synthetic_modified_by_legislator_is_vigent():
    """Un artículo con texto 'modificado por el legislador' debe ser
    clasificado como 'vigent' (no 'modified')."""
    checker = VigencyChecker()
    doc = {"status": "vigente", "effective_until": None}
    article = {
        "number": "1",
        "text": "El destino de las donaciones no podrá ser modificado por el legislador.",
    }
    result = checker.check(document=doc, article=article)
    assert result.status == "vigent", (
        f"Synthetic 'modificado por el legislador' should be 'vigent'. Got: {result.status}"
    )


def test_vigency_synthetic_modified_by_article_is_modified():
    """Un artículo con texto 'modificado por el artículo N de la Ley X'
    debe seguir siendo 'modified'."""
    checker = VigencyChecker()
    doc = {"status": "vigente", "effective_until": None}
    article = {
        "number": "1",
        "text": "Artículo modificado por el artículo 20 del Acto Legislativo 2 de 2015. Texto actual.",
    }
    result = checker.check(document=doc, article=article)
    assert result.status == "modified"


# ===== 6. Consistency VigencyChecker ↔ ContradictionDetector =====

def test_vigency_consistency_with_contradiction_detector_modified():
    """Un artículo con 'modificado por el artículo N de la Ley X' debe
    clasificarse consistentemente como 'modified' por VigencyChecker Y
    como 'modification' por ContradictionDetector."""
    text = "Artículo modificado por el artículo 20 del Acto Legislativo 2 de 2015. Texto actual."
    vc = VigencyChecker()
    vr = vc.check(
        document={"status": "vigente", "effective_until": None},
        article={"number": "25", "text": text},
    )
    assert vr.status == "modified"
    cd = ContradictionDetector()
    citations = [
        {"document": "constitucion", "article": "25", "article_text": text},
        {"document": "constitucion", "article": "26", "article_text": "Texto diferente."},
    ]
    results = cd.detect(citations)
    # The pair (25, 26) should be classified as "modification" because
    # article 25 has a modification marker.
    pair_result = next(
        (r for r in results if r.citation_a == "constitucion art. 25" and r.citation_b == "constitucion art. 26"),
        None,
    )
    assert pair_result is not None, "Expected a result for the pair (25, 26)"
    assert pair_result.relation == "modification", (
        f"Expected 'modification', got {pair_result.relation}"
    )


def test_vigency_consistency_with_contradiction_detector_substantive_use():
    """Un artículo con 'modificado por el legislador' NO debe activar
    'modification' en ContradictionDetector. Consistencia: ambos
    módulos excluyen la frase sustantiva."""
    text = "El destino no podrá ser modificado por el legislador, según el reglamento."
    vc = VigencyChecker()
    vr = vc.check(
        document={"status": "vigente", "effective_until": None},
        article={"number": "1", "text": text},
    )
    assert vr.status == "vigent", (
        f"VigencyChecker should report 'vigent' for substantive use. Got: {vr.status}"
    )
    cd = ContradictionDetector()
    citations = [
        {"document": "constitucion", "article": "1", "article_text": text},
        {"document": "constitucion", "article": "2", "article_text": "Otro texto."},
    ]
    results = cd.detect(citations)
    pair_result = next(
        (r for r in results if r.citation_a == "constitucion art. 1" and r.citation_b == "constitucion art. 2"),
        None,
    )
    assert pair_result is not None
    # Should NOT be 'modification' — should be 'not_determinable' (default)
    assert pair_result.relation != "modification", (
        f"ContradictionDetector should NOT classify substantive use as 'modification'. "
        f"Got: {pair_result.relation}"
    )


# ===== 7. Count regression: total modified decreased by 1 =====

def test_vigency_total_modified_in_v14_corpus_is_86_not_87():
    """En V1.4 corpus real, el total de artículos 'modified' debe ser
    86 (era 87 antes del fix — solo Constitución art. 62 era false positive)."""
    checker = VigencyChecker()
    total_modified = 0
    for slug, doc in ALL_DOCUMENTS_V14:
        if doc.get("document_type") == "jurisprudencia":
            continue
        for art in doc.get("articles", []):
            r = checker.check(document=doc, article=art)
            if r.status == "modified":
                total_modified += 1
    assert total_modified == 86, (
        f"Expected 86 modified articles in V1.4 (after fixing art. 62 false positive). "
        f"Got: {total_modified}"
    )
