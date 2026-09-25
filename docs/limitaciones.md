# Limitaciones conocidas de qml2lyr (F6)

> Qué **no** reproduce el motor QGIS → ArcMap y por qué. La regla de oro del
> proyecto es *avisar y saltar, nunca callar*: casi todo lo de aquí se emite en
> tiempo real como `aviso` en el JSON del emisor y el plugin lo muestra en la UI.
> Este documento consolida esos avisos.
>
> Última revisión: 2026-09-24 · Referencia técnica: `CLAUDE.md` del repo.

## 1. Fuera del alcance del MVP (no-gos, por diseño)

No se convierten y así se decidió en el kickoff / ADR-001:

- **Dirección inversa** ArcMap → QGIS (`.lyr` → `.qml`). La cubre SLYR Community gratis.
- **ArcGIS Pro `.lyrx`** (JSON/CIM). Fase 2 futura; no necesitaría ArcObjects.
- **Etiquetas.** Si la capa lleva etiquetas activas, el `.lyr` sale **sin ellas**
  (se avisa: *"la capa lleva etiquetas activas en QGIS: el .lyr sale sin ellas"*).
- **Rule-based por expresión arbitraria**, geometry-generators, data-defined
  properties, expresiones. Solo se soporta el rule-based que se traduce a
  def-query simple (un `.lyr` por regla). Una propiedad **data-defined activa**
  se **avisa** (nombrando cuál): ArcMap emite el valor fijo del estilo.
- **Clasificación por expresión** (un `renderer-v2` cuyo `attr` no es un nombre
  de campo): se rechaza con mensaje explícito. Sí se aceptan nombres de campo
  con tilde o ñ (`"Año"`, `Señal_2`).

## 2. Tipos de dato que el plugin rechaza (avisa y sale)

El `.lyr` necesita un dato que arcpy pueda abrir por ruta:

- **Capas de memoria, PostGIS, WMS/WFS**: sin fichero → no convertibles.
- **GeoPackage**: **sí se convierte** desde 2026-09-20. arcpy 10.5 abre la capa
  como `ruta.gpkg\main.<layername>` (verificado con `MakeFeatureLayer` y con una
  emisión completa a `.lyr`). Requisito: que el origen de la capa en QGIS diga
  qué capa del contenedor usa (`…gpkg|layername=…`). Si no lo dice, se avisa
  con instrucciones (volver a añadirla desde el selector de capas del GPKG) —
  antes esto acababa en un error críptico de arcpy.
  **Con un PUNTO en el nombre de la tabla no funciona** (`|layername=t12_2_…_12.1`):
  arcpy 10.5 interpreta el punto como separador de esquema, `Exists()` da
  `False` y `MakeFeatureLayer` casca con `ERROR 000732` **culpando al
  dataset**, que manda a buscar el fallo donde no está. Medido el 2026-09-21
  (el mismo GPKG con el punto cambiado por `_` abre sin problema); desde esa
  fecha se detecta antes y se avisa diciendo que hay que renombrar la tabla.
- **Otros contenedores multicapa** (`.kml|layername=…`, `.sqlite`…): se rechazan
  con mensaje claro; hay que exportar a shapefile.
- **Definition query**: **ya no se pierde**. Viaja por `subsetString()` de la
  capa viva (plugin) o por el `|subset=` del datasource (batch), y se combina
  con la de cada regla cuando el renderer es rule-based. Desde el 2026-09-21
  soporta un `|` **dentro** del SQL (un literal `'x|y'`, el concatenador `||`):
  antes se partía por todos los `|` y la def-query se **truncaba en silencio**.

## 3. Degradaciones que ArcMap 10.5 no puede representar (se avisan)

ArcMap tiene menos expresividad que QGIS en varios puntos. El motor emite el
símbolo más fiel posible y **avisa** de la pérdida:

