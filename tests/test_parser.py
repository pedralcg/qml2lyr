# -*- coding: utf-8 -*-
"""Tests del PARSER (XML de QGIS -> modelo intermedio) que no necesitan ArcGIS.

`run_regresion_qml.py` prueba la cadena entera hasta el .lyr, pero exige
ArcGIS 10.5 (ArcObjects). Este fichero cubre la mitad que es Python puro y
por eso corre tambien en el CI de GitHub, en Linux: si un cambio rompe la
lectura del XML de QGIS, salta aqui aunque nadie tenga ArcGIS a mano.

Python 2.7 (el parser usa literales `ur""`, igual que el emisor):

    python2 tests/test_parser.py

Todos los fixtures los escribio QGIS 3.44.12 (`tests/generar_fixtures_qgis.py`):
uno hecho a mano solo probaria lo que suponemos que escribe QGIS.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

import parser_qgis  # noqa: E402
from modelo import (SimboloMarcador, SimboloMarcadorCaracter,  # noqa: E402
                    RendererValoresUnicos, SimbologiaNoSoportada)

DIR_QML = os.path.join(RAIZ, "tests", "fixtures", "qml")
QGZ_BATCH = os.path.join(RAIZ, "tests", "fixtures", "batch_sintetico.qgz")
QGZ_REMAP = os.path.join(RAIZ, "tests", "fixtures", "batch_remap.qgz")
MM2PT = 2.834645669


def _qml(nombre):
    return parser_qgis.parse_qml(os.path.join(DIR_QML, nombre))


def _igual(fallos, obtenido, esperado, que):
    if obtenido != esperado:
        fallos.append(u"%s: esperado %r, obtenido %r" % (que, esperado, obtenido))


def _cerca(fallos, obtenido, esperado, que, tol=1e-3):
    if obtenido is None or abs(obtenido - esperado) > tol:
        fallos.append(u"%s: esperado ~%r, obtenido %r" % (que, esperado, obtenido))


def test_regla_desmarcada(fallos):
    """QGIS 3.44.12: la regla con checkstate="0" no sale ni entra en el ELSE."""
    capas = _qml("reglas_con_desmarcada.qml")
    _igual(fallos, [c.nombre for c in capas], [u"Rios", u"Resto"], u"reglas")
    _igual(fallos, capas[1].defquery,
           u'NOT (("TIPO" = \'rio\')) OR "TIPO" IS NULL', u"def-query del ELSE")


def test_regla_desmarcada_simbolo_raro(fallos):
    """QGIS 3.44.12: un simbolo no soportado en una regla desmarcada no tumba
    la capa (antes saltaba SimbologiaNoSoportada por un MarkerLine)."""
    capas = _qml("reglas_desmarcada_simbolo_raro.qml")
    _igual(fallos, [c.nombre for c in capas], [u"Rios", u"Resto"], u"reglas")


def test_opacidad(fallos):
    """QGIS 3.44.12: <layerOpacity> se lee tambien por el camino .qml."""
    _igual(fallos, _qml("poligono_opacidad_50.qml")[0].opacidad, 0.5,
           u"opacidad de capa")


def test_angulo_escalas(fallos):
    """QGIS 3.44.12: el modelo guarda el angulo de QGIS (horario); el cambio
    de sentido lo hace el emisor, no el parser."""
    capa = _qml("punto_angulo_escalas.qml")[0]
    _igual(fallos, capa.escala_min, 50000.0, u"escala minima")
    _igual(fallos, capa.escala_max, 1000.0, u"escala maxima")
    simbolo = capa.renderer.simbolo
    if not isinstance(simbolo, SimboloMarcador):
        fallos.append(u"se esperaba SimboloMarcador: %r" % simbolo)
        return
    _igual(fallos, simbolo.angulo, 45.0, u"angulo")
    _igual(fallos, simbolo.forma, u"cuadrado", u"forma")


def test_marcador_glifo(fallos):
    """QGIS 3.44.12: triangulo y estrella -> glifo de ESRI Default Marker."""
    capa = _qml("puntos_triangulo_estrella.qml")[0]
    if not isinstance(capa.renderer, RendererValoresUnicos):
        fallos.append(u"se esperaba categorizado: %r" % capa.renderer)
        return
    por_valor = dict((c.valor, c.simbolo) for c in capa.renderer.clases)
    tri, est = por_valor.get(u"hito"), por_valor.get(u"vertice")
    for s, que in ((tri, u"triangulo"), (est, u"estrella")):
        if not isinstance(s, SimboloMarcadorCaracter):
            fallos.append(u"%s: se esperaba SimboloMarcadorCaracter, es %r"
                          % (que, s))
            return
    _igual(fallos, tri.char_relleno, 35, u"glifo del triangulo")
    _cerca(fallos, tri.size_pt, 4 * MM2PT / 0.615, u"tamanyo de fuente")
    _cerca(fallos, tri.contorno_pt, 0.4 * MM2PT, u"grosor del borde")
    _igual(fallos, tri.contorno_rgb, (0, 0, 0), u"color del borde")
    _igual(fallos, tri.angulo, 30.0, u"angulo")
    _igual(fallos, est.char_relleno, 94, u"glifo de la estrella")
    _igual(fallos, est.contorno_rgb, None, u"estrella sin borde")
    if not any(u"ESRI Default Marker" in a for a in capa.avisos):
        fallos.append(u"falta el aviso del glifo: %r" % capa.avisos)


def test_hexagono_equilatero(fallos):
    """QGIS 3.44.12: el hexagono lleva +30 grados (QGIS lo dibuja con un
    vertice arriba, el glifo 37 con un lado) y el equilatero su propio factor
    de tamanyo. Ambos medidos por render el 2026-09-24."""
    capa = _qml("puntos_hexagono_equilatero.qml")[0]
    por_valor = dict((c.valor, c.simbolo) for c in capa.renderer.clases)
    hexa, equi = por_valor.get(u"hito"), por_valor.get(u"vertice")
    _igual(fallos, getattr(hexa, "char_relleno", None), 37, u"glifo hexagono")
    _igual(fallos, getattr(hexa, "angulo", None), 30.0, u"giro del hexagono")
    _igual(fallos, getattr(equi, "char_relleno", None), 35, u"glifo equilatero")
    _cerca(fallos, getattr(equi, "size_pt", None), 5 * MM2PT / 0.714,
           u"tamanyo de fuente del equilatero")


def test_categoria_oculta_no_soportada(fallos):
    """QGIS 3.44.12: una categoria oculta con un simbolo sin equivalente
    (arrow) no tumba la capa: su simbolo ni se parsea."""
    try:
        capa = _qml("categoria_oculta_no_soportada.qml")[0]
    except SimbologiaNoSoportada as e:
        fallos.append(u"la categoria oculta tumba la capa: %s" % unicode(e))
        return
    _igual(fallos, [c.valor for c in capa.renderer.clases], [u"hito"],
           u"categorias emitidas")


def test_avisos_por_regla(fallos):
    """QGIS 3.44.12: el aviso del simbolo de una regla (la estrella por
    glifo) va solo en el .lyr de esa regla, no en los de las demas."""
    capas = dict((c.nombre, c) for c in _qml("reglas_avisos_por_regla.qml"))
    _igual(fallos, sorted(capas), [u"Hitos", u"Resto"], u"reglas")
    glifo = lambda c: any(u"ESRI Default Marker" in a for a in c.avisos)
    if u"Resto" in capas and not glifo(capas[u"Resto"]):
        fallos.append(u"'Resto' (estrella) deberia avisar del glifo")
    if u"Hitos" in capas and glifo(capas[u"Hitos"]):
        fallos.append(u"'Hitos' (circulo) hereda el aviso de la estrella: %r"
                      % capas[u"Hitos"].avisos)


def test_forma_sin_equivalente(fallos):
    """Una forma sin SimpleMarker ni glifo (arrow) se rechaza con mensaje."""
    import xml.etree.ElementTree as ET
    symbol = ET.fromstring(
        '<symbol type="marker" name="0" alpha="1"><layer class="SimpleMarker" '
        'enabled="1"><Option type="Map">'
        '<Option type="QString" name="name" value="arrow"/>'
        '<Option type="QString" name="color" value="255,0,0,255"/>'
        '<Option type="QString" name="outline_style" value="no"/>'
        '</Option></layer></symbol>')
    try:
        parser_qgis._simbolo_desde_symbol(symbol, [])
        fallos.append(u"arrow deberia rechazarse")
    except SimbologiaNoSoportada as e:
        if u"arrow" not in unicode(e):
            fallos.append(u"el mensaje no nombra la forma: %s" % unicode(e))


def test_batch_qgz(fallos):
    """QGIS 3.44.12: las 5 capas del .qgz sintetico, sin tocar ningun dato."""
    raiz = parser_qgis._raiz_qgs(QGZ_BATCH)
    resultado = {}
    for ml in raiz.iter("maplayer"):
        nombre = ml.findtext("layername")
        try:
            resultado[nombre] = parser_qgis.parse_maplayer(ml)
        except SimbologiaNoSoportada as e:
            resultado[nombre] = e
    _igual(fallos, sorted(resultado), [u"Hitos flecha", u"Paleta",
                                       u"Solo rios", u"Zonas GPKG",
                                       u"Zonas por tipo"], u"capas del .qgz")
    if not isinstance(resultado.get(u"Hitos flecha"), SimbologiaNoSoportada):
        fallos.append(u"'Hitos flecha' deberia fallar: %r"
                      % resultado.get(u"Hitos flecha"))
    rios = resultado.get(u"Solo rios")
    if isinstance(rios, list):
        _igual(fallos, rios[0].defquery, u"\"TIPO\" = 'rio'",
               u"def-query por |subset=")
        _igual(fallos, rios[0].datasource.replace(u"\\", u"/"),
               u"../../tmp/regresion_qml/lineas.shp", u"ruta relativa")
    gpkg = resultado.get(u"Zonas GPKG")
    if isinstance(gpkg, list):
        if not gpkg[0].datasource.endswith(u"zonas.gpkg\\main.zonas"):
            fallos.append(u"GeoPackage mal resuelto: %s" % gpkg[0].datasource)
    zonas = resultado.get(u"Zonas por tipo")
    if isinstance(zonas, list):
        _igual(fallos, zonas[0].opacidad, 0.5, u"opacidad de 'Zonas por tipo'")


def test_datasource_y_campos(fallos):
    """Resolucion de rutas multicapa y nombres de campo unicode."""
    _igual(fallos, parser_qgis._campo(u'"Año"'), u"Año", u"campo con enye")
    ruta, defquery = parser_qgis._partir_datasource(
        u"C:\\x\\y.gpkg|layername=zonas|subset=\"TIPO\" = 'A'")
    _igual(fallos, ruta, u"C:\\x\\y.gpkg\\main.zonas", u"ruta de GeoPackage")
    _igual(fallos, defquery, u"\"TIPO\" = 'A'", u"subset")
    ruta, defquery = parser_qgis._partir_datasource(
        u"C:\\x\\y.shp|subset=\"A\" = 'x|y'")
    _igual(fallos, defquery, u"\"A\" = 'x|y'", u"| dentro de un literal")


def test_remap(fallos):
    """Reglas de --remap: prefijo con frontera de separador y sin mayusculas."""
    regla = parser_qgis.parse_remap(u"Z:=L:\\Mi unidad\\Carto\\")
    _igual(fallos, regla, (u"Z:", u"L:\\Mi unidad\\Carto"), u"regla")
    _igual(fallos, parser_qgis.parse_remap(u"z:/=L:/Carto"),
           (u"z:", u"L:\\Carto"), u"regla con barras de QGIS")
    _igual(fallos, parser_qgis.remapear(u"Z:\\LiDAR\\a.tif", [regla]),
           (u"L:\\Mi unidad\\Carto\\LiDAR\\a.tif", regla), u"ruta remapeada")
    _igual(fallos, parser_qgis.remapear(u"z:/LiDAR/a.tif", [regla])[0],
           u"L:\\Mi unidad\\Carto\\LiDAR\\a.tif", u"minusculas y barras /")
    otra = parser_qgis.parse_remap(u"C:\\datos=D:\\datos")
    _igual(fallos, parser_qgis.remapear(u"C:\\datos_viejos\\x.shp", [otra]),
           (u"C:\\datos_viejos\\x.shp", None), u"prefijo sin frontera")
    _igual(fallos, parser_qgis.remapear(u"X:\\a.shp", [regla, otra]),
           (u"X:\\a.shp", None), u"ninguna regla casa")
    for mala in (u"Z:", u"=L:\\x", u"Z:="):
        try:
            parser_qgis.parse_remap(mala)
            fallos.append(u"regla mal formada aceptada: %r" % mala)
        except ValueError:
            pass
    capas = parser_qgis._raiz_qgs(QGZ_REMAP).iter("maplayer")
    fuentes = sorted(parser_qgis.parse_maplayer(ml)[0].datasource
                     for ml in capas)
    _igual(fallos, fuentes, [u"Q:/paleta.tif", u"Q:/poligonos.shp",
                             u"Q:/zonas.gpkg\\main.zonas"],
           u"datasources del fixture de --remap")


TESTS = [(n, f) for n, f in sorted(globals().items())
         if n.startswith("test_") and callable(f)]


def main():
    malos = 0
    for nombre, funcion in TESTS:
        fallos = []
        try:
            funcion(fallos)
        except Exception as e:
            fallos.append(u"excepcion: %r" % (e,))
        print("%-5s %s" % ("PASS" if not fallos else "FAIL", nombre))
        for f in fallos:
            print(("      " + f).encode("utf-8"))
        malos += bool(fallos)
    print("\nTOTAL: %d/%d PASS" % (len(TESTS) - malos, len(TESTS)))
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main())
