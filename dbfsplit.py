# -*- coding: utf-8 -*-

import os
import os.path as osp
import numpy as np

from PIL import Image, ImageDraw, ImageEnhance
import tifffile

import geopandas
from shapely.geometry import *
from shapely.affinity import translate

import sys
import json
import datetime

def load_image_file(filename):
    ext = osp.splitext(filename)[1].lower()

    try:
      if ext in [".tif", ".tiff"]:
        image = tifffile.imread(filename)
        image = image.astype("uint8")
        image = image[:,:,:3]
        image_pil = Image.fromarray(image)
      else:
        image_pil = Image.open(filename)
    except IOError:
      logger.error("Failed opening image file: {}".format(filename))
      return
    return np.array(image_pil)

if __name__ == '__main__':
  crop_size = (512, 512)
  margin = (128, 128)

  imagename = "./examples/hyper/WGS84_UTM zone 52N/t.tiff"

  path = osp.dirname(imagename)
  out_dir = osp.join(path, "sub")
  if not osp.exists(out_dir):
    os.mkdir(out_dir)

  sf = osp.splitext(imagename)[0] + ".shp"
  gdf = geopandas.read_file(sf, encoding='cp949')

  base, ext = osp.splitext(osp.basename(imagename))
  base = osp.join(out_dir, base)
  try:
    img = load_image_file(imagename)
    height, width, _ = img.shape
    
    si=0
    for y in range(margin[1], height-crop_size[1]-margin[1], crop_size[1]):
      for  x in range(margin[0], width-crop_size[0]-margin[0], crop_size[0]):
        sub = base + "_{}".format(si)
        sub_img = img[y-margin[1]:y+crop_size[1]+margin[1], x-margin[0]:x+crop_size[0]+margin[0], :].copy()

        image_pil = Image.fromarray(sub_img)
        sw, sh = image_pil.size
        overlay = Image.new(image_pil.mode, image_pil.size, 'white')
        blended = np.array(Image.blend(image_pil, overlay, 0.4))

        blended[margin[1]:crop_size[1]+margin[1], margin[0]:crop_size[0]+margin[0], :] = sub_img[margin[1]:crop_size[1]+margin[1], margin[0]:crop_size[0]+margin[0], :]
        image_pil = Image.fromarray(blended)
        #ImageDraw.Draw(image_pil).rectangle([(margin[0], margin[1]), (sw-margin[0], sh-margin[1])], outline='red')
        image_pil.save(sub + ext)

        #clip = Polygon([(x, -y), (x+crop_size[0], -y), (x+crop_size[0], -y-crop_size[1]), (x, -y-crop_size[1])])
        clip = Polygon([(x-margin[0], -y+margin[1]), (x+crop_size[0]+margin[0], -y+margin[1]), (x+crop_size[0]+margin[0], -y-crop_size[1]-margin[1]), (x-margin[0], -y-crop_size[1]-margin[1])])
        clipped = geopandas.clip(gdf, clip, True)
        if clipped.shape[0] > 0:
          geo = clipped.geometry
          clipped.geometry = geo.apply(lambda pt: translate(pt, xoff=-(x-margin[0]), yoff=(y-margin[1])))
          clipped.to_file(sub + ".shp", encoding='cp949')
        si+=1
  except Exception as e:
    print(e)
  sys.exit(0)