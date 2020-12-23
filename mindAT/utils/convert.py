import math
import uuid
import re
import cv2

import numpy as np
import PIL.Image
import PIL.ImageDraw

from mindAT.logger import logger
from mindAT.annotation import Annotation
from mindAT import PY2

from qtpy import QtCore

def polygons_to_mask(img_shape, polygons, shape_type=None):
  logger.warning(
    "The 'polygons_to_mask' function is deprecated, "
    "use 'shape_to_mask' instead."
  )
  return shape_to_mask(img_shape, points=polygons, shape_type=shape_type)


def shape_to_mask(
  img_shape, points, shape_type=None, line_width=10, point_size=5
):
  mask = np.zeros(img_shape[:2], dtype=np.uint8)
  mask = PIL.Image.fromarray(mask)
  draw = PIL.ImageDraw.Draw(mask)
  xy = [tuple(point) for point in points]
  if shape_type == "circle":
    assert len(xy) == 2, "Shape of shape_type=circle must have 2 points"
    (cx, cy), (px, py) = xy
    d = math.sqrt((cx - px) ** 2 + (cy - py) ** 2)
    draw.ellipse([cx - d, cy - d, cx + d, cy + d], outline=1, fill=1)
  elif shape_type == "rectangle":
    assert len(xy) == 2, "Shape of shape_type=rectangle must have 2 points"
    draw.rectangle(xy, outline=1, fill=1)
  elif shape_type == "line":
    assert len(xy) == 2, "Shape of shape_type=line must have 2 points"
    draw.line(xy=xy, fill=1, width=line_width)
  elif shape_type == "linestrip":
    draw.line(xy=xy, fill=1, width=line_width)
  elif shape_type == "point":
    assert len(xy) == 1, "Shape of shape_type=point must have 1 points"
    cx, cy = xy[0]
    r = point_size
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=1, fill=1)
  else:
    assert len(xy) > 2, "Polygon must have points more than 2"
    draw.polygon(xy=xy, outline=1, fill=1)
  mask = np.array(mask, dtype=bool)
  return mask

def annotations_to_label(img_shape, annotations, classes):
  cls = np.zeros(img_shape[:2], dtype=np.int32)
  ins = np.zeros_like(cls)
  instances = []
  for annotation in annotations:
    shape_type = annotation.get("shape_type", None)
    points = annotation["points"]
    label = annotation["label"]
    group_id = annotation.get("group_id")
    if group_id is None:
      group_id = uuid.uuid1()

    cls_name = label
    instance = (cls_name, group_id)

    if instance not in instances:
      instances.append(instance)
    ins_id = instances.index(instance) + 1
    cls_id = classes[cls_name]

    mask = shape_to_mask(img_shape[:2], points, shape_type)
    cls[mask] = cls_id
    ins[mask] = ins_id

  return cls, ins

def masks_to_bboxes(masks):
  if masks.ndim != 3:
    raise ValueError(
      "masks.ndim must be 3, but it is {}".format(masks.ndim)
    )
  if masks.dtype != bool:
    raise ValueError(
      "masks.dtype must be bool type, but it is {}".format(masks.dtype)
    )
  bboxes = []
  for mask in masks:
    where = np.argwhere(mask)
    (y1, x1), (y2, x2) = where.min(0), where.max(0) + 1
    bboxes.append((y1, x1, y2, x2))
  bboxes = np.asarray(bboxes, dtype=np.float32)
  return bboxes


def annotation_to_dict(annotation):
  data = dict(
    label=annotation.label.encode("utf-8") if PY2 else annotation.label,
    shape_type=annotation.shape_type,
    points=[(p.x(), p.y()) for p in annotation.points],
    group_id=annotation.group_id,
    flags=annotation.flags,
    other_data=annotation.other_data,
  )
  return data

def dict_to_annotation(annotation, default_flags=None):
  label = annotation["label"]
  shape_type = annotation["shape_type"]
  points = annotation["points"]
  flags = annotation["flags"]
  group_id = annotation["group_id"]
  other_data = annotation["other_data"]
  annotation = Annotation(label=label, shape_type=shape_type, group_id=group_id)
  for x, y in points:
    annotation.addPoint(QtCore.QPointF(x, y))
  annotation.close()

  default_matched_flags = {}
  if default_flags:
    for pattern, keys in default_flags.items():
      if re.match(pattern, label):
        for key in keys:
          default_matched_flags[key] = False
  annotation.flags = default_matched_flags
  annotation.flags.update(flags)
  annotation.other_data = other_data

  return annotation


def to_categorical(y, num_classes=None):
  y = np.array(y, dtype='uint8').ravel()
  if not num_classes:
    #num_classes = np.max(y) + 1
    num_classes = 256
  n = y.shape[0]
  categorical = np.zeros((n, num_classes), dtype='uint8')
  categorical[np.arange(n), y] = 1
  return categorical

def pixelmap_to_annotation(pixmap, labels, epsilon=0.1):
  if pixmap.shape[-1] == 3:
    pixmap = cv2.cvtColor(pixmap, cv2.COLOR_BGR2GRAY)

  shape = (pixmap.shape[0],pixmap.shape[1],1)
  pixmap = pixmap.reshape(shape)
  images = to_categorical(pixmap).reshape((pixmap.shape[0],pixmap.shape[1],-1))

  annotations = []

  for label in labels: 
    gray = labels[label]['gray']
    labeled = images[:,:,gray]
    labeled[labeled>0] = 255
    contours, hierarchy = cv2.findContours(labeled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for i,c in enumerate(contours) :
      contours[i] = cv2.approxPolyDP(c,epsilon,True)
      if contours[i].shape[0] < 3:
        continue
    
      annot = Annotation(label=label, shape_type="polygon")
      for x, y in contours[i].reshape(contours[i].shape[0],contours[i].shape[2]).tolist():
        annot.addPoint(QtCore.QPointF(x, y))
      
      annotations.append(annot)

  return annotations