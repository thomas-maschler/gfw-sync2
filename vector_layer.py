__author__ = 'Thomas.Maschler'

import os
import arcpy
from layer import Layer
import warnings
import time
#from datetime import datetime
import cartodb
from settings import settings


class VectorLayer(Layer):
    """
    Vector layer class. Inherits from Layer
    """

    def __init__(self, layerdef):

        super(VectorLayer, self).__init__(layerdef)

        if not hasattr(self, 'workspace'):
            self._workspace = None
            self.workspace = settings['sde_connections']['gfw']

        self._dataset = None
        self.dataset = layerdef['dataset']

        self._fc = None
        self.fc = os.path.join(self.workspace, self.dataset, self.name)

        self.selection = None

        self.fields = self._get_fields()

        self._transformation = None
        if "transformation" in layerdef:
            self.transformation = layerdef['transformation']
        else:
            self.transformation = None

        self._where_clause = None
        if "where_clause" in layerdef:
            self.where_clause = layerdef['where_clause']
        else:
            self.where_clause = None

        self._version = None
        self.version = None
        self.create_version()

        self.wgs84_file = None
        self.export_file = None



    # Validate dataset
    @property
    def dataset(self):
        return self._dataset

    @dataset.setter
    def dataset(self, d):
        if not d:
            self._dataset = ""
        else:
            desc = arcpy.Describe(os.path.join(self.workspace, d))
            if desc.datasetType != 'FeatureDataset':
                warnings.warn("Dataset is not a FeatureDataset", Warning)
            self._dataset = d

    # Validate feature class
    @property
    def fc(self):
        return self._fc

    @fc.setter
    def fc(self, f):
        if not arcpy.Exists(f):
            warnings.warn("Feature class {0!s} does not exists".format(f), Warning)
        desc = arcpy.Describe(f)
        if desc.datasetType != 'FeatureClass':
            warnings.warn("Dataset {0!s} is not a FeatureClass".format(f), Warning)
        self._fc = f

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, v):
        print v
        arcpy.CreateVersion_management(self.workspace, "sde.DEFAULT", v, "PRIVATE")
        self._version = v


    # Validate transformation
    @property
    def transformation(self):
        return self._transformation

    @transformation.setter
    def transformation(self, t):
        if self.src is not None:
            from_desc = arcpy.Describe(self.src)
            from_srs = from_desc.spatialReference
            to_desc = arcpy.Describe(self.fc)
            to_srs = to_desc.spatialReference
            if from_srs.GCS != to_srs.GCS:
                if t is None:
                    warnings.warn("No transformation defined", Warning)
                else:
                    extent = from_desc.extent
                    transformations = arcpy.ListTransformations(from_srs, to_srs, extent)
                    if self.transformation not in transformations:
                        warnings.warn("Transformation {0!s}: not compatible with in- and output spatial reference or extent".format(self.transformation), Warning)
        self._transformation = t

    # Validate where clause
    @property
    def where_clause(self):
        return self._where_clause

    @where_clause.setter
    def where_clause(self, w):
        if self.src is not None:
            if w is not None:
                try:
                    arcpy.MakeFeatureLayer_management(self.src, self.name, w)
                except:
                    warnings.warn("Where clause '{0!s}' is invalide".format(self.where_clause))
        self._where_clause = w

    def archive(self):
        if self.export_file is not None:
            self._archive(self.export_file, True)
        if self.wgs84_file is not None:
            self._archive(self.wgs84_file, False)

    def append_features(self, input_layer, fms=None):

        """  Append new features to Vector Layer
        :param input_layer: an arcpy layer
        :param fms: an arcpy fieldmap
        :return: Nothing
        """

        self.select()

        if fms is None:
            arcpy.Append_management(input_layer, self.selection.name, "NO_TEST")
        else:
            arcpy.Append_management(input_layer, self.selection.name, "NO_TEST", fms, "")

        return

    def create_version(self):
        self.version = self.name + "_" + str(int(time.time()))

    def delete_features(self, where_clause=None):
        """ Delete Features from Vector Layer
        :param where_clause: SQL Where statement
        :return: Nothing
        """
        self.select(where_clause)
        arcpy.DeleteFeatures_management(self.selection.name)

        return

    def delete_version(self, v=None):
        if v is None:
            v = self.version
        # Set the workspace environment
        arcpy.env.workspace = self.workspace

        # Use a list comprehension to get a list of version names where the owner
        # is the current user and make sure sde.default is not selected.
        ver_list = [ver.name for ver in arcpy.da.ListVersions() if ver.isOwner
                   is True and ver.name.lower() != 'sde.default']

        if v in ver_list:
            arcpy.DeleteVersion_management(self.workspace, v)
        else:
            raise RuntimeError("Version {0!s} does not exist".format(v))

    def export_2_shp(self, wgs84=True, simplify=False):
        """ Export Vector Layer to Shapefile
        :param wgs84: Output will be in WGS 1984
        :param simplify: Output features will be simplified (10 meter precision)
        :return: Nothing
        """

        export_folder = os.path.join(self.scratch_workspace, "export")
        if not os.path.exists(export_folder):
            os.mkdir(export_folder)

        self.export_file = os.path.join(export_folder, self.name + ".shp")

        if not simplify:
            arcpy.FeatureClassToShapefile_conversion([self.fc], export_folder)
        else:
            arcpy.SimplifyPolygon_cartography(self.fc,
                                              self.export_file,
                                              "POINT_REMOVE",
                                              "10 Meters",
                                              "0 Unknown",
                                              "RESOLVE_ERRORS",
                                              "KEEP_COLLAPSED_POINTS")
        if wgs84:
            wgs84_folder = os.path.join(export_folder, "wgs84")
            if not os.path.exists(wgs84_folder):
                os.mkdir(wgs84_folder)
            self.wgs84_file = os.path.join(wgs84_folder, self.name + ".shp")

            if self.transformation is None:
                arcpy.Project_management(self.export_file, self.wgs84_file, "WGS_1984")
            else:
                arcpy.Project_management(self.export_file, self.wgs84_file, "WGS_1984", self.transformation)

        return

    def _get_fields(self):
        return arcpy.ListFields(self.fc)

    def post_version(self):
        arcpy.ReconcileVersions_management(self.workspace,
                                           "ALL_VERSIONS",
                                           "SDE.Default",
                                           [self.version],
                                           "LOCK_ACQUIRED",
                                           "NO_ABORT",
                                           "BY_OBJECT",
                                           "FAVOR_TARGET_VERSION",
                                           "POST",
                                           "DELETE_VERSION"
                                           #, "c:\RecLog.txt"
                                           )

    def update(self):

        self.delete_features()

        if self.transformation:
            arcpy.env.geographicTransformations = self.transformation
        else:
            arcpy.env.geographicTransformations = ""

        if self.where_clause:
            arcpy.MakeFeatureLayer_management(self.src, "source_layer", self.where_clause)
        else:
            arcpy.MakeFeatureLayer_management(self.src, "source_layer")

        self.append_features("source_layer")

        self.update_gfwid()

        self.post_version()

        self.export_2_shp()

        self.archive()

        self.sync_cartodb()

    def update_field(self, field, expression, language=None):
        if language is None:
            arcpy.CalculateField_management(self.selection.name, field, "'{0!s}'".format(expression), "PYTHON")
        else:
            arcpy.CalculateField_management(self.selection.name, field, expression, language, "")

    def update_gfwid(self):

        found = False
        for field in self.fields:
            if field.name == "gfwid":
                found = True
                break

        if not found:
            arcpy.AddField_management(self.fc, "gfwid", "TEXT", field_length="50", field_alias="GFW ID")
            self.fields = self._get_fields()

        self.select()

        arcpy.CalculateField_management(in_table=self.selection.name,
                                        field="gfwid",
                                        expression="md5(!Shape!.WKT)",
                                        expression_type="PYTHON_9.3",
                                        code_block="import hashlib\n"
                                                   "def md5(shape):\n"
                                                   "   hash = hashlib.md5()\n"
                                                   "   hash.update(shape)\n"
                                                   "   return hash.hexdigest()")

    def _select(self, where_clause=None):
        if where_clause is None:
            l = arcpy.MakeFeatureLayer_management(self.fc, self.name)
            arcpy.ChangeVersion_management(self.name, 'TRANSACTIONAL', self.version, '')
        else:
            l = arcpy.MakeFeatureLayer_management(self.fc, self.name, where_clause)
            arcpy.ChangeVersion_management(self.name, 'TRANSACTIONAL', self.version, '')
        return l.getOutput(0)

    def select(self, where_clause=None):
        self.selection = self._select(where_clause)

    def sync_cartodb(self):
        #TODO: Shapefile needs suffix _prefly
        cartodb.cartodb_sync(self.wgs84_file, self.name)

        #TODO: Add extra procedure for imazon_sad
        #layerspec_table="layerspec_nuclear_hazard"
        #print "update layer spec max date"
        #sql = "UPDATE %s set maxdate= (SELECT max(date)+1 FROM %s) WHERE table_name='%s'" % (layerspec_table, production_table, production_table )
        #cartodb@wri-01.cartodb_sql(sql)