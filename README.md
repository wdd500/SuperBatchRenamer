# Windows 64-bit Batch Renamer

A Windows desktop recreation of the supplied tool's visible features, with a
high-DPI-ready interface for file and folder renaming. Features include general
name/extension construction, replace or delete, insertion, case conversion,
position-based character replacement, repeatable random English-letter
generation, text encoding output, live batch preview, collision checks, and
undo. The **替换/删除** page also supports deleting a selected number of
characters from a 1-based position. Preview columns automatically size to
their contents, with a horizontal scrollbar for long names or paths and visible
cell gridlines.

**详细功能介绍：** [功能介绍.md](功能介绍.md)

In **位置字符**, enter a 1-based start position and character count, then choose
random English letters with a configurable output length and no duplicate
generated strings within the current batch (case-insensitively), fixed
replacement text, or incrementing numeric identifiers starting at 1 with a
configurable digit width. Use the separate
**编码生成** page to encode the selected scope directly; it does not require a
character position or count. Supported output includes UTF-8/GBK hexadecimal,
UTF-8 URL encoding, UTF-8 Base64, and Unicode escapes. Positions past the end
of a name are reported in the preview instead of being silently changed.

Numeric settings such as sequence start/increment, digit width, insertion
position, character start/count, and numeric-identifier digit width have `+`
and `−` buttons and accept digits (and an optional minus sign for signed
sequence values).

Switch the **重命名对象** selector to **文件夹** to choose a parent folder and
batch-rename its immediate child folders. File mode can add individual files or
import files from a folder, optionally including subdirectories.
Drag files into the app in file mode. Dragging a folder into file mode imports
its files (and nested files when that option is checked). In folder mode, drag
the folders themselves to add them to the rename list.

Select **关于** in the title bar for a feature overview and a clickable link to
the open-source repository.

The UI is based on the observed original window and tabs. Unobserved edge cases
use conservative behavior: existing destinations are never overwritten and
batch moves are staged through temporary names to support swaps.

## Build a Windows 64-bit executable

Use 64-bit Python 3.10 or later. Install the pinned build and drag-and-drop
dependencies once:

```powershell
python -m pip install -r requirements.txt
```

Then build:

```powershell
.\build_windows.bat
```

The standalone GUI executable is written to `dist\SuperBatchRenamer.exe`.
The build script checks that the active Python interpreter is 64-bit before
packaging. To run from source instead:

```powershell
python app.py
```

Run the tests:

```powershell
python -m unittest
```
