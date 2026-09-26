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

Sin argumentos regenera TODOS. Con nombres, solo esos:

    ... generar_fixtures_qgis.py poligono_simple linea_dash_dot

QGIS cambia UUID, fecha y algun color aleatorio en cada pasada: regenerar un
fixture que no se queria tocar ensucia el diff. Nombres validos: las claves de
`GENERADORES` (el nombre del fichero sin extension). `--listar` los muestra.
"""
import os
import sys

from qgis.core import (
    QgsApplication, QgsCategorizedSymbolRenderer, QgsFillSymbol,
    QgsLineSymbol, QgsMarkerLineSymbolLayer, QgsMarkerSymbol,
    QgsPalettedRasterRenderer, QgsProject, QgsRasterLayer,
    QgsRendererCategory, QgsRuleBasedRenderer, QgsSimpleLineSymbolLayer,
    QgsVectorLayer)
from qgis.PyQt.QtCore import Qt
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


def _linea(color, estilo="solid", ancho=0.6):
    sl = QgsSimpleLineSymbolLayer(QColor(color), ancho)
    sl.setPenStyle({"solid": Qt.SolidLine, "dash": Qt.DashLine,
                    "dash dot": Qt.DashDotLine}[estilo])
    return QgsLineSymbol([sl])


def _relleno(color, ancho_borde):
    return QgsFillSymbol.createSimple(
        {"color": color, "outline_color": "#000000",
         "outline_width": str(ancho_borde), "style": "solid"})


def qml_poligono_simple():
    """Camino del PLUGIN, caso base: relleno solido sin opacidad de capa.
    Sirve para probar la def-query y los textos con tilde, que NO viajan
    dentro del .qml."""
    capa = _vectorial("poligonos.shp", "Zonas")
    capa.renderer().setSymbol(_relleno("#c81e1e", 0.5))
    _guardar_qml(capa, "poligono_simple.qml")


def qml_poligono_opacidad_50():
    """Opacidad de CAPA al 50%: `<layerOpacity>` cuelga de la raiz <qgis>
    igual que del <maplayer> de un .qgz. Hasta 2026-09-20 `parse_qml` no lo
    leia y la transparencia se perdia entera por la via del plugin."""
    capa = _vectorial("poligonos.shp", "Opaca a medias")
    capa.renderer().setSymbol(_relleno("#1e78c8", 0.26))
    capa.setOpacity(0.5)
    _guardar_qml(capa, "poligono_opacidad_50.qml")


def qml_linea_dash_dot():
    """Trazo `dash dot`: QGIS escribe el estilo con ESPACIOS. Ancho 0,4 mm
    (1,13 pt), por debajo del umbral en el que ArcMap dibuja el patron
    continuo, para que el test mire el estilo y no el aviso."""
    capa = _vectorial("lineas.shp", "Trazo dash dot")
    capa.renderer().setSymbol(_linea("#0000ff", "dash dot", 0.4))
    _guardar_qml(capa, "linea_dash_dot.qml")


def qml_raster_paleta_alfa0():
    """Raster paletado con una clase de ALFA 0, invisible en QGIS. Hasta
    2026-09-20 salia OPACA y sin aviso; ArcMap la reproduce con simbolo nulo."""
    capa = QgsRasterLayer(os.path.join(DIR_DATOS, "paleta.tif"), "Paleta")
    if not capa.isValid():
        sys.exit("raster no valido (corre antes run_regresion_qml.py)")
    invisible = QColor("#ff0000")
    invisible.setAlpha(0)
    clases = [QgsPalettedRasterRenderer.Class(0, invisible, "cero (invisible)"),
              QgsPalettedRasterRenderer.Class(1, QColor("#00ff00"), "uno"),
              QgsPalettedRasterRenderer.Class(2, QColor("#0000ff"), "dos")]
    capa.setRenderer(QgsPalettedRasterRenderer(capa.dataProvider(), 1, clases))
    _guardar_qml(capa, "raster_paleta_alfa0.qml")


def qml_punto_angulo_escalas():
    """Marcador cuadrado rotado 45 grados + visibilidad por escala de la capa
    (1:1000 acercado, 1:50000 alejado). OJO al probar el giro: un cuadrado a
    45 se ve igual en los dos sentidos; el sentido lo prueban los glifos."""
    capa = _vectorial("puntos.shp", "Hitos rotados")
    capa.renderer().setSymbol(QgsMarkerSymbol.createSimple(
        {"name": "square", "color": "#0078c8", "size": "4",
         "outline_color": "#000000", "outline_width": "0.4", "angle": "45"}))
    capa.setScaleBasedVisibility(True)
    capa.setMinimumScale(50000)
    capa.setMaximumScale(1000)
    _guardar_qml(capa, "punto_angulo_escalas.qml")


def qml_reglas_con_desmarcada():
    """RuleRenderer con una regla DESMARCADA: QGIS no la dibuja, asi que ni
    sale su .lyr ni entra su filtro en el ELSE. El ELSE lleva ademas limites
    de escala, que ArcMap no admite por clase y se ignoran con aviso."""
    capa = _vectorial("lineas.shp", "Red hidrografica")
    raiz = QgsRuleBasedRenderer.Rule(None)
    raiz.appendChild(QgsRuleBasedRenderer.Rule(
        _linea("#ff0000", ancho=1), 0, 0, "\"TIPO\" = 'rio'", "Rios"))
    ramblas = QgsRuleBasedRenderer.Rule(
        _linea("#0000ff", ancho=1), 0, 0, "\"TIPO\" = 'rambla'", "Ramblas")
    ramblas.setActive(False)
    raiz.appendChild(ramblas)
    # Rule(simbolo, maximumScale, minimumScale, ...): 1:1000 es el limite
    # acercado y 1:50000 el alejado.
    raiz.appendChild(QgsRuleBasedRenderer.Rule(
        _linea("#008000", ancho=1), 1000, 50000, "ELSE", "Resto"))
    capa.setRenderer(QgsRuleBasedRenderer(raiz))
    _guardar_qml(capa, "reglas_con_desmarcada.qml")


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


def qml_categoria_resto_nula():
    """Categoria A + la categoria NULL que QGIS usa como "todos los demas
    valores" (QgsRendererCategory con valor nulo). B no tiene categoria: en
    QGIS cae en la NULL, asi que tiene que dibujarse tambien en ArcMap."""
    capa = _vectorial("poligonos.shp", "Resto nulo")
    capa.setRenderer(QgsCategorizedSymbolRenderer("TIPO", [
        QgsRendererCategory("A", _relleno("#e41a1c", 0.26), "Tipo A"),
        QgsRendererCategory(None, _relleno("#999999", 0.26),
                            "Todos los demas valores")]))
    _guardar_qml(capa, "categoria_resto_nula.qml")


def _categorizado_nulos(expresion, categorias, nombre_fichero):
    capa = QgsVectorLayer(os.path.join(DIR_DATOS, "nulos.gdb")
                          + "|layername=cuadros", "Nulos", "ogr")
    if not capa.isValid():
        sys.exit("nulos.gdb no valida (corre antes run_regresion_qml.py)")
    capa.setRenderer(QgsCategorizedSymbolRenderer(expresion, [
        QgsRendererCategory(valor, _relleno(color, 0.26), etiqueta)
        for valor, color, etiqueta in categorias]))
    _guardar_qml(capa, nombre_fichero)


def qml_categorizado_multicampo():
    """concat(coalesce(G,''), ', ', coalesce(R,'')): QGIS convierte los nulos
    en '' dentro del valor. Categorias con un componente vacio."""
    _categorizado_nulos(
        "concat(coalesce(\"G\",''), ', ', coalesce(\"R\",''))",
        [("1, Forestal MUP", "#e41a1c", "1, Forestal MUP"),
         ("1, ", "#4daf4a", "Grupo 1 sin red"),
         (", Rural", "#377eb8", "Rural sin grupo"),
         (None, "#999999", "Todos los demas valores")],
        "categorizado_multicampo.qml")


def qml_categorizado_multicampo_barras():
    """"G" || ', ' || "R" sin coalesce: un nulo anula el valor entero y la
    entidad cae en "todos los demas"."""
    _categorizado_nulos(
        "\"G\" || ', ' || \"R\"",
        [("1, Forestal MUP", "#e41a1c", "1, Forestal MUP"),
         ("1, ", "#4daf4a", "Grupo 1 sin red"),
         (None, "#999999", "Todos los demas valores")],
        "categorizado_multicampo_barras.qml")


def qml_raster_cortes():
    """Pseudocolor DISCRETO (clases) sobre un raster flotante, y el .aux.xml
    que GDAL deja al pedir estadisticas aproximadas (sin histograma): la
    combinacion que tumbaba la emision con la pendiente de Majal Blanco."""
    import shutil
    from osgeo import gdal
    from qgis.core import (QgsColorRampShader, QgsRasterShader,
                           QgsSingleBandPseudoColorRenderer)
    ruta = os.path.join(DIR_DATOS, "cortes.tif")
    aux = ruta + ".aux.xml"
    if os.path.exists(aux):
        os.remove(aux)
    capa = QgsRasterLayer(ruta, "Cortes")
    if not capa.isValid():
        sys.exit("cortes.tif no valido (corre antes run_regresion_qml.py)")
    rampa = QgsColorRampShader(0, 45, None, QgsColorRampShader.Discrete)
    rampa.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(10, QColor("#38a800"), "llano"),
        QgsColorRampShader.ColorRampItem(30, QColor("#ffff00"), "medio"),
        QgsColorRampShader.ColorRampItem(float("inf"), QColor("#e60000"),
                                         "fuerte")])
    sombreado = QgsRasterShader()
    sombreado.setRasterShaderFunction(rampa)
    capa.setRenderer(QgsSingleBandPseudoColorRenderer(
        capa.dataProvider(), 1, sombreado))
    _guardar_qml(capa, "raster_cortes.qml")
    del capa
    # El sidecar lo escribe GDAL, no la mano: estadisticas aproximadas, que es
    # lo que deja QGIS (STATISTICS_APPROXIMATE=YES, sin histograma).
    ds = gdal.Open(ruta)
    ds.GetRasterBand(1).ComputeStatistics(True)
    ds = None
    destino = os.path.join(DIR_FIX, "aux_gdal")
    if not os.path.isdir(destino):
        os.makedirs(destino)
    shutil.move(aux, os.path.join(destino, "cortes.tif.aux.xml"))
    print("escrito", os.path.join(destino, "cortes.tif.aux.xml"))


def _etiquetar(capa, campo, es_expresion, tamano, unidad, color, negrita=False,
               cursiva=False, halo=None, escalas=None):
    from qgis.core import (Qgis, QgsPalLayerSettings, QgsTextBufferSettings,
                           QgsTextFormat, QgsVectorLayerSimpleLabeling)
    from qgis.PyQt.QtGui import QFont
    ajustes = QgsPalLayerSettings()
    ajustes.fieldName = campo
    ajustes.isExpression = es_expresion
    formato = QgsTextFormat()
    fuente = QFont("Arial")
    fuente.setBold(negrita)
    fuente.setItalic(cursiva)
    formato.setFont(fuente)
    formato.setSize(tamano)
    formato.setSizeUnit(unidad)
    formato.setColor(QColor(color))
    if halo:
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(halo[0])
        buffer.setSizeUnit(Qgis.RenderUnit.Millimeters)
        buffer.setColor(QColor(halo[1]))
        formato.setBuffer(buffer)
    ajustes.setFormat(formato)
    if escalas:
        # API: minimumScale = limite ALEJADO. En el XML sale como scaleMax.
        ajustes.scaleVisibility = True
        ajustes.minimumScale, ajustes.maximumScale = escalas
    capa.setLabeling(QgsVectorLayerSimpleLabeling(ajustes))
    capa.setLabelsEnabled(True)


def qml_etiquetas_simples():
    """Campo, Arial negrita y cursiva de 10 pt, color, halo de 1 mm y escalas."""
    from qgis.core import Qgis
    capa = _vectorial("poligonos.shp", "Etiquetas simples")
    _etiquetar(capa, "TIPO", False, 10, Qgis.RenderUnit.Points, "#123456",
               negrita=True, cursiva=True, halo=(1, "#ffff00"),
               escalas=(50000, 1000))
    _guardar_qml(capa, "etiquetas_simples.qml")


def qml_etiquetas_expresion():
    """Concatenacion con || y tamano en mm (sin halo)."""
    from qgis.core import Qgis
    capa = QgsVectorLayer(os.path.join(DIR_DATOS, "nulos.gdb")
                          + "|layername=cuadros", "Etiquetas expresion", "ogr")
    if not capa.isValid():
        sys.exit("nulos.gdb no valida (corre antes run_regresion_qml.py)")
    _etiquetar(capa, "\"G\" || ' - ' || \"R\"", True, 3,
               Qgis.RenderUnit.Millimeters, "#e41a1c")
    _guardar_qml(capa, "etiquetas_expresion.qml")


def qml_etiquetas_no_traducible():
    """Expresion que ArcMap no sabe evaluar: la capa sale, sin etiquetas."""
    from qgis.core import Qgis
    capa = _vectorial("poligonos.shp", "Etiquetas upper")
    _etiquetar(capa, "upper(\"TIPO\")", True, 10, Qgis.RenderUnit.Points,
               "#000000")
    _guardar_qml(capa, "etiquetas_no_traducible.qml")


def _rgb(nombre_fichero, bandas, realces, raster="rgb.tif"):
    """RGB sobre rgb.tif (8 bits) o rgb16.tif (16 bits). `realces`: por
    banda, None (sin realce) o (algoritmo, minimo, maximo)."""
    from qgis.core import QgsContrastEnhancement, QgsMultiBandColorRenderer
    capa = QgsRasterLayer(os.path.join(DIR_DATOS, raster), "RGB")
    if not capa.isValid():
        sys.exit("%s no valido (corre antes run_regresion_qml.py)" % raster)
    render = QgsMultiBandColorRenderer(capa.dataProvider(), *bandas)
    fijar = (render.setRedContrastEnhancement,
             render.setGreenContrastEnhancement,
             render.setBlueContrastEnhancement)
    for fija, banda, realce in zip(fijar, bandas, realces):
        if realce is None:
            continue
        algoritmo, minimo, maximo = realce
        ce = QgsContrastEnhancement(capa.dataProvider().dataType(banda))
        ce.setContrastEnhancementAlgorithm(getattr(
            QgsContrastEnhancement, algoritmo))
        ce.setMinimumValue(minimo)
        ce.setMaximumValue(maximo)
        fija(ce)
    capa.setRenderer(render)
    _guardar_qml(capa, nombre_fichero)


def qml_raster_rgb():
    _rgb("raster_rgb_sin_realce.qml", (1, 2, 3), (None, None, None))
    # Bandas cambiadas (3-2-1) y estirado con minimo/maximo propios por banda.
    _rgb("raster_rgb_estirado.qml", (3, 2, 1), (
        ("StretchToMinimumMaximum", 0, 200),
        ("StretchToMinimumMaximum", 10, 220),
        ("StretchToMinimumMaximum", 20, 240)))
    # Sin realce en una banda y estirado en las otras: no se traduce.
    _rgb("raster_rgb_mixto.qml", (1, 2, 3), (
        None, ("StretchToMinimumMaximum", 10, 220),
        ("StretchToMinimumMaximum", 20, 240)))
    # 16 bits: estirado interior (ArcMap lo reproduce compensando su 5%) y
    # sin realce (el tramo 0-255 no se puede empezar en 0: se avisa).
    _rgb("raster_rgb16_estirado.qml", (1, 2, 3), (
        ("StretchToMinimumMaximum", 30, 200),
        ("StretchToMinimumMaximum", 40, 210),
        ("StretchToMinimumMaximum", 50, 220)), raster="rgb16.tif")
    _rgb("raster_rgb16_sin_realce.qml", (1, 2, 3), (None, None, None),
         raster="rgb16.tif")


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


#: Unidad que el fixture de --remap tiene escrita y que NO debe existir al
#: correr la regresion (el caso de uso: un proyecto con rutas `Z:` convertido
#: donde esa unidad no esta montada). La regresion la importa de aqui.
UNIDAD_REMAP = "Q:"


def qgz_batch_remap():
    """Proyecto con rutas ABSOLUTAS a una unidad que luego no existe.

    Para que las rutas las escriba QGIS y no una sustitucion de texto, la
    unidad se crea de verdad con `subst` sobre los datos sinteticos mientras
    QGIS carga las capas y guarda, y se quita al terminar."""
    import subprocess
    if os.path.exists(UNIDAD_REMAP + "\\"):
        sys.exit("la unidad %s ya existe: el fixture necesita una libre"
                 % UNIDAD_REMAP)
    subprocess.check_call(["subst", UNIDAD_REMAP, DIR_DATOS])
    try:
        proyecto = QgsProject.instance()
        proyecto.clear()
        zonas = QgsVectorLayer(UNIDAD_REMAP + "/poligonos.shp",
                               "Zonas remap", "ogr")
        cats = [QgsRendererCategory(v, QgsFillSymbol.createSimple(
            {"color": c, "outline_color": "#000000"}), "Tipo %s" % v)
            for v, c in (("A", "#e41a1c"), ("B", "#377eb8"))]
        zonas.setRenderer(QgsCategorizedSymbolRenderer("TIPO", cats))
        paleta = QgsRasterLayer(UNIDAD_REMAP + "/paleta.tif", "Paleta remap")
        clases = [QgsPalettedRasterRenderer.Class(v, QColor(c), et)
                  for v, c, et in ((0, "#ffffcc", "cero"), (1, "#41b6c4", "uno"),
                                   (2, "#253494", "dos"))]
        if paleta.isValid():
            paleta.setRenderer(QgsPalettedRasterRenderer(
                paleta.dataProvider(), 1, clases))
        gpkg = QgsVectorLayer(UNIDAD_REMAP + "/zonas.gpkg|layername=zonas",
                              "GPKG remap", "ogr")
        for capa in (zonas, paleta, gpkg):
            if not capa.isValid():
                sys.exit("capa no valida en %s: %s (corre antes "
                         "run_regresion_qml.py)" % (UNIDAD_REMAP, capa.name()))
            proyecto.addMapLayer(capa)
        proyecto.writeEntryBool("Paths", "/Absolute", True)
        metadatos = proyecto.metadata()
        metadatos.setAuthor("qml2lyr tests")
        proyecto.setMetadata(metadatos)
        salida = os.path.join(DIR_FIX, "batch_remap.qgz")
        if not proyecto.write(salida):
            sys.exit("QgsProject.write fallo: %s" % proyecto.error())
        proyecto.clear()
        print("escrito", salida)
    finally:
        subprocess.call(["subst", UNIDAD_REMAP, "/D"])


def qgz_batch_wms():
    """Capas WMS contra el servidor local de `wms_local.py` (sin red externa):
    QGIS se conecta de verdad y escribe el datasource tal como lo guarda."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import wms_local
    servidor = wms_local.arrancar()
    try:
        proyecto = QgsProject.instance()
        proyecto.clear()
        casos = (("WMS dos hojas", ["parcelas", "textos"], 0.7),
                 ("WMS grupo", ["catastro"], 1.0),
                 ("WMS con una que falta", ["masas", "no_existe"], 1.0))
        for nombre, capas, opacidad in casos:
            uri = "crs=EPSG:25830&format=image/png&%s&%s&url=%s" % (
                "&".join("layers=" + c for c in capas),
                "&".join("styles" for _ in capas), wms_local.URL)
            capa = QgsRasterLayer(uri, nombre, "wms")
            if not capa.isValid():
                sys.exit("capa WMS no valida: %s" % capa.error().summary())
            capa.renderer().setOpacity(opacidad)
            proyecto.addMapLayer(capa)
        # WMTS pidiendo la matriz EPSG:25830, que NO es la primera del
        # servicio (ArcObjects se queda con la primera si no se fija).
        wmts = QgsRasterLayer(
            "crs=EPSG:25830&format=image/png&layers=mapa&styles=default&"
            "tileMatrixSet=EPSG:25830&url=" + wms_local.URL_WMTS,
            "WMTS mapa", "wms")
        if not wmts.isValid():
            sys.exit("capa WMTS no valida: %s" % wmts.error().summary())
        proyecto.addMapLayer(wmts)
        metadatos = proyecto.metadata()
        metadatos.setAuthor("qml2lyr tests")
        proyecto.setMetadata(metadatos)
        salida = os.path.join(DIR_FIX, "batch_wms.qgz")
        if not proyecto.write(salida):
            sys.exit("QgsProject.write fallo: %s" % proyecto.error())
        proyecto.clear()
        print("escrito", salida)
    finally:
        servidor.shutdown()


