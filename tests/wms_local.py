# -*- coding: utf-8 -*-
"""Servidor WMS minimo en local para los tests: sin red externa.

Lo arrancan el generador de fixtures (py3, para que QGIS escriba de verdad el
.qgz con una capa WMS) y la regresion (py2.7, para que ArcObjects se conecte).
Responde GetCapabilities con un arbol fijo y cualquier otra peticion con un
PNG de 1x1.

Los NOMBRES de capa difieren de sus TITULOS a proposito: QGIS pide las capas
por nombre (`layers=`) y ArcMap las muestra por titulo, asi que un emisor que
casara por titulo encenderia lo que no es.
"""
import base64
import threading

try:  # py3
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:  # py2.7
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

PUERTO = 8765
URL = "http://127.0.0.1:%d/wms" % PUERTO

#: Hojas del servicio, en el orden de GetCapabilities: (nombre, titulo).
HOJAS = [("parcelas", "Parcelas catastrales"), ("masas", "Masas"),
         ("textos", "Textos")]

_CAPA = """<Layer queryable="0"><Name>%s</Name><Title>%s</Title>
<CRS>EPSG:25830</CRS>
<EX_GeographicBoundingBox><westBoundLongitude>-2</westBoundLongitude>
<eastBoundLongitude>-1</eastBoundLongitude><southBoundLatitude>37</southBoundLatitude>
<northBoundLatitude>38</northBoundLatitude></EX_GeographicBoundingBox>
<BoundingBox CRS="EPSG:25830" minx="500000" miny="4100000" maxx="700000" maxy="4300000"/>
</Layer>"""

CAPABILITIES = ("""<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms"
 xmlns:xlink="http://www.w3.org/1999/xlink">
<Service><Name>WMS</Name><Title>WMS local de qml2lyr</Title>
<OnlineResource xlink:href="%(url)s"/></Service>
<Capability>
<Request>
<GetCapabilities><Format>text/xml</Format><DCPType><HTTP><Get>
<OnlineResource xlink:href="%(url)s?"/></Get></HTTP></DCPType></GetCapabilities>
<GetMap><Format>image/png</Format><DCPType><HTTP><Get>
<OnlineResource xlink:href="%(url)s?"/></Get></HTTP></DCPType></GetMap>
</Request>
<Exception><Format>XML</Format></Exception>
<Layer><Title>Raiz</Title><CRS>EPSG:25830</CRS>
<EX_GeographicBoundingBox><westBoundLongitude>-2</westBoundLongitude>
<eastBoundLongitude>-1</eastBoundLongitude><southBoundLatitude>37</southBoundLatitude>
<northBoundLatitude>38</northBoundLatitude></EX_GeographicBoundingBox>
<Layer><Name>catastro</Name><Title>Cartografia catastral</Title>
%(hojas)s
</Layer>
</Layer>
</Capability>
</WMS_Capabilities>
""" % {"url": URL, "hojas": "\n".join(_CAPA % h for h in HOJAS)}).encode("utf-8")

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA"
    "60e6kgAAAABJRU5ErkJggg==")


class _Manejador(BaseHTTPRequestHandler):
    def do_GET(self):
        if "getcapabilities" in self.path.lower():
            cuerpo, tipo = CAPABILITIES, "text/xml"
        else:
            cuerpo, tipo = _PNG_1X1, "image/png"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *args):
        pass


def arrancar():
    """Arranca el servidor en un hilo y lo devuelve (llamar a .shutdown())."""
    servidor = HTTPServer(("127.0.0.1", PUERTO), _Manejador)
    hilo = threading.Thread(target=servidor.serve_forever)
    hilo.daemon = True
    hilo.start()
    return servidor
