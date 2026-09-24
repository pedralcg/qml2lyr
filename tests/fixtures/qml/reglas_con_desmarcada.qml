<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<!-- Fixture del camino del PLUGIN: RuleRenderer con una regla DESMARCADA.
     Atributo `checkstate="0"` (asi lo escribe QGIS 3.44, no `checked`). QGIS no
     dibuja esa regla: ni debe salir su .lyr ni debe entrar su filtro en el
     ELSE. El ELSE ademas lleva escalas, que se ignoran con aviso. -->
<qgis labelsEnabled="0" hasScaleBasedVisibilityFlag="0" maxScale="0" minScale="100000000" version="3.44.12-Solothurn" styleCategories="AllStyleCategories">
  <renderer-v2 symbollevels="0" referencescale="-1" type="RuleRenderer" enableorderby="0" forceraster="0">
    <rules key="{00000000-0000-0000-0000-0000000000a0}">
      <rule symbol="0" filter="&quot;TIPO&quot; = 'rio'" key="{00000000-0000-0000-0000-0000000000a1}" label="Rios"/>
      <rule symbol="1" filter="&quot;TIPO&quot; = 'rambla'" checkstate="0" key="{00000000-0000-0000-0000-0000000000a2}" label="Ramblas"/>
      <rule symbol="2" filter="ELSE" scalemaxdenom="1000" scalemindenom="50000" key="{00000000-0000-0000-0000-0000000000a3}" label="Resto"/>
    </rules>
    <symbols>
      <symbol clip_to_extent="1" is_animated="0" frame_rate="10" type="line" name="0" force_rhr="0" alpha="1">
        <layer id="{00000000-0000-0000-0000-0000000000b1}" pass="0" locked="0" enabled="1" class="SimpleLine">
          <Option type="Map">
            <Option type="QString" name="line_color" value="255,0,0,255,rgb:1,0,0,1"/>
            <Option type="QString" name="line_style" value="solid"/>
            <Option type="QString" name="line_width" value="1"/>
            <Option type="QString" name="line_width_unit" value="MM"/>
            <Option type="QString" name="offset" value="0"/>
            <Option type="QString" name="offset_unit" value="MM"/>
          </Option>
        </layer>
      </symbol>
      <symbol clip_to_extent="1" is_animated="0" frame_rate="10" type="line" name="1" force_rhr="0" alpha="1">
        <layer id="{00000000-0000-0000-0000-0000000000b2}" pass="0" locked="0" enabled="1" class="SimpleLine">
          <Option type="Map">
            <Option type="QString" name="line_color" value="0,0,255,255,rgb:0,0,1,1"/>
            <Option type="QString" name="line_style" value="solid"/>
            <Option type="QString" name="line_width" value="1"/>
            <Option type="QString" name="line_width_unit" value="MM"/>
            <Option type="QString" name="offset" value="0"/>
            <Option type="QString" name="offset_unit" value="MM"/>
          </Option>
        </layer>
      </symbol>
      <symbol clip_to_extent="1" is_animated="0" frame_rate="10" type="line" name="2" force_rhr="0" alpha="1">
        <layer id="{00000000-0000-0000-0000-0000000000b3}" pass="0" locked="0" enabled="1" class="SimpleLine">
          <Option type="Map">
            <Option type="QString" name="line_color" value="0,128,0,255,rgb:0,0.5019608,0,1"/>
            <Option type="QString" name="line_style" value="solid"/>
            <Option type="QString" name="line_width" value="1"/>
            <Option type="QString" name="line_width_unit" value="MM"/>
            <Option type="QString" name="offset" value="0"/>
            <Option type="QString" name="offset_unit" value="MM"/>
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