def qgz_proyecto_mxd():
    """Proyecto para el modo --mxd: grupos anidados, capas apagadas, una capa
    que no convierte (flecha), un grupo que se queda vacio y un raster RGB.

        x Zonas por tipo
        x Grupo A
            - Solo rios
            - Sub B
                x Paleta
        x Hitos flecha          <- no convierte: se omite
        x Solo fallos           <- su unica capa no convierte: grupo omitido
            x Hitos flecha 2
        - RGB                   <- raster RGB: entra con el render por defecto
    """
    from qgis.core import QgsCoordinateReferenceSystem, QgsReferencedRectangle
    from qgis.core import QgsRectangle
    proyecto = QgsProject.instance()
    proyecto.clear()
    proyecto.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
    proyecto.setTitle("Proyecto de prueba del modo MXD")

    zonas = _vectorial("poligonos.shp", "Zonas por tipo")
    zonas.setRenderer(QgsCategorizedSymbolRenderer("TIPO", [
        QgsRendererCategory("A", _relleno("#e41a1c", 0.26), "Tipo A"),
        QgsRendererCategory("B", _relleno("#377eb8", 0.26), "Tipo B")]))
    rios = _vectorial("lineas.shp", "Solo rios", subset="\"TIPO\" = 'rio'")
    rios.renderer().setSymbol(_linea("#0000ff"))
    paleta = QgsRasterLayer(os.path.join(DIR_DATOS, "paleta.tif"), "Paleta")
    paleta.setRenderer(QgsPalettedRasterRenderer(paleta.dataProvider(), 1, [
        QgsPalettedRasterRenderer.Class(v, QColor(c), et) for v, c, et in
        ((0, "#ffffcc", "cero"), (1, "#41b6c4", "uno"), (2, "#253494", "dos"))]))
    flechas = []
    for nombre in ("Hitos flecha", "Hitos flecha 2"):
        hitos = _vectorial("puntos.shp", nombre)
        hitos.renderer().setSymbol(QgsMarkerSymbol.createSimple(
            {"name": "arrow", "color": "#ff7f00", "size": "3"}))
        flechas.append(hitos)
    rgb = QgsRasterLayer(os.path.join(DIR_DATOS, "rgb.tif"), "RGB")
    for capa in [zonas, rios, paleta, rgb] + flechas:
        if not capa.isValid():
            sys.exit("capa no valida: %s (corre antes run_regresion_qml.py)"
                     % capa.name())
        proyecto.addMapLayer(capa, False)

    raiz = proyecto.layerTreeRoot()
    raiz.addLayer(zonas)
    grupo_a = raiz.addGroup("Grupo A")
    grupo_a.addLayer(rios).setItemVisibilityChecked(False)
    sub_b = grupo_a.addGroup("Sub B")
    sub_b.setItemVisibilityChecked(False)
    sub_b.addLayer(paleta)
    raiz.addLayer(flechas[0])
    raiz.addGroup("Solo fallos").addLayer(flechas[1])
    raiz.addLayer(rgb).setItemVisibilityChecked(False)

    proyecto.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(
        QgsRectangle(599900, 4199900, 600500, 4200300), proyecto.crs()))
    proyecto.writeEntryBool("Paths", "/Absolute", False)
    metadatos = proyecto.metadata()
    metadatos.setAuthor("qml2lyr tests")
    proyecto.setMetadata(metadatos)
    salida = os.path.join(DIR_FIX, "proyecto_mxd.qgz")
    if not proyecto.write(salida):
        sys.exit("QgsProject.write fallo: %s" % proyecto.error())
    proyecto.clear()
    print("escrito", salida)


