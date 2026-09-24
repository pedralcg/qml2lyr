<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<!-- Fixture del camino del PLUGIN: trazo `dash dot`.
     QGIS escribe el estilo con ESPACIOS ("dash dot", "dash dot dot"); hasta
     2026-09-20 el parser solo aceptaba solid/dash/dot y la capa se rechazaba
     entera. El ancho (0,4 mm = 1,13 pt) se queda por debajo del umbral en el
     que ArcMap dibuja el patron continuo, para que el test mire el estilo y no
     el aviso. -->
<qgis labelsEnabled="0" hasScaleBasedVisibilityFlag="0" maxScale="0" minScale="100000000" version="3.44.12-Solothurn" styleCategories="AllStyleCategories">
  <renderer-v2 symbollevels="0" referencescale="-1" type="singleSymbol" enableorderby="0" forceraster="0">
    <symbols>
      <symbol clip_to_extent="1" is_animated="0" frame_rate="10" type="line" name="0" force_rhr="0" alpha="1">
        <layer id="{00000000-0000-0000-0000-000000000003}" pass="0" locked="0" enabled="1" class="SimpleLine">
          <Option type="Map">
            <Option type="QString" name="capstyle" value="square"/>
            <Option type="QString" name="customdash" value="5;2"/>
            <Option type="QString" name="customdash_unit" value="MM"/>
            <Option type="QString" name="joinstyle" value="bevel"/>
            <Option type="QString" name="line_color" value="0,0,255,255,rgb:0,0,1,1"/>
            <Option type="QString" name="line_style" value="dash dot"/>
            <Option type="QString" name="line_width" value="0.4"/>
            <Option type="QString" name="line_width_unit" value="MM"/>
            <Option type="QString" name="offset" value="0"/>
            <Option type="QString" name="offset_unit" value="MM"/>
            <Option type="QString" name="use_custom_dash" value="0"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
  <blendMode>0</blendMode>
  <featureBlendMode>0</featureBlendMode>
  <layerOpacity>1</layerOpacity>
  <layerGeometryType>1</layerGeometryType>
</qgis>
