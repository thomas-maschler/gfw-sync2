import os
import arcpy
import json

def byteify(unicode_string):
    if isinstance(unicode_string, dict):
        return {byteify(key):byteify(value) for key, value in unicode_string.iteritems()}
    elif isinstance(unicode_string, list):
        return [byteify(element) for element in unicode_string]
    elif isinstance(unicode_string, unicode):
        return unicode_string.encode('utf-8')
    else:
        return unicode_string


def get_srs(layer):
    desc = arcpy.Describe(layer)
    return desc.spatialReference.name


def csl_to_list(csl):
    l = csl.split(',')
    result = []
    for item in l:
        result.append(item.strip())
    return result

def get_token(token_file):
    abspath = os.path.abspath(__file__)
    dir_name = os.path.dirname(abspath)
    token_path = os.path.join(dir_name, r"tokens\{0!s}".format(token_file))
    if not os.path.exists(token_file):
        raise IOError('Cannot find any token for {0!s}\n Make sure there is a file called {1!s} in the tokens directory'.format(token_file, token_file))
    else:
        if os.path.splitext(token_file)[1] == '.json':
            return json.load(open(token_path))
        else:
            with open(token_path, "r") as f:
                for row in f:
                    return row

