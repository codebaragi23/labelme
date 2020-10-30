import cv2
import numpy as np
import os
import os.path as osp
import argparse
import json

from geojson import Polygon, Feature, FeatureCollection, dump

parser = argparse.ArgumentParser()
parser.add_argument('--epsilon', type=float, default=2.5, help='epsilon pixel to approximate the polygons')
parser.add_argument('--input', type=str, default="GT/", help='image mask input or directory to compute all polygons')
parser.add_argument('--output', type=str, default="result.json", help='json output file(if input is a image file)')
parser.add_argument('--config', type=str, default="GT/config.json", help='config file content labels informations')
opt = parser.parse_args()

def pixelmap_to_json(ifilename, ofilename, epsilon, config):
  img = cv2.imread(ifilename)
  gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

  shape = (gray.shape[0],gray.shape[1],1)
  gray = gray.reshape(shape)

  def to_categorical(y, num_classes=None):
    y = np.array(y, dtype='uint8').ravel()
    if not num_classes: num_classes = 256
    n = y.shape[0]
    categorical = np.zeros((n, num_classes), dtype='uint8')
    categorical[np.arange(n), y] = 1
    return categorical

  images = to_categorical(gray).reshape((gray.shape[0],gray.shape[1],-1))

  filename = os.path.basename(ifilename)
  features = []

  property = {}
  property['img_width'] = img.shape[1]
  property['img_height'] = img.shape[0]
    
  for label in config['labels'] : 
    id = config['labels'][label]['id']
    property['ann_code'] = id
    property['ann_name'] = label
    if type(id) == list:
      id = cv2.cvtColor(np.array(id).astype(np.uint8).reshape(1,1,3), cv2.COLOR_RGB2GRAY)[0, 0]
    
    labeled = images[:,:,id]
    labeled[labeled>0] = 255
    contour, hierarchy = cv2.findContours(labeled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for i,c in enumerate(contour) :
      contour[i] = cv2.approxPolyDP(c,epsilon,True)
      if contour[i].shape[0] < 3: continue

      polygon = Polygon([contour[i].reshape(contour[i].shape[0],contour[i].shape[2]).tolist()])
      features.append(Feature(geometry=polygon, properties=property))
  
  feature_collection = FeatureCollection(features, name=filename)
  with open(ofilename, 'w', encoding='UTF-8') as f:
    dump(feature_collection,f,indent="\t",ensure_ascii=False)

def scan_all_images(folderPath):
  extensions = ['.bmp', '.cur', '.gif', '.icns', '.ico', '.jpeg', '.jpg', '.pbm', '.pgm', '.png', '.ppm', '.svg', '.svgz', '.tga', '.tif', '.tiff', '.wbmp', '.webp', '.xbm', '.xpm']

  files = os.listdir(folderPath)
  images = [osp.join(folderPath, file) for file in files if file.lower().endswith(tuple(extensions))]
  images.sort(key=lambda x: x.lower())
  return images

if __name__ == "__main__":
  config = json.load(open(opt.config))
  if osp.isdir(opt.input):
    images = scan_all_images(opt.input)
    for input in images:
      output = osp.splitext(input)[0] + ".geojson"
      pixelmap_to_json(input, output, opt.epsilon, config)
  else:
    pixelmap_to_json(opt.input, opt.output, opt.epsilon, config)
    