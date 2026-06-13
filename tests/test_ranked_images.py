from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from product_writer.image_assets import (
    configured_image_slots,
    load_image_slots,
    select_article_slot_images,
)
from product_writer.prompt_loader import config_with_prompt_promoted_order
from product_writer.renderer import find_detail_image_anchors, neutral_image_anchor


class RankedImageTests(unittest.TestCase):
    def test_numbered_sections_are_not_treated_as_product_ranks(self) -> None:
        config = {
            "promoted_products": [
                {"rank": 1, "brand": "仙芳思"},
                {"rank": 2, "brand": "赤大师"},
            ]
        }
        blocks = [
            "一、年度关注点",
            "这里讨论行业变化和选购时需要注意的信息。" * 4,
            "二、品类与复配基础",
            "这里解释胶原蛋白肽饮的剂型和复配思路。" * 4,
            "推荐一：仙芳思胶原蛋白肽饮",
            "仙芳思的产品资料和配方细节在这里展开说明。" * 4,
            "推荐二：赤大师胶原蛋白肽饮",
            "赤大师的产品资料和配方细节在这里展开说明。" * 4,
        ]

        self.assertEqual(find_detail_image_anchors(blocks, config), {1: 4, 2: 6})

    def test_configured_promoted_ranks_can_omit_missing_slot(self) -> None:
        config = {
            "illustrations": {
                "neutral_slot": "neutral",
                "promoted_ranks": [1, 2],
            },
            "promoted_products": [
                {"rank": 1, "image_slot": "first"},
                {"rank": 2, "image_slot": "second"},
                {"rank": 3, "image_slot": "third"},
            ],
        }

        self.assertEqual(
            configured_image_slots(config),
            ["neutral", "first", "second"],
        )

    def test_product_image_follows_product_when_rank_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            slots = {}
            for slot in ("neutral", "chidashi", "dishesi", "liutuo"):
                image = root / slot / f"{slot}.png"
                image.parent.mkdir()
                image.write_bytes(b"test")
                slots[slot] = [image]

            config = {
                "illustrations": {"neutral_slot": "neutral"},
                "promoted_products": [
                    {"rank": 3, "brand": "赤大师", "image_slot": "chidashi"},
                    {"rank": 1, "brand": "迪奢思", "image_slot": "dishesi"},
                    {"rank": 2, "brand": "六驼", "image_slot": "liutuo"},
                ],
            }

            selected = select_article_slot_images(slots, "换位测试", config)

            self.assertEqual(selected.by_rank[1].parent.name, "dishesi")
            self.assertEqual(selected.by_rank[2].parent.name, "liutuo")
            self.assertEqual(selected.by_rank[3].parent.name, "chidashi")
            self.assertEqual(
                configured_image_slots(config),
                ["neutral", "chidashi", "dishesi", "liutuo"],
            )

    def test_prompt_controls_promoted_order(self) -> None:
        config = {
            "ranking": {"promoted_order_source": "prompt"},
            "promoted_products": [
                {"rank": 1, "brand": "赤大师", "image_slot": "chidashi"},
                {"rank": 2, "brand": "迪奢思", "image_slot": "dishesi"},
                {"rank": 3, "brand": "六驼", "image_slot": "liutuo"},
            ],
        }
        prompt = """
        TOP1：迪奢思有机纯驼乳粉
        推荐二：六驼儿童成长配方骆驼奶粉
        第三名：赤大师有机纯驼奶粉
        """

        article_config = config_with_prompt_promoted_order(prompt, config)

        self.assertEqual(
            [(item["rank"], item["brand"]) for item in article_config["promoted_products"]],
            [(1, "迪奢思"), (2, "六驼"), (3, "赤大师")],
        )

    def test_neutral_image_matches_title_and_article_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ingredient = root / "neutral_ingredient.png"
            dry_skin = root / "neutral_dry_skin.png"
            ingredient.write_bytes(b"test")
            dry_skin.write_bytes(b"test")
            config = {
                "illustrations": {
                    "neutral_slot": "neutral",
                    "neutral_image_keywords": {
                        ingredient.name: ["白番茄", "成分"],
                        dry_skin.name: "[干燥, 缺水]",
                    },
                },
                "promoted_products": [],
            }

            selected = select_article_slot_images(
                {"neutral": [ingredient, dry_skin]},
                "换季干燥怎么补",
                config,
                "皮肤缺水时容易紧绷。",
            )

            self.assertEqual(selected.neutral, dry_skin)

    def test_neutral_image_is_anchored_after_matching_paragraph(self) -> None:
        image = Path("neutral_dry_skin.png")
        config = {
            "illustrations": {
                "semantic_neutral_anchor": True,
                "minimum_body_paragraphs_between_images": 2,
                "minimum_body_paragraphs_before_neutral": 2,
                "neutral_image_keywords": {
                    image.name: ["干燥", "缺水"],
                },
            }
        }
        blocks = [
            "开场内容较长，主要讨论日常选择时容易忽略的标签和规格问题。" * 2,
            "换季后皮肤干燥、缺水和紧绷更明显，可以先梳理饮食与日常习惯。" * 2,
            "配料信息需要逐项核对，不能只看包装正面的宣传名称。" * 2,
            "长期饮用还要结合每盒数量、建议用量和预算安排。" * 2,
            "推荐一：测试产品",
        ]

        self.assertEqual(
            neutral_image_anchor(blocks, 4, config, image),
            ("after", 1),
        )

    def test_neutral_allowlist_excludes_unapproved_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            neutral = project / "images" / "neutral"
            neutral.mkdir(parents=True)
            approved = neutral / "approved.png"
            excluded = neutral / "excluded.png"
            approved.write_bytes(b"test")
            excluded.write_bytes(b"test")
            config = {
                "project": {"images_dir": "images"},
                "features": {"images": True},
                "illustrations": {
                    "neutral_slot": "neutral",
                    "neutral_image_allowlist": [approved.name],
                    "promoted_ranks": [],
                },
                "promoted_products": [],
            }

            self.assertEqual(load_image_slots(project, config)["neutral"], [approved])


if __name__ == "__main__":
    unittest.main()
