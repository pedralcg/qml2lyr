# -*- coding: utf-8 -*-
"""Plugin qml2lyr: "Guardar estilo como .lyr" sobre la capa activa y
"Exportar proyecto a .mxd" (menu Complementos) sobre el proyecto guardado.

Flujo (ADR-001):
  1. Capa activa -> validar que es de fichero (ogr/gdal) y resolver su dato.
  2. `saveNamedStyle` vuelca el estilo vivo a un .qml temporal.
  3. Dialogo de fichero para elegir la salida .lyr.
  4. Subproceso con el Python 2.7 de ArcGIS -> emisor.py --args-json -> JSON.
  5. Reporte en la UI: exito / error / avisos por capa (avisar y saltar).

La definition query NO viaja en el .qml (es una propiedad del proveedor, no del
estilo): se lee aparte con `subsetString()` y se pasa al emisor. Lo mismo el
origen de una capa WMS/WMTS: va aparte, como `servicio` (su `source()`).

El .mxd sale del proyecto GUARDADO en disco (el motor lee el .qgz): con cambios
sin guardar se ofrece guardar. Tarda (~1 min en un proyecto de 26 capas), asi
que corre en una QgsTask y QGIS no se congela.
"""

import os
import re
import tempfile

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox, QApplication
from qgis.core import QgsApplication, QgsProject, QgsTask, QgsVectorLayer

from .compat_qt import (boton_mensaje, cursor_espera, nivel_mensaje,
                        tarea_sin_flags, tipos_capa)
from .emisor_runner import ejecutar_mxd, ejecutar_qml, EmisorError
from .informe import resumen_mxd
from . import rutas
from .settings_dialog import SettingsDialog

PLUGIN_DIR = os.path.dirname(__file__)
MENU = u"qml2lyr"


