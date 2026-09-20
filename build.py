import os
import shutil
import subprocess
import sys

NAME = "띵과사전"
ENTRY = "app.py"

HIDDEN = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
]

EXCLUDE = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtNetworkAuth", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "shiboken6.Shiboken", "tkinter", "matplotlib", "numpy", "PIL", "pandas",
    "unittest", "pydoc", "doctest",
]


def clean():
    for d in ("build", "dist", "__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    spec = NAME + ".spec"
    if os.path.exists(spec):
        os.remove(spec)


def main():
    clean()
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", NAME,
    ]
    for h in HIDDEN:
        args += ["--hidden-import", h]
    for e in EXCLUDE:
        args += ["--exclude-module", e]
    if os.path.exists("icon.ico"):
        args += ["--icon", "icon.ico"]
    args.append(ENTRY)

    print(" ".join(args))
    r = subprocess.run(args)
    if r.returncode != 0:
        return r.returncode

    out = os.path.join("dist", NAME + ".exe")
    if os.path.exists(out):
        print("built: %s (%.1f MB)" % (out, os.path.getsize(out) / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
