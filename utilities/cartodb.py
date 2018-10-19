import json
import logging
import os
import sys
import urllib
import requests
import arcpy
from collections import OrderedDict
from retrying import retry

import util
import settings
import token_util


def get_api_key_and_url(gfw_env):

    key = token_util.get_token(settings.get_settings(gfw_env)['cartodb']['token'])
    api_url = settings.get_settings(gfw_env)["cartodb"]["sql_api"]
    # sync_api = settings.get_settings(gfw_env)["cartodb"]["synchronization_api"]

    return key, api_url#, sync_api


def cartodb_sql(sql, gfw_env):
    """
    Execute a SQL statement using the API
    :param sql: a SQL statment
    :param gfw_env: the gfw_env-- used to grab the correct API token
    :return:
    """

    logging.debug(sql)
    key, api_url = get_api_key_and_url(gfw_env)

    result = urllib.urlopen("{0!s}?api_key={1!s}&q={2!s}".format(api_url, key, sql))
    print "{0!s}?api_key={1!s}&q={2!s}".format(api_url, key, sql)
    json_result = json.loads(result.readlines()[0], object_pairs_hook=OrderedDict)

    print json_result

    if "error" in json_result.keys():
        raise SyntaxError(json_result['error'])

    return json_result


def sqlite_row_count(sqlite_db):

    ogrinfo = util.run_subprocess(['ogrinfo', '-q', sqlite_db])

    # Grab the first line from the ogrinfo command, split it, and take the second value
    # Example ogrinfo output: "1: tiger_conservation_landscapes (Multi Polygon)"
    table_name = ogrinfo[0].split()[1]

    ogr_row_count_text = util.run_subprocess(['ogrinfo', sqlite_db, '-q',
                                         '-sql', 'SELECT count(*) FROM {0}'.format(table_name)])

    # Response looks like this ['', 'Layer  name: SELECT', 'OGRFeature(SELECT):0', 'count(*) (Integer) = 76', '']
    row_count = int(ogr_row_count_text[-2].split(' = ')[1])

    return row_count


def get_layer_type(in_fc):
    """
    Get the layer type-- important for ogr2ogr; if we're working with a line string need to explicitly set the otuput
    to line string, not polyline/whatever it is natively in Arc
    :param in_fc:
    :return:
    """

    if os.path.splitext(in_fc)[1] == '.sqlite':
        ogrinfo = util.run_subprocess(['ogrinfo', '-q', in_fc], log=False)
        shapetype = ogrinfo[0].split('(')[1].lower()

    else:
        shapetype = arcpy.Describe(in_fc).shapeType.lower()

    if 'string' in shapetype or 'line' in shapetype:
        layer_type = 'LINE'
    elif 'polygon' in shapetype:
        layer_type = 'POLYGON'
    else:
        logging.error("Unknown layer type: {0}".format(shapetype))
        sys.exit(1)

    return layer_type


def cartodb_create(sqlite_path, template_table, output_table, temp_id_field, gfw_env):
    """
    Create a new dataset/table on cartodb
    :param sqlite_path: path to sqlite database with geometry-cleaned FC
    :param template_table: existing cartodb table used as a template
    :param output_table: name of the new table to create and push data to
    :param temp_id_field: temp id field that will be used to build where_clauses when uploading to cartodb
    :param gfw_env: the gfw-env-- required to pick the API key
    :return:
    """
    logging.debug("upload data from {0} to staging table {1}".format(sqlite_path, output_table))

    # Create a copy of the output table for staging
    create_staging_table_sql = "CREATE TABLE {0} AS SELECT * FROM {1} " \
                               "WHERE cartodb_id = -9999".format(output_table, template_table)

    cartodb_sql(create_staging_table_sql, gfw_env)

    # https://github.com/CartoDB/cartodb/wiki/creating-tables-though-the-SQL-API
    # Make the table we created 'discoverable' in the cartoDB UI
    # Need to use the account name because we're a multi-user account (per cartoDB support)
    account_name = get_account_name(gfw_env)

    # Unclear what the deal is with this; apparently if we're using the default account (wri-01) it
    # will fail if we include that in the select statement. annoying.
    if account_name == 'wri-01':
        cartodb_sql("select cdb_cartodbfytable('{0}');".format(output_table), gfw_env)
    else:
        cartodb_sql("select cdb_cartodbfytable('{0}', '{1}');".format(account_name, output_table), gfw_env)

    # Count dataset rows and compare them to the append limit we're using for each API transaction
    row_count = sqlite_row_count(sqlite_path)

    # Use cartodb_execute_where_clause to generate where_clauses and append them with exponential backoff
    cartodb_execute_where_clause(0, row_count, temp_id_field, sqlite_path, output_table, gfw_env)


