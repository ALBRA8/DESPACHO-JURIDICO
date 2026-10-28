"""
CORPUS V1.2 — REAL SOURCE INGESTION (EXPANDED con Playwright).

V1.1 tenía 12 articles (Constitución 6 + Ley 100 3 + Ley 80 3).
V1.2 expande a 125 articles reales fetched con Playwright V2.3-E desde
secretariasenado.gov.co (HTML estático):
- Constitución 1991: 32 articles (artículos 1-32)
- Ley 100 de 1993: 45 articles
- Ley 80 de 1993: 48 articles

Cada artículo preserva:
- number: str (número de artículo, sin el sufijo 'o.' del estilo legal colombiano)
- text: str (texto del artículo, limpio de HTML tags + prefijo 'o. ')

Source URLs:
- Constitución: http://www.secretariasenado.gov.co/senado/basedoc/constitucion_politica_1991.htm
- Ley 100: http://www.secretariasenado.gov.co/senado/basedoc/ley_0100_1993.html
- Ley 80: http://www.secretariasenado.gov.co/senado/basedoc/ley_0080_1993.html

REGLA: contenido 100% real fetched de fuente oficial. Sin síntesis.
"""
from __future__ import annotations

import hashlib

# === CONSTITUCIÓN 1991 (32 articles) ===
_CONST_ARTICLES = {
    "1": "Colombia es un Estado social de derecho, organizado en forma de República unitaria, descentralizada, con autonomía de sus entidades territoriales, democrática, participativa y pluralista, fundada en el respeto de la dignidad humana, en el trabajo y la solidaridad de las personas que la integran y en la prevalencia del interés general.",
    "2": "Son fines esenciales del Estado: servir a la comunidad, promover la prosperidad general y garantizar la efectividad de los principios, derechos y deberes consagrados en la Constitución; facilitar la participación de todos en las decisiones que los afectan y en la vida económica, política, administrativa y cultural de la Nación; defender la independencia nacional, mantener la integridad territorial y asegurar la convivencia pacífica y la vigencia de un orden justo.",
    "3": "La soberanía reside exclusivamente en el pueblo, del cual emana el poder público. El pueblo la ejerce en forma directa o por medio de sus representantes, en los términos que la Constitución establece.",
    "4": "La Constitución es norma de normas. En todo caso de incompatibilidad entre la Constitución y la ley u otra norma jurídica, se aplicarán las disposiciones constitucionales.",
    "5": "El Estado reconoce, sin discriminación alguna, la primacía de los derechos inalienables de la persona y ampara a la familia como institución básica de la sociedad.",
    "6": "Los particulares sólo son responsables ante las autoridades por infringir la Constitución y las leyes. Los servidores públicos lo son por la misma causa y por omisión o extralimitación en el ejercicio de sus funciones.",
    "7": "El Estado reconoce y protege la diversidad étnica y cultural de la Nación colombiana.",
    "8": "Es obligación del Estado y de las personas proteger las riquezas culturales y naturales de la Nación.",
    "9": "Las relaciones exteriores del Estado se fundamentan en la soberanía nacional, en el respeto a la autodeterminación de los pueblos y en el reconocimiento de los principios del derecho internacional aceptados por Colombia.",
    "10": "El castellano es el idioma oficial de Colombia. Las lenguas y dialectos de los grupos étnicos son también oficiales en sus territorios. La enseñanza que se imparta en las comunidades con tradiciones lingüísticas propias será bilingüe.",
    "11": "El derecho a la vida es inviolable. No habrá pena de muerte.",
    "12": "Nadie será sometido a desaparición forzada, a torturas ni a tratos o penas crueles, inhumanos o degradantes.",
    "13": "Todas las personas nacen libres e iguales ante la ley, recibirán la misma protección y trato de las autoridades y gozarán de los mismos derechos, libertades y oportunidades sin ninguna discriminación por razones de sexo, raza, origen nacional o familiar, lengua, religión, opinión política o filosófica.",
    "14": "Toda persona tiene derecho al reconocimiento de su personalidad jurídica.",
    "15": "Todas las personas tienen derecho a su intimidad personal y familiar y a su buen nombre, y el Estado debe respetarlos y hacerlos respetar. De igual modo, tienen derecho a conocer, actualizar y rectificar las informaciones que se hayan recogido sobre ellas en bancos de datos y en archivos de entidades públicas y privadas.",
    "16": "Todas las personas tienen derecho al libre desarrollo de su personalidad sin más limitaciones que las que imponen los derechos de los demás y el orden jurídico.",
    "17": "Se prohíben la esclavitud, la servidumbre y la trata de seres humanos en todas sus formas.",
    "18": "Se garantiza la libertad de conciencia. Nadie será molestado por razón de sus convicciones o creencias ni compelido a revelarlas ni obligado a actuar contra su conciencia.",
    "19": "Se garantiza la libertad de cultos. Toda persona tiene derecho a profesar libremente su religión y a difundirla en forma individual o colectiva.",
    "20": "Se garantiza a toda persona la libertad de expresar y difundir su pensamiento y opiniones, la de informar y recibir información veraz e imparcial, y la de fundar medios masivos de comunicación.",
    "21": "Se garantiza el derecho a la honra. La ley señalará la forma de su protección.",
    "22": "La paz es un derecho y un deber de obligatorio cumplimiento.",
    "23": "Toda persona tiene derecho a presentar peticiones respetuosas a las autoridades por motivos de interés general o particular y a obtener pronta resolución. El legislador podrá reglamentar su ejercicio ante organizaciones privadas para garantizar los derechos fundamentales.",
    "24": "Todo colombiano, con las limitaciones que establezca la ley, tiene derecho a circular libremente por el territorio nacional, a entrar y salir de él, y a permanecer y residenciarse en Colombia.",
    "25": "El trabajo es un derecho y una obligación social y goza, en todas sus modalidades, de la especial protección del Estado. Toda persona tiene derecho a un trabajo en condiciones dignas y justas.",
    "26": "Toda persona es libre de escoger profesión u oficio. La ley podrá exigir títulos de idoneidad. Las autoridades competentes inspeccionarán y vigilarán el ejercicio de las profesiones. Las ocupaciones, artes y oficios que no exijan formación académica son de libre ejercicio, salvo aquellas que impliquen un riesgo social.",
    "27": "El Estado garantiza las libertades de enseñanza, aprendizaje, investigación y cátedra.",
    "28": "Toda persona es libre. Nadie puede ser molestado en su persona o familia, ni reducido a prisión o arresto, ni detenido, ni su domicilio registrado, sino en virtud de mandamiento escrito de autoridad judicial competente, con las formalidades legales y por motivo previamente definido en la ley.",
    "29": "El debido proceso se aplicará a toda clase de actuaciones judiciales y administrativas.",
    "30": "Quien estuviere privado de su libertad, y creyere estarlo ilegalmente, tiene derecho a invocar ante cualquier autoridad judicial, en todo tiempo, por sí o por interpuesta persona, el Habeas Corpus, el cual debe resolverse en el término de treinta y seis horas.",
    "31": "Toda sentencia judicial podrá ser apelada o consultada, salvo las excepciones que consagre la ley.",
    "32": "El delincuente sorprendido en flagrancia podrá ser aprehendido y llevado ante el juez por cualquier persona. Si los agentes de la autoridad lo persiguieren y se refugiare en su propio domicilio, podrán penetrar en él, para el acto de la aprehensión; si se acogiere a domicilio ajeno, deberá preceder requerimiento al morador.",
}

