"""
INGESTA COLOMBIA — coordinator para fetch de fuentes jurídicas oficiales colombianas.

V2.3-D: infraestructura lista. V2.3-E añadirá Playwright para JS-driven sites.

Fuentes soportadas (V2.3-D):
- Gestor Normativo Función Pública (https://www.funcionpublica.gov.co/eva/es/gestor-normativo)
- Corte Suprema Relatoría Sala Laboral (https://cortesuprema.gov.co/corte/index.php/rl_aplicativo/)
- SUIN-Juriscol (https://www.suin-juriscol.gov.co/)
- Secretaría Senado (HTTP static HTML, V1.1 ya usado con éxito)

Detección de JS-driven:
- HTTP 200 + HTML sin artículos identificables + presence de patrones como
  '<div id="root">' o '<noscript>Debe habilitar JavaScript' → JS-driven detection.
- En ese caso, fallback graceful con mensaje claro al usuario.

Uso:
    coordinator = IngestionCoordinator()
    result = coordinator.attempt_official_source("gestor_normativo")
    if result.js_driven:
        # V2.3-E: usar Playwright
        print(f"JS-driven detectado en {result.url}. Reintentar con Playwright.")
    else:
        for article in result.articles:
            citation_graph.add_node(...)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger


@dataclass
class IngestionResult:
    """Resultado de un intento de ingesta."""
    source_name: str
    url: str
    http_status: int = 0
    js_driven: bool = False
    articles_extracted: list[dict[str, str]] = field(default_factory=list)
    error: str = ""
    content_hash: str = ""
    raw_html_size: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "url": self.url,
            "http_status": self.http_status,
            "js_driven": self.js_driven,
            "articles_count": len(self.articles_extracted),
            "articles_extracted": self.articles_extracted,
            "error": self.error,
            "content_hash": self.content_hash,
            "raw_html_size": self.raw_html_size,
        }


# Patrones de detección JS-driven
_JS_DRIVEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'<div\s+id="root"\s*>', re.IGNORECASE),
    re.compile(r'<noscript>.*?JavaScript.*?</noscript>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<div\s+id="__next"\s*>', re.IGNORECASE),
    re.compile(r'ng-app=', re.IGNORECASE),  # Angular
    re.compile(r'data-react-helmet', re.IGNORECASE),  # React Helmet
    re.compile(r'window\.__PRELOADED_STATE__', re.IGNORECASE),  # Redux
    re.compile(r'__INITIAL_STATE__', re.IGNORECASE),
    re.compile(r'<body[^>]*>\s*<script', re.IGNORECASE),  # body empieza con script
]


# Patrones de extracción de artículos
_ARTICLE_PATTERNS: list[re.Pattern[str]] = [
    # Constitución/Ley: "ARTICULO 1. <text>" o "ARTÍCULO 1. <text>"
    # [^<] NO captura tags; cambiamos a \S+\s+ para permitir tags inline.
    # Texto captura todo hasta el próximo ARTICULO o fin de string/párrafo.
    re.compile(
        r'ART[IÍ]CULO\s+(?P<num>\d{1,3})\.?\s*(?P<text>.+?)(?=\s*ART[IÍ]CULO\s+\d|<p[^>]*>|</p>|<li|<h\d|$)',
        re.IGNORECASE | re.DOTALL,
    ),
    # Ley con número: "Artículo 1°."
    re.compile(
        r'Art[ií]culo\s+(?P<num>\d{1,3})°?\.?\s*(?P<text>.+?)(?=\s*Art[ií]culo\s+\d|<p[^>]*>|</p>|<li|<h\d|$)',
        re.IGNORECASE | re.DOTALL,
    ),
]


# URLs oficiales colombianas conocidas (V2.3-D)
OFFICIAL_SOURCES: dict[str, dict[str, str]] = {
    "gestor_normativo": {
        "url": "https://www.funcionpublica.gov.co/eva/es/gestor-normativo",
        "description": "Leyes, decretos, circulares, sentencias del Estado colombiano",
        "v2_3_d_status": "JS-driven (probable). Requiere Playwright en V2.3-E.",
    },
    "corte_suprema_laboral": {
        "url": "https://cortesuprema.gov.co/corte/index.php/rl_aplicativo/",
        "description": "Sentencias Sala de Casación Laboral (con 7 modos de búsqueda)",
        "v2_3_d_status": "JS-driven confirmado V1.1. Requiere Playwright en V2.3-E.",
    },
    "suin_juriscol": {
        "url": "https://www.suin-juriscol.gov.co/",
        "description": "Sistema unificado de información jurídica del Ministerio de Justicia",
        "v2_3_d_status": "Liferay portal JS-driven. Requiere Playwright en V2.4.",
    },
    "secretaria_senado": {
        "url": "http://www.secretariasenado.gov.co/senado/basedoc/constitucion_politica_1991.htm",
        "description": "Constitución Política de 1991 (HTML estático, USADO CON ÉXITO en V1.1)",
        "v2_3_d_status": "HTTP estático. Fetch directo OK.",
    },
}


class IngestionCoordinator:
    """Coordinator para fetch de fuentes jurídicas oficiales colombianas.

    V2.3-D: solo infraestructura + fetch estático. JS-driven detection graceful.
    V2.3-E: añadir Playwright para JS-driven sites.
    """

    def __init__(self, http_fetcher: Any = None) -> None:
        """
        http_fetcher: callable async o sync que recibe URL y devuelve
        (status_code, html_text). Por defecto usa urllib.request.
        Para tests, inyecta mock fetcher.
        """
        self.log = get_logger("albra.knowledge.ingestion_colombia")
        self._fetcher = http_fetcher or self._default_fetcher

    def _default_fetcher(self, url: str) -> tuple[int, str]:
        """Default fetcher: urllib.request. Para V2.3-D; V2.3-E añadir Playwright."""
        try:
            from urllib.error import HTTPError, URLError
            from urllib.request import Request, urlopen
            req = Request(url, headers={"User-Agent": "ALBRA-V2.3/1.0 (legal-research)"})
            with urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            return e.code, ""
        except (URLError, OSError) as e:
            self.log.warning("ingestion.fetch_failed", url=url, error=str(e))
            return 0, ""

    # ===== Detección JS-driven =====

    def _detect_js_driven(self, html: str) -> bool:
        """Detecta si el HTML es JS-driven (sin contenido útil estático)."""
        if not html:
            return False
        for pattern in _JS_DRIVEN_PATTERNS:
            if pattern.search(html):
                return True
        return False

    # ===== Extracción de artículos =====

    def extract_articles(self, html: str, document_type: str = "ley") -> list[dict[str, str]]:
        """Extrae artículos de un HTML de ley/constitución.

        Returns: list of {number: str, text: str}.
        Vacío si no encuentra patrón ARTICULO N.
        """
        if not html:
            return []
        articles: list[dict[str, str]] = []
        seen_numbers: set[str] = set()
        for pattern in _ARTICLE_PATTERNS:
            for match in pattern.finditer(html):
                num = match.group("num").strip()
                text = match.group("text").strip()
                # Clean HTML tags del text
                text = re.sub(r"<[^>]+>", " ", text).strip()
                text = re.sub(r"\s+", " ", text)
                if len(text) < 20 or num in seen_numbers:
                    continue
                seen_numbers.add(num)
                articles.append({
                    "number": num,
                    "text": text,
                    "document_type": document_type,
                })
        return articles

    # ===== Orquestador de fuente oficial =====

    def attempt_official_source(
        self,
        source_name: str,
        url: str | None = None,
    ) -> IngestionResult:
        """Intenta fetch + extract de una fuente oficial colombiana.

        Si source_name está en OFFICIAL_SOURCES, usa URL default.
        Si url se pasa, override.

        Returns: IngestionResult con:
        - http_status: 200 si OK, 0 si fetch failed, 403/404 si HTTP error.
        - js_driven: True si detecta JS-driven (V2.3-E reintentará con Playwright).
        - articles_extracted: list of {number, text, document_type}.
        - error: mensaje si falla.
        """
        source = OFFICIAL_SOURCES.get(source_name)
        if not source and not url:
            return IngestionResult(
                source_name=source_name,
                url="",
                error=f"Unknown source: {source_name!r}. Known: {list(OFFICIAL_SOURCES)}",
            )
        target_url = url or source["url"]
        result = IngestionResult(source_name=source_name, url=target_url)

        # Fetch
        try:
            status, html = self._fetcher(target_url)
            result.http_status = status
            result.raw_html_size = len(html) if html else 0
        except Exception as e:
            result.error = f"Fetch exception: {e}"
            self.log.error("ingestion.fetch_exception", source=source_name, error=str(e))
            return result

        if status != 200 or not html:
            result.error = f"HTTP {status} or empty response"
            return result

        # Detect JS-driven
        if self._detect_js_driven(html):
            result.js_driven = True
            result.error = (
                "JS-driven site detected. V2.3-D supports static HTML only. "
                "Reintentar con Playwright en V2.3-E."
            )
            self.log.info(
                "ingestion.js_driven_detected",
                source=source_name, url=target_url, html_size=len(html),
            )
            return result

        # Extract articles
        articles = self.extract_articles(html, document_type=source.get("document_type", "ley") if source else "ley")
        result.articles_extracted = articles
        self.log.info(
            "ingestion.success",
            source=source_name, url=target_url,
            articles_count=len(articles), html_size=len(html),
        )
        return result

    def list_supported_sources(self) -> list[dict[str, str]]:
        """Lista las fuentes oficiales soportadas."""
        return [
            {
                "name": name,
                "url": info["url"],
                "description": info["description"],
                "v2_3_d_status": info["v2_3_d_status"],
            }
            for name, info in OFFICIAL_SOURCES.items()
        ]

    def stats(self) -> dict[str, Any]:
        """Stats del coordinator."""
        return {
            "supported_sources_count": len(OFFICIAL_SOURCES),
            "supported_sources": list(OFFICIAL_SOURCES.keys()),
            "playwright_available": False,  # V2.3-E
            "v2_3_d_status": "static HTML only. JS-driven sites require V2.3-E.",
        }