def add_fc_to_ogr2ogr_cmd(in_path, cmd):
    """
    Add FC or spatialite DB to ogr2ogr, handling issue of different format for .shp vs GDB FC vs spatialite
    Also add conversion from multiline string to singleline string if it's a line FC
    :param in_path: path to shape/GDB/spatialite DB
    :param cmd: current list of CMD parameters
    :return: updated cmd list of parameters
    """

    layer_type = get_layer_type(in_path)

    if layer_type == 'LINE':
        cmd += ['-nlt', 'LINESTRING']

    elif layer_type == 'POLYGON':
        cmd += ['-nlt', 'MULTIPOLYGON']

    # Check if the input FC is a GDB
    if os.path.splitext(in_path)[1] == '':
        cmd += [os.path.dirname(in_path), os.path.basename(in_path)]

    else:
        cmd += [in_path]

    return cmd


def add_where_clause_to_ogr2ogr_cmd(in_where_clause, cmd):
    """
    Add where clause to cmd list of parameters if it exists
    :param in_where_clause: where clause
    :param cmd: current list of CMD parameters
    :return: updated cmd list of parameters
    """
    if in_where_clause:
        cmd.insert(1, '-where')
        cmd.insert(2, in_where_clause)

    return cmd


def cartodb_append(sqlite_db_path, out_cartodb_name, gfw_env, where_clause=None):
    """
    Append a local FC to a cartoDB dataset
    :param sqlite_db_path: path to local sqlite db
    :param out_cartodb_name: cartoDB table
    :param gfw_env: gfw_env
    :param where_clause: where_clause to apply to the dataset
    :return:
    """
    key = token_util.get_token(settings.get_settings(gfw_env)['cartodb']['token'])
    account_name = get_account_name(gfw_env)

    # Help: http://www.gdal.org/ogr2ogr.html
    # The -dim 2 option ensures that only two dimensional data is created; no Z or M values
    cmd = [r'C:\Program Files\GDAL\ogr2ogr', '--config', 'CARTODB_API_KEY', key, '-append', '-skipfailures', '-t_srs', 'EPSG:4326',
           '-f', 'CartoDB',  '-nln', out_cartodb_name, '-dim', '2', 'CartoDB:{0}'.format(account_name)]

    cmd = add_fc_to_ogr2ogr_cmd(sqlite_db_path, cmd)
    cmd = add_where_clause_to_ogr2ogr_cmd(where_clause, cmd)

    util.run_subprocess(cmd)


def get_account_name(gfw_env):
    account_name = settings.get_settings(gfw_env)['cartodb']['token'].split('@')[0]

    return account_name


def cartodb_check_exists(table_name, gfw_env):
    """
    Check if the table exists by executing a LIMIT 1 query against it
    :param table_name: cartoDB table name
    :param gfw_env: gfw env
    :return: True | False
    """
    sql = "SELECT * FROM {0} LIMIT 1".format(table_name)

    try:
        cartodb_sql(sql, gfw_env)
        table_exists = True
    except SyntaxError:
        table_exists = False

    return table_exists


def get_column_order(table_name, gfw_env):
    """
    Get column order-- used to list fields for cartoDB datasets
    :param table_name: cartoDB table
    :param gfw_env: gfw env
    :return: field list
    """
    sql = 'SELECT * FROM {0} LIMIT 1'.format(table_name)

    return cartodb_sql(sql, gfw_env)['fields'].keys()


def cartodb_min_max(table_name, gfw_env):
    """
    Get min/max id for cartodb_id in table
    :param table_name: cartoDB table
    :param gfw_env: gfw env
    :return: int value of row count
    """
    sql = "SELECT min(cartodb_id) as a, max(cartodb_id) as b FROM {0}".format(table_name)
    result = cartodb_sql(sql, gfw_env)['rows'][0]
    print '\n\n'
    print result
    print '\n\n'

    min_cartodb_id = result['a']

    # Add 1 to this value so that it's included in any >= and < statements
    max_cartodb_id = result['b'] + 1

    logging.debug('CartoDB ID min: {0}, max: {1}'.format(min_cartodb_id, max_cartodb_id))

    return min_cartodb_id, max_cartodb_id


