# -*- coding: utf-8 -*-
"""Regresion del camino del PLUGIN: .qml -> emisor.py (SUBPROCESO) -> .lyr.

La regresion contra proyectos reales ejercitaba solo el camino batch/.qgz
(`parse_maplayer` + `emitir`). El camino que usa de verdad el plugin -- `parse_qml` + `emitir_qml`,
y sobre todo el CONTRATO del subproceso -- no tenia ningun test, y justo ahi
vivian tres fallos: la def-query se perdia, la opacidad de capa se perdia y un
argumento con tilde reventaba el JSON de salida DESPUES de escribir el .lyr.

Aqui `emisor.py` se lanza como proceso hijo de verdad, en sus DOS modos (el
`--args-json` que usa el plugin y el posicional clasico), sobre datos
sinteticos creados con arcpy, y el resultado se verifica con `lyr_dump`.

    C:\\Python27\\ArcGIS10.5\\python.exe run_regresion_qml.py [nombre_caso ...]

Sin argumentos corre todos los casos. No usa datos externos: los
datos sinteticos y las salidas viven en `tmp/` y `out/`, ambos en .gitignore.
"""
import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(RAIZ, "src")
sys.path.insert(0, SRC)

import lyr_dump
import parser_qgis

EMISOR = os.path.join(SRC, "emisor.py")
DIR_QML = os.path.join(RAIZ, "tests", "fixtures", "qml")
DIR_DATOS = os.path.join(RAIZ, "tmp", "regresion_qml")
DIR_OUT = os.path.join(RAIZ, "out", "qml")

SHP_POLIGONOS = os.path.join(DIR_DATOS, "poligonos.shp")
SHP_LINEAS = os.path.join(DIR_DATOS, "lineas.shp")
SHP_PUNTOS = os.path.join(DIR_DATOS, "puntos.shp")
RASTER = os.path.join(DIR_DATOS, "paleta.tif")
GPKG = os.path.join(DIR_DATOS, "zonas.gpkg")
GPKG_CAPA = GPKG + u"\\main.zonas"

# Nombre y ruta con tilde: es lo que reventaba el contrato del subproceso.
NOMBRE_TILDE = u"Vías pecuarias"
# Ω no existe en cp1252: solo puede viajar por el fichero de argumentos.
NOMBRE_EXOTICO = u"Vías pecuarias Ω"


# --------------------------------------------------------------------- datos
def _preparar_datos():
    """Datos sinteticos con arcpy. Se crean una vez y se reutilizan."""
    import arcpy
    arcpy.env.overwriteOutput = True
    if not os.path.isdir(DIR_DATOS):
        os.makedirs(DIR_DATOS)
    sr = arcpy.SpatialReference(25830)  # ETRS89 / UTM 30N

    if not arcpy.Exists(SHP_POLIGONOS):
        arcpy.CreateFeatureclass_management(DIR_DATOS, "poligonos.shp",
                                            "POLYGON", spatial_reference=sr)
        arcpy.AddField_management(SHP_POLIGONOS, "TIPO", "TEXT",
                                  field_length=20)
        cur = arcpy.da.InsertCursor(SHP_POLIGONOS, ["SHAPE@", "TIPO"])
        for i, tipo in enumerate([u"A", u"B"]):
            x, y = 600000 + i * 200, 4200000
            anillo = arcpy.Array([arcpy.Point(x, y), arcpy.Point(x + 100, y),
                                  arcpy.Point(x + 100, y + 100),
                                  arcpy.Point(x, y + 100), arcpy.Point(x, y)])
            cur.insertRow([arcpy.Polygon(anillo, sr), tipo])
        del cur

    if not arcpy.Exists(SHP_LINEAS):
        arcpy.CreateFeatureclass_management(DIR_DATOS, "lineas.shp",
                                            "POLYLINE", spatial_reference=sr)
        arcpy.AddField_management(SHP_LINEAS, "TIPO", "TEXT", field_length=20)
        cur = arcpy.da.InsertCursor(SHP_LINEAS, ["SHAPE@", "TIPO"])
        for i, tipo in enumerate([u"rio", u"rambla", u"acequia"]):
            puntos = arcpy.Array([arcpy.Point(600000 + i * 100, 4200000),
                                  arcpy.Point(600100 + i * 100, 4200100)])
            cur.insertRow([arcpy.Polyline(puntos, sr), tipo])
        del cur

    if not arcpy.Exists(SHP_PUNTOS):
        arcpy.CreateFeatureclass_management(DIR_DATOS, "puntos.shp", "POINT",
                                            spatial_reference=sr)
        arcpy.AddField_management(SHP_PUNTOS, "TIPO", "TEXT", field_length=20)
        cur = arcpy.da.InsertCursor(SHP_PUNTOS, ["SHAPE@", "TIPO"])
        for i, tipo in enumerate([u"hito", u"vertice"]):
            cur.insertRow([arcpy.Point(600000 + i * 50, 4200000), tipo])
        del cur

    if not arcpy.Exists(RASTER):
        import numpy
        arr = numpy.array([[0, 1, 2], [1, 2, 0], [2, 0, 1]], dtype="int32")
        ras = arcpy.NumPyArrayToRaster(arr, arcpy.Point(600000, 4200000),
                                       10, 10)
        ras.save(RASTER)
        arcpy.DefineProjection_management(RASTER, sr)
        arcpy.CalculateStatistics_management(RASTER)

    if not os.path.exists(GPKG):
        # GeoPackage sintetico: es el contenedor multicapa que el plugin
        # resuelve a `ruta.gpkg\main.<capa>`.
        arcpy.CreateSQLiteDatabase_management(GPKG, "GEOPACKAGE")
        arcpy.FeatureClassToFeatureClass_conversion(SHP_POLIGONOS, GPKG,
                                                    "zonas")


