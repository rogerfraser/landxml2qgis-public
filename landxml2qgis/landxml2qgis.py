"""
/***************************************************************************
 LandXML2QGIS
                                 A QGIS plugin
 Import Vic, NSW LandXML into QGIS temp layers
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2019-08-22
        git sha              : $Format:%H$
        copyright            : (C) 2019 by James Leversha, Department of Environment, Land, Water and Planning
        email                : james.k.leversha@delwp.vic.gov.au
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsGeometry, QgsField, QgsVectorLayer, QgsFeature, QgsProject, QgsCoordinateReferenceSystem, \
    QgsMapLayerStyleManager, QgsMapLayerStyle
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox
from qgis.PyQt import QtWidgets
from qgis.PyQt import QtCore
from PyQt5.QtCore import QVariant

import sys
import platform
import os.path
import os
from inspect import getsourcefile
import pickle
import requests

if '..' not in sys.path:
    sys.path.append("..")

if os.path.split(os.path.abspath(getsourcefile(lambda: 0)))[0] not in sys.path:
    sys.path.append(os.path.split(os.path.abspath(getsourcefile(lambda: 0)))[0])

from add_wheels import add_wheels
add_wheels()

import boto3
import botocore
import s3transfer
from utilities.landxmlSDK.landxml import landxml
from utilities.landxmlSDK.dcmgeometry.geometry import Geometries
from utilities.landxmlSDK.dna.dnawriters import DNAWriters
from utilities.landxmlSDK.dna.dnarunner import DNARunner
from utilities.landxmlSDK.dna.dnareaders import DNAReaders
from qgiswriters import *

# Initialize Qt resources from file resources.py
from resources import *

# Import the code for the dialog
from landxml2qgis_dialog import LandXML2QGISDialog

from pathlib import Path
from copy import deepcopy
from datetime import datetime


class LandXML2QGIS:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'LandXML2QGIS_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&LandXML2QGIS')
        self.cwd = os.path.split(os.path.abspath(getsourcefile(lambda: 0)))[0]
        self.swing = None
        self.download_only = None
        self.recalc = None
        self.dna = None
        self.dna_dir = None
        self.only_dna = None
        self.loops = None
        self.points = None
        self.polygons = None
        self.lines = None
        self.filenames = []
        self.out_paths = {}
        self.main_plan = None
        self.max_iter = 100
        self.it_thresh = .0005
        self.multi_thread = False
        self.mis_tol = .1
        this_dir = os.path.dirname(os.path.realpath(__file__))
        self.profile_loc = os.path.join(this_dir, 'utilities/landxmlSDK/resources/aprioris.json')
        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('LandXML2QGIS', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToVectorMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/landxml2qgis/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'LandXML2QGIS'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginVectorMenu(
                self.tr(u'&LandXML2QGIS'),
                action)
            self.iface.removeToolBarIcon(action)

    def get_zone(self):
        pass

    def run_dna(self, xid, ref, geom):
        pass

    def save_settings(self):
        self.dlg.my_settings.setValue('dna_dir', self.dlg.lineEdit_2.text())
        #self.dlg.my_settings.setValue('credentials_dir', self.dlg.lineEdit_5.text())
        self.dlg.my_settings.setValue('dna_outputs', self.dlg.lineEdit_3.text())
        self.dlg.my_settings.setValue('max_iter', self.dlg.lineEdit_8.text())
        self.dlg.my_settings.setValue('iter_thresh', self.dlg.lineEdit_9.text())
        self.dlg.my_settings.setValue("recalc", self.dlg.recalcCheckBox.isChecked())
        self.dlg.my_settings.setValue("multi-thread", self.dlg.multiThreadCheckBox.isChecked())

        # style files

    def set_styles(self):
        
        poly_style = Path(self.cwd, 'styles', 'polygon.qml')
        dna_poly_style = Path(self.cwd, 'styles', 'polygon_dna.qml')
        point_style = Path(self.cwd, 'styles', 'point.qml')
        dna_point_style = Path(self.cwd, 'styles', 'point_dna.qml')
        line_style_m = Path(self.cwd, 'styles', 'line.qml')
        line_style_lf = Path(self.cwd, 'styles', 'line_lf.qml')
        arc_style_m = Path(self.cwd, 'styles', 'arc.qml')
        arc_style_lf = Path(self.cwd, 'styles', 'arc_lf.qml')
        loop_style = Path(self.cwd, 'styles', 'loop.qml')
        outlier_style = Path(self.cwd, 'styles', 'out.qml')
        dna_out_style = Path(self.cwd, 'styles', 'out_dna.qml')

        styles = {'vl_poi': point_style, 'vl_lin_m': line_style_m, 'vl_arc': arc_style_m, 'vl_pol': poly_style,
                  'vl_loop': loop_style, 'vl_lin_lf': line_style_lf, 'vl_arc_lf': arc_style_lf,
                  'vl_pol_dnaadj': dna_poly_style, 'vl_poi_dnaadj': dna_point_style,
                  'vl_lin_dnaadj': line_style_m, 'vl_arc_dnaadj': arc_style_m, 'vl_loop_dnaadj': loop_style,
                  'vl_out_dnaadj': dna_out_style, 'vl_lin_dnaadj_lf': line_style_lf, 'vl_arc_dnaadj_lf': arc_style_lf}
        for k, v in styles.items():
            if v.exists() is False:
                styles[k] = None
        return styles

    def set_box_values(self):
        self.swing = self.dlg.swingCheckBox.isChecked()
        #self.download_only = self.dlg.downloadOnlyCheckBox.isChecked()
        self.recalc = self.dlg.recalcCheckBox.isChecked()
        self.dna = self.dlg.runDNACheckBox.isChecked()
        self.only_dna = self.dlg.onlyDNACheckBox.isChecked()
        self.loops = self.dlg.loopCheckBox.isChecked()
        self.points = self.dlg.pointCheckBox.isChecked()
        self.polygons = self.dlg.polygonCheckBox.isChecked()
        self.lines = self.dlg.lineCheckBox.isChecked()
        
    def get_file_names(self):
        fname = None
        aws_name = self.dlg.AWS_LineEdit.text()
        if len(aws_name) > 0:
            outpath = Path(self.dlg.lineEdit_3.text(), aws_name)
            outxml = Path(outpath, f'{aws_name}.xml')
            if self.dlg.overwriteCheckBox.isChecked() is True or outxml.exists() is False:
                QMessageBox.information(None, "Downloading plan",
                                        'Found plan in the repository, dowloading to:\n'
                                        f'{str(outxml)}')
                bucket_name = 'dcm-file-sharing'
                outpath.mkdir(parents=True, exist_ok=True)
                url = f'https://{bucket_name}.s3.amazonaws.com/all/{aws_name}.xml'
                headers = {'Host': f'{bucket_name}.s3.ap-southeast-2.amazonaws.com'}
                r = requests.get(url, headers=headers)

                if r.ok is True:
                    outpath = Path(self.dlg.lineEdit_3.text(), aws_name)
                    outpath.mkdir(parents=True, exist_ok=True)
                    outxml = Path(outpath, f'{aws_name}.xml')
                    with open(outxml, 'wb') as open_file:
                        open_file.write(r.content)
                    fname = str(outxml)
                else:
                    QMessageBox.information(None, "No plan",
                                            'Couldnt find plan in the repository')
            elif outxml.exists() is True:
                fname = str(outxml)


        if fname is None:
            fname = self.dlg.lineEdit.text()
        fnames = []
        if len(fname) > 0:
            fnames.append(fname)
            
        folders = self.dlg.lineEdit_4.text()
        if len(folders) > 0:
            fnames = []
            for directory, fs, filenames in os.path.walk(folders):
                fnames.extend([str(Path(directory, f)) for f in filenames if f.endswith('.xml')])

        if len(fnames) > 0:
            self.filenames = fnames
            self.main_plan = os.path.split(fnames[0])[-1][:-4]
        else:
            QMessageBox.information(None, "No plan",
                                    'You need to type in a plan')
            raise

    def set_outpaths(self):
        self.out_paths = {}
        for fname in self.filenames:
            out_path_text = Path(self.dlg.lineEdit_3.text())
            xml_name = os.path.split(fname)[-1][:-4]
            if '_AFR' in xml_name:
                xml_name, sep, afr = xml_name.partition('_')
                out_path = Path(out_path_text, xml_name, 'AFRs', afr,
                                     datetime.now().strftime('%Y-%m-%d_%H%M%S'))
            else:
                out_path = Path(out_path_text, xml_name,
                                     datetime.now().strftime('%Y-%m-%d_%H%M%S'))
            self.out_paths[fname] = out_path

    def get_dna_settings(self):

        if self.dlg.lineEdit_7.text() != 'default':
            self.profile_loc = self.dlg.lineEdit_8.text()

        if os.path.exists(self.profile_loc) is False:

            QMessageBox.information(None, "Apriori",
                                    f'Apriori Profile location does not exist {self.profile_loc}')
        try:
            if self.dlg.lineEdit_8.text() != 'default':
                self.max_iter = int(self.dlg.lineEdit_8.text())
        except ValueError:
            QMessageBox.information(None, "Iterations",
                                    f'Iterations needs to be a number setting to {self.max_iter}')

        try:
            if self.dlg.lineEdit_9.text() != 'default':
                self.it_thresh = float(self.dlg.lineEdit_9.text())
        except ValueError:
            QMessageBox.information(None, "Iteration Threshold",
                                    f'Iteration threshold needs to be a number setting to {self.it_thresh}')

        self.multi_thread = self.dlg.multiThreadCheckBox.isChecked()
        self.dna_dir = self.dlg.lineEdit_2.text()

    def set_misclose_value(self):
        try:
            if self.dlg.lineEdit_10.text() != 'default':
                self.mis_tol = float(self.dlg.lineEdit_10.text())
        except ValueError as e:
            QMessageBox.information(None, "Misclose Tolerance", "Misclose must be a "
                                                                f"number\nSetting to {self.mis_tol}")

    def process_dna(self, geom, fn, outpath):
        self.get_dna_settings()
        dna_object = DNAWriters(geom, geom.survey_number, output_dir=outpath, profile_location=self.profile_loc)
        stn_file, msr_file = dna_object.write_stn_msr_file()
        dna_runner = DNARunner(self.dna_dir, multi_thread=self.multi_thread, max_iter=self.max_iter,
                               iter_thresh=self.it_thresh, output_dir=outpath, filename=geom.survey_number)
        dna_adj_fp = dna_runner.run_dna_via_subprocesses(msr_location=msr_file, stn_location=stn_file)

        dna_results = DNAReaders(dna_adj_fp)
        dna_coords = dna_results.coordinates
        dna_outliers = dna_results.get_outliers()
        result = dna_results.global_stats.chi_squared_test
        dna_geom = deepcopy(geom)
        new_points = {}
        for k, v in dna_geom.points.items():
            point = dna_coords.get(k)
            if point is not None:
                v.set_new_geometry(point.geometry)
                new_points[k] = v
        dna_geom.points = new_points
        dna_geom.update_geometries()
        return dna_geom, dna_outliers, result

    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False
            self.dlg = LandXML2QGISDialog()

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()

        # See if OK was pressed
        if result:
            self.set_box_values()
            self.get_file_names()
            styles = self.set_styles()
            self.set_outpaths()
            self.set_misclose_value()

            lines = {}
            arcs = {}
            dna_lines = {}
            dna_arcs = {}
            points = {}
            dna_points = {}
            polygons = {}
            dna_polygons = {}
            loops = {}
            dna_loops = {}
            outliers = {}
            result = ''
            for fn in self.filenames:
                data = landxml.parse(fn, silence=True, print_warnings=False)
                geom = Geometries(data, self.mis_tol)
                if self.recalc is True:
                    geom.recalc_geometries(ref_point=geom.ccc, swing=self.swing)
                outpath = self.out_paths.get(fn)
                outpath.mkdir(parents=True, exist_ok=True)
                dna_geom = None
                dna_outliers = []

                if self.dna is True:
                    dna_geom, dna_outliers, result = self.process_dna(geom, fn, outpath)
                    if self.dlg.lineCheckBox.isChecked() is False:
                        dna_outliers = []
                qgis_geoms = QGISAllObjects(geom, dna_geom, dna_outliers)
                if self.dlg.lineCheckBox.isChecked() is True:
                    if len(qgis_geoms.lines) > 0:
                        lines[geom.survey_number] = qgis_geoms.lines
                    if len(qgis_geoms.arcs) > 0:
                        arcs[geom.survey_number] = qgis_geoms.arcs
                    if self.dna is True:
                        if len(qgis_geoms.dna_lines) > 0:
                            dna_lines[geom.survey_number] = qgis_geoms.dna_lines
                        if len(qgis_geoms.dna_arcs) > 0:
                            dna_arcs[geom.survey_number] = qgis_geoms.dna_arcs

                if self.dlg.pointCheckBox.isChecked() is True:
                    if len(qgis_geoms.points) > 0:
                        points[geom.survey_number] = qgis_geoms.points
                    if self.dna is True:
                        dna_points[geom.survey_number] = qgis_geoms.dna_points

                if self.dlg.polygonCheckBox.isChecked() is True:
                    if len(qgis_geoms.polygons) > 0:
                        polygons[geom.survey_number] = qgis_geoms.polygons
                    if self.dna is True:
                        dna_polygons[geom.survey_number] = qgis_geoms.dna_polygons
                
                if self.dlg.loopCheckBox.isChecked() is True:
                    if len(qgis_geoms.loops) > 0:
                        loops[geom.survey_number] = qgis_geoms.loops
                        if self.dna is True:
                            dna_loops[geom.survey_number] = qgis_geoms.dna_loops

                if self.dlg.outlierCheckBox.isChecked() is True:
                    if len(dna_outliers) > 0:
                        outliers[geom.survey_number] = qgis_geoms.outliers


            if len(polygons) > 0 and self.only_dna is False:
                layer_styles = [v for k, v in styles.items() if 'pol' in k and 'dna' not in k]
                QGISLayer(polygons, layer_type='Polygon', styles=layer_styles, process=True, suffix='Polygons',
                          fields_to_remove=['line_order', 'original_geom', 'coord_lookup', 'inner_angles',
                                            'point_lookup', 'calculated_polygon', 'polygon_points'])
            if len(loops) > 0 and self.only_dna is False:
                layer_styles = [v for k, v in styles.items() if 'loop' in k and 'dna' not in k]
                QGISLayer(loops, layer_type='MultiLineString', styles=layer_styles, process=True, suffix='Loops')
            if len(lines) > 0 and self.only_dna is False:
                layer_styles = [v for k, v in styles.items() if 'lin' in k and 'dna' not in k]
                QGISLayer(lines, layer_type='LineString', styles=layer_styles, process=True, suffix='Lines')
            if len(arcs) > 0 and self.only_dna is False:
                layer_styles = [v for k, v in styles.items() if 'arc' in k and 'dna' not in k]
                QGISLayer(arcs, layer_type='LineString', styles=layer_styles, process=True, suffix='Arcs')
            if len(points) > 0 and self.only_dna is False:
                layer_styles = [v for k, v in styles.items() if 'poi' in k and 'dna' not in k]
                QGISLayer(points, layer_type='Point', styles=layer_styles, process=True, suffix='Points')

            if len(outliers) > 0:
                layer_styles = [v for k, v in styles.items() if 'out' in k and 'dna' in k]
                QGISLayer(outliers, layer_type='LineString', styles=layer_styles, process=True,
                          suffix=f'DNA_Outliers_{result}')

            if len(dna_loops) > 0:
                layer_styles = [v for k, v in styles.items() if 'loop' in k and 'dna' not in k]
                QGISLayer(dna_loops, layer_type='MultiLineString', styles=layer_styles, process=True,
                          suffix='DNA_Loops')

            if len(dna_lines) > 0:
                layer_styles = [v for k, v in styles.items() if 'lin' in k and 'dna' in k]
                QGISLayer(dna_lines, layer_type='LineString', styles=layer_styles, process=True,
                          suffix=f'DNA_Lines_{result}')
            if len(dna_arcs) > 0:
                layer_styles = [v for k, v in styles.items() if 'arc' in k and 'dna' in k]
                QGISLayer(dna_arcs, layer_type='LineString', styles=layer_styles, process=True,
                          suffix=f'DNA_Arcs_{result}')
            if len(dna_points) > 0:
                layer_styles = [v for k, v in styles.items() if 'poi' in k and 'dna' in k]
                QGISLayer(dna_points, layer_type='Point', styles=layer_styles, process=True,
                          suffix=f'DNA_Points_{result}')
            if len(dna_polygons) > 0:
                layer_styles = [v for k, v in styles.items() if 'pol' in k and 'dna' in k]
                QGISLayer(dna_polygons, layer_type='Polygon', styles=layer_styles, process=True,
                          suffix=f'DNA_Polygons_{result}')

            self.save_settings()
