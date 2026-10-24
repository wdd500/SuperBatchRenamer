import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from renamer_core import (
    RenameOptions,
    collect_dropped_paths,
    filename_problem,
    make_folder_name,
    make_filename,
    generate_unique_random_characters,
    transactional_move,
)


class MakeFilenameTests(unittest.TestCase):
    def test_general_filename_and_sequence(self):
        options = RenameOptions(
            name_prefix="img_",
            name_base="photo",
            name_suffix="_new",
            number_start=3,
            number_width=3,
        )
        self.assertEqual(make_filename("old.jpg", options, index=1), "img_photo004_new.jpg")

    def test_extension_replacement_preserves_dot(self):
        options = RenameOptions(
            mode="extension",
            extension_base=".png",
        )
        self.assertEqual(make_filename("photo.jpeg", options), "photo.png")

    def test_replace_and_delete_in_stem(self):
        options = RenameOptions(
            operation="replace",
            search_text="old",
            replacement_text="new",
        )
        self.assertEqual(make_filename("old-old.txt", options), "new-new.txt")
        options.delete_match = True
        self.assertEqual(make_filename("old-old.txt", options), "-.txt")

    def test_replace_page_deletes_selected_position_and_count(self):
        options = RenameOptions(
            operation="delete_range",
            character_start=3,
            character_count=4,
            scope="filename",
        )
        self.assertEqual(make_filename("abcdefghi.txt", options), "abghi.txt")
        options.scope = "extension"
        self.assertEqual(make_filename("abcdefghi.txt", options), "abcdefghi.tx")
        options.scope = "all"
        self.assertEqual(make_filename("abcdefghi.txt", options), "abghi.txt")

    def test_position_delete_rejects_out_of_range_start(self):
        options = RenameOptions(
            operation="delete_range",
            character_start=5,
            character_count=1,
        )
        with self.assertRaisesRegex(ValueError, "超出名称长度"):
            make_filename("abc.txt", options)

    def test_insert_at_character_position(self):
        options = RenameOptions(
            operation="insert",
            inserted_text="_x",
            insert_position="index",
            insert_index=2,
        )
        self.assertEqual(make_filename("abcd.txt", options), "ab_xcd.txt")

    def test_position_range_replaces_fixed_characters(self):
        options = RenameOptions(
            operation="character",
            character_start=2,
            character_count=3,
            character_action="fixed",
            fixed_characters="XYZ",
        )
        self.assertEqual(make_filename("abcdef.txt", options), "aXYZef.txt")

    def test_position_range_generates_repeatable_english_letters(self):
        options = RenameOptions(
            operation="character",
            character_start=2,
            character_count=5,
            character_action="random",
            character_random_width=5,
        )
        first = make_filename("before-after.txt", options, index=4)
        second = make_filename("before-after.txt", options, index=4)
        self.assertEqual(first, second)
        replacement = first.removesuffix("-after.txt").removeprefix("b")
        self.assertEqual(len(replacement), 5)
        self.assertTrue(replacement.isascii() and replacement.isalpha())

    def test_batch_random_character_strings_are_unique_and_repeatable(self):
        names = ["alpha.txt", "bravo.txt", "charlie.txt", "delta.txt"]
        options = RenameOptions(
            operation="character",
            character_start=2,
            character_count=2,
            character_action="random",
            character_random_width=3,
        )
        first = generate_unique_random_characters(names, options)
        second = generate_unique_random_characters(names, options)
        self.assertEqual(first, second)
        self.assertEqual(len(first), len({value.casefold() for value in first}))
        self.assertTrue(all(len(value) == 3 and value.isalpha() for value in first))

    def test_random_character_width_limits_batch_unique_codes(self):
        options = RenameOptions(character_random_width=1)
        with self.assertRaisesRegex(ValueError, "最多只能生成"):
            generate_unique_random_characters(
                [f"file-{index}" for index in range(27)], options
            )

    def test_position_range_generates_incrementing_padded_numbers(self):
        options = RenameOptions(
            operation="character",
            character_start=2,
            character_count=2,
            character_action="number",
            character_number_width=3,
        )
        self.assertEqual(
            make_filename("x__tail.txt", options, index=0), "x001tail.txt"
        )
        self.assertEqual(
            make_filename("x__tail.txt", options, index=1), "x002tail.txt"
        )
        self.assertEqual(
            make_filename("x__tail.txt", options, index=9), "x010tail.txt"
        )

    def test_position_range_generates_selected_encoding(self):
        options = RenameOptions(
            operation="encode",
            encoding_format="utf-8-hex",
        )
        self.assertEqual(make_filename("A中B.txt", options), "41E4B8AD42.txt")
        options.encoding_format = "url"
        self.assertEqual(
            make_filename("A中B.txt", options),
            "A%E4%B8%ADB.txt",
        )
        options.encoding_format = "base64"
        self.assertEqual(make_filename("A中B.txt", options), "QeS4rUI=.txt")

    def test_encoding_is_a_separate_operation(self):
        options = RenameOptions(
            operation="encode",
            encoding_format="base64",
        )
        self.assertEqual(make_filename("A中B.txt", options), "QeS4rUI=.txt")

    def test_encoding_respects_filename_extension_and_all_scopes(self):
        options = RenameOptions(operation="encode", encoding_format="base64")
        self.assertEqual(make_filename("ab.txt", options), "YWI=.txt")
        options.scope = "extension"
        self.assertEqual(make_filename("ab.txt", options), "ab.dHh0")
        options.scope = "all"
        self.assertEqual(make_filename("ab.txt", options), "YWIudHh0")

    def test_position_range_validates_position_and_fixed_value(self):
        options = RenameOptions(
            operation="character",
            character_start=5,
            character_count=1,
            character_action="fixed",
            fixed_characters="x",
        )
        with self.assertRaisesRegex(ValueError, "超出名称长度"):
            make_filename("abc.txt", options)
        options.character_start = 1
        options.fixed_characters = ""
        with self.assertRaisesRegex(ValueError, "固定字符"):
            make_filename("abc.txt", options)

    def test_case_conversion_can_target_extension(self):
        options = RenameOptions(
            operation="case",
            scope="extension",
            case_mode="upper",
        )
        self.assertEqual(make_filename("Photo.jpeg", options), "Photo.JPEG")

    def test_windows_reserved_names_and_invalid_chars(self):
        self.assertIsNotNone(filename_problem("CON.txt"))
        self.assertIsNotNone(filename_problem("bad?.txt"))
        self.assertIsNone(filename_problem("photo_01.txt"))

    def test_folder_rules_transform_the_whole_dotted_name(self):
        options = RenameOptions(
            name_prefix="Archive-",
            name_base="batch",
            name_suffix="-done",
            number_start=5,
            number_width=3,
        )
        self.assertEqual(
            make_folder_name("Project.v1", options, index=2),
            "Archive-batch007-done",
        )

    def test_folder_replace_operates_on_the_complete_name(self):
        options = RenameOptions(
            operation="replace",
            search_text="old",
            replacement_text="new",
            scope="extension",
        )
        self.assertEqual(
            make_folder_name("old.folder.old", options),
            "new.fnewer.new",
        )

    def test_drop_files_and_folders_in_file_mode(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "files to rename"
            source.mkdir()
            direct = source / "direct.txt"
            direct.write_text("direct", encoding="utf-8")
            nested = source / "nested"
            nested.mkdir()
            nested_file = nested / "nested.txt"
            nested_file.write_text("nested", encoding="utf-8")
            other = root / "single file.txt"
            other.write_text("single", encoding="utf-8")

            immediate = collect_dropped_paths([source, other], "file")
            self.assertEqual(immediate, [direct, other])
            recursive = collect_dropped_paths([source, other], "file", recursive=True)
            self.assertEqual(recursive, [direct, nested_file, other])

    def test_drop_directories_in_folder_mode(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "folder one"
            second = root / "folder two"
            first.mkdir()
            second.mkdir()
            file_path = root / "ordinary.txt"
            file_path.write_text("file", encoding="utf-8")

            dropped = collect_dropped_paths(
                [first, file_path, first, second], "folder"
            )
            self.assertEqual(dropped, [first, second])

    def test_transactional_move_supports_swaps_and_undo(self):
        with TemporaryDirectory() as directory:
            first = Path(directory, "a.txt")
            second = Path(directory, "b.txt")
            first.write_text("A", encoding="utf-8")
            second.write_text("B", encoding="utf-8")
            transactional_move([(first, second), (second, first)])
            self.assertEqual(first.read_text(encoding="utf-8"), "B")
            self.assertEqual(second.read_text(encoding="utf-8"), "A")
            transactional_move([(first, second), (second, first)])
            self.assertEqual(first.read_text(encoding="utf-8"), "A")
            self.assertEqual(second.read_text(encoding="utf-8"), "B")

    def test_transactional_move_never_overwrites_unselected_file(self):
        with TemporaryDirectory() as directory:
            source = Path(directory, "source.txt")
            occupied = Path(directory, "occupied.txt")
            source.write_text("source", encoding="utf-8")
            occupied.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                transactional_move([(source, occupied)])
            self.assertEqual(source.read_text(encoding="utf-8"), "source")
            self.assertEqual(occupied.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
