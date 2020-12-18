"""Converts PASCAL dataset to TFRecords file format."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import os
import sys
import tensorflow as tf

from mindAT.deepLab.utils import dataset_util
from mindAT.deepLab.config import *

parser = argparse.ArgumentParser()

parser.add_argument('--data_dir', type=str, default=DATA_PATH,
                    help='Path to the directory containing the PASCAL VOC data.')

parser.add_argument('--output_path', type=str, default=os.path.join(DATA_PATH, 'tfrecord'),
                    help='Path to the directory to create TFRecords outputs.')

parser.add_argument('--train_data_list', type=str, default=os.path.join(DATA_PATH, 'train/train.txt'),
                    help='Path to the file listing the training data.')

parser.add_argument('--valid_data_list', type=str, default=os.path.join(DATA_PATH, 'test/test.txt'),
                    help='Path to the file listing the validation data.')

parser.add_argument('--image_data_dir', type=str, default='image',
                    help='The directory containing the image data.')

parser.add_argument('--label_data_dir', type=str, default='label',
                    help='The directory containing the augmented label data.')


def image_patch(image, label, patch_size, r, c):
	sub_image = image[r:r + patch_size, c:c + patch_size]
	sub_label = label[r:r + patch_size, c:c + patch_size]

	if sub_image.shape[:2] != sub_label.shape[:2]:
		print(
			"Size is Different sub_image = {}, sub_label = {}, image = {}, label={}, r={}, c={}, patch_size={}".format(
				sub_image.shape, sub_label.shape, image.shape, label.shape, r, c, patch_size))

	return sub_image, sub_label


def save_image(sub_image, sub_label, writer, filename=None, r=0, c=0, row=0, col=0, train=False):
	if train:
		image_raw = sub_image.tostring()
		label_raw = sub_label.tostring()

		row = sub_image.shape[0]
		col = sub_image.shape[1]

		example = tf.train.Example(features=tf.train.Features(feature={
			'row': dataset_util.int64_feature(row),
			'col': dataset_util.int64_feature(col),
			'image_raw': dataset_util.bytes_feature(image_raw),
			'label_raw': dataset_util.bytes_feature(label_raw),
		}))
		writer.write(example.SerializeToString())
	else:
		image_raw = sub_image.tostring()
		label_raw = sub_label.tostring()
		example = tf.train.Example(features=tf.train.Features(feature={
			'row': dataset_util.int64_feature(row),
			'col': dataset_util.int64_feature(col),
			'image_raw': dataset_util.bytes_feature(image_raw),
			'label_raw': dataset_util.bytes_feature(label_raw),
			'row_off': dataset_util.int64_feature(r),
			'col_off': dataset_util.int64_feature(c),
			'filename': dataset_util.bytes_feature(tf.compat.as_bytes(filename))
		}))
		writer.write(example.SerializeToString())


def create_tf_record(output_filename, image_dir, label_dir, examples, isTrain):
	writer = tf.io.TFRecordWriter(output_filename)
	total_sample_num = 0

	for example in examples:
		img_path = os.path.join(image_dir, example)
		label_path = os.path.join(label_dir, example[:-4] + "_FGT.tif")
		image, label = dataset_util.load_image(img_path, label_path, bit16=False)
		image_row, image_col = image.shape[:2]
		label_row, label_col = label.shape[:2]
		row = min(image_row, label_row)
		col = min(image_col, label_col)
		image = image[:row, :col, :]
		label = label[:row, :col]
		print(img_path, label_path, row, col)

		if isTrain:
			row_list = list(range(0, row - SAMPLE_SIZE, int(SAMPLE_SIZE / 2)))
			row_list.append(row - SAMPLE_SIZE)
			col_list = list(range(0, col - SAMPLE_SIZE, int(SAMPLE_SIZE / 2)))
			col_list.append(col - SAMPLE_SIZE)
			for r in row_list:
				for c in col_list:
					sub_image, sub_label = image_patch(image, label, SAMPLE_SIZE, r, c)
					save_image(sub_image, sub_label, writer, train=True)
			total_sample_num += (len(row_list) * len(col_list))
			print("Total Train Sample Num = {}".format(total_sample_num))
		else:
			row_list = list(range(0, row - PATCH_SIZE, int(PATCH_SIZE / 2)))
			row_list.append(row - PATCH_SIZE)
			col_list = list(range(0, col - PATCH_SIZE, int(PATCH_SIZE / 2)))
			col_list.append(col - PATCH_SIZE)
			for r in row_list:
				for c in col_list:
					sub_image, sub_label = image_patch(image, label, PATCH_SIZE, r, c)
					save_image(sub_image, sub_label, writer, example, r, c, row, col)
			total_sample_num += (len(row_list) * len(col_list))
			print("Total Test Sample Num = {}".format(total_sample_num))


def main(unused_argv):
	if not os.path.exists(FLAGS.output_path):
		os.makedirs(FLAGS.output_path)

	# data_path = os.path.join(FLAGS.data_dir, "train")
	# image_dir = os.path.join(data_path, FLAGS.image_data_dir)
	# label_dir = os.path.join(data_path, FLAGS.label_data_dir)

	# if not os.path.isdir(label_dir):
	# 	raise ValueError("Missing Augmentation label directory. "
	# 	                 "You may download the augmented labels from the link (Thanks to DrSleep): "
	# 	                 "https://www.dropbox.com/s/oeu149j8qtbs1x0/SegmentationClassAug.zip")
	train_examples = dataset_util.read_examples_list(FLAGS.train_data_list)
	val_examples = dataset_util.read_examples_list(FLAGS.valid_data_list)
	# val_examples = os.listdir(image_dir)

	train_output_path = os.path.join(FLAGS.output_path, 'train.record')
	val_output_path = os.path.join(FLAGS.output_path, 'val.record')
	test_output_path = os.path.join(FLAGS.output_path, 'test.record')

	create_tf_record(train_output_path, os.path.join(FLAGS.data_dir, "train/image"),
	                 os.path.join(FLAGS.data_dir, "train/label"), train_examples, isTrain=True)
	create_tf_record(val_output_path, os.path.join(FLAGS.data_dir, "test/image"),
	                 os.path.join(FLAGS.data_dir, "test/label"), val_examples, isTrain=True)
	create_tf_record(test_output_path, os.path.join(FLAGS.data_dir, "test/image"),
	                 os.path.join(FLAGS.data_dir, "test/label"), val_examples, isTrain=False)


if __name__ == '__main__':
	tf.logging.set_verbosity(tf.logging.INFO)
	FLAGS, unparsed = parser.parse_known_args()
	tf.app.run(main=main, argv=[sys.argv[0]] + unparsed)
