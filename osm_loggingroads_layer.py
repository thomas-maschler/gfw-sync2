import urllib
import urllib2
import json
import time
import zipfile
import os
import glob
import arcpy

from vector_layer import VectorLayer

class OSMLoggingRoadsLayer(VectorLayer):

    def __init__(self, layerdef):
        super(OSMLoggingRoadsLayer, self).__init__(layerdef)


def get_auth_key():
    return "d2cf58f46fd21ad1e4c21d300fc0d3c9c3292a78"

def rerun_job(job_uid):
    authKey = get_auth_key()
    headers = {"Content-Type":"application/json", "Authorization":"Token " + authKey}
    url = "http://export.hotosm.org/api/rerun?job_uid={0!s}".format(job_uid)
    request = urllib2.Request(url)

    for key, value in headers.items():
        request.add_header(key, value)

    return urllib2.urlopen(request)


def get_job(job_uid):
    authKey = get_auth_key()
    headers = {"Content-Type":"application/json", "Authorization":"Token " + authKey}
    url = "http://export.hotosm.org/api/runs?job_uid={0!s}".format(job_uid)

    request = urllib2.Request(url)

    for key, value in headers.items():
        request.add_header(key, value)

    return urllib2.urlopen(request)

job_uids = ["232bfe18-6d54-4922-82a9-901cf378d66f",
            "2300c2a0-0853-40ca-b8dd-761341a29234",
            "4e4c3427-28f2-4dcc-9623-1ef22958ee97",
            "c8be360c-1531-467e-978b-e3d77521e01f",
            "5466b5aa-2b3a-4956-a8a7-6739b444ca75",
            "87360642-9a33-47f5-ae94-f580e1376409"]


#for job_uid in job_uids:
#    print "rerun job %s" % job_uid
#    rerun_job(job_uid)

results = {}

for job_uid in job_uids:
    results[job_uid] = {}
    results[job_uid]["reruns"] = 0
    results[job_uid]["url"] = None

done = False

while done:

    time.sleep(60)
    done = True

    for job_uid in job_uids:

        if results[job_uid]["url"] is None:

            print "get job {0!s}".format(job_uid)
            data = json.load(get_job(job_uid))

            if data[0]['status'] == 'SUBMITTED':
                print "SUMBITTED"
                done = False
            elif data[0]['status'] == 'COMPLETED' and data[0]['tasks'][4]['status'] == 'SUCCESS':
                print "COMPLETED"
                results[job_uid]["url"] = data[0]['tasks'][4]['result']['url']
                results[job_uid]["filename"] = data[0]['tasks'][4]['result']['filename']

            else:
                results[job_uid]["reruns"] += 1
                if results[job_uid]["reruns"] > 4:
                    print "fob {0!s} failed".format(job_uid)

                else:
                    rerun_job(job_uid)
                    done = False




temp_folder = r"c:\temp"
shps = []
for job_uid in job_uids:
    if results[job_uid]["url"] is not None:
        zip_path = os.path.join(temp_folder, results[job_uid]["filename"])
        unzip_folder = os.path.join(temp_folder, os.path.splitext(results[job_uid]["filename"])[0])
        if not os.path.exists(unzip_folder):
            os.mkdir(unzip_folder)

        #print "download job %s" % job_uid
        #urllib.urlretrieve(results[job_uid]["url"], zip_path)

        #with zipfile.ZipFile(zip_path, "r") as z:
        #    z.extractall(unzip_folder)

        #os.remove(zip_path)

        shps = shps + glob.glob(unzip_folder + r'\*.shp')

i = 0
inputs = []

for shp in shps:
    i += 1
    if i == 1:
        target = shp
    else:
        inputs.append(shp)

print "append shapefiles"
arcpy.Append_management(inputs, target, "TEST")

# Replace a layer/table view name with a path to a dataset (which can be a layer file) or create the layer/table view within the script
# The following inputs are layers or table views: "roads_paths_lines"

arcpy.env.overwriteOutput = True
out_feature_class = os.path.join(temp_folder, "osm_logging_roads.shp")

print "dissolve shapefile"
arcpy.Dissolve_management(target,
                          out_feature_class,
                          "osm_id;access;bridge;end_date;ferry;ford;highway;informal;maxspeed;name;oneway;opening_ho;operator;ref;route;seasonal;smoothness;source;start_date;surface;trail_visi;tunnel;width",
                          "",
                          "MULTI_PART",
                          "DISSOLVE_LINES")

