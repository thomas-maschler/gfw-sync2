from vector_layer import VectorLayer
from settings import *
import warnings


class S3VectorLayer(VectorLayer):

    def __init__(self, layerdef):

        self.type = "S3Layer"

        self._src_bucket = None
        self.src_bucket = layerdef['source']['bucket']

        self._src_path = None
        self.src_path = layerdef['source']['path']

        self._bucket_drive = settings["bucket_drives"][self.src_bucket]

        self._src = None
        self.src = os.path.join(self._bucket_drive, self.src_path)

        super(S3VectorLayer, self).__init__(layerdef)

    # Validate bucket
    @property
    def src_bucket(self):
        return self._src_bucket

    @src_bucket.setter
    def src_bucket(self, b):
        if not b:
            warnings.warn("Bucket cannot be empty", Warning)
        if b not in settings["bucket_drives"]:
            warnings.warn("Bucket '{0!s}' not registered in config file".format(b), Warning)
        self._src_bucket = b

    # Validate folder
    @property
    def src_path(self):
        return self._src_path

    @src_path.setter
    def src_path(self, p):
        if not p:
            warnings.warn("Folder cannot be empty", Warning)
        self._src_path = p

    # Validate source
    @property
    def src(self):
        return self._src

    @src.setter
    def src(self, s):
        if not os.path.exists(s):
            warnings.warn("Cannot find source file", Warning)
        self._src_path = s


class S3CountryVectorLayer(S3VectorLayer):

    def __init__(self, layerdef):

        self.type = "S3CountryVectorLayer"

        self._workspace = None
        self.workspace = settings['sde_connections']['gfw_countries']
        super(S3CountryVectorLayer, self).__init__(layerdef)
