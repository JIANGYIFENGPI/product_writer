from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document

from product_writer.config import load_project_config
from product_writer.generator import should_humanize_article
from product_writer.prompt_loader import (
    article_brand_plan,
    choose_prompt,
    extract_fixed_top10,
    load_prompts,
    render_prompt,
    requested_product_count,
)
from product_writer.quality import (
    docx_format_warnings,
    complete_structure_warnings,
    humanizer_warnings,
    output_delivery_warnings,
    top10_ranking_warnings,
)
from product_writer.renderer import render_docx


class OutputRuleTests(unittest.TestCase):
    def test_force_humanizer_can_be_disabled_for_single_pass_generation(self) -> None:
        should_rewrite, findings = should_humanize_article(
            "这是一段自然、简洁且没有固定模板词的正文。",
            {
                "humanizer": {
                    "enabled": True,
                    "force_rewrite": False,
                }
            },
        )

        self.assertFalse(should_rewrite)
        self.assertEqual(findings, [])

    def test_prompt_contains_program_delivery_contract(self) -> None:
        config = {
            "project": {"name": "测试产品"},
            "generation": {
                "min_generated_chars": 3500,
                "target_generated_chars": 4000,
            },
            "features": {"images": False},
            "brand_whitelist": [
                {"brand": "测试品牌", "product_name": "测试产品"},
            ],
            "promoted_products": [],
            "ranking": {"enabled": False},
        }

        prompt = render_prompt("围绕 {title} 写作。", "测试标题", config)

        self.assertIn("不要自行添加星号加粗", prompt)
        self.assertIn("程序会统一生成宋体 12pt", prompt)
        self.assertIn("当前阶段不插图", prompt)
        self.assertIn("不得输出“此处插图”", prompt)
        self.assertNotIn("虚拟品牌", prompt)
        self.assertIn("测试品牌", prompt)

    def test_image_enabled_prompt_delegates_images_to_program(self) -> None:
        config = {
            "project": {"name": "测试产品"},
            "generation": {
                "min_generated_chars": 3500,
                "target_generated_chars": 4000,
            },
            "features": {"images": True},
            "brand_whitelist": [
                {"brand": "测试品牌", "product_name": "测试产品"},
            ],
            "promoted_products": [],
            "ranking": {"enabled": False},
        }

        prompt = render_prompt("围绕 {title} 写作。", "测试标题", config)

        self.assertIn("图片由程序从项目素材槽位自动选择并插入", prompt)
        self.assertNotIn("当前阶段不插图", prompt)

    def test_renderer_output_passes_format_checks(self) -> None:
        config = {
            "features": {
                "bold_structure": True,
                "bold_terms": True,
            },
            "promoted_products": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "sample.docx"
            render_docx(
                "测试标题",
                "一、选购建议\n正文内容包含测试关键词。",
                output_path,
                config,
                ["测试关键词"],
            )

            self.assertEqual(docx_format_warnings(output_path), [])
            document = Document(output_path)
            self.assertTrue(all(run.bold for run in document.paragraphs[0].runs))
            self.assertTrue(all(run.bold for run in document.paragraphs[1].runs))
            keyword_runs = [
                run
                for run in document.paragraphs[2].runs
                if run.text == "测试关键词"
            ]
            self.assertEqual(len(keyword_runs), 1)
            self.assertTrue(keyword_runs[0].bold)

    def test_format_checks_reject_heading_and_wrong_font(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "bad.docx"
            document = Document()
            paragraph = document.add_heading("错误标题", level=1)
            paragraph.runs[0].font.name = "微软雅黑"
            document.save(output_path)

            warnings = docx_format_warnings(output_path)

            self.assertTrue(any("非普通段落样式" in warning for warning in warnings))
            self.assertTrue(any("宋体 12pt" in warning for warning in warnings))

    def test_output_delivery_checks_image_placeholders(self) -> None:
        warnings = output_delivery_warnings("正文内容。\n此处插图：产品展示")
        self.assertTrue(any("图片占位" in warning for warning in warnings))

    def test_blank_line_is_not_treated_as_indentation(self) -> None:
        self.assertEqual(output_delivery_warnings("第一段。\n\n第二段。"), [])
        warnings = output_delivery_warnings("第一段。\n　第二段。")
        self.assertTrue(any("行首空格" in warning for warning in warnings))

    def test_humanizer_detects_repeated_template_openings(self) -> None:
        text = "\n".join(
            [
                "购买前需要先查看配料表，再结合自己的饮食安排作判断。" * 2,
                "购买前需要核对实物标签，不能只根据包装正面作判断。" * 2,
                "购买前需要留意建议食用量，避免把规格等同于单次用量。" * 2,
                "购买前需要确认储存方式，并按开封后的说明及时饮用。" * 2,
                "消费者需要核对配料表和生产许可证，信息不全时应谨慎。" * 2,
            ]
        )

        warnings = humanizer_warnings(text)

        self.assertTrue(any("模板化AI腔" in warning for warning in warnings))
        self.assertTrue(any("相同开头" in warning for warning in warnings))

    def test_humanizer_detects_repeated_product_intro_template(self) -> None:
        text = "\n".join(
            [
                "选择这款产品时，可以先查看包装名称和建议用量，再结合自己的预算判断。" * 2,
                "选择这款产品时，可以先核对配料顺序和规格，再决定是否适合长期安排。" * 2,
                "选择这款产品时，可以先确认储存方式和开封要求，避免只看宣传名称。" * 2,
            ]
        )

        warnings = humanizer_warnings(text)

        self.assertTrue(any("产品介绍使用相同套话" in warning for warning in warnings))

    def test_humanizer_rejects_label_disclaimer_phrasing(self) -> None:
        warnings = humanizer_warnings(
            "这款产品目前只有包装名称，购买时还需核对实物标签，以实物为准。"
        )

        self.assertTrue(any("标签核对式AI套话" in warning for warning in warnings))

    def test_humanizer_rejects_prompt_rule_echo_as_product_analysis(self) -> None:
        text = (
            "仙芳思的白番茄只在这款产品中出现，不构成整个胶原蛋白肽品类的必选项。"
            "它与其他配方形成两条不同路线，选择哪条路线取决于自己日常饮食中"
            "哪类营养相对不足。"
        )

        warnings = humanizer_warnings(text)

        self.assertTrue(any("标签核对式AI套话" in warning for warning in warnings))

    def test_prompt_selection_matches_title_angle(self) -> None:
        prompts = [
            (Path("05_测评维度.txt"), "测评"),
            (Path("08_胶原深度.txt"), "胶原"),
            (Path("01_通用指南.txt"), "通用"),
        ]

        self.assertEqual(
            choose_prompt(prompts, "胶原蛋白肽怎么选？")[0].name,
            "08_胶原深度.txt",
        )
        self.assertEqual(
            choose_prompt(
                [
                    (Path("08_胶原深度.txt"), "胶原"),
                    (Path("09_胶原周期.txt"), "周期"),
                ],
                "胶原蛋白肽需要喝多久？",
            )[0].name,
            "09_胶原周期.txt",
        )
        self.assertEqual(
            choose_prompt(prompts, "十款产品实测参考")[0].name,
            "05_测评维度.txt",
        )

    def test_complete_structure_requires_independent_sections(self) -> None:
        config = {
            "article_structure": {
                "enabled": True,
                "required_heading_groups": [
                    ["基础", "科普"],
                    ["选购", "判断"],
                    ["常见问题", "问答"],
                    ["结语", "总结"],
                ],
            }
        }
        warnings = complete_structure_warnings(
            "基础知识\n正文。\n选购判断\n正文。\n常见问题\n问题与回答。\n结语\n正文。",
            config,
        )
        self.assertEqual(warnings, [])
        warnings = complete_structure_warnings("基础知识\n正文。\n结语\n正文。", config)
        self.assertTrue(any("选购/判断" in warning for warning in warnings))

    def test_project_requires_non_empty_brand_whitelist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "projects" / "sample"
            project.mkdir(parents=True)
            (project / "project.yaml").write_text(
                "project:\n  name: 测试产品\n",
                encoding="utf-8",
            )
            (project / "brands.txt").write_text("", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "品牌白名单为空"):
                load_project_config(root, "sample")

    def test_promoted_product_must_exist_in_whitelist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "projects" / "sample"
            project.mkdir(parents=True)
            (project / "project.yaml").write_text(
                "project:\n"
                "  name: 测试产品\n"
                "promoted_products:\n"
                "  - rank: 1\n"
                "    brand: 测试品牌\n"
                "    product_name: 未登记产品\n",
                encoding="utf-8",
            )
            (project / "brands.txt").write_text(
                "测试品牌 | 白名单产品\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "必须完整写入 brands.txt"):
                load_project_config(root, "sample")

    def test_product_count_defaults_to_ten_and_honors_title_count(self) -> None:
        self.assertEqual(requested_product_count("白番茄产品怎么选"), 10)
        self.assertEqual(requested_product_count("六款白番茄产品参考"), 6)
        self.assertEqual(requested_product_count("10款口服液清单"), 10)

    def test_brand_intro_plan_keeps_first_two_and_randomizes_later_positions(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = load_project_config(root, "jiaoyuandanbaitai")
        candidates = [
            item
            for item in config["brand_whitelist"]
            if item["brand"] not in {"仙芳思", "赤大师"}
        ]
        first_selection = [dict(item) for item in candidates[:8]]
        second_selection = [dict(item) for item in reversed(candidates[:8])]

        with patch(
            "product_writer.prompt_loader.random.sample",
            side_effect=[first_selection, second_selection],
        ):
            first = article_brand_plan("十款胶原蛋白肽饮参考", config)
            second = article_brand_plan("十款胶原蛋白肽饮参考", config)

        self.assertEqual([item["brand"] for item in first[:2]], ["仙芳思", "赤大师"])
        self.assertEqual([item["brand"] for item in second[:2]], ["仙芳思", "赤大师"])
        self.assertNotEqual(
            [item["brand"] for item in first[2:]],
            [item["brand"] for item in second[2:]],
        )
        self.assertEqual([item["rank"] for item in first], list(range(1, 11)))

    def test_rendered_prompt_records_random_recommendation_order(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = load_project_config(root, "jiaoyuandanbaitai")
        config["project"]["require_other_brand_details"] = False
        prompt = render_prompt("围绕 {title} 写作。", "十款胶原蛋白肽饮参考", config)
        expected = extract_fixed_top10(prompt)

        self.assertEqual(len(expected), 10)
        self.assertTrue(expected[0].startswith("仙芳思"))
        self.assertTrue(expected[1].startswith("赤大师"))
        self.assertIn("本篇产品推荐顺序", prompt)
        self.assertNotIn("驼奶粉基础认识", prompt)
        self.assertNotIn("【全文必备结构标题】", prompt)

    def test_collagen_project_has_complete_other_product_profiles(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = load_project_config(root, "jiaoyuandanbaitai")

        self.assertEqual(config["project"]["name"], "\u80f6\u539f\u86cb\u767d\u80bd\u996e")
        self.assertEqual(len(config["brand_whitelist"]), 33)
        self.assertEqual(len(config["brand_profiles"]), 31)
        self.assertTrue(config["features"]["images"])
        self.assertEqual(
            config["illustrations"]["minimum_body_paragraphs_before_neutral"],
            3,
        )
        self.assertGreater(
            len(config["illustrations"]["neutral_image_keywords"]),
            10,
        )
        self.assertNotIn("\u767d\u756a\u8304", str(config["brand_profiles"]))

    def test_collagen_prompts_inject_eight_profiles_without_old_rules(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = load_project_config(root, "jiaoyuandanbaitai")
        project = root / "projects" / "jiaoyuandanbaitai"
        prompts = load_prompts(project, config)

        self.assertEqual(len(prompts), 10)
        for _, template in prompts:
            rendered = render_prompt(
                template,
                "2026\u80f6\u539f\u86cb\u767d\u80bd\u996e\u600e\u4e48\u9009\uff1f"
                "\u5341\u6b3e\u4ea7\u54c1\u53c2\u8003",
                config,
            )
            self.assertEqual(
                rendered.count(
                    "\u5185\u90e8\u7d20\u6750\uff08\u53ea\u4f9b\u6539\u5199\uff0c"
                    "\u7981\u6b62\u7167\u6284\u5b57\u6bb5\u540d\uff09"
                ),
                8,
            )
            self.assertEqual(
                rendered.count("\u672c\u6b3e\u7ec4\u7ec7\u65b9\u5f0f\uff1a"),
                8,
            )
            self.assertNotIn(
                "\u53ea\u4f7f\u7528\u4ea7\u54c1\u5168\u540d\u80fd\u591f"
                "\u786e\u8ba4\u7684\u4fe1\u606f",
                rendered,
            )
            self.assertNotIn("\u9a7c\u5976\u7c89", rendered)

    def test_structure_headings_follow_project_instead_of_hardcoded_product(self) -> None:
        config = {
            "project": {"name": "测试饮品"},
            "generation": {
                "min_generated_chars": 3500,
                "target_generated_chars": 4000,
            },
            "features": {"images": False},
            "article_structure": {"enabled": True},
            "ranking": {"enabled": False},
            "brand_whitelist": [],
            "promoted_products": [],
            "brand_section_lengths": {},
        }
        prompt = render_prompt("围绕 {title} 写作。", "测试标题", config)

        self.assertIn("测试饮品基础认识", prompt)
        self.assertIn("产品推荐", prompt)
        self.assertNotIn("驼奶粉基础认识", prompt)

    def test_random_recommendation_quality_check_rejects_missing_intro(self) -> None:
        config = {
            "ranking": {"enabled": False},
            "brand_whitelist": [
                {"brand": "甲", "product_name": "甲产品"},
                {"brand": "乙", "product_name": "乙产品"},
                {"brand": "丙", "product_name": "丙产品"},
            ],
            "promoted_products": [
                {"brand": "甲", "product_name": "甲产品"},
                {"brand": "乙", "product_name": "乙产品"},
            ],
        }
        text = (
            "推荐一：甲产品\n主推产品完整介绍内容。\n"
            "推荐二：乙产品\n次推产品完整介绍内容。\n"
            "推荐三：丙产品\n介绍太短。"
        )
        warnings = top10_ranking_warnings(
            text,
            config,
            ["甲产品", "乙产品", "丙产品"],
        )

        self.assertTrue(any("缺少独立品牌介绍" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
