import urllib
import subprocess
import os
import util
import json
from settings import settings


def cartodb_sql(sql, raise_error=True):
    key = util.get_token(settings['cartodb']['token'])
    result = urllib.urlopen("{0!s}?api_key={1!s}&q={2!s}".format(settings["cartodb"]["sql_api"], key, sql))
    json_result = json.loads(result.readlines()[0])
    if raise_error and "error" in json_result.keys():
        raise SyntaxError("Wrong SQL syntax.\n {0!s}".format(json_result['error']))
    return json_result


def cartodb_create(file_name, raise_error=True):
    key = util.get_token(settings['cartodb']['token'])
    result = subprocess.check_call([r'ogr2ogr',
                                    '--config', 'CARTODB_API_KEY', key,
                                    '-progress', '-skipfailures',
                                    '-t_srs', 'EPSG:4326',
                                    '-f', 'CartoDB',
                                    'CartoDB:wri-01', file_name])
    if raise_error and result == 0:
        raise RuntimeError("OGR2OGR threw an error")


def cartodb_append(file_name, raise_error=True):
    key = util.get_token(settings['cartodb']['token'])
    result = subprocess.check_call([r'C:\Program Files\GDAL\ogr2ogr.exe',
                                    '--config', 'CARTODB_API_KEY', key,
                                    '-append', '-progress', '-skipfailures',
                                    '-t_srs', 'EPSG:4326',
                                    '-f', 'CartoDB',
                                    'CartoDB:wri-01', file_name])
    if raise_error and result == 0:
        raise RuntimeError("OGR2OGR threw an error")


def cartodb_sync(shp, production_table):

    basename = os.path.basename(shp)
    staging_table = os.path.splitext(basename)[0]

    print "upload data"
    cartodb_create(shp)

    print "repair geometry"
    sql = 'UPDATE {0!s} SET the_geom = ST_MakeValid(the_geom), the_geom_webmercator = ST_MakeValid(the_geom_webmercator) WHERE ST_IsValid(the_geom) = false'.format(staging_table)
    cartodb_sql(sql)

    print "push to production"
    sql = 'TRUNCATE {0!s}; INSERT INTO {1!s} SELECT * FROM {2!s}; COMMIT'.format(production_table, production_table, staging_table)
    cartodb_sql(sql)

    print "delete staging"
    sql = 'DROP TABLE IF EXISTS {0!s} CASCADE'.format(staging_table)
    cartodb_sql(sql)
