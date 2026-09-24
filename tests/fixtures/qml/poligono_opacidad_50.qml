<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<!-- Fixture del camino del PLUGIN: opacidad de CAPA al 50%.
     `<layerOpacity>` cuelga de la raiz <qgis> igual que del <maplayer> de un
     .qgz; hasta 2026-09-20 `parse_qml` no lo leia y la transparencia se perdia
     entera por la via del plugin. -->
<qgis labelsEnabled="0" hasScaleBasedVisibilityFlag="0" maxScale="0" minScale="100000000" version="3.44.12-Solothurn" styleCategories="AllStyleCategories">
  <renderer-v2 symbollevels="0" referencescale="-1" type="singleSymbol" enableorderby="0" forceraster="0">
    <symbols>
      <symbol clip_to_extent="1" is_animated="0" frame_rate="10" type="fill" name="0" force_rhr="0" alpha="1">
        <layer id="{00000000-0000-0000-0000-000000000002}" pass="0" locked="0" enabled="1" class="SimpleFill">
          <Option type="Map">
            <Option type="QString" name="color" value="30,120,200,255,rgb:0.1176471,0.4705882,0.7843137,1"/>
            <Option type="QString" name="joinstyle" value="bevel"/>
            <Option type="QString" name="offset" value="0,0"/>
            <Option type="QString" name="offset_unit" value="MM"/>
            <Option type="QString" name="outline_color" value="0,0,0,255,rgb:0,0,0,1"/>
            <Option type="QString" name="outline_style" value="solid"/>
            <Option type="QString" name="outline_width" value="0.26"/>
            <Option type="QString" name="outline_width_unit" value="MM"/>
            <Option type="QString" name="style" value="solid"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
  <blendMode>0</blendMode>
  <featureBlendMode>0</featureBlendMode>
  <layerOpacity>0.5</layerOpacity>
  <layerGeometryType>2</layerGeometryType>
</qgis>
