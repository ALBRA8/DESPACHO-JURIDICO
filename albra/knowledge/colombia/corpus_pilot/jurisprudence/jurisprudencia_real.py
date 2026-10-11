"""
CORPUS PILOTO — Jurisprudencia colombiana real.

1. Sentencia C-251/2002 - Corte Constitucional
   Derecho a la salud como derecho fundamental
   reach=erga_omnes, force=vinculante

2. Sentencia T-760/2008 - Corte Constitucional
   Reorganizacion del sistema de salud
   reach=erga_omnes, force=vinculante

3. Sentencia argentina (NO CO) para probar aislamiento
"""

SENTENCIA_C_251_2002 = {
    "source_id": "sent_c_251_2002",
    "source_url": "https://www.corteconstitucional.gov.co/relatoria/2002/C-251-02.htm",
    "source_tier": "S0_PRIMARY_SUPERIOR",
    "authority": "Corte Constitucional",
    "jurisdiction": "CO",
    "document_type": "sentencia",
    "title": "Sentencia C-251 de 2002 - Derecho a la salud como derecho fundamental",
    "number": "C-251/2002",
    "date_issued": "2002-04-25",
    "publication_date": "2002-04-25",
    "effective_from": "2002-04-25",
    "effective_until": None,
    "status": "vigente",
    "raw_content": b"Sentencia C-251 de 2002 Corte Constitucional - Derecho a la salud",
    "reach": "erga_omnes",
    "force": "vinculante",
    "ponente": "Magistrado Eduardo Montealegre Lynett",
    "legal_issue": "¿Se configura el derecho fundamental a la salud cuando su vulneracion amenaza otros derechos fundamentales?",
    "decision": "La Corte declara que el derecho a la salud es un derecho fundamental susceptible de proteccion mediante accion de tutela cuando su vulneracion amenaza la dignidad humana o la vida.",
    "ratio_decidendi": "El derecho a la salud, aunque pertenece al sistema de seguridad social, es un derecho fundamental cuya proteccion procede mediante accion de tutela cuando su vulneracion amenaza la dignidad humana o la vida.",
}

SENTENCIA_T_760_2008 = {
    "source_id": "sent_t_760_2008",
    "source_url": "https://www.corteconstitucional.gov.co/relatoria/2008/T-760-08.htm",
    "source_tier": "S0_PRIMARY_SUPERIOR",
    "authority": "Corte Constitucional",
    "jurisdiction": "CO",
    "document_type": "sentencia",
    "title": "Sentencia T-760 de 2008 - Reorganizacion del sistema de salud",
    "number": "T-760/2008",
    "date_issued": "2008-07-17",
    "publication_date": "2008-07-17",
    "effective_from": "2008-07-17",
    "effective_until": None,
    "status": "vigente",
    "raw_content": b"Sentencia T-760 de 2008 Corte Constitucional - Sistema de salud",
    "reach": "erga_omnes",
    "force": "vinculante",
    "ponente": "Magistrado Manuel Jose Cepeda Espinosa",
    "legal_issue": "Reorganizacion del sistema de salud para garantizar el goce efectivo del derecho a la salud.",
    "decision": "La Corte establece lineamientos para la reorganizacion del sistema de salud y la proteccion del derecho a la salud como derecho fundamental.",
    "ratio_decidendi": "El derecho a la salud debe ser garantizado por el Estado mediante la reorganizacion del sistema de seguridad social en salud, garantizando el goce efectivo del derecho.",
}

# Documento extranjero (Argentina) para probar aislamiento de jurisdiccion
SENTENCIA_AR = {
    "source_id": "sent_ar_001_2020",
    "source_url": "https://www.csjn.gov.ar/sentencia",
    "source_tier": "S1_OFFICIAL",
    "authority": "Corte Suprema de Justicia Argentina",
    "jurisdiction": "AR",
    "document_type": "sentencia",
    "title": "Sentencia argentina sobre derecho a la salud",
    "number": "AR-CS-001/2020",
    "date_issued": "2020-03-15",
    "publication_date": "2020-03-15",
    "effective_from": "2020-03-15",
    "effective_until": None,
    "status": "vigente",
    "raw_content": b"Sentencia argentina sobre salud y tutela",
    "reach": "inter_partes",
    "force": "precedente",
    "ponente": "Magistrado argentino",
    "legal_issue": "Derecho a la salud en Argentina",
    "decision": "Decision sobre salud",
    "ratio_decidendi": "El derecho a la salud en Argentina debe ser garantizado por el Estado segun la Constitucion Nacional.",
}

# Doctrina S3 para probar jerarquia
DOCTRINA_1 = {
    "source_id": "doctrine_1",
    "source_url": "https://www.editorialtemis.com/libro",
    "source_tier": "S3_DOCTRINE",
    "authority": "Editorial Temis",
    "jurisdiction": "CO",
    "document_type": "libro_doctrina",
    "title": "Compendio de Derecho Constitucional Colombiano",
    "number": "",
    "date_issued": "2020-01-01",
    "publication_date": "2020-01-01",
    "effective_from": None,
    "effective_until": None,
    "status": "vigente",
    "raw_content": b"El Estado social de derecho se fundamenta en la dignidad humana y la solidaridad.",
}
