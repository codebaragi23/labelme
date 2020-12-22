import base64
import contextlib
from ctypes import c_uint8
import io
import json
import os.path as osp


import affine
import copy
import geopandas

import cv2
from tifffile import TiffFile
from PIL import Image

from mindAT import __version__
from mindAT.logger import logger
from mindAT import PY2
from mindAT import QT4
from mindAT import utils

Image.MAX_IMAGE_PIXELS = None


@contextlib.contextmanager
def open(name, mode):
  assert mode in ["r", "w"]
  if PY2:
    mode += "b"
    encoding = None
  else:
    encoding = "utf-8"
  yield io.open(name, mode, encoding=encoding)
  return


class LabelFileError(Exception):
  pass

class LabelFile(object):
  suffix = ".geojson"

  label_indi = "label"
  shape_type_indi = "shape_type"

  def __init__(self, filename=None, geo_transfrom=None, config=None):
    self.annotations = []
    self.imagePath = None
    self.imageData = None
    if filename is not None and geo_transfrom is not None:
      self.load(filename, geo_transfrom)
    self.filename = filename

  @staticmethod
  def load_image_file(filename, real_bitdepth=8):
    ext = osp.splitext(filename)[1].lower()

    import numpy as np
    try:
      if ext in [".tif", ".tiff"]:
        with TiffFile(filename) as tif:
          image = tif.asarray()

        if len(image.shape) < 3:
          image_pil = Image.open(filename)
          image_pil = image_pil.convert("RGB")

        #농업
        else:
          if image.shape[-1] != 3:
            image = image.transpose(1,2,0)

          if image.dtype != 'uint8' and real_bitdepth > 8:
            diff_bitdepth = real_bitdepth-8
            image = (image/(1<<diff_bitdepth)).clip(0, 255)
            image = image.astype("uint8")
            #image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
          image_pil = Image.fromarray(image)
      else:
        image_pil = Image.open(filename)
        
      image_pil = image_pil.convert("RGB")

    except IOError:
      logger.error("Failed opening image file: {}".format(filename))
      return

    # apply orientation to image according to exif
    image_pil = utils.apply_exif_orientation(image_pil)

    with io.BytesIO() as f:
      if PY2 and QT4:
        format = "PNG"
      elif ext in [".jpg", ".jpeg"]:
        format = "JPEG"
      else:
        format = "PNG"
      image_pil.save(f, format=format)
      f.seek(0)
      return f.read()

  def load(self, filename, geo_transfrom):
    keys = [
      "features",  # polygonal annotations
    ]
    features_keys = [
      "type",
      "properties",
      "geometry",
    ]
    annotation_keys = [
      self.label_indi,
    ]

    try:
      with open(filename, "r") as f:
        data = json.load(f)

      self.transform = affine.Affine.from_gdal(*geo_transfrom)
      transform = ~self.transform
      annotations = []
      for feature in data["features"]:
        if feature["geometry"][self.shape_type_indi].lower() == "multipolygon":
          multilen = len(feature["geometry"]["coordinates"][0])
          annot = dict(
            label=str(feature["properties"][self.label_indi]),
            shape_type="polygon",
            points=[list(transform*(geox, geoy)) for geox, geoy in feature["geometry"]["coordinates"][0][0]],
            
            flags={},
            group_id=None,
            other_data={
              k:v for k, v in feature["properties"].items() if k not in annotation_keys
            },
          )
          annotations.append(annot)

          for i in range(1, multilen, 2):
            annot = dict(
              label="_background_",
              shape_type="polygon",
              points=[list(transform*(geox, geoy)) for geox, geoy in feature["geometry"]["coordinates"][0][i]],
              
              flags={},
              group_id=None,
              other_data={
                k:v for k, v in feature["properties"].items() if k not in annotation_keys
              },
            )
            annotations.append(annot)

        else:
          annot = dict(
            label=str(feature["properties"][self.label_indi]),
            shape_type=feature["geometry"][self.shape_type_indi].lower(),
            points=[list(transform*(geox, geoy)) for geox, geoy in feature["geometry"]["coordinates"][0]],
            
            flags={},
            group_id=None,
            other_data={
              k:v for k, v in feature["properties"].items() if k not in annotation_keys
            },
          )
          annotations.append(annot)
    
    except Exception as e:
      raise LabelFileError(e)

    del data["features"]

    self.flags = {}
    self.imagePath = None
    self.imageData = None
    self.filename = None
    self.annotations = annotations
    self.otherData = data;

  def save(
    self,
    filename,
    annotations,
    imagePath,
    imageHeight,
    imageWidth,
    imageData=None,
    otherData=None,
    flags=None,
  ):
    data = self.otherData
    transform = self.transform

    features = []
    for annot in annotations:
      geometry = dict(
        type=annot["shape_type"].capitalize(),
        coordinates=[[list(transform*(x, y)) for x, y in annot["points"] ]]
      )
      properties = dict({self.label_indi:annot["label"]})
      properties.update(annot["other_data"])
      feature = dict(
        type="Feature",
        properties=properties,
        geometry=geometry,
      )
      features.append(feature)

    data["features"] = features

    try:
      with open(filename, "w") as f:
        json.dump(data, f, ensure_ascii=False)
      self.filename = filename
    except Exception as e:
      raise LabelFileError(e)

  @staticmethod
  def is_label_file(filename):
    return osp.splitext(filename)[1].lower() == LabelFile.suffix
