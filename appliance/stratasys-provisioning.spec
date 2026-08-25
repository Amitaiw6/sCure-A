# PyInstaller spec — Stratasys Factory Provisioning Tool (desktop)
#   pyinstaller stratasys-provisioning.spec   -> dist/StratasysProvisioning/StratasysProvisioning.exe
# Run on the station OS you target (Windows here); ship the trust/ dir with the
# Stratasys public keys next to the .exe, never a private key.
import os
block_cipher = None
a = Analysis(
    ['provisioning-tool/app.py'],
    pathex=['common', 'provisioning-tool'],
    binaries=[],
    datas=[('provisioning-tool/hardware-profiles.yaml', 'provisioning-tool')],
    hiddenimports=['tests_support', 'stratasys_appliance.crypto', 'stratasys_appliance.serials',
                   'stratasys_appliance.license', 'stratasys_appliance.manifests',
                   'stratasys_appliance.identity', 'stratasys_appliance.audit', 'yaml'],
    hookspath=[], runtime_hooks=[], excludes=['tkinter'], cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='StratasysProvisioning',
          console=False, icon=None)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='StratasysProvisioning')
