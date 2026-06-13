from __future__ import annotations

import unittest

from product_writer.cleaner import clean_model_output


class ParagraphSplittingTests(unittest.TestCase):
    def test_consecutive_bold_points_become_separate_paragraphs(self) -> None:
        source = (
            "**选购时，配料表是重要判断标准。**后面是配料说明。"
            "**奶源地生态逻辑也不能忽略。**后面是奶源说明。"
            "**根据饮用人群选择产品类型很重要。**后面是人群说明。"
        )

        cleaned = clean_model_output(source)

        self.assertEqual(
            cleaned.splitlines(),
            [
                "**选购时，配料表是重要判断标准。**后面是配料说明。",
                "**奶源地生态逻辑也不能忽略。**后面是奶源说明。",
                "**根据饮用人群选择产品类型很重要。**后面是人群说明。",
            ],
        )

    def test_inline_bold_keyword_does_not_force_a_paragraph(self) -> None:
        source = "查看配料表中的**生驼乳**含量，再结合营养成分判断。"

        self.assertEqual(clean_model_output(source), source)

    def test_leading_and_trailing_line_spaces_are_removed(self) -> None:
        source = "  一、选购建议  \n　正文内容。 "

        self.assertEqual(
            clean_model_output(source),
            "一、选购建议\n正文内容。",
        )


if __name__ == "__main__":
    unittest.main()
