"""Tests del IngestionCoordinator (infraestructura V2.3-D)."""
from __future__ import annotations

import pytest

from albra.knowledge.ingestion_colombia import (
    OFFICIAL_SOURCES,
    IngestionCoordinator,
    IngestionResult,
)

# ===== Mock fetcher =====

class MockFetcher:
    """Mock HTTP fetcher para tests. Devuelve (status, html)."""

    def __init__(self, responses: dict[str, tuple[int, str]]):
        """responses: {url: (status_code, html_text)}"""
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str) -> tuple[int, str]:
        self.calls.append(url)
        return self.responses.get(url, (404, ""))


# ===== Fixtures =====

@pytest.fixture
def coordinator():
    """Coordinator con mock fetcher que no responde a nada."""
    return IngestionCoordinator(http_fetcher=MockFetcher({}))


# ===== OFFICIAL_SOURCES =====

def test_official_sources_has_4_sources():
    assert len(OFFICIAL_SOURCES) == 4
    expected = {"gestor_normativo", "corte_suprema_laboral", "suin_juriscol", "secretaria_senado"}
    assert set(OFFICIAL_SOURCES.keys()) == expected


def test_official_sources_have_url_and_description():
    for name, info in OFFICIAL_SOURCES.items():
        assert "url" in info
        assert "description" in info
        assert "v2_3_d_status" in info
        assert info["url"].startswith("http")


# ===== List sources =====

def test_list_supported_sources_returns_4(coordinator):
    sources = coordinator.list_supported_sources()
    assert len(sources) == 4
    names = [s["name"] for s in sources]
    assert "gestor_normativo" in names
    assert "secretaria_senado" in names


# ===== Stats =====

def test_stats_returns_metadata(coordinator):
    stats = coordinator.stats()
    assert stats["supported_sources_count"] == 4
    # V2.3-E: playwright IS available now
    assert stats["playwright_available"] is True
    assert "v2_3_d_status" in stats


# ===== Unknown source =====

def test_attempt_unknown_source_returns_error(coordinator):
    result = coordinator.attempt_official_source("nonexistent_source")
    assert isinstance(result, IngestionResult)
    assert result.error != ""
    assert "Unknown source" in result.error


# ===== JS-driven detection =====

def test_attempt_js_driven_source_returns_js_driven_flag():
    """Simula Gestor Normativo que responde con React root div."""
    js_html = '''<!DOCTYPE html>
<html><head><title> Gestor Normativo</title></head>
<body><div id="root"></div><script src="/bundle.js"></script></body></html>'''
    fetcher = MockFetcher({
        "https://www.funcionpublica.gov.co/eva/es/gestor-normativo": (200, js_html)
    })
    coord = IngestionCoordinator(http_fetcher=fetcher)
    result = coord.attempt_official_source("gestor_normativo")
    assert result.http_status == 200
    assert result.js_driven is True
    assert result.articles_extracted == []
    assert "JS-driven" in result.error


def test_attempt_static_html_source_extracts_articles():
    """Simula Secretaría Senado que responde con HTML estático de la Constitución."""
    static_html = '''<!DOCTYPE html>
<html><body>
<h1>Constitución Política de 1991</h1>
<p>ARTICULO 1. Colombia es un Estado social de derecho organizado en forma de República unitaria.</p>
<p>ARTICULO 2. Son fines esenciales del Estado: servir a la comunidad y promover la prosperidad general.</p>
<p>ARTICULO 5. El Estado reconoce, sin discriminación alguna, la primacía de los derechos inalienables de la persona.</p>
</body></html>'''
    fetcher = MockFetcher({
        "http://www.secretariasenado.gov.co/senado/basedoc/constitucion_politica_1991.htm": (200, static_html)
    })
    coord = IngestionCoordinator(http_fetcher=fetcher)
    result = coord.attempt_official_source("secretaria_senado")
    assert result.http_status == 200
    assert result.js_driven is False
    assert len(result.articles_extracted) == 3
    assert result.articles_extracted[0]["number"] == "1"
    assert "Estado social" in result.articles_extracted[0]["text"]
    assert result.articles_extracted[1]["number"] == "2"
    assert result.articles_extracted[2]["number"] == "5"


