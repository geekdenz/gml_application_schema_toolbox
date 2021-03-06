# -*- coding: utf-8 -*-

#   Copyright (C) 2017 BRGM (http:///brgm.fr)
#   Copyright (C) 2017 Oslandia <infos@oslandia.com>
#
#   This library is free software; you can redistribute it and/or
#   modify it under the terms of the GNU Library General Public
#   License as published by the Free Software Foundation; either
#   version 2 of the License, or (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#   Library General Public License for more details.
#   You should have received a copy of the GNU Library General Public
#   License along with this library; if not, see <http://www.gnu.org/licenses/>.

from qgis.core import QgsVectorLayer, QgsProject, QgsCoordinateReferenceSystem, QgsRelation, QgsEditorWidgetSetup
from qgis.core import QgsEditFormConfig, QgsAttributeEditorField, QgsAttributeEditorRelation, QgsAttributeEditorContainer
from qgis.PyQt.QtCore import QVariant

from osgeo import ogr

def _qgis_layer(uri, schema_name, layer_name, geometry_column, provider, qgis_layer_name):
    if geometry_column is not None:
        g_column = "({})".format(geometry_column)
    else:
        g_column = ""
    if provider == "SQLite":
        # use OGR for spatialite loading
        l = QgsVectorLayer("{}|layername={}{}".format(uri, layer_name, g_column), qgis_layer_name, "ogr")
        l.setProviderEncoding("UTF-8")
    else:
        if schema_name is not None:
            s_table = '"{}"."{}"'.format(schema_name, layer_name)
        else:
            s_table = '"{}"'.format(layer_name)
        # remove "PG:" in front of the uri
        uri = uri[3:]
        l = QgsVectorLayer("{} table={} {} sql=".format(uri, s_table, g_column), qgis_layer_name, "postgres")
    return l

