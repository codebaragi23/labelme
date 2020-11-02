import base64
import contextlib
import io
import json
import os.path as osp

import cv2
import PIL.Image
import tifffile

from labelme import __version__
from labelme.logger import logger
from labelme import PY2
from labelme import QT4
from labelme import utils

PIL.Image.MAX_IMAGE_PIXELS = None


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

def LabelFileFromGeo(geo, geo_transfrom):
  labelFile = LabelFile()
  labelFile.fromGeo(geo, geo_transfrom)
  return labelFile

class LabelFile(object):
  suffix = ".json"

  def __init__(self, filename=None):
    self.annotations = []
    self.imagePath = None
    self.imageData = None
    if filename is not None:
      self.load(filename)
    self.filename = filename

  @staticmethod
  def load_image_file(filename):
    ext = osp.splitext(filename)[1].lower()

    import numpy as np
    try:
      if ext in [".tif", ".tiff"]:
        image = tifffile.imread(filename)
        image = image.astype("uint8")
        #image = image[:,:,:3]
        image_pil = PIL.Image.fromarray(image)
      else:
        image_pil = PIL.Image.open(filename)
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

  def fromGeo(self, data, geo_transfrom):
    keys = [
      "features",  # polygonal annotations
    ]
    features_keys = [
      "type",
      "properties",
      "geometry",
    ]
    annotation_keys = [
      "id",
      "type",
      "geometry",
    ]

    # relative path from label file to relative path from cwd
    # annotations = [
    #   dict(
    #     # label=feature["properties"]["작물ID"],
    #     # shape_type=feature["geometry"]["type"].lower(),
    #     # points=[[(geox-geo_transfrom[0])/geo_transfrom[1], (geoy-geo_transfrom[3])/geo_transfrom[5]] for geox, geoy in feature["geometry"]["coordinates"][0]],

    #     # t1
    #     # label=str(feature["properties"]["속성"]),
    #     # shape_type=feature["geometry"]["type"].lower(),
    #     # points=[[(geox-geo_transfrom[0])/geo_transfrom[1], (geoy-geo_transfrom[3])/geo_transfrom[5]] for geox, geoy in feature["geometry"]["coordinates"][0]],

    #     # t2
    #     # label=str(feature["properties"]["ann_name"]),
    #     # shape_type="polygon" if feature["geometry"]["type"].lower() == "multipolygon" else feature["geometry"]["type"].lower(),
    #     # #points=[[(geox-geo_transfrom[0])/geo_transfrom[1], (geoy-geo_transfrom[3])/geo_transfrom[5]] for geox, geoy in feature["geometry"]["coordinates"][0]],
    #     # points=[[x, y] for x, y in feature["geometry"]["coordinates"][0]],

    #     # t3
    #     label=str(feature["properties"]["ann_name"]),
    #     shape_type="polygon" if feature["geometry"]["type"].lower() == "multipolygon" else feature["geometry"]["type"].lower(),
    #     points=[[(geox-geo_transfrom[0])/geo_transfrom[1], (geoy-geo_transfrom[3])/geo_transfrom[5]] for geox, geoy in feature["geometry"]["coordinates"][0]],
        
    #     flags=feature.get("flags", {}),
    #     group_id=feature.get("group_id", None),
    #     other_data={
    #       k:v for k, v in feature.items() if k not in annotation_keys
    #     },
    #   )
    #   for feature in data["features"]
    # ]

    annotations = []
    for feature in data["features"]:
      if feature["geometry"]["type"].lower() == "multipolygon":
        multilen = len(feature["geometry"]["coordinates"])
        for i in range(multilen-1):
          annot = dict(
            label=str(feature["properties"]["ann_name"]),
            shape_type="polygon",
            points=[[(geox-geo_transfrom[0])/geo_transfrom[1], (geoy-geo_transfrom[3])/geo_transfrom[5]] for geox, geoy in feature["geometry"]["coordinates"][i][0]],
            
            flags=feature.get("flags", {}),
            group_id=feature.get("group_id", None),
            other_data={
              k:v for k, v in feature.items() if k not in annotation_keys
            },
          )
          annotations.append(annot)

        annot = dict(
          label=str(feature["properties"]["ann_name"]),
          shape_type="polygon",
          points=[[(geox-geo_transfrom[0])/geo_transfrom[1], (geoy-geo_transfrom[3])/geo_transfrom[5]] for geox, geoy in feature["geometry"]["coordinates"][multilen-1][0]],
          
          flags=feature.get("flags", {}),
          group_id=feature.get("group_id", None),
          other_data={
            k:v for k, v in feature.items() if k not in annotation_keys
          },
        )
      else:
        annot = dict(
          label=str(feature["properties"]["ann_name"]),
          shape_type=feature["geometry"]["type"].lower(),
          points=[[(geox-geo_transfrom[0])/geo_transfrom[1], (geoy-geo_transfrom[3])/geo_transfrom[5]] for geox, geoy in feature["geometry"]["coordinates"][0]],
          
          flags=feature.get("flags", {}),
          group_id=feature.get("group_id", None),
          other_data={
            k:v for k, v in feature.items() if k not in annotation_keys
          },
        )
      annotations.append(annot)

    otherData = {k:v for k, v in data.items() if k not in keys}
    
    self.flags = {}
    self.imagePath = None
    self.imageData = None
    self.filename = None
    self.annotations = annotations
    self.otherData = otherData

  def load(self, filename):
    keys = [
      "version",
      "imageData",
      "imagePath",
      "annotations",  # polygonal annotations
      "flags",  # image level flags
      "imageHeight",
      "imageWidth",
    ]
    annotation_keys = [
      "label",
      "shape_type",
      "points",
      "group_id",
      "flags",
    ]

    try:
      with open(filename, "r") as f:
        data = json.load(f)
        version = data.get("version")
        if version is None and format == "simple":
          logger.warn(
            "Loading JSON file ({}) of unknown version".format(
              filename
            )
          )
        elif version.split(".")[0] != __version__.split(".")[0]:
          logger.warn(
            "This JSON file ({}) may be incompatible with "
            "current labelme. version in file: {}, "
            "current version: {}".format(
              filename, version, __version__
            )
          )
      
      if data["imageData"] is not None:
        imageData = base64.b64decode(data["imageData"])
        if PY2 and QT4:
          imageData = utils.img_data_to_png_data(imageData)
      elif data["imagePath"] is not None:
        # relative path from label file to relative path from cwd
        imagePath = osp.join(osp.dirname(filename), data["imagePath"])
        imageData = self.load_image_file(imagePath)
      else:
        imageData = None

      flags = data.get("flags") or {}
      imagePath = data["imagePath"]
      if imageData is not None:
        self._check_image_height_and_width(
          base64.b64encode(imageData).decode("utf-8"),
          data.get("imageHeight"),
          data.get("imageWidth"),
        )
      annotations = [
        dict(
          label=annot["label"],
          shape_type=annot.get("shape_type", "polygon"),
          points=annot["points"],
          flags=annot.get("flags", {}),
          group_id=annot.get("group_id"),
          other_data={
            k: v for k, v in annot.items() if k not in annotation_keys
          },
        )
        for annot in data["annotations"]
      ]

      otherData = {}
      for key, value in data.items():
        if key not in keys:
          otherData[key] = value

    except Exception as e:
      raise LabelFileError(e)

    # Only replace data after everything is loaded.
    self.flags = flags
    self.annotations = annotations
    self.imagePath = imagePath
    self.imageData = imageData
    self.filename = filename
    self.otherData = otherData

  @staticmethod
  def _check_image_height_and_width(imageData, imageHeight, imageWidth):
    img_arr = utils.img_b64_to_arr(imageData)
    if imageHeight is not None and img_arr.shape[0] != imageHeight:
      logger.error(
        "imageHeight does not match with imageData or imagePath, "
        "so getting imageHeight from actual image."
      )
      imageHeight = img_arr.shape[0]
    if imageWidth is not None and img_arr.shape[1] != imageWidth:
      logger.error(
        "imageWidth does not match with imageData or imagePath, "
        "so getting imageWidth from actual image."
      )
      imageWidth = img_arr.shape[1]
    return imageHeight, imageWidth

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
    if imageData is not None:
      imageData = base64.b64encode(imageData).decode("utf-8")
      imageHeight, imageWidth = self._check_image_height_and_width(
        imageData, imageHeight, imageWidth
      )
    if otherData is None:
      otherData = {}
    if flags is None:
      flags = {}
    
    data = dict(
      version=__version__,
      flags=flags,
      annotations=annotations,
      imagePath=imagePath,
      imageData=imageData,
      imageHeight=imageHeight,
      imageWidth=imageWidth,
    )
    for key, value in otherData.items():
      assert key not in data
      data[key] = value

    # if format == 'GeoJSON':
    #   data = dict(
    #     type=otherData.get("type", "FeatureCollection"),
    #     crs=otherData.get("crs", { "type": "name", "properties": { "name": "urn:ogc:def:crs:EPSG::32652" } }),
    #     features= [dict({"type":"Feature", "properties":{"관리번호":None, "작물ID": k["label"], "작업위치":None}, "geometry":{"type":k["shape_type"].capitalize(), "coordinates":[[[x, -y] for x, y in k["points"] ]]}}) for k in annotations]
    #   )

    try:
      with open(filename, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
      self.filename = filename
    except Exception as e:
      raise LabelFileError(e)

  @staticmethod
  def is_label_file(filename):
    return osp.splitext(filename)[1].lower() == LabelFile.suffix