_CONST_SOURCE_URL = "http://www.secretariasenado.gov.co/senado/basedoc/constitucion_politica_1991.htm"


def _build_articles_text(articles_dict):
    """Build raw text from articles dict, sorted by numeric article number."""
    def sort_key(item):
        k = item[0]
        try:
            return (0, int(k))
        except (ValueError, TypeError):
            return (1, k)

    return "\n\n".join(
        f"ARTICULO {num}. {text}" for num, text in sorted(articles_dict.items(), key=sort_key)
    )


_CONST_ARTICLES_TEXT = _build_articles_text(_CONST_ARTICLES)
_CONST_RAW_CONTENT = _CONST_ARTICLES_TEXT.encode("utf-8")
_CONST_CONTENT_HASH = hashlib.sha256(_CONST_RAW_CONTENT).hexdigest()

CONSTITUCION_1991_V12 = {
    "source_id": "const_1991_real_v12",
    "source_url": _CONST_SOURCE_URL,
    "source_tier": "S0_PRIMARY_SUPERIOR",
    "authority": "Asamblea Nacional Constituyente",
    "jurisdiction": "CO",
    "document_type": "constitucion",
    "title": "Constitución Política de Colombia",
    "number": "Constitución Política de 1991",
    "date_issued": "1991-07-04",
    "publication_date": "1991-07-07",
    "effective_from": "1991-07-04",
    "effective_until": None,
    "status": "vigente",
    "raw_content": _CONST_RAW_CONTENT,
    "content_hash": _CONST_CONTENT_HASH,
    "transformation": "HTML → plain text (Playwright V2.3-E + regex ARTICULO N + cleanup 'o.' prefix)",
    "articles": [
        {"number": num, "text": text}
        for num, text in sorted(_CONST_ARTICLES.items(), key=lambda x: (0, int(x[0])) if x[0].isdigit() else (1, x[0]))
    ],
}

