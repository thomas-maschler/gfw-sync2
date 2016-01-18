import glob
import os
from configobj import ConfigObj


def get_ini_file(folder, ini_f):
    abspath = os.path.abspath(__file__)
    dir_name = os.path.dirname(abspath)
    ini_file = os.path.join(dir_name, folder, ini_f)
    content = ConfigObj(ini_file)

    return content


def get_settings():
    return get_ini_file('config', 'settings.ini')


def get_layers_from_file(f):
    return get_ini_file('layers', f)


def get_country_iso3_list():
    return get_ini_file('config', 'country_iso3.ini')


def get_layer_ini_files():
    abspath = os.path.abspath(__file__)
    dir_name = os.path.dirname(abspath)
    layer_folder = os.path.join(dir_name, 'layers')
    ini_files = glob.glob(r"{0!s}\*.ini".format(layer_folder))
        
    return ini_files


def get_layers():
    layers = []
    for f in get_layer_ini_files():
        layers.append(ConfigObj(f))

    return layers


def get_layer_list():

    layers = get_layers()
    layer_list = []
    for layer in layers:
        layer_list.append(layer.keys()[0])

    return layer_list


settings = get_settings()

