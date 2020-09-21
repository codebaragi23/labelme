# -*- coding: utf-8 -*-

import geopandas
import argparse
import sys

if __name__ == '__main__':
  dbf_fn = "./WGS84_UTM zone 52N/t.shp"
  json_fn = dbf_fn.replace('shp', 'geojson')
  
  try:
    dbf_file = geopandas.read_file(dbf_fn, encoding='cp949')
    dbf_file.to_file(json_fn, driver='GeoJSON')
  except Exception as e:
    print(e)