def cartodb_push_to_production(staging_table, production_table, gfw_env):
    """
    Push temporary cartoDB staging table to production by selecting rows from it and inserting into production table
    :param staging_table: staging table
    :param production_table: prod table
    :param gfw_env: gfw env
    :return:
    """
    logging.debug("push staging to production table: {0}".format(production_table))

    min_cartodb_id, max_cartodb_id = cartodb_min_max(staging_table, gfw_env)

    prod_columns = get_column_order(production_table, gfw_env)
    staging_columns = get_column_order(staging_table, gfw_env)

    # Find the columns they have in common, excluding cartodb_id
    final_columns = [x for x in prod_columns if x in staging_columns if x != 'cartodb_id']
    final_columns_sql = ', '.join(final_columns)

    sql = 'INSERT INTO {0} ({1}) SELECT {1} FROM {2} WHERE {3}'
    format_tuple = (production_table, final_columns_sql, staging_table)

    cartodb_execute_where_clause(min_cartodb_id, max_cartodb_id, 'cartodb_id', None, None, gfw_env, sql, format_tuple)


def cartodb_execute_where_clause(start_row, end_row, id_field, src_fc, out_table, gfw_env, sql=None, format_tuple=None):
    """
    Generates a where clause and executes it to append to a cartodb table or execute SQL against the API
    :param start_row: first row ID of the where clause
    :param end_row: last row ID
    :param id_field: field to use to build integer where clauses
    :param src_fc: source FC, if appending from a local esri FC
    :param out_table: out table, if appending to a cartoDB table
    :param gfw_env: need to know which account to use
    :param sql: SQL statement to execute against the cartoDB API
    :param format_tuple: tuple to pass when formatting the SQL statement
    :return:
    """
    for wc in util.generate_where_clause(start_row, end_row, id_field, 500):
        cartodb_retry(src_fc, out_table, gfw_env, sql, format_tuple, wc)


def cartodb_make_valid_geom_local(src_fc):

    if os.path.splitext(src_fc)[1] == '.shp':
        source_dir = os.path.dirname(src_fc)

    # Need to write the outfile to shp-- ogr2ogr can't handle true curves stored in geodatabases
    # Will represent them as a point, which spatialite will then choke on
    else:
        source_dir = os.path.dirname(os.path.dirname(src_fc))
        file_name = 'source.shp'
        arcpy.FeatureClassToFeatureClass_conversion(src_fc, source_dir, file_name)

        src_fc = os.path.join(source_dir, file_name)

    sqlite_dir = os.path.join(source_dir, 'sqlite')
    os.mkdir(sqlite_dir)

    out_sqlite_path = os.path.join(sqlite_dir, 'out.sqlite')

    cmd = ['ogr2ogr', '-f', 'SQLite', out_sqlite_path]
    cmd = add_fc_to_ogr2ogr_cmd(src_fc, cmd)
    cmd += ["-dsco", "SPATIALITE=yes", '-dim', '2']

    logging.debug('Creating sqlite database')
    util.run_subprocess(cmd)

    table_name = util.gen_paths_shp(src_fc)[2]
    sql = 'UPDATE {0} SET GEOMETRY = ST_MakeValid(GEOMETRY) WHERE ST_IsValid(GEOMETRY) <> 1;'.format(table_name)
    cmd = ['spatialite', out_sqlite_path, sql]

    util.run_subprocess(cmd)

    return out_sqlite_path


@retry(wait_exponential_multiplier=1000, wait_exponential_max=512000, stop_max_delay=18000000)
def cartodb_retry(src_fc, out_table, gfw_env, sql, format_tuple, wc):
    """
    Used to retry the ogr2ogr append/SQL query defined from by the where clause
    Wait 2^x seconds between each retry, up to 8.5 minutes, then 8.5 minutes afterwards until we hit 5 hours
    :param src_fc: the source fc, if appending
    :param out_table: the out table, if appending
    :param gfw_env: gfw_env to know which cartodb account
    :param sql: SQL to execute against the API
    :param format_tuple: tuple to format the sql statement if {0}/{1}/etc included
    :param wc: the where clause to add to the SQL statement
    :return:
    """
    if sql:
        format_tuple += (wc,)
        sql = sql.format(*format_tuple)
        cartodb_sql(sql, gfw_env)

    else:
        cartodb_append(src_fc, out_table, gfw_env, wc)