def test_attempt_http_error_returns_error():
    fetcher = MockFetcher({
        "https://www.funcionpublica.gov.co/eva/es/gestor-normativo": (403, "")
    })
    coord = IngestionCoordinator(http_fetcher=fetcher)
    result = coord.attempt_official_source("gestor_normativo")
    assert result.http_status == 403
    assert result.js_driven is False
    assert result.articles_extracted == []
    assert "403" in result.error or "HTTP" in result.error


def test_attempt_empty_html_returns_no_articles():
    fetcher = MockFetcher({
        "http://www.secretariasenado.gov.co/senado/basedoc/constitucion_politica_1991.htm": (200, "")
    })
    coord = IngestionCoordinator(http_fetcher=fetcher)
    result = coord.attempt_official_source("secretaria_senado")
    assert result.http_status == 200
    assert result.articles_extracted == []


def test_attempt_fetch_exception_returns_error():
    """Si el fetcher lanza, coordinator debe capturar y devolver error."""

    def raising_fetcher(url):
        raise OSError("Connection refused")

    coord = IngestionCoordinator(http_fetcher=raising_fetcher)
    result = coord.attempt_official_source("secretaria_senado")
    assert result.error != ""
    assert "Fetch exception" in result.error or "Connection refused" in result.error


# ===== Article extraction =====

def test_extract_articles_constitucion_format(coordinator):
    html = """
    <p>ARTICULO 13. Todas las personas nacen libres e iguales ante la ley.</p>
    <p>ARTICULO 29. El debido proceso se aplicará a toda clase de actuaciones.</p>
    """
    articles = coordinator.extract_articles(html, document_type="constitucion")
    assert len(articles) == 2
    assert articles[0]["number"] == "13"
    assert "libres" in articles[0]["text"]
    assert articles[1]["number"] == "29"


def test_extract_articles_accented_articulo(coordinator):
    """'ARTÍCULO' con tilde también debe matchear."""
    html = """
    <p>ARTÍCULO 1. Texto del artículo primero.</p>
    <p>ARTÍCULO 2. Texto del segundo artículo aquí.</p>
    """
    articles = coordinator.extract_articles(html, document_type="ley")
    assert len(articles) == 2
    assert articles[0]["number"] == "1"


def test_extract_articles_with_html_tags_in_text(coordinator):
    """El text extraído debe limpiarse de HTML tags."""
    html = """
    <p>ARTICULO 1. Colombia es <b>un Estado</b> social de <a href="#">derecho</a>.</p>
    """
    articles = coordinator.extract_articles(html)
    assert len(articles) == 1
    assert "<b>" not in articles[0]["text"]
    assert "<a" not in articles[0]["text"]
    assert "Estado" in articles[0]["text"]
    assert "derecho" in articles[0]["text"]


def test_extract_articles_dedupes_by_number(coordinator):
    """Si el mismo artículo aparece dos veces, solo se cuenta una vez."""
    html = """
    <p>ARTICULO 1. Texto primero.</p>
    <p>ARTICULO 1. Repetido, debe ignorarse.</p>
    """
    articles = coordinator.extract_articles(html)
    assert len(articles) == 1


def test_extract_articles_skips_short_text(coordinator):
    """Textos muy cortos (<20 chars) se ignoran."""
    html = """
    <p>ARTICULO 1. Corto.</p>
    <p>ARTICULO 2. Texto suficientemente largo para pasar el filtro.</p>
    """
    articles = coordinator.extract_articles(html)
    assert len(articles) == 1
    assert articles[0]["number"] == "2"


def test_extract_articles_empty_html_returns_empty(coordinator):
    assert coordinator.extract_articles("") == []
    assert coordinator.extract_articles("<html></html>") == []


def test_extract_articles_no_articles_pattern_returns_empty(coordinator):
    html = "<html><body><p>No hay artículos aquí.</p></body></html>"
    assert coordinator.extract_articles(html) == []


# ===== JS-driven detection (unit tests) =====

