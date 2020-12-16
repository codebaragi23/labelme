# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files
import sys

sys.setrecursionlimit(5000)
block_cipher = None

a = Analysis(['mindAT/__main__.py'],
             pathex=['mindAT'],
             binaries=collect_dynamic_libs("rtree"),
             datas=collect_data_files('geopandas', subdir='datasets') + [
               ('mindAT/config/default_config.yaml', 'mindAT/config'),
               ('mindAT/icons/*', 'mindAT/icons'),
               ('mindAT/translate/*.qm','mindAT/translate')],
             hiddenimports=['affine', 'pyproj._compat', 'fiona._shim', 'fiona.schema'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='mindAT',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False )

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='bin')

#app = BUNDLE(
#  exe,
#  name='mindAT.app',
#  icon='mindAT/icons/icon.icns',
#  bundle_identifier=None,
#  info_plist={'NSHighResolutionCapable': 'True'},
#)