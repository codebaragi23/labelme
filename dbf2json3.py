# -*- coding: utf-8 -*-

import geopandas
import sys
import json
import datetime


if __name__ == '__main__':
  try:
    #dbf_fn = sys.argv[1]
    dbf_fn = "./examples/hyper/WGS84_UTM zone 52N/t.shp"
    json_fn = dbf_fn.replace('shp', 'json')
    try:
      json_fn = sys.argv[2]
    except IndexError:
      pass
  except IndexError:
    sys.stderr.write('usage: dbf2json <dbf_filename_input> (json_filename_input)\n\t json filename is optional, will write to stdout if not given or -. If - is given for input, it will read from stdin\n')
    sys.stderr.flush()
    sys.exit(1)
  
  dbf_file = geopandas.read_file(dbf_fn, encoding='cp949')
  dbf_file.to_file(json_fn, driver='GeoJSON')
  sys.exit(0)