"""Utility functions for preprocessing data sets."""

import tensorflow as tf

_R_MEAN = 123.68
_G_MEAN = 116.78
_B_MEAN = 103.94


def mean_image_subtraction(image, means=(_R_MEAN, _G_MEAN, _B_MEAN)):
	"""Subtracts the given means from each image channel.

	For example:
	  means = [123.68, 116.779, 103.939]
	  image = _mean_image_subtraction(image, means)

	Note that the rank of `image` must be known.

	Args:
	  image: a tensor of size [height, width, C].
	  means: a C-vector of values to subtract from each channel.

	Returns:
	  the centered image.

	Raises:
	  ValueError: If the rank of `image` is unknown, if `image` has a rank other
		than three or if the number of channels in `image` doesn't match the
		number of values in `means`.
	"""
	if image.get_shape().ndims != 3:
		raise ValueError('Input must be of size [height, width, C>0]')
	num_channels = image.get_shape().as_list()[-1]
	if num_channels == 4:
		means = (_R_MEAN, _G_MEAN, _B_MEAN, 0.0)
	elif num_channels == 5:
		means = (_R_MEAN, _G_MEAN, _B_MEAN, 0.0, 0.0)
	if len(means) != num_channels:
		raise ValueError('len(means) must match the number of channels')

	channels = tf.split(axis=2, num_or_size_splits=num_channels, value=image)
	for i in range(num_channels):
		channels[i] -= means[i]
	return tf.concat(axis=2, values=channels)


def random_crop_image_and_label(image, label, DEPTH, patch_size=256):
	label = label
	label = tf.to_float(label)
	image_and_label = tf.concat([image, label], axis=2)
	crop_size = tf.random_uniform([], minval=int(patch_size*2/3), maxval=int(patch_size*3/2), dtype=tf.int32)
	image_and_label_crop = tf.random_crop(
		image_and_label, [crop_size, crop_size, DEPTH + 1])

	image_crop = image_and_label_crop[:, :, :DEPTH]
	label_crop = image_and_label_crop[:, :, -1]
	label_crop = tf.expand_dims(label_crop, 2)
	label_crop = tf.to_int32(label_crop)
	image = tf.image.resize_images(image_crop, [patch_size, patch_size], method=tf.image.ResizeMethod.BILINEAR)
	# Since label classes are integers, nearest neighbor need to be used.
	label = tf.image.resize_images(label_crop, [patch_size, patch_size], method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
	return image, label


def random_flip_rotate_image_and_label(image, label):
	"""Randomly flip an image and label horizontally (left to right).

	Args:
	  image: A 3-D tensor of shape `[height, width, channels].`
	  label: A 3-D tensor of shape `[height, width, 1].`

	Returns:
	  A 3-D tensor of the same type and shape as `image`.
	  A 3-D tensor of the same type and shape as `label`.
	"""

	uniform_random = tf.random_uniform([], 0, 1.0)
	mirror_cond = tf.less(uniform_random, .5)
	image = tf.cond(mirror_cond, lambda: tf.reverse(image, [1]), lambda: image)
	label = tf.cond(mirror_cond, lambda: tf.reverse(label, [1]), lambda: label)

	rot_random = tf.random_uniform(shape=[], minval=0, maxval=3, dtype=tf.int32)
	image = tf.image.rot90(image, rot_random)
	label = tf.image.rot90(label, rot_random)

	return image, label


def random_variate_image(image, random_range, DEPTH):
	image_rgb = image[:,:,:3]
	if DEPTH == 4:
		image_ir = image[:,:,3]
		image_ir = tf.expand_dims(image_ir, 2)
	elif DEPTH > 4:
		image_ir = image[:,:,3:]
	# image_rgb = tf.image.random_brightness(image_rgb, random_range)
	# image_rgb = tf.image.random_contrast(image_rgb, lower = 1.0 - random_range, upper = 1.0 + random_range)
	# image_rgb = tf.image.random_hue(image_rgb, max_delta=random_range/2.0)
	image_rgb = tf.image.random_saturation(image_rgb, lower = 1.0 - random_range, upper = 1.0 + random_range)

	# random_gamma = tf.random_uniform([], minval=1.0 - random_range, maxval=1.0 + random_range, dtype=tf.float32)
	# random_gain = tf.random_uniform([], minval=1.0 - random_range, maxval=1.0 + random_range, dtype=tf.float32)
	# image_rgb = tf.image.adjust_gamma(image_rgb, random_gamma, gain=1)
	# image_rgb = tf.image.adjust_gamma(image_rgb, random_gamma, random_gain)

	if DEPTH > 3:
		image = tf.concat([image_rgb, image_ir], axis=2)
	else:
		image = image_rgb

	return image
