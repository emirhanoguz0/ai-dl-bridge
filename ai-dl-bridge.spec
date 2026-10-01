# -*- mode: python ; coding: utf-8 -*-
"""ai-dl-bridge — tek .exe paketi.

aria2c ve yt-dlp binary'leri tools/ altına gömülür; bridge/paths.py
çalışma anında sys._MEIPASS içinden çözer. Konsol yok (windowed).
"""

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[
        ('tools/aria2c.exe', 'tools'),
        ('tools/yt-dlp.exe', 'tools'),
        ('tools/ffmpeg.exe', 'tools'),
    ],
    datas=[
        ('assets/logo.png', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', 'docs'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ai-dl-bridge',
    icon='assets/logo.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowed — arka planda çalışan mini uygulama
    disable_windowed_traceback=False,
    argv_emulation=False,
)
