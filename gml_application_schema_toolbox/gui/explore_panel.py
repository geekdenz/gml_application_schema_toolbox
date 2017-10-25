import os
import owslib_hacks
import owslib

from owslib.wfs import WebFeatureService
from owslib.feature.wfs200 import WFSCapabilitiesReader

from tempfile import NamedTemporaryFile

import logging

from qgis.core import QgsCoordinateTransform, QgsCoordinateReferenceSystem
from qgis.utils import iface

from qgis.PyQt.QtCore import (
    Qt, pyqtSignal, pyqtSlot,
    QSettings,
    QUrl, QFile, QIODevice)
# from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QMessageBox, QFileDialog, QListWidgetItem
from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt import uic

from gml_application_schema_toolbox.core.logging import log
from gml_application_schema_toolbox.core.proxy import qgis_proxy_settings
from gml_application_schema_toolbox.core.settings import settings

from .xml_dialog import XmlDialog

WIDGET, BASE = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '..', 'ui', 'explore_panel.ui'))

class ExploreWfs2Panel(BASE, WIDGET):

    #file_downloaded = pyqtSignal(str)

    def __init__(self, parent=None):
        super(ExploreWfs2Panel, self).__init__(parent)
        self.setupUi(self)

    def wfs(self):
        uri = self.uriComboBox.currentText()
        with qgis_proxy_settings():
            return WebFeatureService(url=uri, version='2.0.0')