- **Transparencia alfa por color** (relleno, contorno, marcador, parada de rampa
  con alpha < 255): *"el SÍMBOLO se emite opaco, ArcMap no tiene alfa por
  símbolo"*. ArcMap solo tiene transparencia **de capa entera**, y esa sí viaja
  (`layerOpacity` → `transparencia_pct`).
  **Ojo al leer el aviso** (redactado de nuevo el 2026-09-21, porque el texto
  anterior — *"ArcMap lo pinta opaco"* — se leía como una contradicción en una
  capa que en ArcMap se veía translúcida): son **dos transparencias
  distintas**. Lo que se pierde no es "algo de transparencia", es la
  **diferencia entre clases**: dos clases con alfa 90/255 y 50/255 acaban
  igual de opacas bajo la misma transparencia de capa.
- **Offset del tramado** (`LinePatternFill` con `offset` ≠ 0): `ILineFillSymbol`
  no desplaza el patrón; se dibuja sin ese desplazamiento. Se avisa desde el
  2026-09-21 (antes se perdía mudo; hay casos reales con `offset=1.5`).
- **RasterFill (relleno con imagen)**: se emite como `PictureFillSymbol`, pero el
  **tamaño exacto del mosaico** (no se fija XScale/YScale) y la **transparencia
  alfa** (ArcMap usa color-clave, no alfa) quedan para **QA visual**.
- **Símbolos multicapa** (relleno hueco + trama = Red Natura / ENP): el orden de
  índices está verificado, pero el **dibujado** queda pendiente de **QA visual**.
- **symbol-layers desactivados** en QGIS: no se emiten (se avisa cuántos).
- **Categorías / intervalos ocultos** en QGIS: no se emiten (se avisa por cada uno).
- **Trazo discontinuo con ancho ≥ 2 pt**: ArcMap lo dibuja **continuo**. Medido
  por render el 2026-09-20 (`dash`, `dot`, `dash dot` a 0,5 / 1 / 2 / 3 / 6 pt:
  a partir de 2 pt sale una sola línea). El patrón de `esriSimpleLineStyle` está
  en unidades de dispositivo y lo tapa el grosor de la pluma. Se emite el estilo
  pedido y **se avisa**.
- **Guion personalizado** (`use_custom_dash="1"`): QGIS **ignora** `line_style` y
  dibuja el patrón de `customdash`. ArcMap no lo reproduce y la línea sale con
  el `line_style` (normalmente `solid`) → **aviso fuerte**, con el patrón que se
  pierde.
- **`offset` de línea o de marcador**: ArcMap dibuja sobre el eje / centrado en
  el punto (se avisa con el desplazamiento y su unidad).
- **Borde de marcador con ancho 0**: en QGIS es un *hairline* (1 px) y sí se ve.
  ArcMap no tiene hairline y un ancho mínimo inventado engordaría el símbolo a
  cualquier escala de impresión → el `.lyr` sale **sin borde** y se avisa
  (decisión 2026-09-20; la solución es poner un ancho explícito en QGIS).
- **Formas de marcador**: ArcMap solo tiene `circle`, `square`, `cross`,
  `cross2` y `diamond` en `SimpleMarkerSymbol`. `triangle`,
  `equilateral_triangle`, `pentagon`, `hexagon`, `octagon` y `star` se dibujan
  con un **glifo de la fuente *ESRI Default Marker*** (verificado por render el
  2026-09-24): el tamaño es **aproximado** (90-105 % del de QGIS) y el borde sale
  como **halo** por fuera de la forma. Se avisa. El resto (`arrow`,
  `half_square`, `heart`…) se **rechaza** con mensaje explícito: no hay glifo
  verificado y no se inventa. **Sí** viaja la rotación (`angle`), con el
  sentido invertido (QGIS gira en horario y ArcMap en antihorario).
- **Visibilidad por escala de una REGLA** (`scalemindenom`/`scalemaxdenom` en un
  rule-based): se ignora y se avisa. ArcMap solo tiene escalas por capa, y la
  capa ya lleva las suyas (esas **sí** se trasladan).
