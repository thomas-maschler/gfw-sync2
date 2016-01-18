import sys
import getopt
from settings import *

from s3_vector_layer import *
#from osm_loggingroads_layer import OSMLoggingRoadsLayer
#from wdpa_layer import WDPALayer


def main(argv):
    print "{0!s} v{1!s}".format(settings['tool_info']['name'], settings['tool_info']['version'])
    print ""

    layers = []
    countries = []
    validate = False
    verbose = True
    logging = True
    try:
        opts, args = getopt.getopt(argv, "hl:c:", ["help", "layers=", "country="])
    except getopt.GetoptError:
        print "Error: Invalide argument"
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        #elif opt == "-d":
        #    global _debug
        #    _debug = 1
        if opt in ("-n", "--nonverbose"):
            verbose = False
        if opt in ("-g", "--nolog"):
            logging = False
        if opt in ("-l", "--layers"):
            layers.append(arg.lower())
        if opt in ("-c", "--country"):
            countries.append(arg.upper())
               
    if not len(layers):
        #print len(layers)
        layers = get_layer_list()
        print layers

    layerdefs = get_layers()

    for l in layers:
        layerdef = layerdefs[0][l]
        layerdef["name"] = l

        if layerdef["type"] == "s3_vector":
            layer = S3VectorLayer(layerdef)
        elif layerdef["type"] == "s3_country_vector":
            layer = S3CountryVectorLayer(layerdef)
       # elif layerdef["type"] == "wdpa":
       #     layer = WDPALayer(layerdef)
       # elif layerdef["type"] == "osm_loggingroads":
       #     layer = OSMLoggingRoadsLayer(layerdef)
       # elif layerdef["type"] == "wdpa_layer":
       #     layer = WDPALayer(layerdef)
        else:
            raise RuntimeError("Layer type unknown")

        #layer.update()


def usage():
    layers = settings.get_layer_list()

    print "Usage: gfw-sync.py [options]"
    print "Options:"
    print "-h, --help               Show help of GFW Sync Tool"
    print "-n, --nonverbose        Turn console messages off"
    print "-g, --nolog             Turn logging off"
    print "-c <country ISO3 code>   Country to be updated. Update will affect all selected layers."
    print "                         If left out, all countries will be selected."
    print "                         You can use this option multiple times"
    print "-l <GFW layers name>      GFW Layer, which will be updated. Update will affect all selected countries"
    print "                         If left out, all layers will be selected."
    print "                         You can use this option multiple times"
    print "                         Currently supported layers:"
    for layer in layers:
        print "                             {0!s}".format(layer)




if __name__ == "__main__":

    main(sys.argv[1:])

