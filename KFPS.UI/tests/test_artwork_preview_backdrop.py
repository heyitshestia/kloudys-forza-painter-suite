from __future__ import annotations

import unittest
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
COMPONENTS = UI / "qml" / "components"
PAGES = UI / "qml" / "pages"


class ArtworkPreviewBackdropTests(unittest.TestCase):
    @staticmethod
    def _relative_luminance(hex_color: str) -> float:
        channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    @classmethod
    def _contrast(cls, first: str, second: str) -> float:
        bright, dark = sorted((cls._relative_luminance(first), cls._relative_luminance(second)), reverse=True)
        return (bright + 0.05) / (dark + 0.05)

    def test_backdrop_uses_one_cached_tiled_texture(self):
        asset = (UI / "assets" / "artwork-checker.svg").read_text(encoding="utf-8")
        component = (COMPONENTS / "ArtworkPreviewBackdrop.qml").read_text(encoding="utf-8")

        self.assertIn('viewBox="0 0 24 24"', asset)
        self.assertIn('fill="#8b8b8b"', asset)
        self.assertIn('fill="#626262"', asset)
        self.assertIn('source: assetRoot + "/artwork-checker.svg"', component)
        self.assertIn("fillMode: Image.Tile", component)
        self.assertIn("cache: true", component)
        self.assertNotIn("Repeater", component)
        self.assertNotIn("ShaderEffect", component)

    def test_each_checker_square_contrasts_with_white_and_black_artwork(self):
        for checker_color in ("#8b8b8b", "#626262"):
            self.assertGreaterEqual(self._contrast(checker_color, "#ffffff"), 3.0)
            self.assertGreaterEqual(self._contrast(checker_color, "#000000"), 3.0)

    def test_outputs_and_community_artwork_surfaces_use_the_backdrop(self):
        expected_counts = {
            PAGES / "JsonPage.qml": 2,
            PAGES / "CommunityPage.qml": 3,
            COMPONENTS / "CommunityArtworkCard.qml": 1,
            COMPONENTS / "CommunityUploadTile.qml": 1,
        }

        for path, expected in expected_counts.items():
            source = path.read_text(encoding="utf-8")
            self.assertEqual(
                source.count("ArtworkPreviewBackdrop {"),
                expected,
                f"Unexpected artwork backdrop coverage in {path.name}",
            )


if __name__ == "__main__":
    unittest.main()