- **Categoría «Todos los demás valores»** (la categoría NULL de QGIS): pasa al
  **símbolo por defecto** de ArcMap. En QGIS esa categoría recoge los nulos y
  todo valor sin categoría propia, igual que el símbolo por defecto de ArcMap
  (medido en los dos programas el 2026-09-25). Hasta esa fecha se emitía como
  una clase `<Null>` y en ArcMap **no se dibujaban** los valores sin categoría.

### Ráster, específico

- **Valores ocultos por transparencia** (`rasterTransparency`): ArcMap no tiene
  transparencia por clase. El 100% oculto se reproduce con símbolo nulo
  (p.ej. el 0 "No combustible" de un ráster de modelos de combustible); transparencias
  parciales solo se avisan.
- **Clase con alfa 0** (invisible en QGIS):
  - *paletted*: **se reproduce** con símbolo nulo, igual que las ocultas por
    `<rasterTransparency>`. Antes salía opaca y sin aviso.
  - *pseudocolor DISCRETE / INTERPOLATED*: ArcMap no puede ocultar una clase ni
    una parada de estos renderers → sale **opaca** y se **avisa**.
- **Valor de celda fuera de la paleta**: ArcMap lo deja **transparente**
  (verificado por render el 2026-09-20). No hay nada que emitir; se documenta
  para que no se confunda con un fallo de conversión.
- **Banda alfa** del ráster: ArcMap no la aplica (se avisa).
- **Shader con `clip` activo**: ArcMap no recorta igual (se avisa).
- **Estirado (INTERPOLATED)**: usa el min/max del **dataset**, no el rango de la
  clasificación QGIS. Si difieren, la leyenda cambiaría de reparto → se **avisa**
  para que el usuario lo sepa (no se falsea en silencio).
- **Ocultación por combinación RGB**: ArcMap no la soporta (se avisa).

## 4. Datos malformados (se saltan, no se inventan)

- **`outline_color=""`** (estilos migrados de QGIS 2.x donde la clave era
  `border_color`): QGIS lo decodifica a un QColor inválido cuyo render no se
  deduce del XML → la capa se **avisa y se salta**, no se inventa un negro.
  **Solución**: fijar el color del borde en QGIS y reexportar.

## 5. Limitaciones de entorno (no del motor)

- **Doble dependencia dura**: la máquina necesita **QGIS y ArcGIS Desktop 10.5**.
  El plugin no funciona en equipos sin ArcGIS 10.5 (el emisor es ArcObjects/py2.7).
- **Rutas absolutas**: el emisor abre el dato por su ruta. Si el shapefile/GeoTIFF
  se mueve, el `.lyr` apunta a la ruta ABSOLUTA con la que se generó (comportamiento
  de ArcMap, no del motor).
- Los **tests** (`run_regresion_qml.py`) necesitan ArcGIS 10.5 para emitir y
  volcar los `.lyr`; se fabrican sus propios datos sintéticos con arcpy.

## 6. Qué SÍ se reproduce (contexto)

Para no leer esta lista como "no hace casi nada": el motor cubre el 80% real de
los mapas temáticos forestales — fill sólido/hueco/tramado (6 patrones Qt) /
multicapa / línea (`solid`, `dash`, `dot`, `dash dot`, `dash dot dot`) /
marcador (5 formas + 6 por glifo + rotación) / def-query / opacidad de capa / visibilidad por
escala; ráster paletted, pseudocolor DISCRETE e INTERPOLATED, y RasterFill; los
4 renderers vectoriales (single, categorized, graduated, rule-based); shapefile,
ráster de fichero y GeoPackage. Validado contra `.lyr` entregados en proyectos
reales, contra decenas de capas de proyectos QGIS de terceros y, en este repo,
contra los casos sintéticos de `run_regresion_qml.py`.
