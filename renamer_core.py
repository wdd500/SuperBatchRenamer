from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Iterable
import base64
import hashlib
import os
from pathlib import Path, PurePath
import random
import re
import string
from urllib.parse import quote
import uuid


@dataclass
class RenameOptions:
    operation: str = "general"
    mode: str = "filename"
    number_start: int = 0
    number_step: int = 1
    number_width: int = 1
    name_prefix: str = ""
    name_base: str = ""
    name_suffix: str = ""
    extension_prefix: str = ""
    extension_base: str = ""
    extension_suffix: str = ""
    scope: str = "filename"
    search_text: str = ""
    replacement_text: str = ""
    delete_match: bool = False
    inserted_text: str = ""
    insert_position: str = "prefix"
    insert_index: int = 0
    case_mode: str = "upper"
    character_start: int = 1
    character_count: int = 1
    character_action: str = "random"
    character_random_width: int = 1
    character_number_width: int = 1
    fixed_characters: str = ""
    encoding_format: str = "utf-8-hex"


def _number(options: RenameOptions, index: int) -> str:
    value = options.number_start + index * options.number_step
    return str(value).zfill(max(1, options.number_width))


def _build_part(
    current: str,
    prefix: str,
    base: str,
    suffix: str,
    options: RenameOptions,
    index: int,
    numbered: bool = True,
) -> str:
    if not (prefix or base or suffix):
        return current
    middle = base if base else current
    serial = _number(options, index) if base and numbered else ""
    return f"{prefix}{middle}{serial}{suffix}"


def _transform_case(value: str, case_mode: str) -> str:
    if case_mode == "upper":
        return value.upper()
    if case_mode == "lower":
        return value.lower()
    if case_mode == "title":
        return value.title()
    if case_mode == "swap":
        return value.swapcase()
    return value


def _insert(value: str, text: str, position: str, index: int) -> str:
    if not text:
        return value
    if position == "suffix":
        return value + text
    if position == "index":
        point = max(0, min(index, len(value)))
        return value[:point] + text + value[point:]
    return text + value


def _edit_part(value: str, options: RenameOptions, index: int) -> str:
    operation = options.operation
    if operation == "replace":
        if not options.search_text:
            return value
        replacement = "" if options.delete_match else options.replacement_text
        return value.replace(options.search_text, replacement)
    if operation == "delete_range":
        start = options.character_start
        count = options.character_count
        if start < 1:
            raise ValueError("起始位置必须大于或等于 1")
        if count < 1:
            raise ValueError("字符数必须大于或等于 1")
        if start > len(value):
            raise ValueError(f"起始位置超出名称长度（当前 {len(value)} 个字符）")
        begin = start - 1
        return value[:begin] + value[min(begin + count, len(value)):]
    if operation == "insert":
        return _insert(
            value,
            options.inserted_text,
            options.insert_position,
            options.insert_index,
        )
    if operation == "case":
        return _transform_case(value, options.case_mode)
    if operation == "character":
        return _edit_character_range(value, options, index)
    if operation == "encode":
        return _encode_text(value, options.encoding_format)
    return value


def _encode_text(value: str, encoding_format: str) -> str:
    if encoding_format == "utf-8-hex":
        return value.encode("utf-8").hex().upper()
    if encoding_format == "gbk-hex":
        return value.encode("gbk").hex().upper()
    if encoding_format == "url":
        return quote(value, safe="", encoding="utf-8", errors="strict")
    if encoding_format == "base64":
        return base64.b64encode(value.encode("utf-8")).decode("ascii")
    if encoding_format == "unicode":
        return value.encode("unicode_escape").decode("ascii")
    raise ValueError(f"不支持的编码格式：{encoding_format}")


def _edit_character_range(value: str, options: RenameOptions, index: int) -> str:
    start = options.character_start
    count = options.character_count
    if start < 1:
        raise ValueError("起始位置必须大于或等于 1")
    if count < 1:
        raise ValueError("字符数必须大于或等于 1")
    if start > len(value):
        raise ValueError(f"起始位置超出名称长度（当前 {len(value)} 个字符）")

    begin = start - 1
    end = min(begin + count, len(value))
    selected = value[begin:end]

    if options.character_action == "fixed":
        if not options.fixed_characters:
            raise ValueError("请填写要替换为的固定字符")
        replacement_text = options.fixed_characters
    elif options.character_action == "random":
        seed = hashlib.sha256(
            f"{value}\0{index}\0{start}\0{count}\0{options.character_random_width}".encode(
                "utf-8"
            )
        ).digest()
        generator = random.Random(seed)
        replacement_text = "".join(
            generator.choices(
                string.ascii_letters,
                k=max(1, min(options.character_random_width, 12)),
            )
        )
    elif options.character_action == "encode":
        replacement_text = _encode_text(selected, options.encoding_format)
    elif options.character_action == "number":
        replacement_text = str(index + 1).zfill(
            max(1, min(options.character_number_width, 12))
        )
    else:
        raise ValueError(f"不支持的字符处理方式：{options.character_action}")

    return value[:begin] + replacement_text + value[end:]


