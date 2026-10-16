# PyInstaller: сборка MacBookCam.app (запускать на Mac: ./build_mac.sh)
import sys
sys.path.insert(0, SPECPATH)
from macbookcam import __version__

a = Analysis(
    ["mac_app.py"],
    datas=[("assets", "assets")],
    hiddenimports=["AVFoundation", "AppKit", "Foundation"],
    excludes=["tkinter", "customtkinter", "pyvirtualcam"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MacBookCam", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="MacBookCam")
app = BUNDLE(
    coll,
    name="MacBookCam.app",
    icon="assets/icon.png",
    bundle_identifier="com.hikinokomora.macbookcam",
    version=__version__,
    info_plist={
        "CFBundleName": "MacBookCam",
        "CFBundleDisplayName": "MacBookCam",
        "CFBundleShortVersionString": __version__,
        "LSUIElement": True,
        "NSCameraUsageDescription": "MacBookCam передаёт изображение с камеры на ваш ПК по локальной сети.",
        "NSLocalNetworkUsageDescription": "MacBookCam принимает подключения от ПК в локальной сети.",
        "NSHighResolutionCapable": True,
    },
)
