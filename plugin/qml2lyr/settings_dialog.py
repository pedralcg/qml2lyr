# -*- coding: utf-8 -*-
"""Dialogo de ajustes: rutas al Python 2.7 de ArcGIS y a emisor.py.

Se guardan en QSettings (clave `qml2lyr/...`). No se hardcodean en el codigo:
cada equipo puede tener ArcGIS y el repo en rutas distintas (gotcha de rutas
absolutas del proyecto).
"""

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QDialogButtonBox,
)

from .compat_qt import botones_ok_cancel

# Ruta de instalacion por defecto de ArcGIS 10.5; el usuario lo cambia si su ArcGIS esta en otro sitio.
DEFAULT_PY27 = r"C:\Python27\ArcGIS10.5\python.exe"


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle(u"qml2lyr — ajustes")
        self.setMinimumWidth(520)

        s = QSettings()
        py27 = s.value("qml2lyr/python27", DEFAULT_PY27)
        emisor = s.value("qml2lyr/emisor", "")

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(u"Python 2.7 de ArcGIS 10.5 (python.exe):"))
        self.ed_py27, fila1 = self._fila(
            py27, u"Selecciona python.exe de ArcGIS", u"python.exe (python.exe)")
        lay.addLayout(fila1)

        lay.addWidget(QLabel(u"Ruta a emisor.py (carpeta src del repo qml2lyr):"))
        self.ed_emisor, fila2 = self._fila(
            emisor, u"Selecciona emisor.py", u"emisor.py (emisor.py)")
        lay.addLayout(fila2)

        bb = QDialogButtonBox(botones_ok_cancel())
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _fila(self, valor, titulo, filtro):
        row = QHBoxLayout()
        ed = QLineEdit(valor or "")
        btn = QPushButton(u"…")
        btn.setFixedWidth(32)

        def browse():
            f, _ = QFileDialog.getOpenFileName(self, titulo, ed.text(), filtro)
            if f:
                ed.setText(f)

        btn.clicked.connect(browse)
        row.addWidget(ed)
        row.addWidget(btn)
        return ed, row

    def accept(self):
        s = QSettings()
        s.setValue("qml2lyr/python27", self.ed_py27.text().strip())
        s.setValue("qml2lyr/emisor", self.ed_emisor.text().strip())
        QDialog.accept(self)
