# -*- mode: python ; coding: utf-8 -*-
import sys
sys.setrecursionlimit(5000)
block_cipher = None


a = Analysis(['mindAT/__main__.py'],
             pathex=['mindAT'],
             binaries=[],
              datas=[
  ('mindAT/config/default_config.yaml', 'mindAT/config'),
  ('mindAT/icons/*', 'mindAT/icons'),
  ('mindAT/spatialindex_c-64.dll', './'),
  ('mindAT/spatialindex-64.dll', './'),
  ('mindAT/translate/*','translate')],
             hiddenimports=[],
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
          name='MindAT',
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
               upx_exclude=[],
               name='__MindAT__')
