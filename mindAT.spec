# -*- mode: python -*-
# vim: ft=python
from PyInstaller.utils.hooks import collect_data_files
import sys


sys.setrecursionlimit(5000)  # required on Windows


a = Analysis(
  ['mindAT/__main__.py'],
  pathex=['mindAT', '/usr/lib/python3.6/dist-packages/cv2/python-3.6', '/usr/share/gdal/2.2/'],
  binaries=[],
  datas=collect_data_files('geopandas', subdir='datasets') + [
    ('mindAT/config/default_config.yaml', 'mindAT/config'),
    ('mindAT/icons/*', 'mindAT/icons'),
    ('mindAT/translate/*.qm','mindAT/translate')],
  hiddenimports=['affine', 'pyproj._compat', 'fiona._shim', 'fiona.schema'],
  hookspath=[],
  runtime_hooks=[],
  excludes=[],
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
  pyz,
  a.scripts,
  a.binaries,
  a.zipfiles,
  a.datas,
  name='mindAT',
  debug=False,
  strip=False,
  upx=True,
  runtime_tmpdir=None,
  console=False,
  icon='mindAT/icons/icon.ico',
)
app = BUNDLE(
  exe,
  name='mindAT.app',
  icon='mindAT/icons/icon.icns',
  bundle_identifier=None,
  info_plist={'NSHighResolutionCapable': 'True'},
)