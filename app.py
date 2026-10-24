from __future__ import annotations

import ctypes
import os
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk
from collections.abc import Iterable
import webbrowser

from tkinterdnd2 import DND_FILES, COPY
from tkinterdnd2 import Tk as DnDTk

from renamer_core import RenameOptions, filename_problem, make_filename
from renamer_core import collect_dropped_paths
from renamer_core import generate_unique_random_characters
from renamer_core import make_folder_name
from renamer_core import transactional_move


class PreviewGrid(ttk.Frame):
    COLUMNS = (
        ("原名称", 120, 900),
        ("新名称预览", 140, 900),
        ("所在路径", 180, 900),
        ("状态", 90, 280),
    )

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Card.TFrame")
        self.rows: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        self.widths = [minimum for _title, minimum, _maximum in self.COLUMNS]
        self._measure_font = tkfont.Font(family="Segoe UI", size=10)
        self._header_font = tkfont.Font(
            family="Segoe UI", size=9, weight="bold"
        )
        self.canvas = tk.Canvas(
            self,
            background="#ffffff",
            highlightthickness=0,
            borderwidth=0,
        )
        self.vertical_scrollbar = ttk.Scrollbar(
            self, orient=tk.VERTICAL, command=self.canvas.yview
        )
        self.horizontal_scrollbar = ttk.Scrollbar(
            self, orient=tk.HORIZONTAL, command=self.canvas.xview
        )
        self.canvas.configure(
            yscrollcommand=self.vertical_scrollbar.set,
            xscrollcommand=self.horizontal_scrollbar.set,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        self.horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.tag_colors: dict[str, str] = {
            "row_odd": "#ffffff",
            "row_even": "#f5f8fc",
        }

    def tag_configure(self, tag: str, **options: str) -> None:
        background = options.get("background")
        if background:
            self.tag_colors[tag] = background

    def clear(self) -> None:
        self.rows.clear()
        self.render()

    def set_rows(
        self, rows: list[tuple[tuple[str, ...], tuple[str, ...]]]
    ) -> None:
        self.rows = rows
        self.render()

    def insert(
        self,
        parent: str,
        index: str | int,
        values: tuple[str, ...],
        tags: tuple[str, ...] = (),
    ) -> str:
        row = tuple(str(value) for value in values)
        if index == tk.END:
            self.rows.append((row, tags))
            row_index = len(self.rows) - 1
        else:
            row_index = int(index)
            self.rows.insert(row_index, (row, tags))
        self.render()
        return str(row_index)

    def get_children(self) -> tuple[str, ...]:
        return tuple(str(index) for index in range(len(self.rows)))

    def item(self, item: str | int, option: str | None = None) -> object:
        values, tags = self.rows[int(item)]
        data: dict[str, object] = {"values": values, "tags": tags}
        return data[option] if option else data

    def xview(self, *args: object) -> None:
        self.canvas.xview(*args)

    def yview(self, *args: object) -> None:
        self.canvas.yview(*args)

    @staticmethod
    def _fit_text(value: str, font: tkfont.Font, max_width: int) -> str:
        if font.measure(value) <= max_width:
            return value
        suffix = "…"
        value = value.rstrip()
        while value and font.measure(value + suffix) > max_width:
            value = value[:-1]
        return value + suffix

    def render(self) -> None:
        self.canvas.delete("all")
        widths: list[int] = []
        for column, (title, minimum, maximum) in enumerate(self.COLUMNS):
            longest = self._header_font.measure(title)
            for values, _tags in self.rows:
                if column < len(values):
                    longest = max(longest, self._measure_font.measure(values[column]))
            widths.append(max(minimum, min(maximum, longest + 24)))
        self.widths = widths

        header_height = 38
        row_height = 34
        grid_color = "#bdc9d8"
        x_positions = [0]
        for width in widths:
            x_positions.append(x_positions[-1] + width)
        total_width = x_positions[-1]
        total_height = header_height + row_height * len(self.rows)

        for column, (title, _minimum, _maximum) in enumerate(self.COLUMNS):
            left, right = x_positions[column], x_positions[column + 1]
            self.canvas.create_rectangle(
                left,
                0,
                right,
                header_height,
                fill="#e8eef6",
                outline=grid_color,
                width=1,
            )
            text = self._fit_text(title, self._header_font, widths[column] - 16)
            self.canvas.create_text(
                left + 9,
                header_height // 2,
                text=text,
                font=self._header_font,
                fill="#344a66",
                anchor=tk.W,
            )

        for row_index, (values, tags) in enumerate(self.rows):
            top = header_height + row_height * row_index
            bottom = top + row_height
            background = next(
                (self.tag_colors[tag] for tag in tags if tag in self.tag_colors),
                "#ffffff",
            )
            for column, value in enumerate(values[: len(widths)]):
                left, right = x_positions[column], x_positions[column + 1]
                self.canvas.create_rectangle(
                    left,
                    top,
                    right,
                    bottom,
                    fill=background,
                    outline=grid_color,
                    width=1,
                )
                text = self._fit_text(value, self._measure_font, widths[column] - 18)
                self.canvas.create_text(
                    left + 9,
                    top + row_height // 2,
                    text=text,
                    font=self._measure_font,
                    fill="#29394f",
                    anchor=tk.W,
                )

        self.canvas.configure(scrollregion=(0, 0, total_width, total_height))


def enable_windows_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass


class BatchRenamer(DnDTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("超级文件批量重命名工具")
        self.geometry("1220x820")
        self.minsize(980, 680)
        if os.name == "nt":
            self.state("zoomed")
        self.configure(bg="#f3f6fb")

        self.files: list[Path] = []
        self.target_kind = "file"
        self.last_moves: list[tuple[Path, Path]] = []
        self.vars: dict[str, tk.Variable] = {}
        self.numeric_specs: dict[str, tuple[int, int, int]] = {}
        self.numeric_entries: dict[str, ttk.Entry] = {}
        self._configure_style()
        self._build_ui()
        self._register_drop_targets(self)
        self._watch_inputs()
        self.refresh_preview()

    def _register_drop_targets(self, widget: tk.Misc) -> None:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", self._on_drop)
        for child in widget.winfo_children():
            self._register_drop_targets(child)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background="#f3f6fb")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure(
            "TLabelframe",
            background="#ffffff",
            bordercolor="#dce4ef",
            relief="solid",
        )
        style.configure(
            "TLabelframe.Label",
            background="#ffffff",
            foreground="#18365f",
            font=("Segoe UI Semibold", 10),
        )
        style.configure("TLabel", background="#f3f6fb", foreground="#26344a")
        style.configure("Card.TLabel", background="#ffffff", foreground="#26344a")
        style.configure(
            "Title.TLabel",
            background="#152c4e",
            foreground="#ffffff",
            font=("Segoe UI Semibold", 19),
        )
        style.configure(
            "Subtitle.TLabel",
            background="#152c4e",
            foreground="#c5d4e8",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Section.TLabel",
            background="#ffffff",
            foreground="#18365f",
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "TButton",
            padding=(12, 7),
            background="#e9eff7",
            foreground="#21344f",
            borderwidth=0,
        )
        style.map(
            "TButton",
            background=[("active", "#d9e5f3"), ("disabled", "#eff2f6")],
            foreground=[("disabled", "#9aa6b5")],
        )
        style.configure(
            "Accent.TButton",
            padding=(16, 9),
            background="#1769d2",
            foreground="#ffffff",
            font=("Segoe UI Semibold", 10),
        )
        style.map("Accent.TButton", background=[("active", "#0f57b5")])
        style.configure(
            "Danger.TButton",
            padding=(12, 7),
            background="#fff0ed",
            foreground="#a33a2c",
        )
        style.map("Danger.TButton", background=[("active", "#ffe0d9")])
        style.configure(
            "TNotebook",
            background="#ffffff",
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            padding=(17, 10),
            background="#eef2f8",
            foreground="#52637a",
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#ffffff")],
            foreground=[("selected", "#1769d2")],
        )
        style.configure(
            "Treeview",
            rowheight=32,
            font=("Segoe UI", 10),
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground="#29394f",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Treeview.Item",
            relief="solid",
            borderwidth=1,
            padding=(5, 2),
        )
        style.configure(
            "Treeview.Heading",
            padding=(10, 10),
            background="#edf2f8",
            foreground="#42556f",
            font=("Segoe UI Semibold", 9),
            relief="flat",
        )
        style.map("Treeview", background=[("selected", "#dbeafe")])
        style.configure(
            "TEntry",
            padding=(8, 7),
            fieldbackground="#ffffff",
            foreground="#1e2e43",
        )
        style.configure(
            "TCombobox",
            padding=(7, 6),
            fieldbackground="#ffffff",
            foreground="#1e2e43",
        )
        style.configure(
            "TRadiobutton",
            background="#ffffff",
            foreground="#35465d",
            indicatorsize=18,
            indicatormargin=5,
        )
        style.configure(
            "TCheckbutton",
            background="#ffffff",
            foreground="#35465d",
            indicatorsize=18,
            indicatormargin=5,
        )
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family="Segoe UI", size=10)
            except tk.TclError:
                pass

    def _var(self, name: str, value: object) -> tk.Variable:
        if name not in self.vars:
            self.vars[name] = tk.StringVar(value=str(value))
        return self.vars[name]

    def _entry(
        self,
        parent: ttk.Frame | ttk.LabelFrame,
        label: str,
        name: str,
        default: str = "",
        width: int = 16,
    ) -> None:
        cell = ttk.Frame(parent)
        cell.pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Label(cell, text=label).pack(anchor=tk.W)
        ttk.Entry(cell, textvariable=self._var(name, default), width=width).pack()

    def _validate_integer(self, proposed: str, signed: str) -> bool:
        if proposed == "":
            return True
        if signed == "1" and proposed == "-":
            return True
        digits = proposed[1:] if signed == "1" and proposed.startswith("-") else proposed
        return bool(digits) and all("0" <= character <= "9" for character in digits)

    def _change_number(self, name: str, amount: int) -> None:
        minimum, maximum, _default = self.numeric_specs[name]
        try:
            current = int(str(self.vars[name].get()))
        except ValueError:
            current = minimum
        self.vars[name].set(str(max(minimum, min(maximum, current + amount))))

    def _normalize_number(self, name: str) -> None:
        minimum, maximum, default = self.numeric_specs[name]
        try:
            current = int(str(self.vars[name].get()))
        except ValueError:
            current = default
        self.vars[name].set(str(max(minimum, min(maximum, current))))

    def _number_entry(
        self,
        parent: ttk.Frame | ttk.LabelFrame,
        label: str,
        name: str,
        default: str,
        width: int,
        minimum: int,
        maximum: int,
        step: int = 1,
    ) -> None:
        cell = ttk.Frame(parent)
        cell.pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Label(cell, text=label).pack(anchor=tk.W)
        control = ttk.Frame(cell)
        control.pack(fill=tk.X)
        signed = minimum < 0
        validator = (self.register(self._validate_integer), "%P", "1" if signed else "0")
        entry = ttk.Entry(
            control,
            textvariable=self._var(name, default),
            width=width,
            validate="key",
            validatecommand=validator,
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.numeric_entries[name] = entry
        buttons = ttk.Frame(control)
        buttons.pack(side=tk.LEFT, padx=(3, 0))
        self.numeric_specs[name] = (minimum, maximum, int(default))
        ttk.Button(
            buttons,
            text="+",
            width=2,
            command=lambda: self._change_number(name, step),
        ).pack()
        ttk.Button(
            buttons,
            text="−",
            width=2,
            command=lambda: self._change_number(name, -step),
        ).pack()
        entry.bind("<FocusOut>", lambda _event: self._normalize_number(name))

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg="#152c4e", padx=24, pady=17)
        header.pack(fill=tk.X)
        title_block = tk.Frame(header, bg="#152c4e")
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            title_block,
            text="超级文件批量重命名工具",
            bg="#152c4e",
            fg="#ffffff",
            font=("Segoe UI", 19, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            title_block,
            text="批量预览 · 安全重命名 · 支持文件与文件夹",
            bg="#152c4e",
            fg="#c5d4e8",
            font=("Segoe UI", 10),
        ).pack(anchor=tk.W, pady=(3, 0))
        ttk.Button(
            header,
            text="关于",
            command=self._show_about,
        ).pack(side=tk.RIGHT, padx=(12, 0))

        target_card = ttk.Frame(self, style="Card.TFrame", padding=(15, 10))
        target_card.pack(fill=tk.X, padx=18, pady=(14, 8))
        ttk.Label(
            target_card, text="重命名对象", style="Section.TLabel"
        ).pack(side=tk.LEFT, padx=(0, 14))
        self.target_var = tk.StringVar(value="file")
        self.file_target_radio = ttk.Radiobutton(
            target_card,
            text="文件",
            value="file",
            variable=self.target_var,
            command=self._set_target_kind,
        )
        self.file_target_radio.pack(side=tk.LEFT, padx=5)
        self.folder_target_radio = ttk.Radiobutton(
            target_card,
            text="文件夹",
            value="folder",
            variable=self.target_var,
            command=self._set_target_kind,
        )
        self.folder_target_radio.pack(side=tk.LEFT, padx=5)
        ttk.Label(
            target_card,
            text="文件夹模式：选择父目录，批量重命名其中的子文件夹",
            foreground="#718198",
            style="Card.TLabel",
        ).pack(side=tk.LEFT, padx=(18, 0))

        toolbar = ttk.Frame(self, style="Card.TFrame", padding=(12, 10))
        toolbar.pack(fill=tk.X, padx=18, pady=(0, 8))
        self.add_files_button = ttk.Button(
            toolbar, text="添加文件", command=self.add_files
        )
        self.add_files_button.pack(side=tk.LEFT, padx=(0, 7))
        self.add_folder_button = ttk.Button(
            toolbar, text="导入文件夹内文件", command=self.add_folder
        )
        self.add_folder_button.pack(side=tk.LEFT, padx=(0, 7))
        self.add_subfolders_button = ttk.Button(
            toolbar, text="批量添加子文件夹", command=self.add_subfolders
        )
        self.add_subfolders_button.pack(side=tk.LEFT, padx=(0, 7))
        ttk.Button(
            toolbar,
            text="撤销上次操作",
            command=self.undo,
        ).pack(side=tk.LEFT, padx=(8, 7))
        ttk.Button(
            toolbar,
            text="清空列表",
            command=self.clear_files,
            style="Danger.TButton",
        ).pack(side=tk.LEFT, padx=(0, 7))
        ttk.Button(
            toolbar,
            text="执行重命名",
            command=self.apply_renames,
            style="Accent.TButton",
        ).pack(side=tk.RIGHT)
        self.recursive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar,
            text="导入文件时包含子目录",
            variable=self.recursive_var,
        ).pack(side=tk.RIGHT, padx=(8, 16))

        rules_card = ttk.Frame(self, style="Card.TFrame", padding=(10, 0, 10, 8))
        rules_card.pack(fill=tk.X, padx=18, pady=(0, 8))
        self.tabs = ttk.Notebook(rules_card)
        self.tabs.pack(fill=tk.X)
        self._build_general_tab()
        self._build_replace_tab()
        self._build_insert_tab()
        self._build_case_tab()
        self._build_character_tab()
        self._build_encoding_tab()

        table_card = ttk.Frame(self, style="Card.TFrame", padding=(10, 10, 10, 8))
        table_card.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 12))
        table_heading = ttk.Frame(table_card, style="Card.TFrame")
        table_heading.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            table_heading, text="重命名预览", style="Section.TLabel"
        ).pack(side=tk.LEFT)
        ttk.Label(
            table_heading,
            text="可将文件或文件夹拖到窗口/列表中；预览确认后点击“执行重命名”",
            style="Card.TLabel",
            foreground="#718198",
        ).pack(side=tk.RIGHT, padx=12)
        table_frame = ttk.Frame(table_card, style="Card.TFrame")
        table_frame.pack(fill=tk.BOTH, expand=True)
        self.table = PreviewGrid(table_frame)
        self.table.tag_configure("row_odd", background="#ffffff")
        self.table.tag_configure("row_even", background="#f5f8fc")
        self.table.grid(row=0, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="0 个文件")
        ttk.Label(
            self,
            textvariable=self.status_var,
            relief=tk.FLAT,
            anchor=tk.W,
            padding=(20, 7),
            background="#e8edf4",
            foreground="#53647a",
        ).pack(fill=tk.X, side=tk.BOTTOM)

    def _show_about(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("关于超级文件批量重命名工具")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.configure(bg="#ffffff")

        content = ttk.Frame(dialog, style="Card.TFrame", padding=24)
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            content,
            text="超级文件批量重命名工具",
            style="Section.TLabel",
            font=("Segoe UI Semibold", 15),
        ).pack(anchor=tk.W)
        ttk.Label(
            content,
            text=(
                "Windows 64 位批量重命名工具，支持文件和文件夹批量处理、"
                "实时预览、安全重命名与撤销。\n\n"
                "功能包括常规命名、查找替换、按位置删除或修改字符、"
                "随机英文字母与递增编号、编码生成、拖放导入，以及重名和"
                "无效名称检查。\n\n"
                "本软件为开源项目，欢迎访问仓库查看源码与使用说明："
            ),
            style="Card.TLabel",
            wraplength=470,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(14, 12))

        repository_url = "https://github.com/wdd500/SuperBatchRenamer"
        link = ttk.Label(
            content,
            text=repository_url,
            style="Card.TLabel",
            foreground="#1769d2",
            cursor="hand2",
        )
        link.pack(anchor=tk.W)
        link.bind(
            "<Button-1>",
            lambda _event: self._open_repository(repository_url),
        )

        actions = ttk.Frame(content, style="Card.TFrame")
        actions.pack(fill=tk.X, pady=(20, 0))
        ttk.Button(
            actions,
            text="在浏览器中打开仓库",
            command=lambda: self._open_repository(repository_url),
            style="Accent.TButton",
        ).pack(side=tk.RIGHT)
        ttk.Button(actions, text="关闭", command=dialog.destroy).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.grab_set()
        dialog.focus_set()

    @staticmethod
    def _open_repository(url: str) -> None:
        if not webbrowser.open_new_tab(url):
            messagebox.showerror(
                "无法打开浏览器",
                f"无法打开开源仓库链接：\n{url}",
            )

    def _build_general_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(tab, text="常规")
        modes = ttk.Frame(tab)
        modes.pack(fill=tk.X)
        ttk.Label(modes, text="重命名：").pack(side=tk.LEFT)
        self.name_mode_radio = self._radio(modes, "文件名", "mode", "filename")
        self.extension_mode_radio = self._radio(
            modes, "扩展名", "mode", "extension"
        )
        self.all_mode_radio = self._radio(modes, "全部", "mode", "all")
        self._number_entry(
            modes, "起始量", "number_start", "0", 8, -999999999, 999999999
        )
        self._number_entry(
            modes, "增量", "number_step", "1", 8, -999999999, 999999999
        )

        name_box = ttk.LabelFrame(tab, text="文件名")
        name_box.pack(fill=tk.X, pady=(6, 3))
        self._entry(name_box, "前缀", "name_prefix")
        self._entry(name_box, "主文件名", "name_base", width=24)
        self._number_entry(name_box, "位数", "number_width", "1", 8, 1, 12)
        self._entry(name_box, "后缀", "name_suffix")

        self.extension_box = ttk.LabelFrame(tab, text="扩展名（仅文件模式）")
        self.extension_box.pack(fill=tk.X, pady=3)
        self._entry(self.extension_box, "前缀", "extension_prefix")
        self._entry(self.extension_box, "新扩展名", "extension_base", width=24)
        ttk.Label(
            self.extension_box, text="序号位数使用上方设置", foreground="#666666"
        ).pack(side=tk.LEFT, padx=10, pady=18)
        self._entry(self.extension_box, "后缀", "extension_suffix")

    def _build_replace_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="替换/删除")
        controls = ttk.Frame(tab)
        controls.pack(fill=tk.X)
        self._scope_selector(controls)
        self._entry(controls, "查找内容", "search_text", width=26)
        self._entry(controls, "替换为", "replacement_text", width=26)
        self.delete_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            controls,
            text="删除匹配内容",
            variable=self.delete_var,
            command=self.refresh_preview,
        ).pack(side=tk.LEFT, padx=8, pady=18)
        position_controls = ttk.Frame(tab)
        position_controls.pack(fill=tk.X, pady=(2, 0))
        self.delete_position_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            position_controls,
            text="按位置删除（启用后忽略查找/替换）",
            variable=self.delete_position_var,
            command=self.refresh_preview,
        ).pack(side=tk.LEFT, padx=(4, 8), pady=5)
        self._number_entry(
            position_controls, "起始位置", "character_start", "1", 7, 1, 1000000
        )
        self._number_entry(
            position_controls, "字符数", "character_count", "1", 7, 1, 1000000
        )

    def _build_insert_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="插入")
        self._scope_selector(tab)
        self._entry(tab, "插入内容", "inserted_text", width=26)
        position_frame = ttk.Frame(tab)
        position_frame.pack(side=tk.LEFT, padx=8, pady=5)
        position_cell = ttk.Frame(position_frame)
        position_cell.pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Label(position_cell, text="位置").pack(anchor=tk.W)
        position = ttk.Combobox(
            position_cell,
            textvariable=self._var("insert_position", "prefix"),
            values=("前置", "后置", "指定位置"),
            state="readonly",
            width=12,
        )
        position.pack()
        position.bind("<<ComboboxSelected>>", lambda _event: self.refresh_preview())
        self._number_entry(
            position_frame, "字符位置", "insert_index", "0", 8, 0, 1000000
        )

    def _build_case_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="转大小写")
        self._scope_selector(tab)
        frame = ttk.Frame(tab)
        frame.pack(side=tk.LEFT, padx=8, pady=5)
        ttk.Label(frame, text="转换方式").pack(anchor=tk.W)
        mode = ttk.Combobox(
            frame,
            textvariable=self._var("case_mode", "upper"),
            values=("大写", "小写", "首字母大写", "大小写互换"),
            state="readonly",
            width=12,
        )
        mode.pack()
        mode.bind("<<ComboboxSelected>>", lambda _event: self.refresh_preview())
        ttk.Label(
            tab,
            text="upper=大写  lower=小写  title=首字母大写  swap=大小写互换",
            foreground="#555555",
        ).pack(side=tk.LEFT, padx=8)

    def _build_character_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="位置字符")
        self._scope_selector(tab)
        self._number_entry(
            tab, "起始位置（从 1 开始）", "character_start", "1", 10, 1, 1000000
        )
        self._number_entry(tab, "字符数", "character_count", "1", 8, 1, 1000000)

        action_frame = ttk.Frame(tab)
        action_frame.pack(side=tk.LEFT, padx=8, pady=5)
        ttk.Label(action_frame, text="修改方式").pack(anchor=tk.W)
        action = ttk.Combobox(
            action_frame,
            textvariable=self._var("character_action", "random"),
            values=("随机英文字母", "指定字符替换", "数字编号"),
            state="readonly",
            width=17,
        )
        action.pack()
        action.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._update_character_controls(),
        )

        self.character_number_cell = ttk.Frame(tab)
        self._number_entry(
            self.character_number_cell,
            "编号位数",
            "character_number_width",
            "1",
            7,
            1,
            12,
        )
        self.character_random_cell = ttk.Frame(tab)
        self._number_entry(
            self.character_random_cell,
            "随机字符位数",
            "character_random_width",
            "1",
            7,
            1,
            12,
        )

        self.fixed_characters_cell = ttk.Frame(tab)
        ttk.Label(self.fixed_characters_cell, text="替换为固定字符").pack(anchor=tk.W)
        self.fixed_characters_entry = ttk.Entry(
            self.fixed_characters_cell,
            textvariable=self._var("fixed_characters", ""),
            width=18,
        )
        self.fixed_characters_entry.pack()

        self.character_help_label = ttk.Label(
            tab,
            text="随机字符各项不重复；数字编号从 1 开始递增",
            style="Card.TLabel",
            foreground="#718198",
        )
        self.character_help_label.pack(side=tk.LEFT, padx=10)
        self._update_character_controls(refresh=False)

    def _build_encoding_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="编码生成")
        self._scope_selector(tab)

        encoding_cell = ttk.Frame(tab)
        encoding_cell.pack(side=tk.LEFT, padx=8, pady=5)
        ttk.Label(encoding_cell, text="编码格式").pack(anchor=tk.W)
        self.encoding_combo = ttk.Combobox(
            encoding_cell,
            textvariable=self._var("encoding_format", "utf-8-hex"),
            values=(
                "UTF-8 十六进制",
                "GBK 十六进制",
                "URL 编码（UTF-8）",
                "Base64（UTF-8）",
                "Unicode 转义",
            ),
            state="readonly",
            width=21,
        )
        self.encoding_combo.pack()
        self.encoding_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self.refresh_preview()
        )
        ttk.Label(
            tab,
            text="按作用范围编码整个文件名、扩展名或完整名称",
            style="Card.TLabel",
            foreground="#718198",
        ).pack(side=tk.LEFT, padx=10)

    def _update_character_controls(self, refresh: bool = True) -> None:
        if not hasattr(self, "fixed_characters_entry"):
            return
        action = {
            "随机英文字母": "random",
            "指定字符替换": "fixed",
            "数字编号": "number",
        }.get(str(self.vars["character_action"].get()), "random")
        self.fixed_characters_entry.configure(
            state=tk.NORMAL if action == "fixed" else tk.DISABLED
        )
        self.fixed_characters_cell.pack_forget()
        self.character_number_cell.pack_forget()
        self.character_random_cell.pack_forget()
        if action == "fixed":
            self.fixed_characters_cell.pack(
                side=tk.LEFT, padx=6, pady=5, before=self.character_help_label
            )
        elif action == "number":
            self.character_number_cell.pack(
                side=tk.LEFT, padx=6, pady=5, before=self.character_help_label
            )
        elif action == "random":
            self.character_random_cell.pack(
                side=tk.LEFT, padx=6, pady=5, before=self.character_help_label
            )
        if refresh:
            self.refresh_preview()

    def _radio(
        self, parent: ttk.Frame, label: str, name: str, value: str
    ) -> ttk.Radiobutton:
        radio = ttk.Radiobutton(
            parent,
            text=label,
            value=value,
            variable=self._var(name, value if name not in self.vars else "filename"),
            command=self.refresh_preview,
        )
        radio.pack(side=tk.LEFT, padx=4)
        return radio

    def _scope_selector(self, parent: ttk.Frame) -> None:
        cell = ttk.Frame(parent)
        cell.pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Label(cell, text="作用范围").pack(anchor=tk.W)
        scope = ttk.Combobox(
            cell,
            textvariable=self._var("scope", "filename"),
            values=("文件名", "扩展名", "全部"),
            state="readonly",
            width=14,
        )
        scope.pack()
        scope.bind("<<ComboboxSelected>>", lambda _event: self.refresh_preview())

    def _watch_inputs(self) -> None:
        for variable in self.vars.values():
            variable.trace_add("write", lambda *_args: self.refresh_preview())
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self.refresh_preview())

    def _rename_options(self) -> RenameOptions:
        tab = self.tabs.index(self.tabs.select())
        operation = (
            "general",
            "delete_range" if tab == 1 and self.delete_position_var.get() else "replace",
            "insert",
            "case",
            "character",
            "encode",
        )[tab]

        def integer(name: str, default: int) -> int:
            try:
                return int(str(self.vars[name].get()))
            except (ValueError, KeyError):
                return default

        return RenameOptions(
            operation=operation,
            mode=str(self.vars["mode"].get()),
            number_start=integer("number_start", 0),
            number_step=integer("number_step", 1),
            number_width=max(1, min(integer("number_width", 1), 12)),
            name_prefix=str(self.vars["name_prefix"].get()),
            name_base=str(self.vars["name_base"].get()),
            name_suffix=str(self.vars["name_suffix"].get()),
            extension_prefix=str(self.vars["extension_prefix"].get()),
            extension_base=str(self.vars["extension_base"].get()),
            extension_suffix=str(self.vars["extension_suffix"].get()),
            scope={
                "文件名": "filename",
                "扩展名": "extension",
                "全部": "all",
            }.get(str(self.vars["scope"].get()), "filename"),
            search_text=str(self.vars["search_text"].get()),
            replacement_text=str(self.vars["replacement_text"].get()),
            delete_match=self.delete_var.get(),
            inserted_text=str(self.vars["inserted_text"].get()),
            insert_position={
                "前置": "prefix",
                "后置": "suffix",
                "指定位置": "index",
            }.get(str(self.vars["insert_position"].get()), "prefix"),
            insert_index=integer("insert_index", 0),
            case_mode={
                "大写": "upper",
                "小写": "lower",
                "首字母大写": "title",
                "大小写互换": "swap",
            }.get(str(self.vars["case_mode"].get()), "upper"),
            character_start=integer("character_start", 1),
            character_count=integer("character_count", 1),
            character_action={
                "随机英文字母": "random",
                "指定字符替换": "fixed",
                "数字编号": "number",
            }.get(str(self.vars["character_action"].get()), "random"),
            character_random_width=max(
                1, min(integer("character_random_width", 1), 12)
            ),
            character_number_width=max(
                1, min(integer("character_number_width", 1), 12)
            ),
            fixed_characters=str(self.vars["fixed_characters"].get()),
            encoding_format={
                "UTF-8 十六进制": "utf-8-hex",
                "GBK 十六进制": "gbk-hex",
                "URL 编码（UTF-8）": "url",
                "Base64（UTF-8）": "base64",
                "Unicode 转义": "unicode",
            }.get(str(self.vars["encoding_format"].get()), "utf-8-hex"),
        )

    def add_files(self) -> None:
        if self.target_kind != "file":
            return
        names = filedialog.askopenfilenames(title="选择要重命名的文件")
        self._add_paths(Path(name) for name in names)

    def add_folder(self) -> None:
        if self.target_kind != "file":
            return
        folder = filedialog.askdirectory(title="选择文件夹")
        if not folder:
            return
        root = Path(folder)
        pattern = "**/*" if self.recursive_var.get() else "*"
        self._add_paths(path for path in root.glob(pattern) if path.is_file())

    def add_subfolders(self) -> None:
        if self.target_kind != "folder":
            return
        folder = filedialog.askdirectory(title="选择包含待重命名子文件夹的父目录")
        if not folder:
            return
        root = Path(folder)
        self._add_paths(
            path for path in root.iterdir() if path.is_dir() and not path.is_symlink()
        )

    def _on_drop(self, event: tk.Event) -> str:
        try:
            dropped = self.tk.splitlist(event.data)
            candidates = collect_dropped_paths(
                dropped,
                self.target_kind,
                recursive=self.recursive_var.get(),
            )
        except (OSError, tk.TclError, ValueError) as error:
            messagebox.showerror("拖放失败", f"无法读取拖入的项目：\n{error}")
            return COPY

        before = len(self.files)
        self._add_paths(candidates)
        added = len(self.files) - before
        if added:
            noun = "个文件夹" if self.target_kind == "folder" else "个文件"
            self.status_var.set(
                f"已从拖放导入 {added} {noun}    |    共 {len(self.files)} 项"
            )
        else:
            accepted_type = "文件夹" if self.target_kind == "folder" else "文件或含文件的文件夹"
            messagebox.showinfo(
                "拖放提示",
                f"没有可添加的项目。当前模式接受：{accepted_type}。",
            )
        return COPY

    def _set_target_kind(self) -> None:
        selected = str(self.target_var.get())
        if selected == self.target_kind:
            return
        if self.files and not messagebox.askyesno(
            "切换重命名对象",
            "切换文件/文件夹类型会清空当前列表，是否继续？",
        ):
            self.target_var.set(self.target_kind)
            return
        self.files.clear()
        self.target_kind = selected
        is_folder = selected == "folder"
        self.extension_mode_radio.configure(
            state=tk.DISABLED if is_folder else tk.NORMAL
        )
        self.name_mode_radio.configure(text="文件夹名" if is_folder else "文件名")
        if is_folder and self.vars["mode"].get() == "extension":
            self.vars["mode"].set("filename")
        self.extension_box.configure(
            text="扩展名（仅文件模式）"
        )
        for child in self.extension_box.winfo_children():
            for control in child.winfo_children():
                if isinstance(control, ttk.Entry):
                    control.configure(state=tk.DISABLED if is_folder else tk.NORMAL)
        self.add_files_button.configure(
            state=tk.NORMAL if selected == "file" else tk.DISABLED
        )
        self.add_folder_button.configure(
            state=tk.NORMAL if selected == "file" else tk.DISABLED
        )
        self.add_subfolders_button.configure(
            state=tk.NORMAL if selected == "folder" else tk.DISABLED
        )
        self.refresh_preview()

    def _add_paths(self, paths: Iterable[Path]) -> None:
        existing = {os.path.normcase(str(path.resolve())) for path in self.files}
        for path in paths:
            candidate = Path(path)
            valid = (
                candidate.is_file()
                if self.target_kind == "file"
                else candidate.is_dir() and not candidate.is_symlink()
            )
            if not valid:
                continue
            key = os.path.normcase(str(candidate.resolve()))
            if key not in existing:
                self.files.append(candidate)
                existing.add(key)
        self.refresh_preview()

    def clear_files(self) -> None:
        self.files.clear()
        self.refresh_preview()

    def _make_name(self, name: str, options: RenameOptions, index: int) -> str:
        if self.target_kind == "folder":
            return make_folder_name(name, options, index)
        return make_filename(name, options, index)

    def _make_batch_names(
        self, paths: list[Path], options: RenameOptions
    ) -> list[tuple[Path, str, str]]:
        random_characters: list[str | None] = [None] * len(paths)
        if options.operation == "character" and options.character_action == "random":
            random_characters = generate_unique_random_characters(
                [path.name for path in paths], options
            )

        previews: list[tuple[Path, str, str]] = []
        for index, path in enumerate(paths):
            item_options = options
            token = random_characters[index]
            if token is not None:
                item_options = replace(
                    options,
                    character_action="fixed",
                    fixed_characters=token,
                )
            try:
                new_name = self._make_name(path.name, item_options, index)
            except (UnicodeError, ValueError) as error:
                previews.append((path, path.name, str(error)))
            else:
                previews.append((path, new_name, ""))
        return previews

    def refresh_preview(self) -> None:
        if not hasattr(self, "table"):
            return
        options = self._rename_options()
        rows: list[tuple[Path, str, str]] = []
        target_groups: dict[str, list[int]] = {}
        try:
            previews = self._make_batch_names(self.files, options)
        except ValueError as error:
            previews = [(path, path.name, str(error)) for path in self.files]

        moving_keys: set[str] = set()
        for path, new_name, error in previews:
            if error:
                continue
            if new_name != path.name and not filename_problem(new_name):
                moving_keys.add(
                    os.path.normcase(str(path.with_name(new_name).resolve()))
                )

        for index, (path, new_name, error) in enumerate(previews):
            if error:
                rows.append((path, new_name, error))
                continue
            problem = filename_problem(new_name)
            status = "可重命名" if new_name != path.name else "未更改"
            if problem:
                status = problem
                destination_key = ""
            else:
                destination_key = os.path.normcase(
                    str(path.with_name(new_name).resolve())
                )
            if not problem and new_name != path.name and destination_key not in moving_keys:
                if path.with_name(new_name).exists():
                    status = "目标已存在"
            rows.append((path, new_name, status))
            if not problem and new_name != path.name:
                target_groups.setdefault(destination_key, []).append(index)

        for indices in target_groups.values():
            if len(indices) > 1:
                for index in indices:
                    path, name, _status = rows[index]
                    rows[index] = (path, name, "目标重名")

        display_rows: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        for row_index, (path, new_name, status) in enumerate(rows):
            if status == "可重命名":
                destination_key = os.path.normcase(
                    str(path.with_name(new_name).resolve())
                )
                if destination_key not in moving_keys and path.with_name(new_name).exists():
                    status = "目标已存在"
            display_rows.append(
                (
                    (path.name, new_name, str(path.parent), status),
                    ("row_even" if row_index % 2 else "row_odd",),
                )
            )
        self.table.set_rows(display_rows)

        noun = "文件夹" if self.target_kind == "folder" else "文件"
        self.status_var.set(
            f"{len(self.files)} 个{noun}    |    自动预览：开"
        )

    def apply_renames(self) -> None:
        options = self._rename_options()
        moves: list[tuple[Path, Path]] = []
        destinations: set[str] = set()
        try:
            generated = self._make_batch_names(self.files, options)
        except ValueError as error:
            messagebox.showerror("无法生成名称", str(error))
            return
        previews: list[tuple[Path, str]] = []
        for source, new_name, error in generated:
            if error:
                messagebox.showerror("无法生成名称", f"{source.name}\n{error}")
                return
            previews.append((source, new_name))

        moving_keys = {
            os.path.normcase(str(source.with_name(new_name).resolve()))
            for source, new_name in previews
            if new_name != source.name and not filename_problem(new_name)
        }
        for source, new_name in previews:
            if new_name == source.name:
                continue
            problem = filename_problem(new_name)
            if problem:
                messagebox.showerror("无法重命名", f"{source.name}\n{problem}")
                return
            destination = source.with_name(new_name)
            key = os.path.normcase(str(destination.resolve()))
            if key in destinations:
                messagebox.showerror("无法重命名", f"多个文件将重命名为：\n{new_name}")
                return
            destinations.add(key)
            if destination.exists() and key not in moving_keys:
                messagebox.showerror("无法重命名", f"目标文件已存在：\n{destination}")
                return
            moves.append((source, destination))

        if not moves:
            messagebox.showinfo("重命名", "没有需要更改的文件名。")
            return
        if not messagebox.askyesno(
            "确认重命名", f"即将重命名 {len(moves)} 个文件，是否继续？"
        ):
            return
        try:
            transactional_move(moves)
        except OSError as error:
            messagebox.showerror("重命名失败", str(error))
            self.refresh_preview()
            return
        self.last_moves = moves
        move_map = dict(moves)
        self.files = [move_map.get(path, path) for path in self.files]
        self.refresh_preview()
        noun = "个文件夹" if self.target_kind == "folder" else "个文件"
        messagebox.showinfo("重命名完成", f"已重命名 {len(moves)} {noun}。")

    def undo(self) -> None:
        if not self.last_moves:
            messagebox.showinfo("撤销", "没有可撤销的操作。")
            return
        reverse_moves = [(destination, source) for source, destination in self.last_moves]
        moving_keys = {
            os.path.normcase(str(current.resolve())) for current, _original in reverse_moves
        }
        for current, original in reverse_moves:
            if not current.exists():
                messagebox.showerror("无法撤销", f"找不到文件：\n{current}")
                return
            original_key = os.path.normcase(str(original.resolve()))
            if original.exists() and original_key not in moving_keys:
                messagebox.showerror("无法撤销", f"原文件名已被占用：\n{original}")
                return
        try:
            transactional_move(reverse_moves)
        except OSError as error:
            messagebox.showerror("撤销失败", str(error))
            return
        move_map = {destination: source for source, destination in self.last_moves}
        self.files = [move_map.get(path, path) for path in self.files]
        self.last_moves = []
        self.refresh_preview()


if __name__ == "__main__":
    enable_windows_dpi_awareness()
    BatchRenamer().mainloop()
