import cv2
import os
import numpy as np
import tifffile
from dataset_util import save_visible, load_label


def convert_label_order():
	old_label_path = "D:/hoseok/dataset/segmentation/200610_8bit/train/label/"
	new_label_path = "D:/hoseok/dataset/segmentation/200610_8bit/train/label_new/"
	os.makedirs(new_label_path, exist_ok=True)

	files = os.listdir(old_label_path)

	for file in files:
		if file[-3:] != "tif":
			continue
		file_path = os.path.join(old_label_path, file)
		old_label = cv2.imread(file_path)[:,:,0]

		new_label = np.zeros(old_label.shape)

		new_label[old_label == 1] = 1
		new_label[old_label == 2] = 2
		new_label[old_label == 8] = 3
		new_label[old_label == 9] = 3
		new_label[old_label == 7] = 4
		new_label[old_label == 14] = 5
		new_label[old_label == 10] = 6
		new_label[old_label == 11] = 7
		new_label[old_label == 3] = 8
		new_label[old_label == 4] = 9
		new_label[old_label == 5] = 10
		new_label[old_label == 13] = 11
		new_label[old_label == 6] = 12
		new_label[old_label == 12] = 13
		new_label[old_label == 0] = 0

		label = np.stack([new_label, new_label, new_label], axis=2)
		label = np.uint8(label)
		# print(label)
		cv2.imwrite(os.path.join(new_label_path, file), label)
		# cv2.imshow("", label)
		# cv2.waitKey()
		print(file, label.shape)


def conv_to_5ch(src_path, dst_path):
	os.makedirs(dst_path, exist_ok=True)
	files = os.listdir(src_path)
	for file in files:
		image_3ch = tifffile.imread(os.path.join(src_path, file))
		ch_num = image_3ch.shape[-1]
		if ch_num < 3:
			raise ValueError("Channel Number Error", file)
		zero_ch = np.zeros((image_3ch.shape[0], image_3ch.shape[1], 5-ch_num))
		image = np.dstack((image_3ch, zero_ch))
		# image = resize(image, (image_3ch.shape[1], image_3ch.shape[0], 5))
		image = np.uint8(image)
		print(file, image.shape)
		dst_file = os.path.join(dst_path, file)
		tifffile.imwrite(dst_file, image, planarconfig='CONTIG')


def conv_5ch_to_3ch(src_path, dst_path):
	os.makedirs(dst_path, exist_ok=True)
	files = os.listdir(src_path)
	for file in files:
		image_5ch = tifffile.imread(os.path.join(src_path, file))
		image = image_5ch[:,:,:3]
		image = np.uint8(image)
		image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
		dst_file = os.path.join(dst_path, file)
		cv2.imwrite(dst_file, image)


def conv_gt_to_label(GT_path, label_path):
	os.makedirs(label_path, exist_ok=True)
	files = os.listdir(GT_path)

	for file in files:
		gt_file = os.path.join(GT_path, file)
		label_file = os.path.join(label_path, file)

		label = cv2.imread(gt_file)
		label = label[:,:,0]
		label = np.uint8(label)

		row = label.shape[0]
		col = label.shape[1]
		print(gt_file, row, col)
		image = np.zeros((row, col, 3))
		image[label==180] = [13, 13, 13]
		image[label==170] = [12, 12, 12]
		image[label==160] = [11, 11, 11]
		image[label==150] = [10, 10, 10]
		image[label==140] = [9, 9, 9]
		image[label==130] = [8, 8, 8]
		image[label==120] = [7, 7, 7]
		image[label==110] = [6, 6, 6]
		image[label==50] = [5, 5, 5]
		image[label==40] = [4, 4, 4]
		image[label==30] = [3, 3, 3]
		image[label==20] = [2, 2, 2]
		image[label==10] = [1, 1, 1]
		image = np.uint8(image)

		cv2.imwrite(label_file, image)


def conv_label_to_gt(GT_path, label_path):
	os.makedirs(GT_path, exist_ok=True)
	files = os.listdir(label_path)

	for file in files:
		label_file = os.path.join(label_path, file)
		gt_file = os.path.join(GT_path, file)

		label = cv2.imread(label_file)
		label = label[:,:,0]
		label = np.uint8(label)

		row = label.shape[0]
		col = label.shape[1]
		print(gt_file, row, col)
		image = np.zeros((row, col, 3))
		image[label==13] = [180, 180, 180]
		image[label==12] = [170, 170, 170]
		image[label==11] = [160, 160, 160]
		image[label==10] = [150, 150, 150]
		image[label==9] = [140, 140, 140]
		image[label==8] = [130, 130, 130]
		image[label==7] = [120, 120, 120]
		image[label==6] = [110, 110, 110]
		image[label==5] = [50, 50, 50]
		image[label==4] = [40, 40, 40]
		image[label==3] = [30, 30, 30]
		image[label==2] = [20, 20, 20]
		image[label==1] = [10, 10, 10]
		image[label==0] = [190, 190, 190]
		image = np.uint8(image)

		cv2.imwrite(gt_file, image)


def make_visible_file(path):
	files = os.listdir(path)
	for file in files:
		if file[-3:] != "tif":
			continue
		label = load_label(os.path.join(path, file))
		visible_file = file.replace(".tif", "_visible.png")
		save_visible(os.path.join(path, visible_file), label)


def make_cropped_images(src_file, dst_path):
	image = cv2.imread(src_file)
	h, w = image.shape[:2]
	print(w, h)
	os.makedirs(dst_path, exist_ok=True)
	h_list = list(range(0, h-512, 512))
	h_list.append(h-512)
	w_list = list(range(0, w-512, 512))
	w_list.append(w - 512)
	for h in h_list:
		for w in w_list:
			crop_image = image[h:h+512, w:w+512, :]
			cv2.imwrite(os.path.join(dst_path, f'{w}_{h}.png'), crop_image)


if __name__ =="__main__":
	# conv_to_5ch("D:/hoseok/dataset/segmentation/200610_8bit/image_4ch", "D:/hoseok/dataset/segmentation/200610_8bit/")
	#conv_5ch_to_3ch("D:/hoseok/dataset/segmentation/201007_8bit/test/image", "D:/hoseok/dataset/segmentation/201007_8bit/test/image_3ch")
	# conv_label_to_index("D:/hoseok/dataset/original\OneDrive_2020-09-09/GT", "D:/hoseok/dataset/original\OneDrive_2020-09-09/label")
	make_visible_file("/home/mind3/project/dataset/AI_dataset/201201/test/label")
	# conv_3ch_to_5ch("D:/hoseok/dataset/segmentation/200610_8bit/image_3ch", "D:/hoseok/dataset/segmentation/200610_8bit/image")
	# make_cropped_images("D:/hoseok/dataset/segmentation/200723_8bit_2/image_3ch/AP34603001.tif", "D:/hoseok/dataset/200820_temp/")
