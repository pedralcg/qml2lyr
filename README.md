# qml2lyr

Plugin de QGIS que guarda el estilo de una capa como `.lyr` de **ArcMap 10.5**:
clic derecho sobre la capa → **«Guardar estilo como .lyr…»**. Vectorial y ráster.

Cubre la dirección **QGIS → ArcMap**, que [SLYR](https://north-road.com/slyr/)
no ofrece en su versión gratuita (esa hace ArcMap → QGIS).

## Por qué existe

En equipos que trabajan con QGIS y tienen que entregar en ArcMap, la simbología
se rehace a mano capa por capa: categorías, colores, grosores, tramas, filtros.
qml2lyr lee el estilo que ya tienes en QGIS y escribe el `.lyr` equivalente.

## Cómo funciona

El plugin corre en el Python 3 de QGIS, pero escribir un `.lyr` exige
**ArcObjects**, que solo vive en el Python 2.7 de ArcGIS 10.5. No pueden
compartir proceso, así que el plugin exporta el estilo de la capa y lanza el
motor (`src/emisor.py`) como subproceso:

```
capa de QGIS ──saveNamedStyle──▶ estilo.qml ─┐
             ──subsetString()──▶ def-query  ─┼─▶ emisor.py (py2.7 + ArcObjects) ──▶ capa.lyr
                                             ┘         │
                                         JSON por stdout: avisos y errores por capa
```

La regla del motor es **avisar y saltar, nunca callar**: lo que ArcMap no puede
representar se avisa en el resultado, y lo que no se sabe traducir se rechaza
con un mensaje que dice qué cambiar. Nunca se sustituye en silencio por un
estilo por defecto.

## Qué convierte

| | |
|---|---|
| **Renderers** | símbolo único, categorizado, graduado y basado en reglas (un `.lyr` por regla, con su definition query) |
| **Relleno** | sólido, hueco, tramado (6 patrones), multicapa, relleno con imagen |
| **Línea** | `solid`, `dash`, `dot`, `dash dot`, `dash dot dot` |
| **Marcador** | círculo, cuadrado, cruz, equis y diamante; triángulo, pentágono, hexágono, octógono y estrella con glifos de la fuente *ESRI Default Marker*; rotación |
| **Capa** | definition query, opacidad, visibilidad por escala |
| **Ráster** | paletado (valores únicos), pseudocolor discreto (clases) e interpolado (estirado) |
| **Datos** | shapefile, ráster de fichero y GeoPackage |

Lo que **no** convierte (etiquetas, expresiones, propiedades definidas por datos,
ArcGIS Pro `.lyrx`…) y por qué está en [`docs/limitaciones.md`](docs/limitaciones.md).

## Requisitos

- Windows con **QGIS 3.22+** y **ArcGIS Desktop 10.5** (licencia Advanced) en la
  misma máquina.
- El Python 2.7 de ArcGIS: `C:\Python27\ArcGIS10.5\python.exe` (trae `comtypes`).
- Sin red, sin base de datos, sin credenciales.

## Instalación y uso

Instrucciones del plugin en [`plugin/README.md`](plugin/README.md). En resumen:
copiar `plugin/qml2lyr` al perfil de QGIS (`plugin/deploy.ps1`), activarlo y
decirle en sus ajustes dónde están el Python 2.7 de ArcGIS y `src/emisor.py`.

El motor también se usa sin QGIS, desde la línea de comandos:

```
C:\Python27\ArcGIS10.5\python.exe src\emisor.py <estilo.qml> <dato> <salida.lyr> [--defquery "..."]
C:\Python27\ArcGIS10.5\python.exe src\emisor.py --batch <proyecto.qgz> <carpeta_salida>
```

El modo `--batch` convierte todas las capas de un proyecto. Una capa que falla
se informa y se salta; el lote sigue.

## Tests

```
C:\Python27\ArcGIS10.5\python.exe tests\test_parser.py     # parser, sin ArcGIS (es lo que corre el CI)
C:\Python27\ArcGIS10.5\python.exe run_regresion_qml.py     # cadena completa hasta el .lyr, con ArcGIS 10.5
```

`run_regresion_qml.py` se fabrica sus datos sintéticos con arcpy (en `tmp/`, fuera
de git) y comprueba cada `.lyr` volcándolo con `src/lyr_dump.py`. Los fixtures
nuevos los escribe QGIS de verdad (`tests/generar_fixtures_qgis.py`), no la mano:
un fixture escrito a mano solo prueba lo que *suponemos* que escribe QGIS.

## Estructura

```
src/        parser del XML de QGIS → modelo intermedio → emisor (arcpy + ArcObjects)
plugin/     el plugin de QGIS
tests/      fixtures (.qml, .qgz) y tests del parser
docs/       limitaciones conocidas
```

El modelo intermedio (`src/modelo.py`) no sabe nada de QGIS ni de ArcMap: está
pensado para añadir en el futuro un emisor de `.lyrx` sin tocar el parser.

## Licencia

MIT. Código propio: no incorpora código de SLYR (GPL).