# === LEY 100 DE 1993 (45 articles) ===
_LEY100_ARTICLES = {
    "1": "SISTEMA DE SEGURIDAD SOCIAL INTEGRAL. El sistema de seguridad social integral tiene por objeto garantizar los derechos irrenunciables de la persona y la comunidad para obtener la calidad de vida acorde con la dignidad humana, mediante la protección de las contingencias que la afecten.",
    "2": "PRINCIPIOS. El servicio público esencial de seguridad social se prestará con sujeción a los principios de eficiencia, universalidad, solidaridad, integralidad, unidad y participación:",
    "3": "DEL DERECHO A LA SEGURIDAD SOCIAL. El Estado garantiza a todos los habitantes del territorio nacional, el derecho irrenunciable a la seguridad social.",
    "4": "DEL SERVICIO PÚBLICO DE SEGURIDAD SOCIAL. La Seguridad Social es un servicio público obligatorio, cuya dirección, coordinación y control esta a cargo del Estado y que será prestado por las entidades públicas o privadas en los términos y condiciones establecidos en la presente ley.",
    "5": "CREACIÓN. En desarrollo del artículo 48 o. de la Constitución Política, organízase el Sistema de Seguridad Social Integral cuya dirección, coordinación y control estará a cargo del Estado, en los términos de la presente ley.",
    "6": "OBJETIVOS. El Sistema de Seguridad Social Integral ordenará las instituciones y los recursos necesarios para alcanzar los siguientes objetivos:",
    "7": "ÁMBITO DE ACCIÓN. El Sistema de Seguridad Social Integral garantiza el cubrimiento de las contingencias económicas y de salud, y la prestación de servicios sociales complementarios, en los términos y bajo las modalidades previstos por esta ley.",
    "8": "CONFORMACIÓN DEL SISTEMA DE SEGURIDAD SOCIAL INTEGRAL. El Sistema de Seguridad Social Integral es el conjunto armónico de entidades públicas y privadas, normas y procedimientos y está conformado por los regímenes generales establecidos para pensiones, salud, riesgos profesionales &lt; 6 &gt; y los servicios sociales complementarios que se definen en la presente ley.",
    "9": "DESTINACIÓN DE LOS RECURSOS. No se podrán destinar ni utilizar los recursos de las instituciones de la seguridad social para fines diferentes a ella.",
    "10": "OBJETO DEL SISTEMA GENERAL DE PENSIONES. El Sistema General de Pensiones tiene por objeto garantizar a la población, el amparo contra las contingencias derivadas de la vejez, la invalidez y la muerte, mediante el reconocimiento de las pensiones y prestaciones que se determinan en la presente ley, así como propender por la ampliación progresiva de cobertura a los segmentos de población no cubiertos con un sistema de pensiones.",
    "11": "CAMPO DE APLICACIÓN. &lt;Artículo modificado por el artículo 1 de la Ley 797 de 2003. El nuevo texto es el siguiente:&gt; El Sistema General de Pensiones consagrado en la presente ley, se aplicará a todos los habitantes del territorio nacional, conservando y respetando, adicionalmente todos los derechos, garantías, prerrogativas, servicios y beneficios adquiridos y establecidos conforme a disposiciones normativas anteriores, pactos, acuerdos o convenciones colectivas de trabajo para quienes a la fecha de vigencia de esta ley hayan cumplido los requisitos para acceder a una Pensión o se encuentren pensionados por jubilación, vejez, invalidez, sustitución o sobrevivientes de los sectores público, oficial, semioficial en todos los órdenes del régimen de Prima Media y del sector privado en general.",
    "12": "RÉGIMENES DEL SISTEMA GENERAL DE PENSIONES. El Sistema General de Pensiones está compuesto por dos regímenes solidarios excluyentes pero que coexisten, a saber:",
    "13": "CARACTERÍSTICAS DEL SISTEMA GENERAL DE PENSIONES. El Sistema General de Pensiones tendrá las siguientes características:",
    "14": "REAJUSTE DE PENSIONES. Con el objeto de que las pensiones de vejez o de jubilación, de invalidez y de sustitución o sobreviviente, en cualquiera de los dos regímenes del sistema general de pensiones, mantengan su poder adquisitivo constante, se reajustarán anualmente de oficio, el primero de enero de cada año, según la variación porcentual del Indice de Precios al Consumidor , certificado por el DANE para el año inmediatamente anterior. No obstante, las pensiones cuyo monto mensual sea igual al salario mínimo legal mensual vigente, serán reajustadas de oficio cada vez y con el mismo porcentaje en que se incremente dicho salario por el Gobierno .",
    "15": "AFILIADOS. &lt;Ver Notas del Editor&gt; &lt;Artículo modificado por el artículo 3 de la Ley 797 de 2003. El nuevo texto es el siguiente:&gt; Serán afiliados al Sistema General de Pensiones:",
    "16": "INCOMPATIBILIDAD DE REGÍMENES. Ninguna persona podrá distribuir las cotizaciones obligatorias entre los dos Regímenes del Sistema General de Pensiones.",
    "17": "OBLIGATORIEDAD DE LAS COTIZACIONES. &lt;Artículo modificado por el artículo 4 de la Ley 797 de 2003. El nuevo texto es el siguiente:&gt; Durante la vigencia de la relación laboral y del contrato de prestación de servicios , deberán efectuarse cotizaciones obligatorias a los regímenes del sistema general de pensiones por parte de los afiliados, los empleadores y contratistas con base en el salario o ingresos por prestación de servicios que aquellos devenguen .",
    "18": "BASE DE COTIZACIÓN. &lt;Inciso 4. y parágrafo modificados por el artículo 5 de la Ley 797 de 2003. (El",
    "19": "BASE DE COTIZACIÓN DE LOS TRABAJADORES INDEPENDIENTES. &lt;Artículo modificado por el artículo 6 de la Ley 797 de 2003. El nuevo texto es el siguiente:&gt; Los afiliados al sistema que no estén vinculados mediante contrato de trabajo, contrato de prestación de servicios o como servidores públicos, cotizarán sobre los ingresos que declaren ante la entidad a la cual se afilien, guardando correspondencia con los ingresos efectivamente percibidos.",
    "20": "MONTO DE LAS COTIZACIONES. &lt;Ver Notas del Editor&gt; &lt;Artículo modificado por el artículo 7 de la Ley 797 de 2003. El nuevo texto es el siguiente:&gt; La tasa de cotización continuará en el 13.5%* del ingreso base de cotización.",
    "21": "INGRESO BASE DE LIQUIDACIÓN. Se entiende por ingreso base para liquidar las pensiones previstas en esta ley, el promedio de los salarios o rentas sobre los cuales ha cotizado el afiliado durante los diez (10) años anteriores al reconocimiento de la pensión, o en todo el tiempo si este fuere inferior para el caso de las pensiones de invalidez o sobrevivencia, actualizados anualmente con base en la variación del índice de precios al consumidor, según certificación que expida el DANE.",
    "22": "OBLIGACIONES DEL EMPLEADOR. El empleador será responsable del pago de su aporte y del aporte de los trabajadores a su servicio. Para tal efecto, descontará del salario de cada afiliado, al momento de su pago, el monto de las cotizaciones obligatorias y el de las voluntarias que expresamente haya autorizado por escrito el afiliado, y trasladará estas sumas a la entidad elegida por el trabajador, junto con las correspondientes a su aporte, dentro de los plazos que para el efecto determine el Gobierno.",
    "23": "SANCIÓN MORATORIA. Los aportes que no se consignen dentro de los plazos señalados para el efecto, generarán un interés moratorio a cargo del empleador, igual al que rige para el impuesto sobre la renta y complementarios. Estos intereses se abonarán en el fondo de reparto correspondiente o en las cuentas individuales de ahorro pensional de los respectivos afiliados, según sea el caso.",
    "24": "ACCIONES DE COBRO. &lt;Ver Notas del Editor&gt; Corresponde a las entidades administradoras de los diferentes regímenes adelantar las acciones de cobro con motivo del incumplimiento de las obligaciones del empleador de conformidad con la reglamentación que expida el Gobierno Nacional. Para tal efecto, la liquidación mediante la cual la administradora determine el valor adeudado, prestará mérito ejecutivo.",
    "25": "CREACIÓN DEL FONDO DE SOLIDARIDAD PENSIONAL. Créase el Fondo de Solidaridad Pensional, como una cuenta especial de la Nación sin personería jurídica, adscrita al Ministerio de Trabajo y Seguridad Social &lt; 1 &gt; , cuyos recursos serán administrados en fiducia por las sociedades fiduciarias de naturaleza pública, y preferencialmente por las sociedades fiduciarias del sector social solidario, o por las administradoras de fondos de pensiones y/o cesantía del sector social solidario , las cuales quedan autorizadas para tal efecto por virtud de la presente ley.",
    "26": "OBJETO DEL FONDO. &lt;Ver Notas del Editor&gt; &lt;Texto subrayado corregido en los términos de la Sentencia C-458-15 &gt; El Fondo de Solidaridad Pensional tiene por objeto subsidiar los aportes al Régimen General de Pensiones de los trabajadores asalariados o independientes del sector rural y urbano que carezcan de suficientes recursos para efectuar la totalidad del aporte, tales como artistas, deportistas, músicos, compositores, toreros y sus subalternos, la mujer microempresaria, las madres comunitarias*, personas en situación de discapacidad física, psíquica y sensorial , los miembros de las cooperativas de trabajo asociado y otras formas asociativas de producción, de conformidad con la reglamentación que para el efecto expida el Gobierno Nacional.",
    "27": "RECURSOS. &lt;Artículo modificado por el artículo 8 de la Ley 797 de 2003. El nuevo texto es el siguiente:&gt; El fondo de solidaridad pensional tendrá las siguientes fuentes de recursos:",
    "28": "PARCIALIDAD DEL SUBSIDIO. Los subsidios a que se refiere el presente capítulo serán de naturaleza temporal y parcial, de manera que el beneficiario realice un esfuerzo para el pago parcial del aporte a su cargo.",
    "29": "EXIGIBILIDAD DEL SUBSIDIO. Cuando el afiliado que haya recibido subsidios del Fondo de Solidaridad Pensional exceda de los sesenta y cinco (65) años de edad y no cumpla con los requisitos mínimos para acceder a una pensión de vejez, la entidad administradora respectiva devolverá el monto de los aportes subsidiados con los correspondientes rendimientos financieros a dicho Fondo.",
    "30": "SUBSIDIO A TRABAJADORES DEL SERVICIO DOMÉSTICO. Los aportes del presupuesto Nacional de que trata la ley 11 de 1988, para el subsidio en los aportes de los trabajadores del servicio doméstico, se girarán al Fondo de Solidaridad, en cuentas separadas, para que éste traslade el subsidio correspondiente a la entidad que haya seleccionado el trabajador.",
    "31": "CONCEPTO. El régimen de Prima Media con Prestación Definida es aquel mediante el cual los afiliados o sus beneficiarios obtienen una pensión de vejez, de invalidez o de sobrevivientes, o una indemnización, previamente definidas, de acuerdo con lo previsto en el presente Título.",
    "32": "CARACTERISTICAS. El Régimen de Prima Media con Prestación Definida tendrá las siguientes características:",
    "33": "REQUISITOS PARA OBTENER LA PENSIÓN DE VEJEZ. &lt;Artículo modificado por el artículo 9 de la Ley 797 de 2003. El nuevo texto es el siguiente:&gt; Para tener el derecho a la Pensión de Vejez, el afiliado deberá reunir las siguientes condiciones:",
    "34": "MONTO DE LA PENSIÓN DE VEJEZ. &lt;Artículo modificado por el artículo 10 de la Ley 797 de 2003. El nuevo texto es el siguiente:&gt; El monto mensual de la pensión de vejez, correspondiente a las primeras 1.000 semanas de cotización, será equivalente al 65% del ingreso base de liquidación. Por cada 50 semanas adicionales a las 1.000 hasta las 1.200 semanas, este porcentaje se incrementará en un 2%, llegando a este tiempo de cotización al 73% del ingreso base de liquidación. Por cada 50 semanas adicionales a las 1.200 hasta las 1.400, este porcentaje se incrementará en 3% en lugar del 2%, hasta completar un monto máximo del 85% del ingreso base de liquidación.",
    "35": "PENSIÓN MÍNIMA DE VEJEZ O JUBILACIÓN. &lt;Ver Notas del Editor&gt; El monto mensual de la pensión mínima de vejez o jubilación no podrá ser inferior al valor del salario mínimo legal mensual vigente.",
    "36": "RÉGIMEN DE TRANSICIÓN. La edad para acceder a la pensión de vejez, continuará en cincuenta y cinco (55) años para las mujeres y sesenta (60) para los hombres, hasta el año 2014*, fecha en la cual la edad se incrementará en dos años, es decir, será de 57 años para las mujeres y 62 para los hombres.",
    "37": "INDEMNIZACIÓN SUSTITUTIVA DE LA PENSIÓN DE VEJEZ. Las personas que habiendo cumplido la edad para obtener la pensión de vejez no hayan cotizado el mínimo de semanas exigidas, y declaren su imposibilidad de continuar cotizando, tendrán derecho a recibir, en sustitución, una indemnización equivalente a un salario base de liquidación promedio semanal multiplicado por el número de semanas cotizadas; al resultado así obtenido se le aplica el promedio ponderado de los porcentajes sobre los cuales haya cotizado el afiliado.",
    "38": "ESTADO DE INVALIDEZ. Para los efectos del presente capítulo se considera inválida la persona que por cualquier causa de origen no profesional, no provocada intencionalmente, hubiere perdido el 50% o más de su capacidad laboral.",
    "39": "REQUISITOS PARA OBTENER LA PENSIÓN DE INVALIDEZ. &lt;Artículo modificado por el artículo 1 de la Ley 860 de 2003. El nuevo texto es el siguiente:&gt; Tendrá derecho a la pensión de invalidez el afiliado al sistema que conforme a lo dispuesto en el artículo anterior sea declarado inválido y acredite las siguientes condiciones:",
    "40": "MONTO DE LA PENSIÓN DE INVALIDEZ. El monto mensual de la pensión de invalidez será equivalente a:",
    "41": "CALIFICACIÓN DEL ESTADO DE INVALIDEZ. &lt;Artículo modificado por el artículo 142 del Decreto 19 de 2012. El nuevo texto es el siguiente:&gt; El estado de invalidez será determinado de conformidad con Io dispuesto en los artículos siguientes y con base en el manual único para Ia calificación de invalidez vigente a Ia fecha de calificación. Este manual será expedido por el Gobierno Nacional y deberá contemplar los criterios técnicos de evaluación para calificar Ia imposibilidad que tenga el afectado para desempeñar su trabajo por pérdida de su capacidad laboral.",
    "42": "NATURALEZA, ADMINISTRACIÓN Y FUNCIONAMIENTO DE LAS JUNTAS REGIONALES Y NACIONAL DE CALIFICACIÓN DE INVALIDEZ. &lt;Artículo modificado por el artículo 16 de la Ley 1562 de 2012. El nuevo texto es el siguiente:&gt; Las Juntas Regionales y Nacional de Calificación de invalidez son organismos del Sistema de la Seguridad Social del orden nacional, de creación legal, adscritas al Ministerio de Trabajo con personería jurídica, de derecho privado, sin ánimo de lucro, de carácter interdisciplinario, sujetas a revisoría fiscal, con autonomía técnica y científica en los dictámenes periciales, cuyas decisiones son de carácter obligatorio, sin perjuicio de la segunda instancia que corresponde a la Junta Nacional de Calificación de Invalidez , respecto de las regionales y conforme a la reglamentación que determine el Ministerio de Trabajo.",
    "43": "IMPEDIMENTOS, RECUSACIONES Y SANCIONES. &lt;Artículo modificado por el artículo 19 de la Ley 1562 de 2012. El nuevo texto es el siguiente:&gt; &lt;Aparte tachado INEXEQUIBLE&gt; Los integrantes principales y suplentes de las Juntas Regionales y Nacional, en número impar serán designados, de acuerdo a la reglamentación que expida el Ministerio de Trabajo . Los integrantes serán particulares que ejercen una función pública en la prestación de dicho servicio y mientras sean parte de las Juntas de Calificación de Invalidez , no podrán tener vinculación alguna, ni realizar actividades relacionadas con la calificación del origen y grado de pérdida de la capacidad laboral o labores administrativas o comerciales en las Entidades Administradoras del Sistema Seguridad Social Integral, ni con sus entidades de dirección, vigilancia y control.",
    "44": "REVISIÓN DE LAS PENSIONES DE INVALIDEZ. El estado de invalidez podrá revisarse:",
    "45": "INDEMNIZACIÓN SUSTITUTIVA DE LA PENSIÓN DE INVALIDEZ. El afiliado que al momento de invalidarse no hubiere reunido los requisitos exigidos para la pensión de invalidez , tendrá derecho a recibir, en sustitución, una indemnización equivalente a la que le hubiera correspondido en el caso de la indemnización sustitutiva de la pensión de vejez, prevista en el artículo 37 de la presente ley;",
}

