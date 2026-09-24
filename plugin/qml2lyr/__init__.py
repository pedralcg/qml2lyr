# -*- coding: utf-8 -*-
"""Plugin QGIS qml2lyr: guarda el estilo de la capa activa como .lyr de ArcMap.

Punto de entrada que QGIS invoca al cargar el plugin. La logica vive en
qml2lyr_plugin.Qml2LyrPlugin. El .lyr lo escribe el motor ArcObjects (py2.7 de
ArcGIS) por subproceso; este plugin (py3 de QGIS) solo prepara el .qml y lanza
el emisor (ADR-001).
"""


def classFactory(iface):  # noqa: N802 (nombre exigido por la API de QGIS)
    from .qml2lyr_plugin import Qml2LyrPlugin
    return Qml2LyrPlugin(iface)
