from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [
            item.strip().strip("'\"")
            for item in inner.split(",")
            if item.strip()
        ]
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _simple_yaml_load(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, result)]
    last_key_at_indent: dict[int, tuple[Any, str]] = {}

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if line.startswith("- "):
            item_text = line[2:].strip()
            if not isinstance(parent, list):
                grand_parent, key = last_key_at_indent[stack[-1][0]]
                new_list: list[Any] = []
                grand_parent[key] = new_list
                parent = new_list
                stack[-1] = (stack[-1][0], parent)
            if ":" in item_text:
                key, value = item_text.split(":", 1)
                item = {key.strip(): _parse_scalar(value) if value.strip() else {}}
                parent.append(item)
                stack.append((indent, item))
                if not value.strip():
                    last_key_at_indent[indent] = (item, key.strip())
            else:
                parent.append(_parse_scalar(item_text))
            continue

        key, value = line.split(":", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip()
        if value:
            parent[key] = _parse_scalar(value)
        else:
            parent[key] = {}
            stack.append((indent, parent[key]))
            last_key_at_indent[indent] = (parent, key)
    return result


def _safe_load_yaml(text: str) -> dict[str, Any]:
    if yaml is not None and hasattr(yaml, "safe_load"):
        return yaml.safe_load(text) or {}
    return _simple_yaml_load(text)


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _simple_yaml_dump(data: dict[str, Any], indent: int = 0) -> str:
    lines: list[str] = []
    prefix = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(_simple_yaml_dump(value, indent + 2))
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"{prefix}  -")
                    lines.append(_simple_yaml_dump(item, indent + 4))
                else:
                    lines.append(f"{prefix}  - {_format_scalar(item)}")
        else:
            lines.append(f"{prefix}{key}: {_format_scalar(value)}")
    return "\n".join(line for line in lines if line != "")


def _safe_dump_yaml(data: dict[str, Any]) -> str:
    if yaml is not None and hasattr(yaml, "safe_dump"):
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    return _simple_yaml_dump(data) + "\n"


DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "id": "test_product",
        "name": "测试产品",
        "titles_file": "titles.txt",
        "prompts_dir": "prompts",
        "common_prompt_file": "",
        "terms_file": "terms.txt",
        "brands_file": "brands.txt",
        "brand_profiles_file": "",
        "images_dir": "images",
        "excluded_prompts": [],
        "title_profile_file": "title_profile.json",
    },
    "generation": {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "max_output_tokens": 8000,
        "temperature": 0.9,
        "max_retries": 3,
        "retry_wait_seconds": 5,
        "min_generated_chars": 3500,
        "target_generated_chars": 4000,
    },
    "document": {
        "font_name": "宋体",
        "font_size_pt": 12,
        "space_before_pt": 0,
        "space_after_pt": 0,
        "line_spacing_rule": "single",
        "first_line_indent": False,
        "title_center": False,
        "heading_styles": False,
    },
    "features": {
        "bold_structure": True,
        "bold_terms": True,
        "save_raw_text": False,
        "save_prompt_used": True,
        "images": False,
        "cover": False,
    },
    "illustrations": {
        "neutral_slot": "neutral",
        "neutral_image_allowlist": [],
        "promoted_ranks": [1, 2, 3],
        "required_count": 4,
        "neutral_placement_strategy": "section_boundary_with_spacing",
        "neutral_body_paragraph_min_chars": 60,
        "minimum_body_paragraphs_before_neutral": 5,
        "minimum_body_paragraphs_between_images": 3,
        "validate_positions": True,
    },
    "humanizer": {
        "enabled": True,
        "auto_rewrite": True,
        "force_rewrite": False,
        "max_rewrites": 2,
        "preserve_structure": True,
        "preserve_facts": True,
    },
    "article_structure": {
        "enabled": False,
        "required_heading_groups": [
            ["基础", "科普", "概念", "认识"],
            ["选购", "选择", "购买", "判断", "核验", "核对", "标准", "要点"],
            ["推荐", "产品", "清单", "测评", "评测", "盘点"],
            ["人群", "场景", "按需", "适用", "需求", "饮用", "缩小选择"],
            ["常见问题", "问答", "答疑", "FAQ"],
            ["结语", "总结", "写在最后"],
        ],
    },
    "ranking": {
        "enabled": False,
        "size": 10,
        "fixed_promoted_count": 0,
        "randomize_others": True,
    },
    "promoted_products": [],
    "brand_section_lengths": {},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def project_dir(root: Path, project_id: str) -> Path:
    return root / "projects" / project_id


