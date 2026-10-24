@echo off
setlocal

python -c "import struct,sys; sys.exit(0 if struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo ERROR: Use a 64-bit Python interpreter to build the Windows executable.
    exit /b 1
)

for /f "delims=" %%I in ('python -c "import tkinterdnd2, pathlib; print(pathlib.Path(tkinterdnd2.__file__).parent / 'tkdnd')"') do set TKDND_ROOT=%%I
if not defined TKDND_ROOT (
    echo ERROR: Drag-and-drop dependency is missing. Run: python -m pip install -r requirements.txt
    exit /b 1
)

python -m PyInstaller --noconfirm --clean --windowed --onefile --name SuperBatchRenamer --distpath dist --workpath build\work --specpath build --add-data "%TKDND_ROOT%\win-x64;tkinterdnd2\tkdnd\win-x64" --add-data "%TKDND_ROOT%\win-x64-tcl9;tkinterdnd2\tkdnd\win-x64-tcl9" app.py
if errorlevel 1 (
    echo ERROR: PyInstaller failed to build the application.
    exit /b 1
)

echo Built dist\SuperBatchRenamer.exe
