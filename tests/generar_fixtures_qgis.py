# -*- coding: utf-8 -*-
"""Genera con QGIS DE VERDAD los fixtures que el test lee.

Un fixture escrito a mano prueba el parser contra lo que SUPONEMOS que escribe
QGIS, no contra lo que escribe: si QGIS escribiera otra cosa, el test pasaria
igual sin probar nada. Por eso estos fixtures los escribe PyQGIS
(`saveNamedStyle` y `QgsProject.write`) y se versionan tal cual salen.

Se corre con el Python de QGIS (py3), NO con el py2.7 de ArcGIS:

    & "C:\\Program Files\\QGIS 3.44.12\\bin\\python-qgis-ltr.bat" tests\\generar_fixtures_qgis.py

(el .bat ignora `-c`: hay que pasarle el fichero). Necesita los datos
sinteticos de `tmp/regresion_qml/`, que fabrica con arcpy
`run_regresion_qml.py`: correr ese primero una vez.

Genera:
- `tests/fixtures/qml/reglas_desmarcada_simbolo_raro.qml`: RuleRenderer con una
  regla DESMARCADA cuyo simbolo (linea con MarkerLine) el emisor no soporta.
- `tests/fixtures/batch_sintetico.qgz`: proyecto con capas que apuntan (en
  ruta RELATIVA) a los datos sinteticos, para probar el modo batch sin `R:`.
"""
import os
import sys

from qgis.core import (
    QgsApplication, QgsCategorizedSymbolRenderer, QgsFillSymbol,
    QgsLineSymbol, QgsMarkerLineSymbolLayer, QgsMarkerSymbol,
    QgsPalettedRasterRenderer, QgsProject, QgsRasterLayer,
    QgsRendererCategory, QgsRuleBasedRenderer, QgsSimpleLineSymbolLayer,
    QgsVectorLayer)
from qgis.PyQt.QtGui import QColor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_DATOS = os.path.join(RAIZ, "tmp", "regresion_qml")
DIR_FIX = os.path.join(RAIZ, "tests", "fixtures")


def _vectorial(nombre_fichero, nombre_capa, subset=None):
    ruta = os.path.join(DIR_DATOS, nombre_fichero)
    capa = QgsVectorLayer(ruta, nombre_capa, "ogr")
    if not capa.isValid():
        sys.exit("capa no valida: %s (corre antes run_regresion_qml.py)" % ruta)
    if subset:
        capa.setSubsetString(subset)
    return capa


def _linea(color, estilo="solid"):
    sl = QgsSimpleLineSymbolLayer(QColor(color), 0.6)
    sl.setPenStyle({"solid": 1, "dash": 2}[estilo])
    return QgsLineSymbol([sl])


def qml_regla_desmarcada_simbolo_raro():
    capa = _vectorial("lineas.shp", "Red hidrografica")
    raiz = QgsRuleBasedRenderer.Rule(None)

    rios = QgsRuleBasedRenderer.Rule(_linea("#ff0000"), 0, 0,
                                     "\"TIPO\" = 'rio'", "Rios")
    raiz.appendChild(rios)

    # Linea con un MarkerLine: el emisor no lo soporta. Pero la regla esta
    # DESMARCADA, asi que QGIS no la dibuja y no debe tumbar la capa.
    raro = QgsLineSymbol([QgsMarkerLineSymbolLayer()])
    ramblas = QgsRuleBasedRenderer.Rule(raro, 0, 0,
                                        "\"TIPO\" = 'rambla'", "Ramblas")
    ramblas.setActive(False)
    raiz.appendChild(ramblas)

    resto = QgsRuleBasedRenderer.Rule(_linea("#008000"), 0, 0, "ELSE", "Resto")
    raiz.appendChild(resto)

    capa.setRenderer(QgsRuleBasedRenderer(raiz))
    salida = os.path.join(DIR_FIX, "qml", "reglas_desmarcada_simbolo_raro.qml")
    msg, ok = capa.saveNamedStyle(salida)
    if not ok:
        sys.exit("saveNamedStyle fallo: %s" % msg)
    print("escrito", salida)


