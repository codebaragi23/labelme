import numpy as np
import cv2
import random
import glob
import shutil
import os
import config
from utils import dataset_util

main_path = config.DATA_PATH

img_path = os.path.join(main_path, "image")
label_path = os.path.join(main_path, "label")
num_classes = 14

os.makedirs(os.path.join(main_path, "train/image"), exist_ok=True)
os.makedirs(os.path.join(main_path, "train/label"), exist_ok=True)
os.makedirs(os.path.join(main_path, "test/image"), exist_ok=True)
os.makedirs(os.path.join(main_path, "test/label"), exist_ok=True)

old_img_files = os.listdir(os.path.join(main_path, "test/image")) + os.listdir(os.path.join(main_path, "train/image"))
old_label_files = os.listdir(os.path.join(main_path, "test/label")) + os.listdir(os.path.join(main_path, "train/label"))
# old_img_files = []
# old_label_files = []

for img_file in old_img_files:
	del_file = os.path.join(img_path, img_file)
	if os.path.exists(del_file):
		os.remove(del_file)

for label_file in old_label_files:
	del_file = os.path.join(label_path, label_file)
	if os.path.exists(del_file):
		os.remove(del_file)

bin_count_list = []

files = glob.glob(label_path + "/*.tif")
for file in files:
	# bincount = [0] * 15
	#img = cv2.imread(file)
	#img = img[:,:,0]
	img = dataset_util.load_label(file)
	bincount = np.bincount(img.flatten())
	# print(len(bincount), bincount)
	bincount = np.pad(bincount, (0, num_classes-len(bincount)), 'constant', constant_values=(0))
	bin_count_list.append(bincount)

bin_sum = np.sum(bin_count_list, axis=0)
print(bin_sum)
bin_ratio = bin_sum / sum(bin_sum)
print(bin_ratio)

EXIST_TEST_FILES = 0
num_test_samples = 20 #86 #int(round((len(files)+EXIST_TEST_FILES)/5, 0))-EXIST_TEST_FILES
best_samples = []
best_score = 0

for iter_num in range(100):
	temp_index = random.sample(range(len(files)), k=num_test_samples)
	temp_select = []
	for index in temp_index:
		temp_select.append(bin_count_list[index])
	bin_test_sum = np.sum(temp_select, axis=0)
	bin_test_ratio = bin_test_sum / sum(bin_test_sum)

	score = 0
	for all_ratio, test_ratio in zip(bin_ratio, bin_test_ratio):
		if test_ratio == 0 and all_ratio ==0:
			continue
		score += all_ratio/test_ratio if test_ratio>all_ratio else test_ratio/all_ratio
	if score > best_score:
		best_score = score
		best_samples = temp_index
		print(iter_num, " best", best_score, best_samples)

filenames = []
for file in files:
	filenames.append(os.path.basename(file))
# print(filenames)

print("best set")
best_samples = sorted(best_samples)
test_files = [filenames[i] for i in best_samples]
train_files = []
for file in filenames:
	if file not in test_files:
		train_files.append(file)
# train_files = [file not in test_files for file in files]

print(len(test_files))
print(len(train_files))

for file in test_files:
	image_filename = file[:-8] + ".tif"
	print(file, image_filename)
	label_file = os.path.join(label_path, file)
	visible_file = os.path.join(label_path, file.replace(".tif", "_visible.png"))
	img_file = os.path.join(img_path, image_filename)

	target_label = os.path.join(os.path.join(main_path, "test/label"), file)
	target_visible = os.path.join(os.path.join(main_path, "test/label"), file.replace(".tif", "_visible.png"))
	target_img = os.path.join(os.path.join(main_path, "test/image"), image_filename)

	if os.path.exists(label_file):
		shutil.move(label_file, target_label)
	else:	
		print(label_file)
	if os.path.exists(visible_file):
		shutil.move(visible_file, target_visible)
	else:
		print(visible_file)
	if os.path.exists(img_file):
		shutil.move(img_file, target_img)
	else:
		print(img_file)


for file in train_files:
	image_filename = file[:-8] + ".tif"
	print(file, image_filename)
	label_file = os.path.join(label_path, file)
	visible_file = os.path.join(label_path, file.replace(".tif", "_visible.png"))
	img_file = os.path.join(img_path, image_filename)

	target_label = os.path.join(os.path.join(main_path, "train/label"), file)
	target_visible = os.path.join(os.path.join(main_path, "train/label"), file.replace(".tif", "_visible.png"))
	target_img = os.path.join(os.path.join(main_path, "train/image"), image_filename)

	if os.path.exists(label_file):
		shutil.move(label_file, target_label)
	else:	
		print(label_file)
	if os.path.exists(visible_file):
		shutil.move(visible_file, target_visible)
	else:
		print(visible_file)
	if os.path.exists(img_file):
		shutil.move(img_file, target_img)
	else:
		print(img_file)

for folder in ['test', 'train']:
	folder_path = os.path.join(main_path, folder)
	list_file = os.path.join(folder_path, folder + ".txt")
	f = open(list_file, 'wt')
	files = os.listdir(os.path.join(folder_path, "image"))
	for file in files:
		f.write(file) #[:-4])
		f.write('\n')
	f.close()
