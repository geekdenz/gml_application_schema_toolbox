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

"""Functions to inject a custom QT widget in a QGIS form

This module contains functions that allow the user to "inject"
a custom QT widget in an existing QGIS feature form. This allows
to extend the default feature form dialog with a custom widget.
This mechanism is used for example to display an XML widget.
"""

__all__ = ["install_xml_tree_on_feature_form"]

from qgis.PyQt.QtWidgets import QWidget, QGridLayout, QWidgetItem, QLabel, QPushButton
from qgis.core import QgsEditFormConfig

from . import xml_tree_widget

def install_xml_tree_on_feature_form(lyr):
    """Install an XML tree on feature form of the input layer"""
    
    code = ("def my_form_open(dialog, layer, feature):\n"
            "    from gml_application_schema_toolbox.gui import qgis_form_custom_widget as qq\n"
            "    qq.inject_xml_tree_into_form(dialog, feature)\n")
    conf = lyr.editFormConfig()
    conf.setInitCode(code)
    conf.setInitFunction("my_form_open")
    conf.setInitCodeSource(QgsEditFormConfig.CodeSourceDialog)
    lyr.setEditFormConfig(conf)

def inject_xml_tree_into_form(dialog, feature):
    """Function called on form opening to add a custom XML widget"""
    w = dialog.findChild(QPushButton, "_xml_widget_")
    if w is not None:
        return
    l = __find_label_layout(dialog, "fid")
    if l is None:
        return

    w = xml_tree_widget.XMLTreeWidget(dialog)
    w.setObjectName("_xml_widget_")
    w.updateFeature(feature)
    lbl = QLabel("XML", dialog)
    l.addWidget(lbl, l.rowCount()-1, 0)
    l.addWidget(w, l.rowCount()-1, 1)
    l.setRowStretch(l.rowCount()-1, 2)

    # the tree widget must not be garbage collected yet
    # since we want its Python slots to be called on signals
    # we then transfer its ownership to a C++ object that lives longer
    import sip
    sip.transferto(w, dialog)

def __find_label_layout(dialog, lbl_text):
    """Find the parent layout of a QLabel in a dialog"""
    ll = dialog.findChildren(QWidget)
    ll = [l.layout() for l in ll if l.layout() is not None and isinstance(l.layout(), QGridLayout)]
    for l in ll:
        for i in range(l.count()):
            it = l.itemAt(i)
            if isinstance(it, QWidgetItem) and isinstance(it.widget(), QLabel) and it.widget().text().startswith(lbl_text):
                return l
    return None
