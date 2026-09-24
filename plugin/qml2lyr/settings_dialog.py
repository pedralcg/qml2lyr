# -*- coding: utf-8 -*-
"""Dialogo de ajustes: rutas al Python 2.7 de ArcGIS y a emisor.py.

Las dos son OPCIONALES: vacias, el plugin detecta el Python de ArcGIS 10.5 por
el registro y usa el motor que lleva dentro (ver `rutas.py`). Rellenarlas sirve
para un ArcGIS en ruta no estandar o, en desarrollo, para apuntar al `src/` del
repositorio. Se guardan en QSettings (`qml2lyr/...`), nunca en el codigo.
"""

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QDialogButtonBox,
)

from . import rutas
from .compat_qt import botones_ok_cancel


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle(u"qml2lyr — ajustes")
        self.setMinimumWidth(560)

        s = QSettings()
        lay = QVBoxLayout(self)
        nota = QLabel(u"Normalmente no hay que tocar nada: deja los campos "
                      u"vacíos y qml2lyr lo encuentra solo.")
        nota.setWordWrap(True)
        lay.addWidget(nota)

        detectado = rutas.detectar_python27()
        lay.addWidget(QLabel(u"Python 2.7 de ArcGIS 10.5 (python.exe):"))
        self.ed_py27, fila1 = self._fila(
            s.value("qml2lyr/python27", ""),
            u"automático: %s" % detectado if detectado
            else u"no detectado: indica el python.exe de ArcGIS 10.5",
            u"Selecciona python.exe de ArcGIS", u"python.exe (python.exe)")
        lay.addLayout(fila1)

        lay.addWidget(QLabel(u"Motor (emisor.py):"))
        self.ed_emisor, fila2 = self._fila(
            s.value("qml2lyr/emisor", ""),
            u"automático: el incluido en el plugin" if rutas.emisor_incluido()
            else u"falta el motor incluido: reinstala el plugin",
            u"Selecciona emisor.py", u"emisor.py (emisor.py)")
        lay.addLayout(fila2)

        bb = QDialogButtonBox(botones_ok_cancel())
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _fila(self, valor, ayuda, titulo, filtro):
        row = QHBoxLayout()
        ed = QLineEdit(valor or "")
        ed.setPlaceholderText(ayuda)
        ed.setClearButtonEnabled(True)
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