_LEY100_SOURCE_URL = "http://www.secretariasenado.gov.co/senado/basedoc/ley_0100_1993.html"
_LEY100_ARTICLES_TEXT = _build_articles_text(_LEY100_ARTICLES)
_LEY100_RAW_CONTENT = _LEY100_ARTICLES_TEXT.encode("utf-8")
_LEY100_CONTENT_HASH = hashlib.sha256(_LEY100_RAW_CONTENT).hexdigest()

LEY_100_1993_V12 = {
    "source_id": "ley_100_1993_real_v12",
    "source_url": _LEY100_SOURCE_URL,
    "source_tier": "S0_PRIMARY_SUPERIOR",
    "authority": "Congreso de la República",
    "jurisdiction": "CO",
    "document_type": "ley",
    "title": "Por la cual se crea el sistema de seguridad social integral y se dictan otras disposiciones",
    "number": "Ley 100 de 1993",
    "date_issued": "1993-12-23",
    "publication_date": "1993-12-30",
    "effective_from": "1993-12-30",
    "effective_until": None,
    "status": "modificada",
    "raw_content": _LEY100_RAW_CONTENT,
    "content_hash": _LEY100_CONTENT_HASH,
    "transformation": "HTML → plain text (Playwright V2.3-E + regex ARTICULO N + cleanup 'o.' prefix)",
    "articles": [
        {"number": num, "text": text}
        for num, text in sorted(_LEY100_ARTICLES.items(), key=lambda x: (0, int(x[0])) if x[0].isdigit() else (1, x[0]))
    ],
}

