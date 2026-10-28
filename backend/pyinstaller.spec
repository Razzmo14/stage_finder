# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: freezes the FastAPI sidecar into one binary per OS.

The resulting binary serves the same entry point as `python -m app` and
is declared as externalBin in src-tauri/tauri.conf.json (one binary per
OS/architecture, suffixed with the Rust target triple).
"""

import os
import sys

# Make the backend package importable while the spec is evaluated.
sys.path.insert(0, os.path.dirname(os.path.abspath(SPEC)))

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

hiddenimports = (
    collect_submodules("app")
    + ["uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.lifespan", "uvicorn.lifespan.on"]
    + collect_submodules("uvicorn.protocols")
    + collect_submodules("apscheduler")
    + ["keyring.backends.SecretService", "keyring.backends.chainer"]
)

datas = [
    ("alembic", "alembic"),
    ("alembic.ini", "."),
] + collect_data_files("pdfminer")

a = Analysis(
    ["run_sidecar.py"],
    pathex=["."],
    binaries=collect_dynamic_libs("sqlite_vec"),
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "torch"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="stage-finder-backend",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
