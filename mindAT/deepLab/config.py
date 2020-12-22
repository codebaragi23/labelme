import os.path as osp

DATA_PATH = ''

WEIGHT_PATH = osp.join(osp.dirname(osp.abspath(__file__)), 'weight/trained')

PATCH_SIZE = 256
SAMPLE_SIZE = PATCH_SIZE * 2
DEPTH = 3
DATA_DEPTH = 3

NUM_CLASSES = 9

base_architecture = 'resnet_v2_101'
output_stride = 16