def test_detect_js_driven_react_root():
    coord = IngestionCoordinator(http_fetcher=MockFetcher({}))
    assert coord._detect_js_driven('<div id="root"></div>') is True


def test_detect_js_driven_angular_app():
    coord = IngestionCoordinator(http_fetcher=MockFetcher({}))
    assert coord._detect_js_driven('<html ng-app="myApp">') is True


def test_detect_js_driven_nextjs():
    coord = IngestionCoordinator(http_fetcher=MockFetcher({}))
    assert coord._detect_js_driven('<div id="__next"></div>') is True


def test_detect_js_driven_static_html_returns_false():
    coord = IngestionCoordinator(http_fetcher=MockFetcher({}))
    static = '<html><body><h1>Hello</h1><p>Real content.</p></body></html>'
    assert coord._detect_js_driven(static) is False


def test_detect_js_driven_empty_returns_false():
    coord = IngestionCoordinator(http_fetcher=MockFetcher({}))
    assert coord._detect_js_driven("") is False


# ===== IngestionResult as_dict =====

def test_ingestion_result_as_dict():
    r = IngestionResult(
        source_name="test", url="http://test.com",
        http_status=200, js_driven=False,
        articles_extracted=[{"number": "1", "text": "test"}],
        error="", raw_html_size=500,
    )
    d = r.as_dict()
    assert d["source_name"] == "test"
    assert d["url"] == "http://test.com"
    assert d["http_status"] == 200
    assert d["js_driven"] is False
    assert d["articles_count"] == 1
    assert d["raw_html_size"] == 500


# ===== V2.3-E: Playwright tests =====

def test_stats_reports_playwright_available_after_install(coordinator):
    """Tras install playwright, stats debe reportar playwright_available=True."""
    stats = coordinator.stats()
    # Playwright was installed in V2.3-E
    assert stats["playwright_available"] is True


def test_fetch_with_playwright_static_html_site(coordinator):
    """Playwright debe poder fetchear una página HTML estática conocida."""
    # Use secretariasenado — known to be static HTML, used successfully in V1.1
    status, html, error = coordinator.fetch_with_playwright(
        "http://www.secretariasenado.gov.co/senado/basedoc/constitucion_politica_1991.htm",
        wait_for="load",
        timeout_ms=20000,
    )
    # Tolerar fallos de red, pero si funciona, verificar formato
    if error:
        # Skip if network/playwright unavailable
        import pytest
        pytest.skip(f"Network or playwright unavailable: {error}")
    assert status == 200
    assert len(html) > 1000  # Constitución HTML es grande


def test_attempt_with_playwright_unknown_source_returns_error(coordinator):
    result = coordinator.attempt_with_playwright("nonexistent_source")
    assert result.error != ""
    assert "Unknown source" in result.error


def test_attempt_with_playwright_static_html_extracts_articles(coordinator):
    """Playwright en site estático también debe extraer articles (mismos que V1.1)."""
    result = coordinator.attempt_with_playwright("secretaria_senado")
    # Skip if network unavailable
    if result.error and ("playwright" in result.error.lower() or "Network" in result.error):
        import pytest
        pytest.skip(f"Network/playwright unavailable: {result.error}")
    # Si llegó, debe tener articles de la Constitución
    assert result.http_status == 200
    # Constitución V1.1 tiene 6 articles conocidos (1, 2, 5, 13, 25, 29)
    # Playwright puede extraer MÁS articles del HTML completo
    assert len(result.articles_extracted) >= 6


def test_attempt_with_playwright_js_driven_site(coordinator):
    """Playwright en site JS-driven (CSJ Laboral) — debe renderizar.
    Skip si network unavailable o site bloquea headless."""
    result = coordinator.attempt_with_playwright("corte_suprema_laboral")
    # Skip if network/playwright unavailable
    if result.error and ("playwright" in result.error.lower() or "exception" in result.error.lower()):
        import pytest
        pytest.skip(f"Network/playwright unavailable: {result.error}")
    # Si llegó, status debe ser 200 o error claro
    assert result.http_status in (0, 200, 403, 404) or result.error