# === LEY 80 DE 1993 (48 articles) ===
_LEY80_ARTICLES = {
    "1": "DEL OBJETO. La presente ley tiene por objeto disponer las reglas y principios que rigen los contratos de las entidades estatales.",
    "2": "DE LA DEFINICIÓN DE ENTIDADES, SERVIDORES Y SERVICIOS PÚBLICOS. Para los solos efectos de esta ley:",
    "3": "DE LOS FINES DE LA CONTRATACIÓN ESTATAL. Los servidores públicos tendrán en consideración que al celebrar contratos y con la ejecución de los mismos, las entidades buscan el cumplimiento de los fines estatales, la continua y eficiente prestación de los servicios públicos y la efectividad de los derechos e intereses de los administrados que colaboran con ellas en la consecución de dichos fines.",
    "4": "DE LOS DERECHOS Y DEBERES DE LAS ENTIDADES ESTATALES. Para la consecución de los fines de que trata el artículo anterior, las entidades estatales:",
    "5": "DE LOS DERECHOS Y DEBERES DE LOS CONTRATISTAS. Para la realización de los fines de que trata el artículo 3 o. de esta ley, los contratistas:",
    "6": "DE LA CAPACIDAD PARA CONTRATAR. &lt;Artículo modificado por el artículo 1 de la Ley 2160 de 2021. El nuevo texto es el siguiente:&gt; Pueden celebrar contratos con las entidades estatales las personas consideradas legalmente capaces en las disposiciones vigentes. También podrán celebrar contratos con las entidades estatales los Cabildos Indígenas, las asociaciones de Autoridades Tradicionales Indígenas, los consejos comunitarios de las comunidades negras regulados por la Ley 70 de 1993.",
    "7": "ENTIDADES A CONTRATAR. &lt;Artículo modificado por el artículo 3 de la Ley 2160 de 2021. El nuevo texto es el siguiente:&gt;",
    "8": "DE LAS INHABILIDADES E INCOMPATIBILIDADES PARA CONTRATAR.",
    "9": "DE LAS INHABILIDADES E INCOMPATIBILIDADES SOBREVINIENTES. &lt;Artículo modificado por el artículo 6 de la Ley 2014 de 2019. El nuevo texto es el siguiente:&gt; Si llegare a sobrevenir inhabilidad o incompatibilidad en el contratista, este cederá el contrato previa autorización escrita de la entidad contratante o, si ello no fuere posible, renunciará a su ejecución.",
    "10": "DE LAS EXCEPCIONES A LAS INHABILIDADES E INCOMPATIBILIDADES. No quedan cobijadas por las inhabilidades e incompatibilidades de que tratan los artículos anteriores, las personas que contraten por obligación legal o lo hagan para usar los bienes o servicios que las entidades a que se refiere el presente estatuto ofrezcan al público en condiciones comunes a quienes los soliciten, ni las personas jurídicas sin ánimo de lucro cuyos representantes legales hagan parte de las juntas o consejos directivos en virtud de su cargo o por mandato legal o estatutario, ni quienes celebren contratos en desarrollo de lo previsto en el artículo 60 de la Constitución Política.",
    "11": "DE LA COMPETENCIA PARA DIRIGIR LICITACIONES O CONCURSOS Y PARA CELEBRAR CONTRATOS ESTATALES. &lt;Aparte tachado derogado por el artículo 32 de la Ley 1150 de 2007&gt; En las entidades estatales a que se refiere el artículo 2 o.:",
    "12": "DE LA DELEGACIÓN PARA CONTRATAR. &lt;Aparte tachado derogado por el artículo 32 de la Ley 1150 de 2007&gt; &lt;Ver Notas del Editor&gt; Los jefes y los representantes legales de las entidades estatales podrán delegar total o parcialmente la competencia para celebrar contratos y desconcentrar la realización de licitaciones o concursos en los servidores públicos que desempeñen cargos del nivel directivo o ejecutivo o en sus equivalentes.",
    "13": "DE LA NORMATIVIDAD APLICABLE A LOS CONTRATOS ESTATALES. Los contratos que celebren las entidades a que se refiere el artículo 2 o. del presente estatuto se regirán por las disposiciones comerciales y civiles pertinentes, salvo en las materias particularmente reguladas en esta ley.",
    "14": "DE LOS MEDIOS QUE PUEDEN UTILIZAR LAS ENTIDADES ESTATALES PARA EL CUMPLIMIENTO DEL OBJETO CONTRACTUAL. Para el cumplimiento de los fines de la contratación, las entidades estatales al celebrar un contrato:",
    "15": "DE LA INTERPRETACIÓN UNILATERAL. Si durante la ejecución del contrato surgen discrepancias entre las partes sobre la interpretación de algunas de sus estipulaciones que puedan conducir a la paralización o a la afectación grave del servicio público que se pretende satisfacer con el objeto contratado, la entidad estatal, si no se logra acuerdo, interpretará en acto administrativo debidamente motivado, las estipulaciones o cláusulas objeto de la diferencia.",
    "16": "DE LA MODIFICACIÓN UNILATERAL. Si durante la ejecución del contrato y para evitar la paralización o la afectación grave del servicio público que se deba satisfacer con él, fuere necesario introducir variaciones en el contrato y previamente las partes no llegan al acuerdo respectivo, la entidad en acto administrativo debidamente motivado, lo modificará mediante la supresión o adición de obras, trabajos, suministros o servicios.",
    "17": "DE LA TERMINACIÓN UNILATERAL. La entidad en acto administrativo debidamente motivado dispondrá la terminación anticipada del contrato en los siguientes eventos:",
    "18": "DE LA CADUCIDAD Y SUS EFECTOS. La caducidad es la estipulación en virtud de la cual si se presenta alguno de los hechos constitutivos de incumplimiento de las obligaciones a cargo del contratista, que afecte de manera grave y directa la ejecución del contrato y evidencie que puede conducir a su paralización, la entidad por medio de acto administrativo debidamente motivado lo dará por terminado y ordenará su liquidación en el estado en que se encuentre.",
    "19": "DE LA REVERSIÓN. &lt;Ver Notas del Editor&gt; En los contratos de explotación o concesión de bienes estatales se pactará que, al finalizar el término de la explotación o concesión, los elementos y bienes directamente afectados a la misma pasen a ser propiedad de la entidad contratante, sin que por ello ésta deba efectuar compensación alguna.",
    "20": "DE LA RECIPROCIDAD. En los procesos de contratación estatal se concederá al proponente de bienes y servicios de origen extranjero, el mismo tratamiento y en las mismas condiciones, requisitos, procedimientos y criterios de adjudicación que el tratamiento concedido al nacional, exclusivamente bajo el principio de reciprocidad.",
    "21": "DEL TRATAMIENTO Y PREFERENCIA DE LAS OFERTAS NACIONALES. &lt;Ver Notas del Editor&gt; Las entidades estatales garantizarán la participación de los oferentes de bienes y servicios de origen nacional, en condiciones competitivas de calidad, oportunidad y precio, sin perjuicio del procedimiento de selección objetiva que se utilice y siempre y cuando exista oferta de origen nacional.",
    "22": "DE LOS REGISTROS DE PROPONENTES. &lt;Artículo derogado por el artículo 32 de la Ley 1150 de 2007&gt;",
    "23": "DE LOS PRINCIPIOS EN LAS ACTUACIONES CONTRACTUALES DE LAS ENTIDADES ESTATALES. Las actuaciones de quienes intervengan en la contratación estatal se desarrollarán con arreglo a los principios de transparencia, economía y responsabilidad y de conformidad con los postulados que rigen la función administrativa. Igualmente, se aplicarán en las mismas las normas que regulan la conducta de los servidores públicos, las reglas de interpretación de la contratación, los principios generales del derecho y los particulares del derecho administrativo.",
    "24": "DEL PRINCIPIO DE TRANSPARENCIA. En virtud de este principio:",
    "25": "DEL PRINCIPIO DE ECONOMÍA. En virtud de este principio:",
    "26": "DEL PRINCIPIO DE RESPONSABILIDAD. En virtud de este principio:",
    "27": "DE LA ECUACIÓN CONTRACTUAL. En los contratos estatales se mantendrá la igualdad o equivalencia entre derechos y obligaciones surgidos al momento de proponer o de contratar , según el caso. Si dicha igualdad o equivalencia se rompe por causas no imputables a quien resulte afectado, las partes adoptarán en el menor tiempo posible las medidas necesarias para su restablecimiento.",
    "28": "DE LA INTERPRETACIÓN DE LAS REGLAS CONTRACTUALES. En la interpretación de las normas sobre contratos estatales, relativas a procedimientos de selección y escogencia de contratistas y en la de las cláusulas y estipulaciones de los contratos, se tendrá en consideración los fines y los principios de que trata esta ley, los mandatos de la buena fe y la igualdad y equilibrio entre prestaciones y derechos que caracteriza a los contratos conmutativos.",
    "29": "DEL DEBER DE SELECCIÓN OBJETIVA. &lt;Artículo derogado por el artículo 32 de la Ley 1150 de 2007&gt;",
    "30": "DE LA ESTRUCTURA DE LOS PROCEDIMIENTOS DE SELECCIÓN. &lt;Aparte tachado derogado por el artículo 32 de la Ley 1150 de 2007&gt; La licitación o concurso se efectuará conforme a las siguientes reglas:",
    "89": "de la Ley 1474 de 2011. El nuevo texto es el siguiente:&gt; Cuando lo estime conveniente la entidad interesada, de oficio o a solicitud de un número plural de posibles oferentes, dicho plazo se podrá prorrogar antes de su vencimiento, por un término no superior a la mitad del inicialmente fijado. En todo caso no podrán expedirse adendas dentro de los tres (3) días anteriores en que se tiene previsto el cierre del proceso de selección, ni siquiera para extender el término del mismo. La publicación de estas adendas sólo se podrá realizar en días hábiles y horarios laborales.",
    "31": "DE LA PUBLICACIÓN DE LOS ACTOS Y SENTENCIAS SANCIONATORIAS. &lt;Artículo modificado por el artículo 218 del Decreto 19 de 2012. El nuevo texto es el siguiente:&gt; La parte resolutiva de los actos que declaren Ia caducidad, impongan multas, sanciones o declaren el incumplimiento, una vez ejecutoriados, se publicarán en el SECOP y se comunicarán a Ia cámara de comercio en que se encuentre inscrito el contratista respectivo. También se comunicarán a Ia Procuraduría General de Ia Nación.",
    "32": "DE LOS CONTRATOS ESTATALES. &lt;Ver Notas del Editor&gt; Son contratos estatales todos los actos jurídicos generadores de obligaciones que celebren las entidades a que se refiere el presente estatuto, previstos en el derecho privado o en disposiciones especiales, o derivados del ejercicio de la autonomía de la voluntad, así como los que, a título enunciativo, se definen a continuación:",
    "33": "DE LA CONCESIÓN DE LOS SERVICIOS Y DE LAS ACTIVIDADES DE TELECOMUNICACIONES. &lt;Ver Notas de Vigencia sobre los términos de la derogatoria de este artículo por la Ley 1341 de 2009&gt; Se entiende por actividad de telecomunicaciones el establecimiento de una red de telecomunicaciones, para uso particular y exclusivo, a fin de satisfacer necesidades privadas de telecomunicaciones, y sin conexión a las redes conmutadas del Estado o a otras redes privadas de telecomunicaciones. Para todos los efectos legales las actividades de telecomunicaciones se asimilan a servicios privados.",
    "34": "DE LA CONCESIÓN DEL SERVICIO DE TELEFONIA DE LARGA DISTANCIA NACIONAL E INTERNACIONAL. &lt;Ver Notas de Vigencia sobre los términos de la derogatoria de este artículo por la Ley 1341 de 2009&gt; La concesión para la prestación de los servicios de telefonía básica fija conmutada de larga distancia nacional e internacional, se otorgará conforme a lo dispuesto por el Decreto 2122 de 1992.",
    "35": "DE LA RADIODIFUSIÓN SONORA. &lt;Artículo derogado por el artículo 73 de la Ley 1341 de 2009. Ver artículo 57 &gt;",
    "36": "DE LA DURACIÓN Y PRÓRROGA DE LA CONCESIÓN. &lt;Artículo derogado por el artículo 32 de la Ley 1150 de 2007&gt;",
    "37": "DEL RÉGIMEN DE CONCESIONES Y LICENCIAS DE LOS SERVICIOS POSTALES. &lt;Artículo derogado por el artículo 50 de la Ley 1369 de 2009. Entra a regir a partir del 30 de diciembre de 2009, según lo ordena el artículo 53 de la misma Ley&gt;",
    "38": "DEL RÉGIMEN ESPECIAL PARA LAS ENTIDADES ESTATALES QUE PRESTAN EL SERVICIO DE TELECOMUNICACIONES. &lt;Ver Notas de Vigencia sobre los términos de la derogatoria de este artículo por la Ley 1341 de 2009&gt; Las entidades estatales que tengan por objeto la prestación de servicios y actividades de telecomunicaciones, en los contratos que celebren para la adquisición y suministro de equipos, construcción, instalación y mantenimiento de redes y de los sitios donde se ubiquen, no estarán sujetos a los procedimientos de selección previstos en esta ley.",
    "39": "DE LA FORMA DEL CONTRATO ESTATAL. Los contratos que celebren las entidades estatales constarán por escrito y no requerirán ser elevados a escritura pública, con excepción de aquellos que impliquen mutación del dominio o imposición de gravámenes y servidumbres sobre bienes inmuebles y, en general, aquellos que conforme a las normas legales vigentes deban cumplir con dicha formalidad.",
    "40": "DEL CONTENIDO DEL CONTRATO ESTATAL. Las estipulaciones de los contratos serán las que de acuerdo con las normas civiles, comerciales y las previstas en esta ley, correspondan a su esencia y naturaleza.",
    "41": "DEL PERFECCIONAMIENTO DEL CONTRATO. Los contratos del Estado se perfeccionan cuando se logre acuerdo sobre el objeto y la contraprestación y éste se eleve a escrito.",
    "42": "DE LA URGENCIA MANIFIESTA. &lt;Aparte tachado derogado por el artículo 32 de la Ley 1150 de 2007&gt; Existe urgencia manifiesta cuando la continuidad del servicio exige el suministro de bienes, o la prestación de servicios, o la ejecución de obras en el inmediato futuro; cuando se presenten situaciones relacionadas con los estados de excepción; cuando se trate de conjurar situaciones excepcionales relacionadas con hechos de calamidad o constitutivos de fuerza mayor o desastre que demanden actuaciones inmediatas y, en general, cuando se trate de situaciones similares que imposibiliten acudir a los procedimientos de selección o concurso públicos.",
    "43": "DEL CONTROL DE LA CONTRATACIÓN DE URGENCIA. Inmediatamente después de celebrados los contratos originados en la urgencia manifiesta, éstos y el acto administrativo que la declaró, junto con el expediente contentivo de los antecedentes administrativos, de la actuación y de las pruebas de los hechos, se enviará al funcionario u organismo que ejerza el control fiscal en la respectiva entidad, el cual deberá pronunciarse dentro de los dos (2) meses siguientes sobre los hechos y circunstancias que determinaron tal declaración. Si fuere procedente, dicho funcionario u organismo solicitará al jefe inmediato del servidor público que celebró los referidos contratos o a la autoridad competente, según el caso, la iniciación de la correspondiente investigación disciplinaria y dispondrá el envío del asunto a los funcionarios competentes para el conocimiento de las otras acciones. El uso indebido de la contratación de urgencia será causal de mala conducta.",
    "44": "DE LAS CAUSALES DE NULIDAD ABSOLUTA. Los contratos del Estado son absolutamente nulos en los casos previstos en el derecho común y además cuando:",
    "45": "DE LA NULIDAD ABSOLUTA. &lt;Ver Notas de Vigencia y Notas del Editor&gt; La nulidad absoluta podrá ser alegada por las partes, por el agente del ministerio público, por cualquier persona o declarada de oficio, y no es susceptible de saneamiento por ratificación.",
    "46": "DE LA NULIDAD RELATIVA. Los demás vicios que se presenten en los contratos y que conforme al derecho común constituyen causales de nulidad relativa, pueden sanearse por ratificación expresa de los interesados o por el transcurso de dos (2) años contados a partir de la ocurrencia del hecho generador del vicio.",
    "47": "DE LA NULIDAD PARCIAL. La nulidad de alguna o algunas cláusulas de un contrato no invalidará la totalidad del acto, salvo cuando este no pudiese existir sin la parte viciada.",
}

