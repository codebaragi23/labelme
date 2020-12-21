import os

from mindAT.deepLab.create_satellite_tf_record import create_tf_record
from mindAT.deepLab import train
from mindAT.deepLab import evaluate


class MAP_TASK():

	def __init__(self):
		self.TASKTYPE = 0


	# // 동작 : 데이터의 image 파일과 label 파일이 들어있는 경로를 각각 입력하면 tfrecord_path에 tfrecord 생성
	# // image_path = image 파일이 저장된 경로
	# // label_path = label 파일이 저장된 경로
	# // tfrecord_path = 생성되는 tfrecord 파일을 저장할 경로
	# // isTrain : 학습셋이면 True, 테스트셋이면 False
	# // 한 쌍의 image파일과 label 파일은 서로 다른 경로에 같은 이름을 가지고 있어야 함.
	# // 예를 들어 image 파일이 c:\dataset\image\0000.tif 이면, label 파일은 c:\dataset\label\0000.tif 이런 식이어야 함.
	def create_tfrecord(self, image_path, label_path, tfrecord_path, isTrain):
		print("create_tfrecord, image_path = {}, label_path = {}, tfrecord_path = {}".format(image_path, label_path, tfrecord_path))
		if not os.path.isdir(image_path):
			raise ValueError("image_path folder {} does not exist".format(image_path))
		if not os.path.isdir(label_path):
			raise ValueError("label_path folder {} does not exist".format(label_path))

		#check label file existence
		image_files = os.listdir(image_path)
		image_list = []
		for image_file in image_files:
			filename, ext = os.path.splitext(image_file)
			if ext != ".tif":
				continue
			image_list.append(image_file)

		os.makedirs(tfrecord_path, exist_ok=True)

		if isTrain:
			tfrecord_filename = os.path.join(tfrecord_path, 'train.record')
		else:
			tfrecord_filename = os.path.join(tfrecord_path, 'val.record')

		if os.path.exists(tfrecord_filename):
			print("TFrecord {} already exist.".format(tfrecord_filename))
			return
		create_tf_record(tfrecord_filename, image_path, label_path, image_list, isTrain=True)


	# // 동작 : 위에서 생성한 tfrecord를 이용하여 학습 (마지막으로 저장한 weight 파일 경로 return)
	# // tfrecord_path = tfrecord 저장된 경로
	# // preweight_file = restore할 초기 weight 파일 (저장 경로 전체 포함)
	# // weight_path = 학습한 결과 weight 파일을 저장할 경로
	# // iter_num = 학습 iteration 횟수 (최소값 제한 10000)
	def train(self, tfrecord_path, preweight_path, weight_save_path , iter_num, gpu_id=None):
		train.run(tfrecord_path, preweight_path, weight_save_path , iter_num, gpu_id)


	# // 동작 : 학습한 weight를 이용하여 테스트 셋에 실험함 (pixel accuracy값 return)
	# // weight_path = test할 ckpt weight 파일이 있는 path
	# // test_image_path = test할 image 파일이 저장된 경로
	# // test_label_path = test할 image의 label 파일이 저장된 경로
	# // result_path = 실험 결과 수치를 excel 파일로 저장하고, test할 image 파일 각각의 테스트 결과를 image로 저장할 경로
	def evaluate(self, weight_path, test_image_path, test_label_path, result_path, gpu_id=None):
		accuracy = evaluate.run(weight_path, test_image_path, test_label_path, result_path, gpu_id)

		return accuracy


	# // 동작 : 학습한 weight 여러개를 이용하여 테스트 셋에 실험함 (pixel accuracy값 return)
	# // weight_path_list = test할 ckpt weight 파일이 있는 path들의 list
	# // test_image_path = test할 image 파일이 저장된 경로
	# // test_label_path = test할 image의 label 파일이 저장된 경로
	# // result_path = 실험 결과 수치를 excel 파일로 저장하고, test할 image 파일 각각의 테스트 결과를 image로 저장할 경로
	def evaluate_ensemble(self, weight_path_list, test_image_path, test_label_path, result_path):
		accuracy = evaluate.ensemble(weight_path_list, test_image_path, test_label_path, result_path)

		return accuracy


	# // 동작 : 학습한 weight를 이용하여 image inference 수행
	# // weight_path = test할 ckpt weight 파일이 있는 path
	# // test_image_path = inference할 image 파일이 저장된 경로
	# // result_path = inference한 image 결과를 저장할 경로
	def inference(self, weight_path, test_image_path, result_path, gpu_id=None):
		evaluate.inference(weight_path, test_image_path, result_path, gpu_id)

	# // 동작 : 학습한 weight를 이용하여 image inference 수행
	# // weight_path = test할 ckpt weight 파일이 있는 path
	# // test_image = inference할 image numpy array
	def inference_mindAT(self, sess, placeholder, image_ori, file_name, gpu_id=None):
		return evaluate.inference_mindAT(sess, placeholder, image_ori, file_name, gpu_id)
