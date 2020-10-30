# -*- coding: utf-8 -*-

import geopandas
import gdal

import argparse, sys

import cv2
import PIL.Image

if __name__ == '__main__':
  gname = "_temp/test2/LC_AP_37711081_139_FGT_rgb.tif"
  png_fn = gname.replace('tif', 'png')
  json_fn = gname.replace('tif', 'geojson')
  
  options_list = [
    '-ot Byte',
    '-of JPEG',
    '-b 1',
    '-scale'
  ]           
  options = " ".join(options_list)
  
  try:
    img = cv2.imread("examples/bbox_detection/data_annotated/2011_000003.jpg")
    cv2.imshow("image", img)

    # ds = gdal.Translate(png_fn, gname, format='PNG', outputType=gdal.GDT_Byte, scaleParams=[[0,255]])
    # img = PIL.Image.open("_temp/test2/LC_AP_37711081_138_FGT_rgb.jpg")
    # img.show()



    # ds = gdal.Open(gname, gdal.GA_ReadOnly)
    # rb = ds.GetRasterBand(1)
    # img = rb.ReadAsArray()
    #g = gdal.Open(gname)
    #img = g.ReadAsArray()
    #gdal.Translate(png_fn, gname, options=options)
    # ds = gdal.Translate(png_fn, gname, format='PNG', outputType=gdal.GDT_Byte, scaleParams=[[0,255]])
    # geo_transfrom =  g.GetGeoTransform()
    # geo = geopandas.read_file(json_fn, encoding='cp949')

    # print(geo_transfrom)
    # print(g.RasterXSize, g.RasterYSize)
    # pixel_x = (245415.699909792485414-geo_transfrom[0])/geo_transfrom[1]
    # pixel_y = (520115.511655988113489-geo_transfrom[3])/geo_transfrom[5]
    print("Done")

  except Exception as e:
    print(e)