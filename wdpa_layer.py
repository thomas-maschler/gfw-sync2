from vector_layer import VectorLayer
import os
import warnings
import urllib
import arcpy
import util

class WDPALayer(VectorLayer):
    def __init__(self, layerdef):

        self._url = None
        self.url = layerdef['url']
        self._src_gdb = None
        self.src = None

        super(WDPALayer, self).__init__(layerdef, self.src)
        self.type = "WDPALayer"

    # Validate folder
    @property
    def url(self):
        return self._url

    @url.setter
    def url(self, u):
        try:
            urllib.urlopen(u)  # TODO: Check if there is a better way to check URL
        except:
            warnings.warn("{0!s}\nURL '{1!s}' does not exist".format(self._wrong_def, u), Warning)
        self._url = u

    def _download(self, url):

        name = os.path.basename(url)
        zip_name = "{0!s}.zip".format(name)
        zip_path = os.path.join(self._temp_folder, zip_name)
        gdb = os.path.join(self._temp_folder, "{0!s}.gdb".format(name))

        if os.path.exists(zip_path):
            os.remove(zip_path)
        if arcpy.Exists(gdb):
            arcpy.Delete_management(gdb)

            urllib.urlretrieve(url, zip_path)

        util.unzip(zip_path, self._temp_folder)
        os.remove(zip_path)
        return gdb

    def _get_src(self):
        self._src_gdb = self._download(self.url)
        arcpy.env.workspace = self._src_gdb
        fc_list = arcpy.ListFeatureClasses()

        for fc in fc_list:
            desc = arcpy.Describe(fc)
            if desc.shapeType == 'Polygon':
                return os.path.join(self._src_gdb, fc)

    def update(self):
        self.src = self._get_src()
        # ...

    def __del__(self):
        arcpy.Delete_management(self._src_gdb)

