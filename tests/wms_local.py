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
URL_WMTS = "http://127.0.0.1:%d/wmts" % PUERTO

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

# WMTS con dos matrices de teselas. La de 4326 va PRIMERO a proposito: al
# conectar, ArcObjects se queda con la primera aunque se le pida otra (medido
# con el WMTS del IGN, 2026-09-25), asi que un emisor que no fije la matriz
# despues de conectar sale con la que no es.
_OP = """<ows:Operation name="%%s"><ows:DCP><ows:HTTP><ows:Get xlink:href="%s?">
<ows:Constraint name="GetEncoding"><ows:AllowedValues><ows:Value>KVP</ows:Value>
</ows:AllowedValues></ows:Constraint></ows:Get></ows:HTTP></ows:DCP></ows:Operation>""" % URL_WMTS

CAPABILITIES_WMTS = ("""<?xml version="1.0" encoding="UTF-8"?>
<Capabilities xmlns="http://www.opengis.net/wmts/1.0"
 xmlns:ows="http://www.opengis.net/ows/1.1" xmlns:xlink="http://www.w3.org/1999/xlink"
 version="1.0.0">
<ows:ServiceIdentification><ows:Title>WMTS local de qml2lyr</ows:Title>
<ows:ServiceType>OGC WMTS</ows:ServiceType><ows:ServiceTypeVersion>1.0.0</ows:ServiceTypeVersion>
</ows:ServiceIdentification>
<ows:OperationsMetadata>%(get_cap)s%(get_tile)s</ows:OperationsMetadata>
<Contents>
<Layer><ows:Title>Mapa base</ows:Title>
<ows:WGS84BoundingBox><ows:LowerCorner>-2 37</ows:LowerCorner>
<ows:UpperCorner>-1 38</ows:UpperCorner></ows:WGS84BoundingBox>
<ows:Identifier>mapa</ows:Identifier>
<Style isDefault="true"><ows:Identifier>default</ows:Identifier></Style>
<Format>image/png</Format><Format>image/jpeg</Format>
<TileMatrixSetLink><TileMatrixSet>EPSG:4326</TileMatrixSet></TileMatrixSetLink>
<TileMatrixSetLink><TileMatrixSet>EPSG:25830</TileMatrixSet></TileMatrixSetLink>
</Layer>
<TileMatrixSet><ows:Identifier>EPSG:4326</ows:Identifier>
<ows:SupportedCRS>urn:ogc:def:crs:EPSG::4326</ows:SupportedCRS>
<TileMatrix><ows:Identifier>0</ows:Identifier>
<ScaleDenominator>279541132.0143589</ScaleDenominator>
<TopLeftCorner>90 -180</TopLeftCorner><TileWidth>256</TileWidth>
<TileHeight>256</TileHeight><MatrixWidth>2</MatrixWidth><MatrixHeight>1</MatrixHeight>
</TileMatrix></TileMatrixSet>
<TileMatrixSet><ows:Identifier>EPSG:25830</ows:Identifier>
<ows:SupportedCRS>urn:ogc:def:crs:EPSG::25830</ows:SupportedCRS>
<TileMatrix><ows:Identifier>0</ows:Identifier><ScaleDenominator>1000000</ScaleDenominator>
<TopLeftCorner>0 5000000</TopLeftCorner><TileWidth>256</TileWidth>
<TileHeight>256</TileHeight><MatrixWidth>4</MatrixWidth><MatrixHeight>4</MatrixHeight>
</TileMatrix></TileMatrixSet>
</Contents></Capabilities>
""" % {"get_cap": _OP % "GetCapabilities", "get_tile": _OP % "GetTile"}).encode("utf-8")

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA"
    "60e6kgAAAABJRU5ErkJggg==")


class _Manejador(BaseHTTPRequestHandler):
    def do_GET(self):
        ruta = self.path.lower()
        if "getcapabilities" in ruta and ruta.startswith("/wmts"):
            cuerpo, tipo = CAPABILITIES_WMTS, "text/xml"
        elif "getcapabilities" in ruta:
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
