# -*- coding: utf-8 -*-
"""Enums de Qt/QGIS con y sin scope: mismo codigo en QGIS 3.44 (Qt5) y 4 (Qt6).

En Qt6 los enums son de scope obligatorio (`Qt.CursorShape.WaitCursor`); en Qt5
se usaban sin el (`Qt.WaitCursor`). PyQt5 acepta los dos, pero PyQt6 solo el
primero, asi que se busca primero la forma con scope y se cae a la legada. Sin
esto el plugin revienta con AttributeError en QGIS 4 y no arranca.
"""


def _scoped(clase, scope, nombre):
    """Miembro `nombre` del enum, con scope si existe y sin el si no."""
    contenedor = getattr(clase, scope, None)
    if contenedor is not None and hasattr(contenedor, nombre):
        return getattr(contenedor, nombre)
    # Si tampoco esta sin scope, que salte el AttributeError: es un enum que
    # cambio de nombre y hay que enterarse, no tragarselo.
    return getattr(clase, nombre)


def cursor_espera():
    """Qt.CursorShape.WaitCursor (Qt6) / Qt.WaitCursor (Qt5)."""
    from qgis.PyQt.QtCore import Qt
    return _scoped(Qt, "CursorShape", "WaitCursor")


def nivel_mensaje(nombre):
    """Qgis.MessageLevel.<nombre> / Qgis.<nombre>. nombre: Info, Success,
    Warning, Critical."""
    from qgis.core import Qgis
    return _scoped(Qgis, "MessageLevel", nombre)


def tipos_capa():
    """Tipos de capa para addCustomActionForLayerType (moderno o legado)."""
    from qgis.core import Qgis, QgsMapLayer
    try:
        return [Qgis.LayerType.Vector, Qgis.LayerType.Raster]
    except AttributeError:
        return [QgsMapLayer.VectorLayer, QgsMapLayer.RasterLayer]


def botones_ok_cancel():
    """QDialogButtonBox.StandardButton.Ok|Cancel (Qt6) o sin scope (Qt5)."""
    from qgis.PyQt.QtWidgets import QDialogButtonBox
    return (_scoped(QDialogButtonBox, "StandardButton", "Ok")
            | _scoped(QDialogButtonBox, "StandardButton", "Cancel"))