_LEY80_SOURCE_URL = "http://www.secretariasenado.gov.co/senado/basedoc/ley_0080_1993.html"
_LEY80_ARTICLES_TEXT = _build_articles_text(_LEY80_ARTICLES)
_LEY80_RAW_CONTENT = _LEY80_ARTICLES_TEXT.encode("utf-8")
_LEY80_CONTENT_HASH = hashlib.sha256(_LEY80_RAW_CONTENT).hexdigest()

LEY_80_1993_V12 = {
    "source_id": "ley_80_1993_real_v12",
    "source_url": _LEY80_SOURCE_URL,
    "source_tier": "S0_PRIMARY_SUPERIOR",
    "authority": "Congreso de la República",
    "jurisdiction": "CO",
    "document_type": "ley",
    "title": "Por la cual se expide el Estatuto General de Contratación de la Administración Pública",
    "number": "Ley 80 de 1993",
    "date_issued": "1993-10-28",
    "publication_date": "1993-11-04",
    "effective_from": "1993-11-04",
    "effective_until": None,
    "status": "modificada",
    "raw_content": _LEY80_RAW_CONTENT,
    "content_hash": _LEY80_CONTENT_HASH,
    "transformation": "HTML → plain text (Playwright V2.3-E + regex ARTICULO N + cleanup 'o.' prefix)",
    "articles": [
        {"number": num, "text": text}
        for num, text in sorted(_LEY80_ARTICLES.items(), key=lambda x: (0, int(x[0])) if x[0].isdigit() else (1, x[0]))
    ],
}

# === ALL DOCUMENTS V1.2 ===
ALL_DOCUMENTS_V12 = [
    ("constitucion", CONSTITUCION_1991_V12),
    ("ley", LEY_100_1993_V12),
    ("ley", LEY_80_1993_V12),
]

# V1.1 preserved for backward compatibility
from albra.knowledge.colombia.corpus_pilot.real_corpus_v11 import ALL_DOCUMENTS as _ALL_V11  # noqa: F401

# Stats V1.2 vs V1.1
V12_STATS = {
    "v11_total_articles": 12,
    "v12_total_articles": sum(len(d["articles"]) for _, d in ALL_DOCUMENTS_V12),
    "v11_documents": 3,
    "v12_documents": 3,
    "expansion_factor": "10x",
    "fetch_method": "Playwright headless Chromium (V2.3-E)",
    "source": "secretariasenado.gov.co (static HTML)",
}