def qml_marcadores_glifo():
    """Formas que ArcMap solo dibuja con glifo: triangulo con borde y
    rotado (un caso real, 2026-08-17) y estrella sin borde."""
    capa = _vectorial("puntos.shp", "Puntos glifo")
    triangulo = QgsMarkerSymbol.createSimple(
        {"name": "triangle", "color": "#ff7f00", "size": "4",
         "outline_color": "#000000", "outline_width": "0.4", "angle": "30"})
    estrella = QgsMarkerSymbol.createSimple(
        {"name": "star", "color": "#377eb8", "size": "5",
         "outline_style": "no"})
    capa.setRenderer(QgsCategorizedSymbolRenderer("TIPO", [
        QgsRendererCategory("hito", triangulo, "Hito"),
        QgsRendererCategory("vertice", estrella, "Vertice")]))
    salida = os.path.join(DIR_FIX, "qml", "puntos_triangulo_estrella.qml")
    msg, ok = capa.saveNamedStyle(salida)
    if not ok:
        sys.exit("saveNamedStyle fallo: %s" % msg)
    print("escrito", salida)


def qml_hexagono_equilatero():
    """Glifos con giro extra (hexagono) y factor propio (equilatero)."""
    capa = _vectorial("puntos.shp", "Puntos glifo 2")
    capa.setRenderer(QgsCategorizedSymbolRenderer("TIPO", [
        QgsRendererCategory("hito", QgsMarkerSymbol.createSimple(
            {"name": "hexagon", "color": "#4daf4a", "size": "5",
             "outline_style": "no"}), "Hexagono"),
        QgsRendererCategory("vertice", QgsMarkerSymbol.createSimple(
            {"name": "equilateral_triangle", "color": "#984ea3", "size": "5",
             "outline_style": "no"}), "Equilatero")]))
    _guardar_qml(capa, "puntos_hexagono_equilatero.qml")


def qml_categoria_oculta_no_soportada():
    """Categoria OCULTA (render=false) con un simbolo sin equivalente: no
    debe tumbar la capa, igual que una regla desmarcada."""
    capa = _vectorial("puntos.shp", "Puntos con oculta")
    oculta = QgsRendererCategory("vertice", QgsMarkerSymbol.createSimple(
        {"name": "arrow", "color": "#e41a1c", "size": "3"}), "Vertice")
    oculta.setRenderState(False)
    capa.setRenderer(QgsCategorizedSymbolRenderer("TIPO", [
        QgsRendererCategory("hito", QgsMarkerSymbol.createSimple(
            {"name": "circle", "color": "#377eb8", "size": "3"}), "Hito"),
        oculta]))
    _guardar_qml(capa, "categoria_oculta_no_soportada.qml")


def qml_reglas_avisos_por_regla():
    """Dos reglas: solo la de la estrella genera aviso (glifo). Ese aviso no
    debe aparecer en el .lyr de la otra regla."""
    capa = _vectorial("puntos.shp", "Puntos por reglas")
    raiz = QgsRuleBasedRenderer.Rule(None)
    raiz.appendChild(QgsRuleBasedRenderer.Rule(
        QgsMarkerSymbol.createSimple({"name": "circle", "color": "#377eb8",
                                      "size": "3", "outline_style": "no"}),
        0, 0, "\"TIPO\" = 'hito'", "Hitos"))
    raiz.appendChild(QgsRuleBasedRenderer.Rule(
        QgsMarkerSymbol.createSimple({"name": "star", "color": "#e41a1c",
                                      "size": "4", "outline_style": "no"}),
        0, 0, "ELSE", "Resto"))
    capa.setRenderer(QgsRuleBasedRenderer(raiz))
    _guardar_qml(capa, "reglas_avisos_por_regla.qml")


