import logging
import requests

from utilities import cartodb

def post_process(layerdef):
    """
    Update the date value in the layerspec table-- required for the time slider to work properly
    :param layerdef: the layerdef
    :return:
    """

    if layerdef.gfw_env == 'prod':
        update_layerspec(layerdef)

    else:
        logging.debug('Not updating layerspec table; gfw_env is {0}'.format(layerdef.gfw_env))


def update_layerspec(layerdef):
    sql = "UPDATE layerspec set maxdate = (SELECT max(date) + INTERVAL '1 day' " \
          "FROM gran_chaco_deforestation) WHERE table_name='gran_chaco_deforestation'"

    key, api_url = cartodb.get_api_key_and_url(layerdef.gfw_env)
    payload = {'api_key': key, 'q': sql}

    r = requests.get(api_url, params=payload)

    resp = r.json()
    logging.debug(resp)

    if 'error' in resp.keys():
        raise ValueError('Error in carto response')
