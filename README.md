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
- El Python 2.7 de ArcGIS: `C:\Python27\ArcGIS10.5\python.exe`. ArcGIS **no**
  trae `comtypes`, pero el zip del plugin ya lo lleva dentro. Solo hace falta
  instalarlo (`python.exe -m pip install comtypes==1.1.7`) para usar el motor
  desde la línea de comandos, sin el plugin.
- Sin red, sin base de datos, sin credenciales.

## Instalación y uso

Descarga `qml2lyr-qgis-plugin-X.Y.Z.zip` del último [release](https://github.com/pedralcg/qml2lyr/releases/latest)
(no los «Source code», que son el repositorio) e instálalo en QGIS con **Complementos → Administrar e instalar complementos →
Instalar a partir de ZIP**. No hay que configurar nada: el zip lleva el motor y
el Python 2.7 de ArcGIS 10.5 se detecta solo. Detalles y la instalación desde el
repositorio, en [`plugin/README.md`](plugin/README.md).

El motor también se usa sin QGIS, desde la línea de comandos:

```
C:\Python27\ArcGIS10.5\python.exe src\emisor.py <estilo.qml> <dato> <salida.lyr> [--defquery "..."]
C:\Python27\ArcGIS10.5\python.exe src\emisor.py --batch <proyecto.qgz> <carpeta_salida>
```

El modo `--batch` convierte todas las capas de un proyecto. Una capa que falla
se informa y se salta; el lote sigue.

Si el proyecto apunta a una unidad que en esta máquina se llama de otra forma
(`Z:` es `L:\Mi unidad\Carto`), `--remap` lee el dato donde está y deja el
`.lyr` apuntando a la ruta del proyecto. Es repetible:

```
... --batch proyecto.qgz salida --remap "Z:=L:\Mi unidad\Carto"
```

Si la unidad original no existe aquí, el `.lyr` sale igual y la capa lleva un
aviso: ArcMap la verá rota hasta abrirla donde esa unidad exista.

## Tests

```
C:\Python27\ArcGIS10.5\python.exe tests\test_parser.py     # parser, sin ArcGIS (es lo que corre el CI)
C:\Python27\ArcGIS10.5\python.exe run_regresion_qml.py     # cadena completa hasta el .lyr, con ArcGIS 10.5
```

`run_regresion_qml.py` se fabrica sus datos sintéticos con arcpy (en `tmp/`, fuera
de git) y comprueba cada `.lyr` volcándolo con `src/lyr_dump.py`. Los fixtures
los escribe QGIS de verdad (`tests/generar_fixtures_qgis.py`), no la mano:
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