def _guardar_qml(capa, nombre):
    salida = os.path.join(DIR_FIX, "qml", nombre)
    msg, ok = capa.saveNamedStyle(salida)
    if not ok:
        sys.exit("saveNamedStyle fallo: %s" % msg)
    print("escrito", salida)


def qgz_batch_sintetico():
    proyecto = QgsProject.instance()
    proyecto.clear()

    # 1. Poligonos categorizados + opacidad de capa.
    zonas = _vectorial("poligonos.shp", "Zonas por tipo")
    cats = []
    for valor, color in (("A", "#e41a1c"), ("B", "#377eb8")):
        simbolo = QgsFillSymbol.createSimple(
            {"color": color, "outline_color": "#000000",
             "outline_width": "0.26"})
        cats.append(QgsRendererCategory(valor, simbolo, "Tipo %s" % valor))
    zonas.setRenderer(QgsCategorizedSymbolRenderer("TIPO", cats))
    zonas.setOpacity(0.5)

    # 2. Lineas con def-query (viaja en el datasource, `|subset=`).
    rios = _vectorial("lineas.shp", "Solo rios", subset="\"TIPO\" = 'rio'")
    rios.renderer().setSymbol(_linea("#0000ff", "dash"))

    # 3. Puntos con marcador FLECHA: sin equivalente en ArcMap (ni forma
    #    simple ni glifo verificado). Debe fallar ESTA capa y el lote seguir.
    hitos = _vectorial("puntos.shp", "Hitos flecha")
    hitos.renderer().setSymbol(QgsMarkerSymbol.createSimple(
        {"name": "arrow", "color": "#ff7f00", "size": "3"}))

    # 4. Raster paletado.
    paleta = QgsRasterLayer(os.path.join(DIR_DATOS, "paleta.tif"), "Paleta")
    if not paleta.isValid():
        sys.exit("raster no valido (corre antes run_regresion_qml.py)")
    clases = [QgsPalettedRasterRenderer.Class(v, QColor(c), et) for v, c, et in
              ((0, "#ffffcc", "cero"), (1, "#41b6c4", "uno"),
               (2, "#253494", "dos"))]
    paleta.setRenderer(QgsPalettedRasterRenderer(
        paleta.dataProvider(), 1, clases))

    # 5. Capa de GeoPackage (datasource con `|layername=`).
    gpkg = QgsVectorLayer(os.path.join(DIR_DATOS, "zonas.gpkg")
                          + "|layername=zonas", "Zonas GPKG", "ogr")
    if not gpkg.isValid():
        sys.exit("GeoPackage no valido (corre antes run_regresion_qml.py)")

    for capa in (zonas, rios, hitos, paleta, gpkg):
        proyecto.addMapLayer(capa)

    salida = os.path.join(DIR_FIX, "batch_sintetico.qgz")
    # Rutas RELATIVAS (lo normal en QGIS): el batch las resuelve contra la
    # carpeta del .qgz, y asi el fixture vale en cualquier clon del repo.
    proyecto.writeEntryBool("Paths", "/Absolute", False)
    # Sin el usuario del sistema en los metadatos del fixture versionado.
    metadatos = proyecto.metadata()
    metadatos.setAuthor("qml2lyr tests")
    proyecto.setMetadata(metadatos)
    if not proyecto.write(salida):
        sys.exit("QgsProject.write fallo: %s" % proyecto.error())
    print("escrito", salida)


def main():
    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        print("QGIS", QgsApplication.version() if hasattr(
            QgsApplication, "version") else "")
        qml_regla_desmarcada_simbolo_raro()
        qml_marcadores_glifo()
        qml_hexagono_equilatero()
        qml_categoria_oculta_no_soportada()
        qml_reglas_avisos_por_regla()
        qgz_batch_sintetico()
    finally:
        app.exitQgis()


if __name__ == "__main__":
    main()