def cartodb_delete_where_clause_or_truncate_prod_table(in_prod_table, in_wc, in_gfw_env):
    """
    Delete features from cartoDB prod table, using a where clause if it exists
    :param in_prod_table: prod_table
    :param in_wc: where clause
    :param in_gfw_env: gfw env
    :return:
    """
    logging.debug("delete or truncate rows from production table")

    if in_wc:
        sql = 'DELETE FROM {0!s} WHERE {1}'.format(in_prod_table, in_wc)
    else:
        sql = 'TRUNCATE {0!s};'.format(in_prod_table)

    cartodb_sql(sql, in_gfw_env)


def delete_staging_table_if_exists(staging_table_name, in_gfw_env):
    """
    Delete staging table if it exists
    :param staging_table_name: table name
    :param in_gfw_env: gfw env
    :return:
    """
    logging.debug("delete staging if it exists")

    sql = 'DROP TABLE IF EXISTS {0} CASCADE'.format(staging_table_name)
    cartodb_sql(sql, in_gfw_env)


def ogrinfo_min_max(input_fc, oid_fieldname):
    input_table_name = os.path.basename(os.path.splitext(input_fc)[0])

    # ogrinfo doesn't recognize OBJECTID in these cases, apparently
    # Also need to only have the GDB as an input, doesn't want entire FC path
    if '.gdb' in input_fc:
        oid_fieldname = 'FID'
        input_fc = os.path.dirname(input_fc)

    sql_statement = 'SELECT min({0}), max({0}) FROM {1}'.format(oid_fieldname, input_table_name)
    ogrinfo = util.run_subprocess([r'C:\Program Files\GDAL\ogrinfo', input_fc, '-sql', sql_statement])

    # Grab the last two lines with data (the final line is blank)
    result_lines = ogrinfo[-3:-1]

    # Result lines look like `MIN_FID (Integer) = 0`
    # Split them at the ' = ' and grab the result then convert to int()
    result_vals = [int(l.split(' = ')[1]) for l in result_lines]

    return result_vals[0], result_vals[1]


def cartodb_sync(shp, production_table, where_clause, gfw_env, scratch_workspace):
    """
    Function called by VectorLayer and other Layer objects as part of layer.update()
    Will carry out the sync process from start to finish-- pushing the shp to a staging table on cartodb, then
    to production on cartodb, using a where_clause if included
    :param shp: input feature class (can be GDB FC or SDE too)
    :param production_table: final output table in cartoDB
    :param where_clause: where_clause to use when adding/deleting from final prod table
    :param gfw_env: gfw env
    :param scratch_workspace: scratch workspace
    :return:
    """

    # ogr2ogr can't use an SDE fc as an input; must export to GDB
    if where_clause or 'localhost' in shp:
        shp = util.fc_to_temp_gdb(shp, scratch_workspace, where_clause)

    basename = os.path.basename(shp)
    staging_table = os.path.splitext(basename)[0] + '_staging'

    delete_staging_table_if_exists(staging_table, gfw_env)

    # Create a temp ID field (set equal to OBJECTID) that we'll use to manage pushing to cartodb incrementally
    temp_id_field = util.create_temp_id_field(shp, gfw_env)

    validated_fc_in_sqlite = cartodb_make_valid_geom_local(shp)

    cartodb_create(validated_fc_in_sqlite, production_table, staging_table, temp_id_field, gfw_env)

    cartodb_delete_where_clause_or_truncate_prod_table(production_table, where_clause, gfw_env)

    cartodb_push_to_production(staging_table, production_table, gfw_env)

    delete_staging_table_if_exists(staging_table, gfw_env)


def cartodb_force_sync(gfw_env, table_name):
    """force sync on synced table: https://carto.com/docs/carto-engine/import-api/sync-tables
    :param gfw_env: gfw_env
    :param table_name: carto table name
    """

    key, api_url, sync_api = get_api_key_and_url(gfw_env)

    #get synced tables data
    get_tables_url = ("{0!s}/?api_key={1!s}".format(sync_api, key))

    r = requests.get(get_tables_url)
    table_data = r.json()

    #get sync table id
    for entry in table_data['synchronizations']:
        if entry['name'] == table_name:
            table_id = entry['id']

    #force table sync
    sync_tables_url = ("{0!s}/{1!s}/sync_now?api_key={2!s}".format(sync_api, table_id, key))

    r = requests.put(sync_tables_url)
    status = r.status_code

    if status == 200:
        logging.debug("Sync Table Success for {}".format(table_name))
    else:
        print r.text
        logging.debug(r.text)
        raise ValueError('Request failed with code: {}'.format(status))
