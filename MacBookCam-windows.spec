# PyInstaller: сборка MacBookCam.exe (запускать на Windows: build_windows.bat)
import sys
sys.path.insert(0, SPECPATH)
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [("assets", "assets")] + collect_data_files("customtkinter")
vc_datas, vc_bins, vc_hidden = collect_all("pyvirtualcam")

a = Analysis(
    ["pc_app.py"],
    datas=datas + vc_datas,
    binaries=vc_bins,
    hiddenimports=vc_hidden,
    excludes=["rumps", "AppKit", "AVFoundation"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="MacBookCam", icon="assets/icon.ico",
          console=False, upx=False)
