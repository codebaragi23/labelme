import cv2
import numpy as np
import json
import os
import os.path as osp
import argparse

from PIL import Image 

parser = argparse.ArgumentParser()
parser.add_argument('--epsilon', type=float, default=2.5, help='epsilon pixel to approximate the polygons')
#parser.add_argument('--input', type=str, default="watershed_mask.png", help='image mask input to compute all polygons')
parser.add_argument('--input', type=str, default="examples/hyper/Air_20200331/GT", help='image mask input to compute all polygons')
parser.add_argument('--output', type=str, default="road.json", help='json output file')
parser.add_argument('--config', type=str, default="config.json", help='config file content labels informations')
opt = parser.parse_args()

def to_categorical(y, num_classes=None):
  y = np.array(y, dtype='uint8').ravel()
  if not num_classes:
    num_classes = np.max(y) + 1
  n = y.shape[0]
  categorical = np.zeros((n, num_classes), dtype='uint8')
  categorical[np.arange(n), y] = 1
  return categorical

def pixelmap_to_json(ifname, ofname, epsilon, config):
  #img = Image.open(opt.input)
  #img = np.array(img)
  img = cv2.imread(ifname)
  gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

  shape = (gray.shape[0],gray.shape[1],1)
  gray = gray.reshape(shape)
  images = to_categorical(gray).reshape((gray.shape[0],gray.shape[1],-1))

  out = open(ofname,'w')
  data = {}
  data["version"] = "4.0.0"
  data["flags"] = {}
  data["annotations"] = []
  data["imagePath"]= os.path.basename(ifname)
  data["imageData"]= None
  data["imageHeight"] = img.shape[0]
  data["imageWidth"] = img.shape[1]
    
  for label in config : 
    labeled = images[:,:,config[label]['id']]
    labeled[labeled>0] = 255
    contour, hierarchy = cv2.findContours(labeled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for i,c in enumerate(contour) :
      contour[i] = cv2.approxPolyDP(c,epsilon,True)
      d = {}
      d['label'] = label
      if contour[i].shape[0] < 3:
        continue
      d["points"] = contour[i].reshape(contour[i].shape[0],contour[i].shape[2]).tolist()
      d["group_id"] = None
      d["shape_type"] = "polygon"
      d["flags"] = {}
      data["annotations"].append(d)
    # color = config[label]['color']
    # cv2.drawContours(img, contour, -1, color, 1)
  # cv2.imshow("labeled",img)
  # cv2.waitKey(0)
  json.dump(data,out,indent=2)

if __name__ == "__main__":
  config = json.load(open(opt.config))['labels']
  if osp.isdir(opt.input):
    list = sorted(os.listdir(opt.input))
    for fname in list:
      input = osp.join(opt.input, fname)
      output = osp.splitext(input)[0] + ".json"
      pixelmap_to_json(input, output, opt.epsilon, config)
  else:
    pixelmap_to_json(opt.input, opt.output, opt.epsilon, config)
    