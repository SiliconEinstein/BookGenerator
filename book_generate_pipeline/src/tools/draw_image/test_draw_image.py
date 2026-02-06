import unittest

from draw_image.utils.markdown_tags import parse_image_blocks
from draw_image.insert.tag_inserter import insert_image_tags


class TestDrawImage(unittest.TestCase):
    def test_parse_image_blocks(self) -> None:
        markdown_text = (
            "正文一\n"
            "<image0>\n这里是上下文A\n</image0>\n"
            "正文二\n"
            "<image1>上下文B</image1>\n"
        )
        blocks = parse_image_blocks(markdown_text)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0][0], 0)
        self.assertIn("上下文A", blocks[0][1])
        self.assertEqual(blocks[1][0], 1)
        self.assertEqual(blocks[1][1], "上下文B")

    def test_insert_image_tags(self) -> None:
        markdown_text = "段落一\n段落二\n段落三"
        positions = [
            {"position": "段落二", "context": [1, 2]},
            {"position": "段落三", "context": [2, 3]},
        ]
        tagged, inserted = insert_image_tags(markdown_text, positions)
        self.assertEqual(len(inserted), 2)
        self.assertIn("![image_0.png](image_0.png)", tagged)
        self.assertIn("![image_1.png](image_1.png)", tagged)


if __name__ == "__main__":
    unittest.main()