class Qml2LyrPlugin(object):
    def __init__(self, iface):
        self.iface = iface
        self.action_layer = None
        self.action_settings = None
        self.action_mxd = None
        # Referencia viva a la tarea en curso: si se suelta, Python la recoge
        # y QGIS se queda con un puntero colgando.
        self._tarea = None

    # ------------------------------------------------------------------ ciclo
    def initGui(self):
        icon = QIcon(os.path.join(PLUGIN_DIR, "icon.svg"))

        # Accion en el menu contextual de cada capa (clic derecho en el panel).
        self.action_layer = QAction(
            icon, u"Guardar estilo como .lyr…", self.iface.mainWindow())
        self.action_layer.triggered.connect(self.run)
        for tipo in tipos_capa():
            self.iface.addCustomActionForLayerType(
                self.action_layer, None, tipo, True)

        # Proyecto entero -> .mxd, en el menu Complementos.
        self.action_mxd = QAction(
            icon, u"Exportar proyecto a .mxd…", self.iface.mainWindow())
        self.action_mxd.triggered.connect(self.exportar_mxd)
        self.iface.addPluginToMenu(MENU, self.action_mxd)

        # Accion de ajustes en el menu Complementos.
        self.action_settings = QAction(
            icon, u"qml2lyr: ajustes…", self.iface.mainWindow())
        self.action_settings.triggered.connect(self.abrir_ajustes)
        self.iface.addPluginToMenu(MENU, self.action_settings)

    def unload(self):
        if self.action_layer is not None:
            self.iface.removeCustomActionForLayerType(self.action_layer)
        if self.action_settings is not None:
            self.iface.removePluginMenu(MENU, self.action_settings)
        if self.action_mxd is not None:
            self.iface.removePluginMenu(MENU, self.action_mxd)

    # ------------------------------------------------------------ datasource
    @staticmethod
    def _resolver_dato(source):
        """`layer.source()` -> (ruta que arcpy sabe abrir, error legible).

        El `source` de OGR lleva la ruta y, tras `|`, tokens del proveedor:
        `subset=` (la definition query) y `layername=` (la capa dentro de un
        contenedor multicapa). Antes se hacia `source.split("|")[0]` y se
        tiraban los dos: la def-query se perdia (viaja ahora por
        `subsetString()`) y un GeoPackage acababa dando un error criptico de
        arcpy sobre un .gpkg que no puede abrir.

        GeoPackage SI se soporta: arcpy 10.5 abre `ruta.gpkg\\main.<capa>`
        (verificado el 2026-09-20 con MakeFeatureLayer y con una emision
        completa a .lyr).
        """
        trozos = source.split(u"|")
        ruta = trozos[0]
        layername = None
        for trozo in trozos[1:]:
            if trozo.startswith(u"layername="):
                layername = trozo[len(u"layername="):]
        ext = os.path.splitext(ruta)[1].lower()
        if ext == u".gpkg":
            if not layername:
                return None, (
                    u"Esta capa es un GeoPackage pero su origen no dice qué "
                    u"capa de dentro usar:\n%s\n\nVuelve a añadirla en QGIS "
                    u"eligiéndola en el selector de capas del GeoPackage, o "
                    u"expórtala a shapefile." % ruta)
            return u"%s\\main.%s" % (ruta, layername), None
        if layername:
            return None, (
                u"Capa multicapa «%s» dentro de:\n%s\n\nSolo se convierten "
                u"shapefile, ráster de fichero y GeoPackage. Expórtala a "
                u"shapefile." % (layername, ruta))
        return ruta, None

    @staticmethod
    def _dato_existe(ruta):
        """Un .gpkg resuelto (`x.gpkg\\main.capa`) no es un fichero del
        sistema: lo que tiene que existir es el contenedor."""
        if os.path.exists(ruta):
            return True
        contenedor = os.path.dirname(ruta)
        return (os.path.splitext(contenedor)[1].lower() == u".gpkg"
                and os.path.exists(contenedor))

    # ----------------------------------------------------------------- accion
    def run(self):
        layer = self.iface.activeLayer()
        if layer is None:
            self._warn(u"No hay ninguna capa activa. "
                       u"Haz clic sobre la capa en el panel y vuelve a intentarlo.")
            return

        # Capas de fichero (ogr/gdal) y de servicio WMS/WMTS (proveedor wms,
        # que tambien sirve XYZ: ese lo rechaza el motor diciendo por que).
        # memory / PostGIS / WFS no tienen un dato que arcpy pueda abrir.
        prov = layer.dataProvider().name() if layer.dataProvider() else u""
        if prov not in ("ogr", "gdal", "wms"):
            self._warn(
                u"Solo se convierten capas de fichero (shapefile, GeoTIFF…) y "
                u"WMS/WMTS. Esta capa usa el proveedor «%s», que no se puede "
                u"convertir." % prov)
            return

        servicio = layer.source() if prov == "wms" else None
        ruta_dato = None
        if servicio is None:
            ruta_dato, error = self._resolver_dato(layer.source())
            if error:
                self._error(u"Tipo de dato no soportado", error)
                return
            if not self._dato_existe(ruta_dato):
                self._warn(u"No se encuentra el dato de la capa en disco:\n%s"
                           % ruta_dato)
                return

        # Definition query de la capa VIVA. No esta en el .qml (es propiedad
        # del proveedor, no del estilo) y hasta hoy se perdia entera.
        defquery = None
        if isinstance(layer, QgsVectorLayer):
            defquery = layer.subsetString() or None

        try:
            py27, emisor = rutas.resolver()
        except rutas.RutaNoValida as e:
            self._error(u"qml2lyr no está listo", str(e))
            return

        s = QSettings()
        nombre = layer.name()
        sugerido = self._nombre_fichero(nombre) + u".lyr"
        # En un .gpkg, dirname(ruta_dato) es el propio .gpkg y no una carpeta:
        # el dialogo tiene que abrirse en la carpeta que lo contiene. Una capa
        # de servicio no tiene carpeta: la del proyecto.
        if ruta_dato:
            carpeta_dato = os.path.dirname(ruta_dato)
            if not os.path.isdir(carpeta_dato):
                carpeta_dato = os.path.dirname(carpeta_dato)
        else:
            carpeta_dato = QgsProject.instance().homePath() or \
                os.path.expanduser(u"~")
        ultimo_dir = s.value("qml2lyr/ultimo_dir", carpeta_dato)
        salida, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(), u"Guardar .lyr como",
            os.path.join(ultimo_dir, sugerido), u"ArcMap layer (*.lyr)")
        if not salida:
            return
        if not salida.lower().endswith(u".lyr"):
            salida += u".lyr"
        s.setValue("qml2lyr/ultimo_dir", os.path.dirname(salida))

        # Volcar el estilo vivo a un .qml temporal.
        tmp_qml = os.path.join(
            tempfile.gettempdir(), u"qml2lyr_%d.qml" % os.getpid())
        try:
            ret = layer.saveNamedStyle(tmp_qml)
            msg = ret[0] if isinstance(ret, (tuple, list)) and ret else u""
        except Exception as e:
            msg = str(e)
        if not os.path.isfile(tmp_qml):
            self._error(u"No se pudo exportar el estilo",
                        u"QGIS no generó el .qml de la capa.\n\n%s" % msg)
            return

        # El emisor es sincrono y arrancar ArcObjects tarda varios segundos, asi
        # que el hilo de UI se bloquea. No hay progreso real posible sin mover el
        # emisor a un hilo/QProcess; al menos pintamos el mensaje y ponemos el
        # cursor de espera antes de bloquear.
        self.iface.messageBar().pushMessage(
            MENU, u"Generando .lyr… (ArcMap tarda unos segundos en arrancar)",
            level=nivel_mensaje("Info"), duration=3)
        QApplication.setOverrideCursor(cursor_espera())
        QApplication.processEvents()  # fuerza el repintado del mensaje/cursor
        try:
            data = ejecutar_qml(py27, emisor, tmp_qml, ruta_dato, salida,
                                nombre=nombre, defquery=defquery,
                                servicio=servicio)
        except EmisorError as e:
            self._error(u"Error al ejecutar el emisor", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
            try:
                os.remove(tmp_qml)
            except OSError:
                pass

        self._mostrar_resultado(data)

    # -------------------------------------------------------- proyecto a mxd
    def exportar_mxd(self):
        """El proyecto guardado -> .mxd con el mismo arbol de capas."""
        if self._tarea is not None:
            self._warn(u"Ya hay una exportación a .mxd en marcha.")
            return
        proyecto = QgsProject.instance()
        qgz = proyecto.fileName()
        if not qgz:
            self._warn(u"Guarda el proyecto primero: el .mxd se hace a partir "
                       u"del proyecto guardado en disco.")
            return
        if proyecto.isDirty():
            resp = QMessageBox.question(
                self.iface.mainWindow(), u"qml2lyr",
                u"El proyecto tiene cambios sin guardar y el .mxd se hace a "
                u"partir del fichero en disco.\n\n¿Guardar ahora?",
                boton_mensaje("Save") | boton_mensaje("Ignore")
                | boton_mensaje("Cancel"))
            if resp == boton_mensaje("Cancel"):
                return
            if resp == boton_mensaje("Save") and not proyecto.write():
                self._error(u"No se pudo guardar el proyecto",
                            proyecto.error())
                return

        try:
            py27, emisor = rutas.resolver()
        except rutas.RutaNoValida as e:
            self._error(u"qml2lyr no está listo", str(e))
            return

        sugerido = os.path.splitext(qgz)[0] + u".mxd"
        salida, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(), u"Exportar proyecto a .mxd", sugerido,
            u"ArcMap (*.mxd)")
        if not salida:
            return
        if not salida.lower().endswith(u".mxd"):
            salida += u".mxd"
        if os.path.exists(salida):
            # El dialogo ya pregunto si sobrescribir, pero el motor no
            # sobrescribe a proposito (un .mxd a mano no se pisa): se dice
            # antes de lanzar nada.
            self._error(u"qml2lyr", u"%s ya existe.\n\nqml2lyr no sobrescribe "
                        u"un .mxd: elige otro nombre o borra el existente."
                        % salida)
            return

        remap = rutas.reglas_remap()
        plantilla = rutas.plantilla_mxd()
        self._tarea = TareaMxd(py27, emisor, qgz, salida, plantilla, remap,
                               self._fin_mxd)
        QgsApplication.taskManager().addTask(self._tarea)
        self.iface.messageBar().pushMessage(
            MENU, u"Exportando el proyecto a %s… (en segundo plano)"
            % os.path.basename(salida), level=nivel_mensaje("Info"),
            duration=5)

    def _fin_mxd(self, data, error):
        self._tarea = None
        if error:
            self._error(u"Error al exportar a .mxd", error)
            return
        titulo, texto, ok = resumen_mxd(data)
        self.iface.messageBar().pushMessage(
            MENU, titulo, level=nivel_mensaje("Success" if ok else "Critical"),
            duration=10)
        if ok:
            QMessageBox.information(self.iface.mainWindow(),
                                    u"qml2lyr: " + titulo, texto)
        else:
            self._error(u"qml2lyr: " + titulo, texto)

    def abrir_ajustes(self):
        dlg = SettingsDialog(self.iface.mainWindow())
        # exec_ en Qt5, exec en Qt6.
        (dlg.exec_ if hasattr(dlg, "exec_") else dlg.exec)()

    # --------------------------------------------------------------- reportes
    def _mostrar_resultado(self, data):
        # Fallo global de parseo del .qml (sin capas).
        if not data.get("capas"):
            self._error(
                u"No se pudo convertir el estilo",
                u"%s\n(%s)" % (data.get("error", u"error desconocido"),
                               data.get("tipo_error", u"")))
            return

        capas = data.get("capas", [])
        oks = [c for c in capas if c.get("ok")]
        fallos = [c for c in capas if not c.get("ok")]

        if oks and not fallos:
            nivel = nivel_mensaje("Success")
            resumen = u"Generado: %s" % u", ".join(
                os.path.basename(c.get("salida", u"")) for c in oks)
        elif oks and fallos:
            nivel = nivel_mensaje("Warning")
            resumen = u"%d capa(s) generada(s), %d con error." % (len(oks), len(fallos))
        else:
            nivel = nivel_mensaje("Critical")
            resumen = u"No se generó ningún .lyr."

        detalle = []
        for c in fallos:
            detalle.append(u"✗ %s: %s" % (c.get("nombre", u"?"), c.get("error", u"")))
        avisos = []
        for c in capas:
            for a in c.get("avisos", []):
                avisos.append(u"• [%s] %s" % (c.get("nombre", u"?"), a))
        # Avisos globales del emisor (p.ej. un temporal que no se pudo borrar).
        for a in data.get("avisos", []):
            avisos.append(u"• %s" % a)
        if avisos:
            detalle.append(u"")
            detalle.append(u"Avisos (degradaciones respecto a QGIS):")
            detalle.extend(avisos)

        self.iface.messageBar().pushMessage(MENU, resumen, level=nivel, duration=8)
        if detalle:
            texto = u"\n".join(detalle)
            if fallos:
                self._error(u"qml2lyr: resultado", texto)
            else:
                QMessageBox.information(self.iface.mainWindow(),
                                        u"qml2lyr: avisos", texto)

    def _warn(self, texto):
        self.iface.messageBar().pushMessage(MENU, texto,
                                            level=nivel_mensaje("Warning"),
                                            duration=7)

    def _error(self, titulo, texto):
        QMessageBox.critical(self.iface.mainWindow(), titulo, texto)

    @staticmethod
    def _nombre_fichero(nombre):
        limpio = re.sub(r"[^0-9A-Za-z._-]+", "_", nombre or "capa").strip("_")
        return limpio or "capa"


class TareaMxd(QgsTask):
    """El subproceso del modo MXD en segundo plano. `al_terminar(data, error)`
    se llama en el hilo principal (desde `finished`), que es donde se puede
    tocar la interfaz.

    Cancelar no corta el subproceso (ArcObjects no tiene por donde): la tarea
    no se ofrece como cancelable."""

    def __init__(self, py27, emisor, qgz, salida, plantilla, remap,
                 al_terminar):
        QgsTask.__init__(self, u"qml2lyr: exportar a .mxd", tarea_sin_flags())
        self._args = (py27, emisor, qgz, salida, plantilla, remap)
        self._al_terminar = al_terminar
        self._data = None
        self._error = None

    def run(self):
        py27, emisor, qgz, salida, plantilla, remap = self._args
        try:
            self._data = ejecutar_mxd(py27, emisor, qgz, salida,
                                      plantilla=plantilla, remap=remap)
        except EmisorError as e:
            self._error = str(e)
        except Exception as e:  # nunca callar: se muestra al terminar
            self._error = u"%s: %s" % (type(e).__name__, e)
        return True

    def finished(self, resultado):
        self._al_terminar(self._data, self._error)

