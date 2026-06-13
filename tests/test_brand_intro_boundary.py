from __future__ import annotations

import unittest

from product_writer.quality import brand_mentions_before_recommendations_warnings


class BrandIntroBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "brand_whitelist": [
                {
                    "brand": "仙芳思",
                    "product_name": "仙芳思胶原蛋白肽饮",
                },
                {
                    "brand": "赤大师",
                    "product_name": "赤大师胶原蛋白肽饮",
                },
            ]
        }

    def test_brand_before_first_recommendation_is_rejected(self) -> None:
        text = (
            "先讲通用选择方法。\n"
            "仙芳思的配方数据可以作为例子。\n"
            "推荐一：仙芳思胶原蛋白肽饮\n"
            "这里开始正式介绍产品。"
        )

        warnings = brand_mentions_before_recommendations_warnings(text, self.config)

        self.assertEqual(len(warnings), 1)
        self.assertIn("仙芳思", warnings[0])

    def test_brands_inside_recommendation_section_are_allowed(self) -> None:
        text = (
            "先讲通用选择方法和饮用安排。\n"
            "推荐一：仙芳思胶原蛋白肽饮\n"
            "仙芳思的配方数据从这里开始展开。\n"
            "推荐二：赤大师胶原蛋白肽饮\n"
            "赤大师的产品资料从这里开始展开。"
        )

        self.assertEqual(
            brand_mentions_before_recommendations_warnings(text, self.config),
            [],
        )


if __name__ == "__main__":
    unittest.main()
