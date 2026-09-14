from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kfps_ui.community_tags import MAX_TAGS, SUGGESTED_TAGS, prepare_tags


class CommunityTagTests(unittest.TestCase):
    def test_bank_is_sorted_unique_and_valid(self):
        self.assertEqual(list(SUGGESTED_TAGS), sorted(set(SUGGESTED_TAGS)))
        for tag in SUGGESTED_TAGS:
            self.assertEqual(prepare_tags([], tag), {"tags": [tag], "error": ""})

    def test_custom_and_comma_paste(self):
        self.assertEqual(prepare_tags(["anime"], " racing, custom tag, , retro "),
                         {"tags": ["anime", "racing", "custom tag", "retro"], "error": ""})

    def test_duplicates_are_case_insensitive_and_keep_existing_spelling(self):
        self.assertEqual(prepare_tags(["Anime"], "ANIME, retro, RETRO"),
                         {"tags": ["Anime", "retro"], "error": ""})

    def test_unicode_and_punctuation_match_server_contract(self):
        for tag in ("\ud55c\uad6d\uc5b4", "\u65e5\u672c\u8a9e", "caf\u00e9", "a_b-c.d 1", "123", "\U00010400"):
            self.assertEqual(prepare_tags([], tag), {"tags": [tag], "error": ""})

    def test_invalid_characters_and_first_character(self):
        for tag in ("#anime", "_retro", "-racing", ".art", "a/b", "<tag>", "a\x00b", "a\nb", "a\tb",
                    "\U0001f600", "caf\u0065\u0301", "\ud800"):
            with self.subTest(tag=repr(tag)):
                self.assertTrue(prepare_tags([], tag)["error"])

    def test_24_character_boundary(self):
        self.assertFalse(prepare_tags([], "a" * 24)["error"])
        self.assertTrue(prepare_tags([], "a" * 25)["error"])

    def test_astral_character_length_uses_utf16_like_server(self):
        self.assertFalse(prepare_tags([], "\U00010400" * 12)["error"])
        self.assertTrue(prepare_tags([], "\U00010400" * 13)["error"])

    def test_ten_tag_limit_and_duplicate_at_capacity(self):
        tags = [f"tag{i}" for i in range(MAX_TAGS)]
        self.assertFalse(prepare_tags(tags[:-1], tags[-1])["error"])
        self.assertFalse(prepare_tags(tags, "TAG0")["error"])
        self.assertTrue(prepare_tags(tags, "extra")["error"])

    def test_failed_batch_never_partially_changes_selection_or_input(self):
        tags = ["anime"]
        self.assertEqual(prepare_tags(tags, "racing, #bad")["tags"], ["anime"])
        self.assertEqual(tags, ["anime"])
        self.assertEqual(prepare_tags(tags, ",".join(SUGGESTED_TAGS))["tags"], tags)

    def test_empty_or_commas_preserve_selection(self):
        for entered in ("", " ", ",, ,"):
            self.assertEqual(prepare_tags(["anime"], entered), {"tags": ["anime"], "error": ""})


if __name__ == "__main__":
    unittest.main()
