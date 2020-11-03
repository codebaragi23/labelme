import os, sys, argparse
import os.path as osp
import gdal, json

parser = argparse.ArgumentParser()
#parser.add_argument('--input', type=str, default="test/FR_AP_36705045_001_FGT.tif", help='input<geofile(geotiff and geojson) or directory> to convert all coordinates')
parser.add_argument('--input', type=str, default="sample", help='input<geofile(geotiff and geojson) or directory> to convert all coordinates')
opt = parser.parse_args()

def global_to_pixel_coordi(geoimg_fn, geojson_fn, output_fn):
  try:
    geo_transfrom = None
    g = gdal.Open(geoimg_fn)
    geo_transfrom = g.GetGeoTransform()
    if geo_transfrom is not None:
      geo = json.load(open(geojson_fn, encoding='utf-8'))
      for feature in geo["features"]:
        for ring in feature["geometry"]["rings"]:
          for polygon in ring:
            polygon[0] = (polygon[0]-geo_transfrom[0])/geo_transfrom[1]
            polygon[1] = (polygon[1]-geo_transfrom[3])/geo_transfrom[5]
  
    with open(output_fn,'w', encoding='utf-8') as out:
      json.dump(geo,out,indent=2,ensure_ascii=False)

  except Exception as e:
    print(e)

def scan_all_images(folderPath):
  extensions = ["tif"]

  files = os.listdir(folderPath)
  images = [osp.join(folderPath, file) for file in files if file.lower().endswith(tuple(extensions))]
  images.sort(key=lambda x: x.lower())
  return images

if __name__ == '__main__':
  if osp.isdir(opt.input):
    images = scan_all_images(opt.input)
    for input in images:
      geoimg_fn = input
      geojson_fn = osp.splitext(input)[0] + "_FGT.json"
      output_fn = osp.splitext(input)[0] + "_LC.json"
      global_to_pixel_coordi(geoimg_fn, geojson_fn, output_fn)

  else:
    input = opt.input
    if osp.splitext(input)[1] == ".tif":
      geoimg_fn = input
      geojson_fn = osp.splitext(input)[0] + "_FGT.json"
      output_fn = osp.splitext(input)[0] + "_LC.json"
    elif osp.splitext(input)[1] == ".geojson":
      geojson_fn = input
      geoimg_fn = osp.splitext(input)[0] + ".tif"
      output_fn = osp.splitext(input)[0] + "_LC.json"

    if not (osp.exists(geoimg_fn) and osp.exists(geojson_fn)):
      print(f"No such file or directory: {geoimg_fn}, {geojson_fn}")
      sys.exit(1)

    global_to_pixel_coordi(geoimg_fn, geojson_fn, output_fn)

  print("Done")

  