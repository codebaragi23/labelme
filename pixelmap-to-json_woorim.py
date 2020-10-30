import cv2
import numpy as np
import json
import os
import os.path as osp
import argparse

from PIL import Image 
from qtpy import QtGui

parser = argparse.ArgumentParser()
parser.add_argument('--epsilon', type=float, default=2.5, help='epsilon pixel to approximate the polygons')

# parser.add_argument('--input', type=str, default="examples/hyper/Air_20200331/GT", help='image mask input to compute all polygons')
# parser.add_argument('--output', type=str, default="road.json", help='json output file')
# parser.add_argument('--config', type=str, default="examples/hyper/Air_20200331/GT/config.json", help='config file content labels informations')

parser.add_argument('--input', type=str, default="test/산림_항공_37802098_033_FGT.tif", help='image mask input to compute all polygons')
parser.add_argument('--output', type=str, default="test/산림_항공_37802098_033_FGT.json", help='json output file')
parser.add_argument('--config', type=str, default="test/config.json", help='config file content labels informations')
opt = parser.parse_args()

def to_categorical(y, num_classes=None):
  y = np.array(y, dtype='uint8').ravel()
  if not num_classes:
    num_classes = 256
  n = y.shape[0]
  categorical = np.zeros((n, num_classes), dtype='uint8')
  categorical[np.arange(n), y] = 1
  return categorical

def pixelmap_to_json(ifilename, ofilename, epsilon, config):
  gray = Image.open(ifilename)
  gray = np.array(gray)

  images = to_categorical(gray).reshape((gray.shape[0],gray.shape[1],-1))

  filename = os.path.basename(ifilename)
  data = {}
  data["version"] = "1.0.0"
  data["Image"] = {
    "image_id": osp.splitext(filename)[0],
    "image_path": ".",
    "image_width": gray.shape[1],
    "image_height": gray.shape[0]
  }
  data["annotations"] = []
    
  for label in config['labels'] : 
    id = config['labels'][label]['id']
    code = config['labels'][label]["code"]
    if type(id) == list:
      id = cv2.cvtColor(np.array(id).astype(np.uint8).reshape(1,1,3), cv2.COLOR_RGB2GRAY)[0, 0]
    
    labeled = images[:,:,id]
    labeled[labeled>0] = 255
    contour, hierarchy = cv2.findContours(labeled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for i,c in enumerate(contour) :
      contour[i] = cv2.approxPolyDP(c,epsilon,True)
      if contour[i].shape[0] < 3: continue
      d = {}
      d["annotation_id"] = None
      d["annotation_type"] = "polygon"
      d["annotation_class_code"] = code
      d["annotation_class_name"] = label
      d["coordinates"] = contour[i].reshape(contour[i].shape[0],contour[i].shape[2]).tolist()
      data["annotations"].append(d)

  with open(ofilename,'w', encoding='utf-8') as out:
    json.dump(data,out,indent=2,ensure_ascii=False)

def scan_all_images(folderPath):
  extensions = [
    ".%s" % fmt.data().decode().lower()
    for fmt in QtGui.QImageReader.supportedImageFormats()
  ]

  files = os.listdir(folderPath)
  images = [osp.join(folderPath, file) for file in files if file.lower().endswith(tuple(extensions))]
  images.sort(key=lambda x: x.lower())
  return images

if __name__ == "__main__":
  config = json.load(open(opt.config, encoding='utf-8'))
  if osp.isdir(opt.input):
    images = scan_all_images(opt.input)
    for input in images:
      output = osp.splitext(input)[0] + ".json"
      pixelmap_to_json(input, output, opt.epsilon, config)
  else:
    pixelmap_to_json(opt.input, opt.output, opt.epsilon, config)
  print("Done")
    