def import_in_qgis(gmlas_uri, provider, schema = None):
    """Imports layers from a GMLAS file in QGIS with relations and editor widgets

    @param gmlas_uri connection parameters
    @param provider name of the QGIS provider that handles gmlas_uri parameters (postgresql or spatialite)
    @param schema name of the PostgreSQL schema where tables and metadata tables are
    """
    if schema is not None:
        schema_s = schema + "."
    else:
        schema_s = ""

    ogr.UseExceptions()
    drv = ogr.GetDriverByName(provider)
    ds = drv.Open(gmlas_uri)
    if ds is None:
        raise RuntimeError("Problem opening {}".format(gmlas_uri))

    # get list of layers
    sql = "select o.*, g.f_geometry_column, g.srid from {}_ogr_layers_metadata o left join geometry_columns g on g.f_table_name = o.layer_name".format(schema_s)
    
    l = ds.ExecuteSQL(sql)
    layers = {}
    for f in l:
        ln = f.GetField("layer_name")
        if ln not in layers:
            layers[ln] = {
                'uid': f.GetField("layer_pkid_name"),
                'category': f.GetField("layer_category"),
                'xpath': f.GetField("layer_xpath"),
                'parent_pkid': f.GetField("layer_parent_pkid_name"),
                'srid': f.GetField("srid"),
                'geometry_column': f.GetField("f_geometry_column"),
                '1_n' : [], # 1:N relations
                'layer_id': None,
                'layer_name' : ln,
                'layer': None,
                'fields' : []}
        else:
            # additional geometry columns
            g = f.GetField("f_geometry_column")
            k = "{} ({})".format(ln, g)
            layers[k] = dict(layers[ln])
            layers[k]["geometry_column"] = g
    

    crs = QgsCoordinateReferenceSystem("EPSG:4326")
    for ln in sorted(layers.keys()):
        lyr = layers[ln]
        g_column = lyr["geometry_column"] or None
        l = _qgis_layer(gmlas_uri, schema, lyr["layer_name"], g_column, provider, qgis_layer_name = ln)
        if not l.isValid():
            raise RuntimeError("Problem loading layer {} with {}".format(ln, l.source()))
        if lyr["srid"]:
            crs = QgsCoordinateReferenceSystem("EPSG:{}".format(lyr["srid"]))
        l.setCrs(crs)
        QgsProject.instance().addMapLayer(l)
        layers[ln]['layer_id'] = l.id()
        layers[ln]['layer'] = l

    # add 1:1 relations
    relations_1_1 = []
    sql = """
select
  layer_name, field_name, field_related_layer, r.child_pkid
from
  {0}_ogr_fields_metadata f
  join {0}_ogr_layer_relationships r
    on r.parent_layer = f.layer_name
   and r.parent_element_name = f.field_name
where
  field_category in ('PATH_TO_CHILD_ELEMENT_WITH_LINK', 'PATH_TO_CHILD_ELEMENT_NO_LINK')
  and field_max_occurs=1
""".format(schema_s)
    l = ds.ExecuteSQL(sql)
    if l is not None:
        for f in l:
            rel = QgsRelation()
            rel.setId('1_1_' + f.GetField('layer_name') + '_' + f.GetField('field_name'))
            rel.setName('1_1_' + f.GetField('layer_name') + '_' + f.GetField('field_name'))
            # parent layer
            rel.setReferencingLayer(layers[f.GetField('layer_name')]['layer_id'])
            # child layer
            rel.setReferencedLayer(layers[f.GetField('field_related_layer')]['layer_id'])
            # parent, child
            rel.addFieldPair(f.GetField('field_name'), f.GetField('child_pkid'))
            #rel.generateId()
            if rel.isValid():
                relations_1_1.append(rel)

    # add 1:N relations
    relations_1_n = []
    sql = """
select
  layer_name, r.parent_pkid, field_related_layer as child_layer, r.child_pkid
from
  {0}_ogr_fields_metadata f
  join {0}_ogr_layer_relationships r
    on r.parent_layer = f.layer_name
   and r.child_layer = f.field_related_layer
where
  field_category in ('PATH_TO_CHILD_ELEMENT_WITH_LINK', 'PATH_TO_CHILD_ELEMENT_NO_LINK')
  and field_max_occurs>1
-- junctions - 1st way
union all
select
  layer_name, r.parent_pkid, field_junction_layer as child_layer, 'parent_pkid' as child_pkid
from
  {0}_ogr_fields_metadata f
  join {0}_ogr_layer_relationships r
    on r.parent_layer = f.layer_name
   and r.child_layer = f.field_related_layer
where
  field_category = 'PATH_TO_CHILD_ELEMENT_WITH_JUNCTION_TABLE'
-- junctions - 2nd way
union all
select
  field_related_layer as layer_name, r.child_pkid, field_junction_layer as child_layer, 'child_pkid' as child_pkid
from
  {0}_ogr_fields_metadata f
  join {0}_ogr_layer_relationships r
    on r.parent_layer = f.layer_name
   and r.child_layer = f.field_related_layer
where
  field_category = 'PATH_TO_CHILD_ELEMENT_WITH_JUNCTION_TABLE'
""".format(schema_s)
    l = ds.ExecuteSQL(sql)
    if l is not None:
        for f in l:
            rel = QgsRelation()
            rel.setId('1_n_' + f.GetField('layer_name') + '_' + f.GetField('child_layer') + '_' + f.GetField('parent_pkid') + '_' + f.GetField('child_pkid'))
            rel.setName(f.GetField('child_layer'))
            # parent layer
            rel.setReferencedLayer(layers[f.GetField('layer_name')]['layer_id'])
            # child layer
            rel.setReferencingLayer(layers[f.GetField('child_layer')]['layer_id'])
            # parent, child
            rel.addFieldPair(f.GetField('child_pkid'), f.GetField('parent_pkid'))
            #rel.addFieldPair(f.GetField('child_pkid'), 'ogc_fid')
            if rel.isValid():
                relations_1_n.append(rel)
                # add relation to layer
                layers[f.GetField('layer_name')]['1_n'].append(rel)
            
    QgsProject.instance().relationManager().setRelations(relations_1_1 + relations_1_n)

    # add "show form" option to 1:1 relations
    for rel in relations_1_1:
        l = rel.referencingLayer()
        idx = rel.referencingFields()[0]
        s = QgsEditorWidgetSetup("RelationReference", {'AllowNULL': False,
                                      'ReadOnly': True,
                                      'Relation': rel.id(),
                                      'OrderByValue': False,
                                      'MapIdentification': False,
                                      'AllowAddFeatures': False,
                                      'ShowForm': True})
        l.setEditorWidgetSetup(idx, s)

    # setup form for layers
    for layer, lyr in layers.items():
        l = lyr['layer']
        fc = l.editFormConfig()
        fc.clearTabs()
        fc.setLayout(QgsEditFormConfig.TabLayout)
        # Add fields
        c = QgsAttributeEditorContainer("Main", fc.invisibleRootContainer())
        c.setIsGroupBox(False) # a tab
        for idx, f in enumerate(l.fields()):
            c.addChildElement(QgsAttributeEditorField(f.name(), idx, c))
        fc.addTab(c)

        # Add 1:N relations
        c_1_n = QgsAttributeEditorContainer("1:N links", fc.invisibleRootContainer())
        c_1_n.setIsGroupBox(False) # a tab
        fc.addTab(c_1_n)
        
        for rel in lyr['1_n']:
            c_1_n.addChildElement(QgsAttributeEditorRelation(rel.name(), rel, c_1_n))

        l.setEditFormConfig(fc)