def qml_wms_capa_viva():
    """Capa WMS viva, como la ve el plugin: su .qml (`saveNamedStyle`, que no
    lleva el origen) y su `layer.source()`, que el plugin pasa aparte."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import wms_local
    servidor = wms_local.arrancar()
    try:
        capa = QgsRasterLayer(
            "crs=EPSG:25830&format=image/png&layers=masas&layers=textos&"
            "styles&styles&url=" + wms_local.URL, "WMS viva", "wms")
        if not capa.isValid():
            sys.exit("capa WMS no valida: %s" % capa.error().summary())
        capa.renderer().setOpacity(0.6)
        _guardar_qml(capa, "wms_capa_viva.qml")
        ruta = os.path.join(DIR_FIX, "qml", "wms_capa_viva.source.txt")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(capa.source())
        print("escrito", ruta)
    finally:
        servidor.shutdown()


# Nombre del fichero (sin extension) -> generador.
GENERADORES = {
    "poligono_simple": qml_poligono_simple,
    "poligono_opacidad_50": qml_poligono_opacidad_50,
    "linea_dash_dot": qml_linea_dash_dot,
    "raster_paleta_alfa0": qml_raster_paleta_alfa0,
    "punto_angulo_escalas": qml_punto_angulo_escalas,
    "reglas_con_desmarcada": qml_reglas_con_desmarcada,
    "reglas_desmarcada_simbolo_raro": qml_regla_desmarcada_simbolo_raro,
    "puntos_triangulo_estrella": qml_marcadores_glifo,
    "puntos_hexagono_equilatero": qml_hexagono_equilatero,
    "categoria_oculta_no_soportada": qml_categoria_oculta_no_soportada,
    "reglas_avisos_por_regla": qml_reglas_avisos_por_regla,
    "categoria_resto_nula": qml_categoria_resto_nula,
    "categorizado_multicampo": qml_categorizado_multicampo,
    "categorizado_multicampo_barras": qml_categorizado_multicampo_barras,
    "raster_cortes": qml_raster_cortes,
    "raster_rgb": qml_raster_rgb,
    "etiquetas_simples": qml_etiquetas_simples,
    "etiquetas_expresion": qml_etiquetas_expresion,
    "etiquetas_no_traducible": qml_etiquetas_no_traducible,
    "batch_sintetico": qgz_batch_sintetico,
    "batch_remap": qgz_batch_remap,
    "batch_wms": qgz_batch_wms,
    "proyecto_mxd": qgz_proyecto_mxd,
    "wms_capa_viva": qml_wms_capa_viva,
}


def main():
    pedidos = sys.argv[1:]
    if "--listar" in pedidos:
        print("\n".join(sorted(GENERADORES)))
        return
    desconocidos = [p for p in pedidos if p not in GENERADORES]
    if desconocidos:
        sys.exit("fixture desconocido: %s (usa --listar)" % ", ".join(desconocidos))

    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        print("QGIS", QgsApplication.version() if hasattr(
            QgsApplication, "version") else "")
        for nombre in pedidos or list(GENERADORES):
            GENERADORES[nombre]()
    finally:
        app.exitQgis()


if __name__ == "__main__":
    main()