# ------------------------------------------------------------------ utillaje
def _arg_como_windows(arg):
    """Argumento tal y como lo recibe un py2.7 lanzado desde el plugin (py3).

    El plugin es Python 3 y pasa `str`; Windows se lo entrega al hijo py2.7 en
    BYTES de la codepage ANSI. El `subprocess` de py2.7 no sabe pasar unicode
    (intenta codificar la linea de comandos en ascii y revienta), asi que aqui
    se hace a mano esa misma conversion y el hijo ve exactamente los mismos
    bytes que veria lanzado desde QGIS."""
    if isinstance(arg, unicode):
        return arg.encode(sys.getfilesystemencoding() or "mbcs")
    return arg


def _lanzar(argv):
    """Lanza emisor.py como SUBPROCESO -> (returncode, stdout, stderr) bytes."""
    cmd = [sys.executable, EMISOR] + [_arg_como_windows(a) for a in argv]
    proc = subprocess.Popen(cmd, cwd=SRC, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    salida, error = proc.communicate()
    return proc.returncode, salida, error


def _json_estricto(salida, fallos):
    """stdout -> dict. El decode es ESTRICTO a proposito: el fallo original
    escupia bytes cp1252 por un stdout que el plugin lee como utf-8."""
    try:
        texto = salida.decode("utf-8")
    except UnicodeDecodeError as e:
        fallos.append(u"stdout no es utf-8 valido: %s" % e)
        return None
    try:
        return json.loads(texto)
    except ValueError as e:
        fallos.append(u"stdout no es un JSON valido (%s): %r" % (e, texto[:300]))
        return None


def _escribir_args(nombre_fichero, args):
    """Fichero de argumentos UTF-8 para `emisor.py --args-json`."""
    ruta = os.path.join(DIR_OUT, nombre_fichero)
    f = open(ruta, "wb")
    try:
        f.write(json.dumps(args, ensure_ascii=False).encode("utf-8"))
    finally:
        f.close()
    return ruta


def _igual(fallos, obtenido, esperado, que):
    if obtenido != esperado:
        fallos.append(u"%s: esperado %r, obtenido %r" % (que, esperado, obtenido))


def _salida(nombre):
    return os.path.join(DIR_OUT, nombre)


# --------------------------------------------------------------------- casos
def caso_defquery_args_json(fallos):
    """(1) La def-query de la capa viva llega al .lyr por --args-json."""
    lyr = _salida(u"defquery_json.lyr")
    args = _escribir_args("args_defquery.json", {
        "qml": os.path.join(DIR_QML, "poligono_simple.qml"),
        "dato": SHP_POLIGONOS, "salida": lyr,
        "nombre": u"Zonas A", "defquery": u"TIPO = 'A'"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    _igual(fallos, datos.get("ok"), True, u"ok del JSON")
    volcado = lyr_dump.dump_lyr(lyr)
    _igual(fallos, volcado.get("defquery"), u"TIPO = 'A'", u"def-query del .lyr")
    _igual(fallos, volcado.get("nombre"), u"Zonas A", u"nombre del .lyr")


def caso_defquery_posicional(fallos):
    """(1bis) Lo mismo por el modo posicional clasico (--defquery)."""
    lyr = _salida(u"defquery_pos.lyr")
    rc, out, err = _lanzar([os.path.join(DIR_QML, "poligono_simple.qml"),
                            SHP_POLIGONOS, lyr,
                            u"--nombre", u"Zonas A",
                            u"--defquery", u"TIPO = 'A'"])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    _igual(fallos, datos.get("ok"), True, u"ok del JSON")
    volcado = lyr_dump.dump_lyr(lyr)
    _igual(fallos, volcado.get("defquery"), u"TIPO = 'A'", u"def-query del .lyr")


def caso_opacidad_capa(fallos):
    """(2) <layerOpacity>0.5</layerOpacity> del .qml -> transparencia 50."""
    lyr = _salida(u"opacidad.lyr")
    args = _escribir_args("args_opacidad.json", {
        "qml": os.path.join(DIR_QML, "poligono_opacidad_50.qml"),
        "dato": SHP_POLIGONOS, "salida": lyr, "nombre": u"Opaca a medias"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    volcado = lyr_dump.dump_lyr(lyr)
    _igual(fallos, volcado.get("transparencia_pct"), 50,
           u"transparencia del .lyr")


def caso_tilde_posicional(fallos):
    """(3) Nombre y ruta con tilde por el modo posicional: JSON valido y
    exit 0. Antes reventaba con UnicodeDecodeError tras escribir el .lyr."""
    lyr = _salida(u"salida_ñandú.lyr")
    rc, out, err = _lanzar([os.path.join(DIR_QML, "poligono_simple.qml"),
                            SHP_POLIGONOS, lyr, u"--nombre", NOMBRE_TILDE])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        fallos.append(u"stderr del emisor: %s" % err.decode("utf-8", "replace")[:400])
        return
    _igual(fallos, datos.get("ok"), True, u"ok del JSON")
    capas = datos.get("capas") or [{}]
    _igual(fallos, capas[0].get("nombre"), NOMBRE_TILDE, u"nombre en el JSON")
    _igual(fallos, capas[0].get("salida"), lyr, u"ruta de salida en el JSON")
    if not os.path.exists(lyr):
        fallos.append(u"no se escribio %s" % lyr)
        return
    volcado = lyr_dump.dump_lyr(lyr)
    _igual(fallos, volcado.get("nombre"), NOMBRE_TILDE, u"nombre del .lyr")


def caso_tilde_args_json(fallos):
    """(3bis) Igual por --args-json, ademas con un caracter fuera de cp1252
    (Ω), que por la linea de comandos no podria viajar."""
    lyr = _salida(u"salida_ñandú_json.lyr")
    args = _escribir_args("args_tilde.json", {
        "qml": os.path.join(DIR_QML, "poligono_simple.qml"),
        "dato": SHP_POLIGONOS, "salida": lyr, "nombre": NOMBRE_EXOTICO})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        fallos.append(u"stderr del emisor: %s" % err.decode("utf-8", "replace")[:400])
        return
    volcado = lyr_dump.dump_lyr(lyr)
    _igual(fallos, volcado.get("nombre"), NOMBRE_EXOTICO, u"nombre del .lyr")


def caso_raster_alfa0(fallos):
    """(4) Clase paletada con alfa 0 -> simbolo nulo (no opaco)."""
    lyr = _salida(u"raster_alfa0.lyr")
    args = _escribir_args("args_raster.json", {
        "qml": os.path.join(DIR_QML, "raster_paleta_alfa0.qml"),
        "dato": RASTER, "salida": lyr, "nombre": u"Paleta con clase invisible"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    volcado = lyr_dump.dump_lyr(lyr)
    rend = volcado.get("renderer") or {}
    _igual(fallos, rend.get("tipo"), "raster_valores_unicos", u"tipo de renderer")
    # Se indexa por etiqueta: los valores vuelven del renderer raster como
    # numeros (0.0, 1.0...), no como el texto del .qml.
    por_label = dict((c.get("label"), c) for c in rend.get("clases", []))
    for label, nulo_esperado in ((u"cero (invisible)", True), (u"uno", False),
                                 (u"dos", False)):
        clase = por_label.get(label)
        if clase is None:
            fallos.append(u"falta la clase '%s' (hay: %s)"
                          % (label, u", ".join(sorted(por_label))))
            continue
        color = (clase.get("simbolo") or {}).get("color") or {}
        _igual(fallos, bool(color.get("nulo")), nulo_esperado,
               u"color nulo de la clase '%s'" % label)


def caso_regla_desmarcada(fallos):
    """(5) Regla con checkstate="0": ni .lyr propio ni presencia en el ELSE."""
    base = _salida(u"reglas.lyr")
    args = _escribir_args("args_reglas.json", {
        "qml": os.path.join(DIR_QML, "reglas_con_desmarcada.qml"),
        "dato": SHP_LINEAS, "salida": base, "nombre": u"Red hidrografica"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    capas = datos.get("capas") or []
    _igual(fallos, [c.get("nombre") for c in capas], [u"Rios", u"Resto"],
           u"capas emitidas")
    lyr_ramblas = _salida(u"reglas_Ramblas.lyr")
    if os.path.exists(lyr_ramblas):
        fallos.append(u"se emitio la regla desmarcada: %s" % lyr_ramblas)
    lyr_resto = _salida(u"reglas_Resto.lyr")
    if not os.path.exists(lyr_resto):
        fallos.append(u"no se emitio el ELSE: %s" % lyr_resto)
        return
    volcado = lyr_dump.dump_lyr(lyr_resto)
    # El ELSE solo puede negar los filtros de las reglas que SI se dibujan.
    _igual(fallos, volcado.get("defquery"),
           u'NOT (("TIPO" = \'rio\')) OR "TIPO" IS NULL',
           u"def-query del ELSE")
    avisos = u" | ".join(a for c in capas for a in c.get("avisos", []))
    for trozo in (u"desmarcada", u"scalemindenom"):
        if trozo not in avisos:
            fallos.append(u"falta el aviso que menciona '%s' (avisos: %s)"
                          % (trozo, avisos))


def caso_dash_dot(fallos):
    """(6) line_style="dash dot" -> esriSLSDashDot."""
    lyr = _salida(u"dash_dot.lyr")
    args = _escribir_args("args_dashdot.json", {
        "qml": os.path.join(DIR_QML, "linea_dash_dot.qml"),
        "dato": SHP_LINEAS, "salida": lyr, "nombre": u"Trazo dash dot"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    volcado = lyr_dump.dump_lyr(lyr)
    simbolo = ((volcado.get("renderer") or {}).get("simbolo")) or {}
    _igual(fallos, simbolo.get("estilo"), "dashdot", u"estilo de la linea")


def caso_geopackage(fallos):
    """(7) Una capa de GeoPackage (`x.gpkg\\main.<capa>`) se emite igual.

    Respalda la decision de soportar GPKG en vez de rechazarlo: arcpy 10.5 SI
    la abre por esa ruta (verificado el 2026-09-20)."""
    lyr = _salida(u"gpkg.lyr")
    args = _escribir_args("args_gpkg.json", {
        "qml": os.path.join(DIR_QML, "poligono_simple.qml"),
        "dato": GPKG_CAPA, "salida": lyr, "nombre": u"Zonas GPKG",
        "defquery": u"TIPO = 'A'"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        fallos.append(u"stderr del emisor: %s" % err.decode("utf-8", "replace")[:400])
        return
    _igual(fallos, datos.get("ok"), True, u"ok del JSON")
    volcado = lyr_dump.dump_lyr(lyr)
    _igual(fallos, volcado.get("defquery"), u"TIPO = 'A'", u"def-query del .lyr")


def caso_angulo_escalas(fallos):
    """(9) Marcador rotado 45 deg + visibilidad por escala -> viajan al .lyr.

    Hasta 2026-09-21 el emisor SABIA trasladar las dos cosas y `lyr_dump`
    volcarlas, pero NINGUN fixture las ejercitaba: cero apariciones de
    `angulo` y `escala_min/max` en los 14 golden del batch y en las salidas
    del camino .qml. Codigo nuevo sin una sola comparacion de punta a punta.

    El .qml lo escribio QGIS 3.44.12 de verdad (`saveNamedStyle`), como todos
    los fixtures desde el 2026-09-24.
    """
    lyr = _salida(u"angulo_escalas.lyr")
    args = _escribir_args("args_angulo.json", {
        "qml": os.path.join(DIR_QML, "punto_angulo_escalas.qml"),
        "dato": SHP_PUNTOS, "salida": lyr, "nombre": u"Hitos rotados"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    volcado = lyr_dump.dump_lyr(lyr)
    # Convencion: son DENOMINADORES. QGIS minScale (limite alejado) ->
    # ArcMap MinimumScale; QGIS maxScale (limite acercado) -> MaximumScale.
    _igual(fallos, volcado.get("escala_min"), 50000.0, u"escala minima")
    _igual(fallos, volcado.get("escala_max"), 1000.0, u"escala maxima")
    renderer = volcado.get("renderer", {})
    clases = renderer.get("clases")
    # Renderer simple: el simbolo cuelga del renderer. Categorizado/graduado:
    # de cada clase.
    simbolo = (clases[0]["simbolo"] if clases else renderer.get("simbolo")) or {}
    # QGIS gira en sentido HORARIO y ArcMap en ANTIHORARIO (render del
    # 2026-09-24): 45 de QGIS son 315 de ArcMap. Hasta ese dia se esperaba 45
    # y el test pasaba porque un cuadrado a 45 se ve igual en los dos sentidos.
    _igual(fallos, simbolo.get("angulo"), 315.0, u"angulo del marcador")
    _igual(fallos, simbolo.get("estilo"), u"cuadrado", u"forma del marcador")


def caso_marcador_glifo(fallos):
    """(12) Triangulo y estrella -> glifo de la fuente ESRI Default Marker.

    SimpleMarkerSymbol de ArcMap solo tiene 5 formas; el triangulo tumbaba 2
    de las 28 capas de un lote real (2026-08-17). Se traducen a
    CharacterMarkerSymbol, y el borde a HALO de un MultiLayerMarkerSymbol
    (IMask no lo expone el de caracter). Verificado por render ArcMap vs QGIS
    el 2026-09-24: forma, giro, borde y tamanyo (~90-105 %).

    Fixture escrito por QGIS 3.44.12 (`tests/generar_fixtures_qgis.py`).
    """
    lyr = _salida(u"glifos.lyr")
    args = _escribir_args("args_glifos.json", {
        "qml": os.path.join(DIR_QML, "puntos_triangulo_estrella.qml"),
        "dato": SHP_PUNTOS, "salida": lyr, "nombre": u"Puntos glifo"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    avisos = u" | ".join(a for c in datos.get("capas") or []
                         for a in c.get("avisos", []))
    if u"ESRI Default Marker" not in avisos:
        fallos.append(u"falta el aviso del glifo (avisos: %s)" % avisos)
    clases = dict((c.get("valor"), c.get("simbolo") or {}) for c in
                  (lyr_dump.dump_lyr(lyr).get("renderer") or {}).get("clases", []))

    hito = clases.get(u"hito") or {}
    _igual(fallos, hito.get("tipo"), u"MultiLayerMarker", u"tipo del triangulo")
    _igual(fallos, (hito.get("halo") or {}).get("color", {}).get("rgb"),
           [0, 0, 0], u"color del halo (borde) del triangulo")
    _igual(fallos, (hito.get("halo") or {}).get("tamanyo_pt"), 1.134,
           u"grosor del halo: 0,4 mm")
    glifo = (hito.get("capas") or [{}])[0]
    _igual(fallos, glifo.get("fuente"), u"ESRI Default Marker", u"fuente")
    _igual(fallos, glifo.get("caracter"), 35, u"glifo del triangulo")
    _igual(fallos, glifo.get("angulo"), 330.0,
           u"giro del triangulo (30 horario en QGIS)")
    _igual(fallos, (glifo.get("color") or {}).get("rgb"), [255, 127, 0],
           u"color del triangulo")

    _igual(fallos, glifo.get("tamanyo_pt"), round(4 * 2.834645669 / 0.615, 3),
           u"tamanyo de fuente del triangulo (4 mm / lado del glifo)")

    estrella = clases.get(u"vertice") or {}
    _igual(fallos, estrella.get("tipo"), u"CharacterMarker",
           u"tipo de la estrella (sin borde: sin multicapa)")
    _igual(fallos, estrella.get("caracter"), 94, u"glifo de la estrella")


def caso_hexagono_equilatero(fallos):
    """(13) Hexagono con giro extra de 30 y equilatero con su factor.

    Lo encontro el verificador el 2026-09-24: el glifo 37 tiene un LADO arriba
    y el hexagono de QGIS un VERTICE, asi que salia girado 30 grados; y el
    equilatero salia un 16-20 % grande. Corregido y medido por render (51x58
    frente a 52x58 px; 49x44 frente a 50x44). Fixture de QGIS 3.44.12.
    """
    lyr = _salida(u"glifos2.lyr")
    args = _escribir_args("args_glifos2.json", {
        "qml": os.path.join(DIR_QML, "puntos_hexagono_equilatero.qml"),
        "dato": SHP_PUNTOS, "salida": lyr, "nombre": u"Puntos glifo 2"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    clases = dict((c.get("valor"), c.get("simbolo") or {}) for c in
                  (lyr_dump.dump_lyr(lyr).get("renderer") or {}).get("clases", []))
    hexa = clases.get(u"hito") or {}
    _igual(fallos, hexa.get("caracter"), 37, u"glifo del hexagono")
    # 30 en sentido QGIS (horario) -> 330 en ArcMap (antihorario).
    _igual(fallos, hexa.get("angulo"), 330.0, u"giro del hexagono")
    equi = clases.get(u"vertice") or {}
    _igual(fallos, equi.get("tamanyo_pt"), round(5 * 2.834645669 / 0.714, 3),
           u"tamanyo de fuente del equilatero")


def caso_categoria_oculta(fallos):
    """(14) Categoria oculta con simbolo sin equivalente: la capa sale.

    Mismo fallo que la regla desmarcada, en el categorizado (y el graduado):
    se parseaban todos los simbolos antes de saltar las clases ocultas.
    Encontrado por el verificador el 2026-09-24. Fixture de QGIS 3.44.12.
    """
    lyr = _salida(u"categoria_oculta.lyr")
    args = _escribir_args("args_cat_oculta.json", {
        "qml": os.path.join(DIR_QML, "categoria_oculta_no_soportada.qml"),
        "dato": SHP_PUNTOS, "salida": lyr, "nombre": u"Con oculta"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    _igual(fallos, datos.get("ok"), True, u"ok del JSON")
    if os.path.exists(lyr):
        clases = (lyr_dump.dump_lyr(lyr).get("renderer") or {}).get("clases", [])
        _igual(fallos, [c.get("valor") for c in clases], [u"hito"],
               u"categorias del .lyr")


def caso_regla_desmarcada_simbolo_raro(fallos):
    """(10) Una regla DESMARCADA con un simbolo NO soportado no tumba la capa.

    Hasta 2026-09-24 `_capas_desde_reglas` parseaba el simbolo de todas las
    reglas antes de descartar las desmarcadas: un MarkerLine en una regla que
    QGIS ni dibuja hacia saltar `SimbologiaNoSoportada` y se perdia la capa.

    Fixture escrito por QGIS 3.44.12 (`saveNamedStyle`), generado con
    `tests/generar_fixtures_qgis.py`: no esta hecho a mano.
    """
    base = _salida(u"reglas_raro.lyr")
    args = _escribir_args("args_reglas_raro.json", {
        "qml": os.path.join(DIR_QML, "reglas_desmarcada_simbolo_raro.qml"),
        "dato": SHP_LINEAS, "salida": base, "nombre": u"Red hidrografica"})
    rc, out, err = _lanzar([u"--args-json", args])
    datos = _json_estricto(out, fallos)
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        return
    _igual(fallos, datos.get("error"), None, u"error del JSON")
    capas = datos.get("capas") or []
    _igual(fallos, [c.get("nombre") for c in capas], [u"Rios", u"Resto"],
           u"capas emitidas")
    _igual(fallos, [c.get("ok") for c in capas], [True, True], u"ok por capa")
    if os.path.exists(_salida(u"reglas_raro_Ramblas.lyr")):
        fallos.append(u"se emitio la regla desmarcada")


# Batch sintetico: el .qgz lo escribio QGIS 3.44.12 con rutas RELATIVAS a los
# datos de `tmp/regresion_qml/` (`tests/generar_fixtures_qgis.py`).
QGZ_BATCH = os.path.join(RAIZ, "tests", "fixtures", "batch_sintetico.qgz")
DIR_OUT_BATCH = os.path.join(DIR_OUT, "batch")


def caso_batch_sintetico(fallos):
    """(11) Modo --batch de punta a punta, SIN datos externos.

    La regresion contra proyectos reales prueba el batch, pero necesita sus
    datos: sin ellos no hay suite. Este caso caracteriza el
    lote sobre datos sinteticos: 4 capas que salen (categorizado con
    opacidad, def-query por `|subset=`, raster paletado y GeoPackage por
    `|layername=`) y 1 que falla (marcador flecha) SIN tumbar el lote.
    """
    import shutil
    if os.path.isdir(DIR_OUT_BATCH):
        shutil.rmtree(DIR_OUT_BATCH)
    rc, out, err = _lanzar([u"--batch", QGZ_BATCH, DIR_OUT_BATCH])
    datos = _json_estricto(out, fallos)
    # El batch devuelve exit 0 y ok=True aunque falle alguna capa: el
    # fallo va por capa (avisar-y-saltar).
    _igual(fallos, rc, 0, u"codigo de salida")
    if datos is None:
        fallos.append(u"stderr del emisor: %s" % err.decode("utf-8", "replace")[:400])
        return
    _igual(fallos, datos.get("resumen"), {u"ok": 4, u"error": 1, u"total": 5},
           u"resumen del lote")
    por_nombre = dict((c.get("nombre"), c) for c in datos.get("capas") or [])

    hitos = por_nombre.get(u"Hitos flecha") or {}
    _igual(fallos, hitos.get("ok"), False, u"ok de la capa no soportada")
    _igual(fallos, hitos.get("tipo_error"), u"SimbologiaNoSoportada",
           u"tipo de error de la capa no soportada")
    if u"arrow" not in (hitos.get("error") or u""):
        fallos.append(u"el error no nombra la forma: %r" % hitos.get("error"))

    def _volcado(nombre):
        capa = por_nombre.get(nombre) or {}
        if not capa.get("ok"):
            fallos.append(u"la capa '%s' no salio: %r" % (nombre, capa))
            return None
        return lyr_dump.dump_lyr(capa["salida"])

    zonas = _volcado(u"Zonas por tipo")
    if zonas:
        _igual(fallos, zonas.get("transparencia_pct"), 50,
               u"transparencia de 'Zonas por tipo'")
        rend = zonas.get("renderer") or {}
        _igual(fallos, rend.get("tipo"), "valores_unicos",
               u"renderer de 'Zonas por tipo'")
        _igual(fallos, sorted(c.get("valor") for c in rend.get("clases", [])),
               [u"A", u"B"], u"clases de 'Zonas por tipo'")

    rios = _volcado(u"Solo rios")
    if rios:
        _igual(fallos, rios.get("defquery"), u"\"TIPO\" = 'rio'",
               u"def-query de 'Solo rios'")
        simbolo = (rios.get("renderer") or {}).get("simbolo") or {}
        _igual(fallos, simbolo.get("estilo"), "dash", u"trazo de 'Solo rios'")

    paleta = _volcado(u"Paleta")
    if paleta:
        rend = paleta.get("renderer") or {}
        _igual(fallos, rend.get("tipo"), "raster_valores_unicos",
               u"renderer de 'Paleta'")
        _igual(fallos, sorted(c.get("label") for c in rend.get("clases", [])),
               [u"cero", u"dos", u"uno"], u"clases de 'Paleta'")

    _volcado(u"Zonas GPKG")


def caso_parser_sin_arcobjects(fallos):
    """(8) Lo que se puede comprobar sin ArcObjects: campos unicode, mensajes
    neutros y resolucion de rutas multicapa."""
    _igual(fallos, parser_qgis._campo(u'"Año"'), u"Año", u"campo con enye/tilde")
    _igual(fallos, parser_qgis._campo(u"Señal_2"), u"Señal_2", u"campo unicode")
    try:
        parser_qgis._campo(u'"a" || "b"', u"renderer graduado")
        fallos.append(u"una expresion deberia rechazarse")
    except parser_qgis.SimbologiaNoSoportada as e:
        texto = unicode(e)
        if u"graduado" not in texto:
            fallos.append(u"el mensaje no nombra el renderer real: %s" % texto)
        if u"categorizado" in texto:
            fallos.append(u"el mensaje sigue diciendo 'categorizado': %s" % texto)

    _igual(fallos,
           parser_qgis.ruta_dataset(u"C:\\x\\y.gpkg", layername=u"zonas"),
           u"C:\\x\\y.gpkg\\main.zonas", u"ruta de capa de GeoPackage")
    try:
        parser_qgis.ruta_dataset(u"C:\\x\\y.gpkg")
        fallos.append(u"un .gpkg sin layername deberia rechazarse")
    except parser_qgis.SimbologiaNoSoportada as e:
        if u"GeoPackage" not in unicode(e):
            fallos.append(u"mensaje poco claro para el .gpkg: %s" % unicode(e))

    ruta, defquery = parser_qgis._partir_datasource(
        u"C:\\x\\y.gpkg|layername=zonas|subset=\"TIPO\" = 'A'")
    _igual(fallos, ruta, u"C:\\x\\y.gpkg\\main.zonas", u"ruta del datasource")
    _igual(fallos, defquery, u"\"TIPO\" = 'A'", u"subset del datasource")

    # Un `|` DENTRO del subset no puede truncar la def-query (2026-09-21).
    ruta, defquery = parser_qgis._partir_datasource(
        u"C:\\x\\y.shp|subset=\"A\" = 'x|y'")
    _igual(fallos, ruta, u"C:\\x\\y.shp", u"ruta con un | en el subset")
    _igual(fallos, defquery, u"\"A\" = 'x|y'", u"subset con | en un literal")
    ruta, defquery = parser_qgis._partir_datasource(
        u"C:\\x\\y.shp|subset=\"A\" || \"B\" = 'z'")
    _igual(fallos, defquery, u"\"A\" || \"B\" = 'z'",
           u"subset con el concatenador ||")

    # Un token que no conocemos se avisa, no se tira en silencio.
    avisos = []
    parser_qgis._partir_datasource(u"C:\\x\\y.shp|raro=1", avisos)
    if not any(u"raro=1" in a for a in avisos):
        fallos.append(u"un token desconocido del datasource no avisa: %s"
                      % avisos)

    # layername con PUNTO: arcpy no lo abre; el error tiene que decir por que
    # y no dejar que arcpy culpe al dataset (medido el 2026-09-21).
    try:
        parser_qgis.ruta_dataset(u"C:\\x\\y.gpkg", layername=u"tabla_12.1")
        fallos.append(u"un layername con punto deberia rechazarse")
    except parser_qgis.SimbologiaNoSoportada as e:
        texto = unicode(e)
        if u"PUNTO" not in texto or u"tabla_12.1" not in texto:
            fallos.append(u"el mensaje no explica el punto: %s" % texto)

    _igual(fallos, parser_qgis.combinar_defquery(u"a", u"b"), u"(a) AND (b)",
           u"combinacion de def-queries")
    _igual(fallos, parser_qgis.combinar_defquery(u"a", None), u"a",
           u"def-query solo externa")
    _igual(fallos, parser_qgis.combinar_defquery(None, None), None,
           u"sin def-query")


CASOS = [
    ("defquery_args_json", caso_defquery_args_json),
    ("defquery_posicional", caso_defquery_posicional),
    ("opacidad_capa", caso_opacidad_capa),
    ("tilde_posicional", caso_tilde_posicional),
    ("tilde_args_json", caso_tilde_args_json),
    ("raster_alfa0", caso_raster_alfa0),
    ("regla_desmarcada", caso_regla_desmarcada),
    ("dash_dot", caso_dash_dot),
    ("geopackage", caso_geopackage),
    ("angulo_escalas", caso_angulo_escalas),
    ("marcador_glifo", caso_marcador_glifo),
    ("hexagono_equilatero", caso_hexagono_equilatero),
    ("categoria_oculta", caso_categoria_oculta),
    ("regla_desmarcada_simbolo_raro", caso_regla_desmarcada_simbolo_raro),
    ("batch_sintetico", caso_batch_sintetico),
    ("parser_sin_arcobjects", caso_parser_sin_arcobjects),
]


def main(argv):
    if not os.path.isdir(DIR_OUT):
        os.makedirs(DIR_OUT)
    casos = CASOS
    if argv:
        casos = [c for c in CASOS if c[0] in argv]
        if not casos:
            print("ningun caso coincide con: %s" % ", ".join(argv))
            return 2
    _preparar_datos()

    malos = []
    for nombre, funcion in casos:
        fallos = []
        try:
            funcion(fallos)
        except Exception as e:
            fallos.append(u"excepcion: %r" % (e,))
        estado = "PASS" if not fallos else "FAIL"
        print("%-5s %s" % (estado, nombre))
        for f in fallos:
            print(("      " + f).encode("utf-8"))
        if fallos:
            malos.append(nombre)

    print("")
    print("TOTAL: %d/%d PASS" % (len(casos) - len(malos), len(casos)))
    return 0 if not malos else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