def load_project_config(root: Path, project_id: str) -> dict[str, Any]:
    path = project_dir(root, project_id) / "project.yaml"
    if not path.exists():
        raise FileNotFoundError(f"找不到项目配置：{path}")
    data = _safe_load_yaml(path.read_text(encoding="utf-8"))
    config = deep_merge(DEFAULT_CONFIG, data)
    config["project"]["id"] = project_id
    generation = config["generation"]
    generation["min_generated_chars"] = max(3500, int(generation.get("min_generated_chars") or 0))
    generation["target_generated_chars"] = max(
        int(generation["min_generated_chars"]) + 500,
        int(generation.get("target_generated_chars") or 0),
    )
    promoted = config.get("promoted_products") or []
    promoted_ranks = [int(item.get("rank") or 0) for item in promoted]
    if any(rank <= 0 for rank in promoted_ranks):
        raise ValueError("promoted_products 中每个产品都必须设置正整数 rank")
    if len(promoted_ranks) != len(set(promoted_ranks)):
        raise ValueError("promoted_products 中存在重复 rank")
    config["promoted_products"] = sorted(
        promoted,
        key=lambda item: int(item.get("rank") or 0),
    )
    brands_path = path.parent / config["project"].get("brands_file", "brands.txt")
    config["brand_whitelist"] = load_brand_whitelist(brands_path)
    if not config["brand_whitelist"]:
        raise ValueError(f"品牌白名单为空，请先填写：{brands_path}")

    whitelist_pairs = {
        (
            str(item.get("brand") or "").strip(),
            str(item.get("product_name") or "").strip(),
        )
        for item in config["brand_whitelist"]
    }
    missing_promoted = []
    for item in config["promoted_products"]:
        pair = (
            str(item.get("brand") or "").strip(),
            str(item.get("product_name") or "").strip(),
        )
        if pair not in whitelist_pairs:
            missing_promoted.append(pair[1] or pair[0])
    if missing_promoted:
        raise ValueError(
            "promoted_products 中的产品必须完整写入 brands.txt："
            + "、".join(missing_promoted)
        )
    profiles_file = config["project"].get("brand_profiles_file")
    config["brand_profiles"] = (
        load_brand_profiles(path.parent / profiles_file)
        if profiles_file
        else []
    )
    invalid_profiles = [
        item.get("product_name") or item.get("brand") or ""
        for item in config["brand_profiles"]
        if (
            str(item.get("brand") or "").strip(),
            str(item.get("product_name") or "").strip(),
        )
        not in whitelist_pairs
    ]
    if invalid_profiles:
        raise ValueError(
            "brand_profiles.json 中的产品必须完整写入 brands.txt："
            + "、".join(invalid_profiles)
        )
    profile_pairs = [
        (
            str(item.get("brand") or "").strip(),
            str(item.get("product_name") or "").strip(),
        )
        for item in config["brand_profiles"]
    ]
    if len(profile_pairs) != len(set(profile_pairs)):
        raise ValueError("brand_profiles.json 中存在重复的品牌产品资料")
    if config["project"].get("require_other_brand_details", False):
        promoted_pairs = {
            (
                str(item.get("brand") or "").strip(),
                str(item.get("product_name") or "").strip(),
            )
            for item in config["promoted_products"]
        }
        missing_profiles = sorted(
            product_name or brand
            for brand, product_name in whitelist_pairs - promoted_pairs - set(profile_pairs)
        )
        if missing_profiles:
            raise ValueError(
                "普通白名单产品缺少独立资料："
                + "、".join(missing_profiles)
            )
    return config


def load_brand_whitelist(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    brands = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            brand, product_name = [part.strip() for part in line.split("|", 1)]
        else:
            brand, product_name = line, line
        if brand:
            brands.append({"brand": brand, "product_name": product_name or brand})
    return brands


def load_brand_profiles(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"品牌资料文件必须是 JSON 数组：{path}")
    required = {
        "brand",
        "product_name",
        "formula",
        "format",
        "flavor",
        "packaging",
        "scene",
    }
    profiles = []
    for item in data:
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError(f"品牌资料字段不完整：{path} -> {item}")
        if not isinstance(item["formula"], list) or not item["formula"]:
            raise ValueError(f"品牌资料 formula 必须是非空数组：{path} -> {item}")
        profiles.append(item)
    return profiles


def build_default_config(project_id: str, name: str) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    config["project"]["id"] = project_id
    config["project"]["name"] = name
    return config


def write_project_config(path: Path, config: dict[str, Any]) -> None:
    path.write_text(
        _safe_dump_yaml(config),
        encoding="utf-8",
    )


def init_project(root: Path, project_id: str, name: str, force: bool = False) -> Path:
    path = project_dir(root, project_id)
    prompts_dir = path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    config_path = path / "project.yaml"
    if force or not config_path.exists():
        write_project_config(config_path, build_default_config(project_id, name))

    titles_path = path / "titles.txt"
    if force or not titles_path.exists():
        titles_path.write_text("示例标题：请替换为你的文章标题\n", encoding="utf-8")

    terms_path = path / "terms.txt"
    if force or not terms_path.exists():
        terms_path.write_text("", encoding="utf-8")

    brands_path = path / "brands.txt"
    if force or not brands_path.exists():
        brands_path.write_text("", encoding="utf-8")

    title_profile_path = path / "title_profile.json"
    if force or not title_profile_path.exists():
        title_profile_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "product": name,
                    "samples_file": "title_samples.txt",
                    "history_file": "title_history.txt",
                    "audiences": ["普通消费者"],
                    "leads": ["榜单参考", "选购指南"],
                    "tails": ["梳理实用选购思路"],
                    "topics": [
                        {
                            "question": f"{name}哪个品牌值得选",
                            "angle": "品质筛选",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    for filename in ("title_samples.txt", "title_history.txt"):
        title_data_path = path / filename
        if force or not title_data_path.exists():
            title_data_path.write_text("", encoding="utf-8")

    prompt_path = prompts_dir / "01_提示词.txt"
    if force or not prompt_path.exists():
        prompt_path.write_text(
            "请围绕《{title}》写一篇中文文章，产品名称是{project_name}。\n"
            "要求结构清晰、表达自然、内容完整，避免空泛套话。\n",
            encoding="utf-8",
        )
    return path
