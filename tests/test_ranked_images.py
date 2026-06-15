from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from docx import Document

from product_writer.image_assets import (
    ArticleImages,
    cover_image_context,
    configured_image_slots,
    load_image_slots,
    select_article_slot_images,
)
from product_writer.prompt_loader import config_with_prompt_promoted_order
from product_writer.quality import docx_illustration_warnings
from product_writer.renderer import (
    find_detail_image_anchors,
    neutral_image_anchor,
    render_docx,
)


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

    def test_global_cover_uses_section_boundary_position(self) -> None:
        image = Path("neutral_dry_skin.png")
        config = {
            "illustrations": {
                "neutral_placement_strategy": "section_boundary_with_spacing",
                "minimum_body_paragraphs_between_images": 3,
                "minimum_body_paragraphs_before_neutral": 2,
                "neutral_body_paragraph_min_chars": 80,
                "neutral_image_keywords": {
                    image.name: ["干燥", "缺水"],
                },
            }
        }
        blocks = [
            "开场内容较长，主要讨论日常选择时容易忽略的标签和规格问题。" * 4,
            "换季后皮肤干燥、缺水和紧绷更明显，可以先梳理饮食与日常习惯。" * 4,
            "配方与标签怎么看",
            "配料信息需要逐项核对，不能只看包装正面的宣传名称。" * 4,
            "长期饮用还要结合每盒数量、建议用量和预算安排。" * 4,
            "饮用安排",
            "储存方式与每日建议量需要结合包装说明判断。" * 4,
            "预算安排要换算成每日成本，避免只比较单盒价格。" * 4,
            "推荐一：测试产品",
        ]

        self.assertEqual(
            neutral_image_anchor(blocks, 8, config, image),
            ("after", 1),
        )

    def test_configured_cover_is_delayed_until_third_complete_paragraph(self) -> None:
        blocks = [
            "第一段完整正文，介绍消费者在选择口服液时常遇到的配方与规格问题。" * 4,
            "第二段完整正文，说明核心成分含量和每日摄入信息应该结合查看。" * 4,
            "第三段完整正文，补充生产信息、储存条件和长期成本的判断方法。" * 4,
            "推荐一：测试产品",
        ]
        config = {
            "illustrations": {
                "neutral_placement_strategy": "fixed_body_count",
                "cover_after_body_paragraphs": 3,
                "cover_body_paragraph_min_chars": 80,
            }
        }

        self.assertEqual(
            neutral_image_anchor(blocks, 3, config),
            ("after", 2),
        )

    def test_cover_image_matching_only_uses_configured_opening_paragraphs(self) -> None:
        content = (
            "开场短句。\n"
            + (
                "这一整段主要讨论换季干燥和缺水时怎样查看产品配料，"
                "同时说明日常饮用安排和规格信息需要结合起来判断。"
            )
            * 2
            + "\n推荐一：测试产品\n后文大量讨论白番茄成分。"
        )

        context = cover_image_context(content, paragraph_count=3)

        self.assertIn("换季干燥", context)
        self.assertNotIn("推荐一", context)
        self.assertNotIn("白番茄成分", context)

    def test_promoted_product_can_select_two_distinct_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            neutral = root / "neutral.png"
            first_a = root / "first_a.png"
            first_b = root / "first_b.png"
            second = root / "second.png"
            for image in (neutral, first_a, first_b, second):
                image.write_bytes(b"test")
            config = {
                "illustrations": {
                    "neutral_slot": "neutral",
                    "extra_images_by_promoted_rank": {1: 1},
                },
                "promoted_products": [
                    {"rank": 1, "image_slot": "first"},
                    {"rank": 2, "image_slot": "second"},
                ],
            }

            selected = select_article_slot_images(
                {
                    "neutral": [neutral],
                    "first": [first_a, first_b],
                    "second": [second],
                },
                "两张主推图测试",
                config,
            )

            self.assertEqual(len(selected.extra_by_rank[1]), 1)
            self.assertNotEqual(selected.by_rank[1], selected.extra_by_rank[1][0])

    def test_rendered_docx_places_delayed_cover_and_two_rank_one_images(self) -> None:
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
            "AAAAC0lEQVR42mP8/x8AAusB9Y9Zl9sAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = [root / f"image_{index}.png" for index in range(4)]
            for path in paths:
                path.write_bytes(png)
            output = root / "layout.docx"
            config = {
                "features": {
                    "images": True,
                    "bold_structure": True,
                    "bold_terms": True,
                },
                "illustrations": {
                    "promoted_ranks": [1, 2],
                    "extra_images_by_promoted_rank": {1: 1},
                    "required_count": 4,
                    "cover_after_body_paragraphs": 3,
                    "cover_body_paragraph_min_chars": 80,
                    "minimum_body_paragraphs_between_images": 2,
                    "validate_positions": True,
                },
                "promoted_products": [
                    {
                        "rank": 1,
                        "brand": "仙芳思",
                        "product_name": "仙芳思白番茄烟酰胺胶原蛋白肽饮",
                    },
                    {
                        "rank": 2,
                        "brand": "赤大师",
                        "product_name": "赤大师不老莓PQQ鲟鱼子酱胶原蛋白肽饮",
                    },
                ],
            }
            opening = [
                f"第{index}段正文介绍配方、规格、生产信息、储存条件和日常选择方法，"
                "用于形成完整开篇并让通用图远离标题位置。" * 4
                for index in range(1, 7)
            ]
            rank_one_body = (
                "配方与含量：这里详细说明仙芳思的配方、规格、生产和饮用信息，"
                "表达清楚直接，并达到一个完整正文段所需的长度。" * 4
            )
            rank_two_body = (
                "这里介绍赤大师对应的配方、规格和使用信息，不混用其他产品数据，"
                "并保持中等篇幅。" * 4
            )
            text = "\n".join(
                [
                    *opening,
                    "十款产品年度清单",
                    "推荐一：仙芳思白番茄烟酰胺胶原蛋白肽饮",
                    rank_one_body,
                    "生产与检测：继续补充生产许可、检测和储存安排。" * 5,
                    "推荐二：赤大师不老莓PQQ鲟鱼子酱胶原蛋白肽饮",
                    rank_two_body,
                ]
            )
            render_docx(
                "临时插图位置验证",
                text,
                output,
                config,
                [],
                ArticleImages(
                    neutral=paths[0],
                    by_rank={1: paths[1], 2: paths[3]},
                    extra_by_rank={1: [paths[2]]},
                ),
            )

            self.assertEqual(docx_illustration_warnings(output, config), [])
            document = Document(output)
            image_indices = [
                index
                for index, paragraph in enumerate(document.paragraphs)
                if paragraph._element.xpath(".//w:drawing | .//w:pict")
            ]
            self.assertEqual(len(image_indices), 4)

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