def generate_unique_random_characters(
    names: Iterable[str], options: RenameOptions
) -> list[str]:
    """Generate stable, distinct random-letter strings for the current batch."""
    names = list(names)
    width = options.character_random_width
    if width < 1 or width > 12:
        raise ValueError("随机字符位数必须在 1 到 12 之间")
    max_unique = 26**width
    if len(names) > max_unique:
        raise ValueError(
            f"{width} 位随机英文字母最多只能生成 "
            f"{max_unique} 个不重复编号（忽略大小写）"
        )

    seed_data = repr(
        (
            names,
            options.character_start,
            options.character_count,
            options.scope,
            width,
        )
    ).encode("utf-8")
    generator = random.Random(hashlib.sha256(seed_data).digest())
    generated: list[str] = []
    used: set[str] = set()
    while len(generated) < len(names):
        candidate = "".join(
            generator.choices(string.ascii_letters, k=width)
        )
        normalized = candidate.casefold()
        if normalized not in used:
            used.add(normalized)
            generated.append(candidate)
    return generated


def make_filename(filename: str, options: RenameOptions, index: int = 0) -> str:
    """Return the preview name without touching the filesystem."""
    stem, extension = PurePath(filename).stem, PurePath(filename).suffix
    extension = extension[1:] if extension.startswith(".") else extension

    if options.operation == "general":
        if options.mode in ("filename", "all"):
            stem = _build_part(
                stem,
                options.name_prefix,
                options.name_base,
                options.name_suffix,
                options,
                index,
            )
        if options.mode in ("extension", "all"):
            extension = _build_part(
                extension,
                options.extension_prefix,
                options.extension_base.lstrip("."),
                options.extension_suffix,
                options,
                index,
                numbered=False,
            )
    elif options.scope == "all":
        whole = _edit_part(filename, options, index)
        return whole
    elif options.scope == "extension":
        extension = _edit_part(extension, options, index)
    else:
        stem = _edit_part(stem, options, index)

    return f"{stem}.{extension}" if extension else stem


def make_folder_name(folder_name: str, options: RenameOptions, index: int = 0) -> str:
    """Apply rename rules to a folder's complete leaf name."""
    if options.operation == "general":
        return _build_part(
            folder_name,
            options.name_prefix,
            options.name_base,
            options.name_suffix,
            options,
            index,
        )
    return make_filename(
        folder_name,
        replace(options, scope="all"),
        index,
    )


def collect_dropped_paths(
    paths: Iterable[str | Path],
    target_kind: str,
    recursive: bool = False,
) -> list[Path]:
    """Convert dropped files/folders to the rename targets for the current mode."""
    if target_kind not in ("file", "folder"):
        raise ValueError(f"Unsupported drop target: {target_kind}")

    collected: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = os.path.normcase(str(path.resolve()))
        if key not in seen:
            collected.append(path)
            seen.add(key)

    for raw_path in paths:
        path = Path(raw_path)
        if target_kind == "folder":
            if path.is_dir() and not path.is_symlink():
                add(path)
        elif path.is_file():
            add(path)
        elif path.is_dir() and not path.is_symlink():
            candidates = path.rglob("*") if recursive else path.iterdir()
            for candidate in candidates:
                if candidate.is_file():
                    add(candidate)

    return collected


_INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def filename_problem(filename: str) -> str | None:
    """Explain why a leaf name cannot be safely created on Windows."""
    if not filename:
        return "文件名不能为空"
    if filename in (".", ".."):
        return "不能使用 . 或 .. 作为文件名"
    if _INVALID_WINDOWS_CHARS.search(filename):
        return "文件名包含 Windows 不允许的字符"
    if filename.endswith((" ", ".")):
        return "文件名不能以空格或句点结尾"
    device_name = filename.split(".", 1)[0].upper()
    if device_name in _RESERVED_WINDOWS_NAMES:
        return "文件名是 Windows 保留设备名"
    return None


def transactional_move(moves: list[tuple[Path, Path]]) -> None:
    """Move a batch through unique sibling names, restoring sources on failure."""
    source_keys = {os.path.normcase(str(source.resolve())) for source, _ in moves}
    destination_keys = [
        os.path.normcase(str(destination.resolve())) for _, destination in moves
    ]
    if len(destination_keys) != len(set(destination_keys)):
        raise FileExistsError("多个文件将重命名为同一目标")
    for _source, destination in moves:
        destination_key = os.path.normcase(str(destination.resolve()))
        if destination.exists() and destination_key not in source_keys:
            raise FileExistsError(f"目标文件已存在：{destination}")

    token = uuid.uuid4().hex
    staged: list[tuple[Path, Path, Path]] = []
    try:
        for number, (source, destination) in enumerate(moves):
            temporary = source.with_name(f".renamer-{token}-{number}.tmp")
            source.rename(temporary)
            staged.append((source, temporary, destination))
    except OSError as error:
        rollback_errors = []
        for source, temporary, _destination in reversed(staged):
            if temporary.exists():
                try:
                    temporary.rename(source)
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
        detail = f"重命名未完成：{error}"
        if rollback_errors:
            detail += "\n回滚时发生错误：" + "；".join(rollback_errors)
        raise OSError(detail) from error

    completed: list[tuple[Path, Path, Path]] = []
    try:
        for entry in staged:
            _source, temporary, destination = entry
            temporary.rename(destination)
            completed.append(entry)
    except OSError as error:
        rollback_errors = []
        for _source, temporary, destination in reversed(completed):
            try:
                destination.rename(temporary)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        for source, temporary, _destination in reversed(staged):
            if temporary.exists():
                try:
                    temporary.rename(source)
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
        detail = f"重命名未完成：{error}"
        if rollback_errors:
            detail += "\n回滚时发生错误：" + "；".join(rollback_errors)
        raise OSError(detail) from error
