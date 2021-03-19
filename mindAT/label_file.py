import base64
import contextlib
from ctypes import c_uint8
import io
import json
import os.path as osp

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
  suffix = ".json"

  def __init__(self, filename=None):
    self.annotations = []
    self.imagePath = None
    if filename is not None:
      self.load(filename)
    self.filename = filename

  @staticmethod
  def load_image_file(filename):
    try:
      image_pil = Image.open(filename)
    except IOError:
      logger.error("Failed opening image file: {}".format(filename))
      return

    # apply orientation to image according to exif
    image_pil = utils.apply_exif_orientation(image_pil)

    with io.BytesIO() as f:
      ext = osp.splitext(filename)[1].lower()
      if PY2 and QT4:
        format = "PNG"
      elif ext in [".jpg", ".jpeg"]:
        format = "JPEG"
      else:
        format = "PNG"
      image_pil.save(f, format=format)
      f.seek(0)
      return f.read()

  def load(self, filename):
    keys = [
      "version",
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
            "current mindAT. version in file: {}, "
            "current version: {}".format(
              filename, version, __version__
            )
          )
      

      flags = data.get("flags") or {}
      imagePath = data["imagePath"]
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
    self.filename = filename
    self.otherData = otherData

  def save(
    self,
    filename,
    annotations,
    imagePath,
    imageHeight,
    imageWidth,
    otherData=None,
    flags=None,
  ):
    if otherData is None:
      otherData = {}
    if flags is None:
      flags = {}
    
    data = dict(
      version=__version__,
      flags=flags,
      annotations=annotations,
      imagePath=imagePath,
      imageHeight=imageHeight,
      imageWidth=imageWidth,
    )
    for key, value in otherData.items():
      assert key not in data
      data[key] = value

    try:
      with open(filename, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
      self.filename = filename
    except Exception as e:
      raise LabelFileError(e)

  @staticmethod
  def is_label_file(filename):
    return osp.splitext(filename)[1].lower() == LabelFile.suffix