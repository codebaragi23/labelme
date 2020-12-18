import os.path as osp

here = osp.dirname(osp.abspath(__file__))
support_languages = {'en_US':'English', 'ko_KR':'Korean'}

def get_translator_path():
  return here;
