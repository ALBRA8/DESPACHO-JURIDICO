"""Capa Colombia - placeholders para futura carga de conocimiento jurídico."""

# Esta capa quedará vacía hasta que se carguen normas, jurisprudencia,
# doctrina y procedimientos colombianos en la fase de ALIMENTACIÓN.
# Por ahora solo declaramos las fuentes oficiales prioritarias.

COLOMBIA_OFFICIAL_SOURCES = {
    "constitucion": "https://www.alcaldiabogota.gov.co/sisjur/normas/Norma1.jsp?i=4125",
    "rama_judicial": "https://www.ramajudicial.gov.co",
    "corte_constitucional": "https://www.corteconstitucional.gov.co",
    "corte_suprema": "https://www.cortesuprema.gov.co",
    "consejo_estado": "https://www.consejodeestado.gov.co",
    "ministerio_justicia": "https://www.minjusticia.gov.co",
    "funcion_publica": "https://www.funcionpublica.gov.co",
    "super_sociedades": "https://www.supersociedades.gov.co",
    "super_financiera": "https://www.superfinanciera.gov.co",
    "diario_oficial": "https://dapre.presidencia.gov.co/normatividad",
}

# Códigos principales (vacíos - se cargarán)
COLOMBIA_CODES = {
    "civil": None,
    "comercio": None,
    "penal": None,
    "procedimiento_civil": None,
    "procedimiento_penal": None,
    "procedimiento_administrativo": None,
    "infancia_adolescencia": None,
    "penitenciario": None,
    "contencioso_administrativo": None,
}

# VACÍO - se cargará en la siguiente fase
LOADED = False
