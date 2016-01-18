import os
from settings import settings
import arcpy
import warnings
import shutil
import time
from datetime import datetime
import archive
import json
import arcpy_metadata
import util

class Layer(object):

    def __init__(self, layerdef):
        """ A general Layer class
        :param layerdef: A Layer definition dictionary
        :return:
        """

        self.type = "Layer"

        self._name = None
        self.name = layerdef['name']

        self._alias = None
        self.alias = layerdef['alias']

        self._scratch_workspace = None
        self.scratch_workspace = os.path.join(settings['paths']['scratch_workspace'], self.name)

        self._zip_workspace = None
        self.zip_workspace = os.path.join(self.scratch_workspace, "zip")

        self.metadata = self._get_metadata()

        self._s3_bucket = None
        self.s3_bucket = layerdef['s3']['bucket']

        self._s3_path = None
        self.s3_path = layerdef['s3']['path']

        self._s3_bucket_drive = settings["bucket_drives"][self.s3_bucket]

        self._dst_folder = None
        self.dst_folder = os.path.join(self._s3_bucket_drive, self.s3_path)

        if not hasattr(self, 'src'):
            self._src = None
            self.src = layerdef['src']

    # Validate name
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, n):
        if not n:
            warnings.warn("Name cannot be empty", Warning)
        self._name = n

    # Validate alias
    @property
    def alias(self):
        return self._alias

    @alias.setter
    def alias(self, a):
        if not a:
            warnings.warn("Alias cannot be empty", Warning)
        self._alias = a

    # Validate Scratch workspace
    @property
    def scratch_workspace(self):
        return self._scratch_workspace

    @scratch_workspace.setter
    def scratch_workspace(self, s):
        if os.path.exists(s):
            shutil.rmtree(s)
        os.mkdir(s)
        self._scratch_workspace = s

    # Validate Scratch workspace
    @property
    def zip_workspace(self):
        return self._zip_workspace

    @zip_workspace.setter
    def zip_workspace(self, z):
        if os.path.exists(z):
            shutil.rmtree(z)
        os.mkdir(z)
        self._scratch_workspace = z

    # Validate workspace
    @property
    def workspace(self):
        return self._workspace

    @workspace.setter
    def workspace(self, w):
        if not w:
            warnings.warn("Workspace cannot be empty", Warning)
        elif not arcpy.Exists(w):
            warnings.warn("Workspace {0!s} does not exist".format(w), Warning)
        else:
            desc = arcpy.Describe(w)
            if desc.dataType != "Workspace" and desc.dataType != "Folder":
                print desc.dataType
                warnings.warn("{0!s} is not a Workspace".format(w), Warning)
        self._workspace = w

    # Validate source
    @property
    def src(self):
        return self._src

    @src.setter
    def src(self, s):
        if s is not None:
            if not arcpy.Exists(s):
                warnings.warn("Cannot find source {0!s}".format(s), Warning)
            else:
                drive = os.path.splitdrive(s)[0]
                if drive in settings["bucket_drives"].values():
                    out_data = os.path.join(self.scratch_workspace, os.path.basename(s))
                    arcpy.Copy_management(s, out_data)
                    s = out_data
        self._src = s

    # Validate bucket
    @property
    def s3_bucket(self):
        return self._s3_bucket

    @s3_bucket.setter
    def s3_bucket(self, b):
        if not b:
            warnings.warn("Bucket cannot be empty", Warning)
        if b not in settings["bucket_drives"]:
            warnings.warn("Bucket '{0!s}' not registered in config file".format(b), Warning)
        self._s3_bucket = b

    # Validate folder
    @property
    def s3_path(self):
        return self._s3_path

    @s3_path.setter
    def s3_path(self, p):
        if not p:
            warnings.warn("Folder cannot be empty", Warning)
        self._s3_path = p

    # Validate source
    @property
    def dst_folder(self):
        return self._dst_folder

    @dst_folder.setter
    def dst_folder(self, d):
        if not os.path.exists(d):
            warnings.warn("Cannot find destination folder {0!s}".format(d), Warning)
        self._dst_folder = d

    def _archive(self, input_file, local=False):

        zip_folder = os.path.join(self.dst_folder, "zip")
        archive_folder = os.path.join(self.dst_folder, "archive")

        zip_file = archive.zip_file(input_file, self.zip_workspace, local)
        src = os.path.join(self.zip_workspace, zip_file)

        if not os.path.exists(zip_folder):
            os.mkdir(zip_folder)
        dst = os.path.join(zip_folder, zip_file)
        print "Copy ZIP to {0!s}".format(zip_folder)
        shutil.copy(src, dst)

        if not os.path.exists(archive_folder):
            os.mkdir(archive_folder)
        ts = time.time()
        timestamp = datetime.fromtimestamp(ts).strftime('%Y%m%d%H%M%S')
        dst = os.path.join(archive_folder, "{0!s}_{1!s}.zip".format(os.path.splitext(zip_file)[0], timestamp))
        print "Copy archived ZIP to {0!s}".format(archive_folder)
        shutil.copy(src, dst)

        input_f = os.path.basename(input_file)
        arcpy.Copy_management(input_file, os.path.join(input_f, self.dst_folder))

    def _get_metadata(self, layer):

        md = arcpy_metadata.MetadataEditor(layer)

        cache_file = settings['metadata']['cache']
        with open(cache_file) as c:
            data = c.read()

        md_gspread = json.loads(data)

        if self.name in md_gspread.keys():

            md.title.set(md_gspread[self.name]["Title"])
            md.locals['english'].title.set(md_gspread[self.name]["Translated_Title"])
            md.purpose.set(md_gspread[self.name]["Function"])
            md.abstract.st(md_gspread[self.name]["Overview"])
            md.locals['english'].abstract.set(md_gspread[self.name]["Translated Overview"])
            #  md_gspread[self.name]["category"]
            md.tags.add(util.csl_to_list(md_gspread[self.name]["Tags"]))
            md.extent_description.set(md_gspread[self.name]["Geographic Coverage"])
            md.last_update.set(md_gspread[self.name]["Date of Content"])
            md.update_frequency_description(md_gspread[self.name]["Frequency of Updates"])
            #  md.credits.set(md_gspread[self.name]["credits"])
            md.citation.set(md_gspread[self.name]["Citation"])
            md.limitation.set(md_gspread[self.name]["License"])
            md.supplemental_information.set(md_gspread[self.name]["Cautions"])
            md.source.set(md_gspread[self.name]["Source"])
            md.scale_resolution.set(md_gspread[self.name]["Resolution"])

        else:
            raise RuntimeError("No Metadata for layer {0!s}".format(self.name))

        return md

    def update_metadata(self):
        pass

