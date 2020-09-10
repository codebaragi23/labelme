import cv2 as cv
import numpy as np
import json
import os
import argparse

from PIL import Image 

parser = argparse.ArgumentParser()
parser.add_argument('--epsilon', type=float, default=2.5, help='epsilon pixel to approximate the polygons')
#parser.add_argument('--input', type=str, default="watershed_mask.png", help='image mask input to compute all polygons')
parser.add_argument('--input', type=str, default="examples/hyper/Air_20200331/GT/AP36914094.tif", help='image mask input to compute all polygons')
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

#img = Image.open(opt.input)
#img = np.array(img)
img = cv.imread(opt.input)
gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
config = json.load(open(opt.config))['labels']

shape = (gray.shape[0],gray.shape[1],1)
gray = gray.reshape(shape)
images = to_categorical(gray).reshape((gray.shape[0],gray.shape[1],-1))

out = open(opt.output,'w')
data = {}
data["version"] = "4.0.0"
data["flags"] = {}
data["annotations"] = []
data["imagePath"]= os.path.basename(opt.input)
data["imageData"]= None
data["imageHeight"] = img.shape[0]
data["imageWidth"] = img.shape[1]
  
for label in config : 
  person = images[:,:,config[label]['id']]
  person[person>0] = 255
  contour, hierarchy = cv.findContours(person, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)

  for i,c in enumerate(contour) :
    contour[i] = cv.approxPolyDP(c,opt.epsilon,True)
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
  # cv.drawContours(img, contour, -1, color, 1)
  
# cv.imshow("person",img)
# cv.waitKey(0)

json.dump(data,out,indent=2)