# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Utility functions for creating TFRecord data sets.
source: https://github.com/tensorflow/models/blob/master/research/object_detection/utils/dataset_util.py
"""

import tensorflow as tf
import numpy as np
import imageio
import cv2

def int64_feature(value):
	return tf.train.Feature(int64_list=tf.train.Int64List(value=[value]))


def int64_list_feature(value):
	return tf.train.Feature(int64_list=tf.train.Int64List(value=value))


def bytes_feature(value):
	return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))


def bytes_list_feature(value):
	return tf.train.Feature(bytes_list=tf.train.BytesList(value=value))


def float_list_feature(value):
	return tf.train.Feature(float_list=tf.train.FloatList(value=value))


def read_examples_list(path):
	"""Read list of training or validation examples.

	The file is assumed to contain a single example per line where the first
	token in the line is an identifier that allows us to find the image and
	annotation xml for that example.

	For example, the line:
	xyz 3
	would allow us to find files xyz.jpg and xyz.xml (the 3 would be ignored).

	Args:
	  path: absolute path to examples list file.

	Returns:
	  list of example identifiers (strings).
	"""
	with tf.gfile.GFile(path) as fid:
		lines = fid.readlines()
	return [line.strip().split(' ')[0] for line in lines]


def load_label(label_path):
	label = cv2.imread(label_path)
	label = np.uint8(label[:,:,0]/10)
	label[label>8] = 0
	return label


def load_image(img_path,label_path=None,read_label=True, bit16=False):
	print(img_path)
	image = imageio.imread(img_path)
	# image = cv2.imread(img_path,flags=cv2.IMREAD_UNCHANGED)
	# image = image[:,:,0:3]
	if bit16:
		image = np.uint16(image)
	else:
		image = np.uint8(image)

	if read_label:
		label = load_label(label_path)
		#label = cv2.imread(label_path)
		#label = label[:,:,0]
		#label = np.uint8(label)
		return image, label
	return image


def save_visible(file_path, label):
	print(file_path)
	row = label.shape[0]
	col = label.shape[1]
	image = np.ones((row, col, 3)) * 100
	image = np.uint8(image)

	# BGR order
	image[label == 1] = [34, 47, 157]
	image[label == 2] = [175, 88, 144]
	image[label == 3] = [112, 53, 168]
	image[label == 4] = [122, 200, 177]
	image[label == 5] = [82, 126, 179]
	image[label == 6] = [52, 182, 199]
	image[label == 7] = [34, 99, 30]
	image[label == 8] = [140, 105, 42]
	# image = np.uint8(image)
	cv2.imwrite(file_path, image)
