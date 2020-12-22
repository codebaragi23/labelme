"""Train a DeepLab v3 plus model using tf.estimator API."""
import os
import tensorflow as tf

from mindAT.deepLab import deeplab_model
from mindAT.deepLab.utils import preprocessing
from mindAT.deepLab.config import *

_POWER = 0.9
_MOMENTUM = 0.9
_BATCH_NORM_DECAY = 0.9997


def get_filenames(is_training, data_dir):
	"""Return a list of filenames.

	Args:
	  is_training: A boolean denoting whether the input is for training.
	  data_dir: path to the the directory containing the input data.

	Returns:
	  A list of file names.
	"""
	if is_training:
		return [os.path.join(data_dir, 'train.record')]
	else:
		return [os.path.join(data_dir, 'val.record')]


def parse_record(raw_record):
	"""Parse PASCAL image and label from a tf record."""
	keys_to_features = {
		'row':
			tf.FixedLenFeature((), tf.int64),
		'col':
			tf.FixedLenFeature((), tf.int64),
		'image_raw':
			tf.FixedLenFeature((), tf.string, default_value=''),
		'label_raw':
			tf.FixedLenFeature((), tf.string, default_value=''),
	}

	parsed = tf.parse_single_example(raw_record, keys_to_features)

	image = tf.decode_raw(parsed['image_raw'], tf.uint8)
	image = tf.reshape(image, [SAMPLE_SIZE, SAMPLE_SIZE, DATA_DEPTH])
	image = image[...,:DEPTH]
	image = tf.to_float(tf.image.convert_image_dtype(image, dtype=tf.uint8))

	label = tf.decode_raw(parsed['label_raw'], tf.uint8)
	label = tf.reshape(label, [SAMPLE_SIZE, SAMPLE_SIZE, 1])
	label = tf.to_int32(tf.image.convert_image_dtype(label, dtype=tf.uint8))

	return image, label


def preprocess_image(image, label):
	"""Preprocess a single image of layout [height, width, depth]."""

	image, label = preprocessing.random_crop_image_and_label(image, label, DEPTH, PATCH_SIZE)
	image, label = preprocessing.random_flip_rotate_image_and_label(image, label)

	image = preprocessing.random_variate_image(image, 0.2, DEPTH)
	image = preprocessing.mean_image_subtraction(image)

	return image, label


def input_fn(is_training, data_dir, batch_size, num_epochs=1):
	"""Input_fn using the tf.data input pipeline for CIFAR-10 dataset.

	Args:
	  is_training: A boolean denoting whether the input is for training.
	  data_dir: The directory containing the input data.
	  batch_size: The number of samples per batch.
	  num_epochs: The number of epochs to repeat the dataset.

	Returns:
	  A tuple of images and labels.
	"""
	dataset = tf.data.Dataset.from_tensor_slices(get_filenames(is_training, data_dir))
	dataset = dataset.flat_map(tf.data.TFRecordDataset)

	if is_training:
		# When choosing shuffle buffer sizes, larger sizes result in better
		# randomness, while smaller sizes have better performance.
		# is a relatively small dataset, we choose to shuffle the full epoch.
		dataset = dataset.shuffle(buffer_size=3000)

	dataset = dataset.map(parse_record)
	dataset = dataset.map(
		lambda image, label: preprocess_image(image, label))
	dataset = dataset.prefetch(batch_size)

	# We call repeat after shuffling, rather than before, to prevent separate
	# epochs from blending together.
	dataset = dataset.repeat(num_epochs)
	dataset = dataset.batch(batch_size)

	iterator = dataset.make_one_shot_iterator()
	images, labels = iterator.get_next()

	return images, labels


def run(tfrecord_path, preweight_path, weight_save_path, iter_num, gpu_id, lr=1e-6):
	print("train, tfrecord_path = {}, preweight_path = {}, weight_save_path = {} , iter_num = {}".format(tfrecord_path,
	                                                                                                     preweight_path,
	                                                                                                     weight_save_path,
	                                                                                                     iter_num))

	if gpu_id != None:
		os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
	os.environ['TF_ENABLE_WINOGRAD_NONFUSED'] = '1'
	tf.logging.set_verbosity(tf.logging.INFO)

	epochs_per_eval = 10
	tensorboard_images_max_outputs = 6
	batch_size = 32
	learning_rate_policy = 'poly'
	max_iter = 30000

	freeze_batch_norm = 'store_true'
	initial_learning_rate = 7e-3
	end_learning_rate = lr
	initial_global_step = 0
	weight_decay = 2e-4
	num_train = 10000
	train_epochs = batch_size * iter_num // 10000
	if train_epochs <= 0:
		train_epochs = 1

	print("train epoch = ", train_epochs)
	run_config = tf.estimator.RunConfig()
	model = tf.estimator.Estimator(
		model_fn=deeplab_model.deeplabv3_plus_model_fn,
		model_dir=weight_save_path,
		config=run_config,
		params={
			'output_stride': output_stride,
			'batch_size': batch_size,
			'base_architecture': base_architecture,
			'pre_trained_model': preweight_path,
			'batch_norm_decay': _BATCH_NORM_DECAY,
			'num_classes': NUM_CLASSES,
			'tensorboard_images_max_outputs': tensorboard_images_max_outputs,
			'weight_decay': weight_decay,
			'learning_rate_policy': learning_rate_policy,
			'num_train': num_train,
			'initial_learning_rate': initial_learning_rate,
			'max_iter': max_iter,
			'end_learning_rate': end_learning_rate,
			'power': _POWER,
			'momentum': _MOMENTUM,
			'freeze_batch_norm': freeze_batch_norm,
			'initial_global_step': initial_global_step,
			'num_channels': DEPTH
		})

	for _ in range(train_epochs // epochs_per_eval):
		tensors_to_log = {
			'learning_rate': 'learning_rate',
			'cross_entropy': 'cross_entropy',
			'train_px_accuracy': 'train_px_accuracy',
			'train_mean_iou': 'train_mean_iou',
		}

		logging_hook = tf.train.LoggingTensorHook(
			tensors=tensors_to_log, every_n_iter=1000)
		train_hooks = [logging_hook]
		eval_hooks = None

		tf.logging.info("Start training.")
		model.train(
			input_fn=lambda: input_fn(True, tfrecord_path, batch_size, epochs_per_eval),
			hooks=train_hooks,
			# steps=1  # For debug
		)
		tf.logging.info("Start evaluation.")
		# Evaluate the model and print results
		eval_results = model.evaluate(
			input_fn=lambda: input_fn(False, tfrecord_path, batch_size),
			hooks=eval_hooks,
			# steps=1  # For debug
		)
		print(eval_results)
