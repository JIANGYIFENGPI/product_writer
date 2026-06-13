from __future__ import annotations

from collections import Counter
import json
import re
import time
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from product_writer.cleaner import clean_model_output
from product_writer.env_utils import get_deepseek_api_key
from product_writer.quality import (
    allowed_brand_names,
    brand_mentions_before_recommendations_warnings,
    brand_whitelist_warnings,
    conflicting_title_warnings,
    complete_structure_warnings,
    humanizer_warnings,
    paragraph_structure_warnings,
    top10_ranking_warnings,
)
from product_writer.text_metrics import article_char_count

LOCKED_DEEPSEEK_MODEL = "deepseek-v4-pro"


class GenerationError(RuntimeError):
    pass


def should_humanize_article(text: str, config: dict[str, Any]) -> tuple[bool, list[str]]:
    settings = config.get("humanizer") or {}
    if not settings.get("enabled", True):
        return False, []
    findings = humanizer_warnings(text)
    if settings.get("force_rewrite", False):
        return True, findings or ["执行全篇自然化编辑，避免未命中规则的隐性模板感"]
    return bool(findings), findings


class _FallbackChatCompletions:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def create(self, **payload):
        request = Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GenerationError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(content=item.get("message", {}).get("content", ""))
            )
            for item in data.get("choices", [])
        ]
        if not choices:
            raise GenerationError(f"DeepSeek 返回缺少 choices：{data}")
        return SimpleNamespace(choices=choices)


class _FallbackDeepSeekClient:
    def __init__(self, api_key: str):
        self.chat = SimpleNamespace(completions=_FallbackChatCompletions(api_key))


def _deepseek_client(root):
    api_key = get_deepseek_api_key(root)
    if not api_key:
        raise GenerationError("缺少 DEEPSEEK_API_KEY。dry-run 可以运行，正式生成请先在 .env 中填写 key。")
    if OpenAI is not None:
        return OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=300,
            max_retries=0,
        )
    return _FallbackDeepSeekClient(api_key)


def generate_article(
    root,
    prompt: str,
    config: dict[str, Any],
    expected_top10: list[str] | None = None,
    title: str = "",
) -> str:
    generation = config["generation"]
    min_chars = int(generation["min_generated_chars"])
    target_chars = int(generation["target_generated_chars"])
    client = _deepseek_client(root)
    last_error: Exception | None = None
    current_prompt = prompt
    for attempt in range(1, int(generation["max_retries"]) + 1):
        try:
            response = client.chat.completions.create(
                model=LOCKED_DEEPSEEK_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是资深中文消费内容编辑，直接完成可交付成稿，只输出文章正文。"
                            "写作时同步完成编辑整理，不输出提纲、草稿、写作说明或模板化过渡。"
                            "最高优先级规则：品牌名和产品名只能使用用户资料中的品牌白名单。"
                            "如果白名单只提供一个品牌，不得写多品牌榜单或补足TOP推荐。"
                            "首个正式推荐标题之前不得出现任何品牌名或产品名。"
                        ),
                    },
                    {"role": "user", "content": current_prompt},
                ],
                temperature=float(generation["temperature"]),
                max_tokens=int(generation["max_output_tokens"]),
            )
            content = response.choices[0].message.content or ""
            if content.strip():
                cleaned_content = clean_model_output(content)
                char_count = article_char_count(cleaned_content)
                structure_warnings = brand_whitelist_warnings(cleaned_content, config)
                structure_warnings.extend(
                    brand_mentions_before_recommendations_warnings(cleaned_content, config)
                )
                structure_warnings.extend(conflicting_title_warnings(cleaned_content, title))
                structure_warnings.extend(
                    top10_ranking_warnings(cleaned_content, config, expected_top10 or [])
                )
                structure_warnings.extend(paragraph_structure_warnings(cleaned_content))
                structure_warnings.extend(humanizer_warnings(cleaned_content))
                structure_warnings.extend(complete_structure_warnings(cleaned_content, config))
                if char_count >= min_chars and not structure_warnings:
                    return content
                retry_reasons: list[str] = []
                if char_count < min_chars:
                    retry_reasons.append(
                        f"上次正文只有 {char_count} 个有效字，至少还差 {min_chars - char_count} 字"
                    )
                retry_reasons.extend(structure_warnings)
                last_error = GenerationError("；".join(retry_reasons))
                current_prompt = (
                    f"{prompt}\n\n"
                    f"【上次生成不合格，必须重新完整写作】\n"
                    f"{'；'.join(retry_reasons)}。"
                    f"本次请按约 {target_chars} 字完整重写，确保有效字数不少于 {min_chars} 字。"
                    f"正文中的品牌名和产品名必须全部来自本次提供的品牌白名单。"
                    f"不要解释原因，不要输出修改说明，只输出重新写成的完整文章正文。"
                )
            else:
                last_error = GenerationError("DeepSeek 返回了空内容。")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        if attempt < int(generation["max_retries"]):
            time.sleep(float(generation["retry_wait_seconds"]))
    raise GenerationError(f"DeepSeek 生成失败或正文未达到最低字数，已停止生成 Word：{last_error}")


def _numeric_tokens(text: str) -> Counter[str]:
    return Counter(re.findall(r"\d+(?:\.\d+)?%?", text))


def _protected_brands(text: str, config: dict[str, Any]) -> set[str]:
    return {name for name in allowed_brand_names(config) if name in text}


def _validate_humanized_article(
    *,
    original: str,
    rewritten: str,
    config: dict[str, Any],
    expected_top10: list[str],
) -> list[str]:
    problems: list[str] = []
    min_chars = int(config["generation"]["min_generated_chars"])
    char_count = article_char_count(rewritten)
    if char_count < min_chars:
        problems.append(f"重写后有效字数不足：{char_count} < {min_chars}")

    missing_brands = sorted(
        (name for name in _protected_brands(original, config) if name not in rewritten),
        key=len,
        reverse=True,
    )
    if missing_brands:
        problems.append("重写后遗漏原文品牌/产品：" + "、".join(missing_brands[:10]))

    if config.get("humanizer", {}).get("preserve_facts", True):
        if _numeric_tokens(original) != _numeric_tokens(rewritten):
            problems.append("重写改变、增加或删除了原文数字")

    problems.extend(brand_whitelist_warnings(rewritten, config))
    problems.extend(brand_mentions_before_recommendations_warnings(rewritten, config))
    problems.extend(top10_ranking_warnings(rewritten, config, expected_top10))
    problems.extend(humanizer_warnings(rewritten))
    problems.extend(complete_structure_warnings(rewritten, config))
    problems.extend(paragraph_structure_warnings(rewritten))
    return problems


def humanize_article(
    root,
    text: str,
    config: dict[str, Any],
    expected_top10: list[str],
) -> str:
    settings = config.get("humanizer") or {}
    should_rewrite, findings = should_humanize_article(text, config)
    if not should_rewrite:
        return text
    if not settings.get("auto_rewrite", True):
        return text

    generation = config["generation"]
    min_chars = int(generation["min_generated_chars"])
    target_chars = int(generation["target_generated_chars"])
    max_rewrites = max(1, int(settings.get("max_rewrites") or 1))
    protected_brands = sorted(_protected_brands(text, config), key=len, reverse=True)
    protected_numbers = sorted(_numeric_tokens(text).elements())
    client = _deepseek_client(root)
    last_problems = findings

    for rewrite_index in range(max_rewrites):
        try:
            response = client.chat.completions.create(
                model=LOCKED_DEEPSEEK_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是资深中文消费内容编辑。将机器生成的提纲腔改成自然、克制、"
                            "有编辑判断的成稿，不改变事实、数字、品牌、产品名、推荐顺序、"
                            "标题结构和段落功能。不得增加任何新事实。只输出完整正文。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "请对下方完整文章逐段做自然化改写，重点消除重复开头、机械连接词、"
                            "提纲扩写感和每段相同的“解释—提醒—结论”节奏。\n"
                            "语言要直接、平实、有具体信息，不要为了显得生动而增加抽象比喻、"
                            "连续反问、作者旁白或“信息迷雾、选择困境、底层逻辑、判断框架”"
                            "一类故作自然的修辞。\n"
                            "禁止出现“本文、这篇文章、接下来我们”等讲述写作过程的表达。\n"
                            "开头直接写消费者遇到的具体问题和判断要点，不介绍下文安排，"
                            "不解释写作目的。\n"
                            "必须保留原有完整结构、全部信息、推荐行和推荐顺序，不得删减品牌介绍。\n"
                            "结构标题和“推荐一/推荐二”等推荐行保持原样；正文句式、段落开头和"
                            "信息顺序可以调整。\n"
                            "不要把各章节都写成相同的开场、三点展开和一句提醒；允许有的段落先给"
                            "结论，有的先写场景，有的直接解释数字。相邻段落长短、句式和"
                            "信息密度要有自然差异。\n"
                            "没有独立资料的普通白名单产品只保留产品全名，不生成介绍段、购买提醒"
                            "或资料不足说明。\n"
                            f"有效字数不得少于 {min_chars} 字，目标约 {target_chars} 字。\n"
                            f"必须原样保留的品牌/产品：{'、'.join(protected_brands) or '无'}\n"
                            f"必须保持完全一致的数字清单：{'、'.join(protected_numbers) or '无'}\n"
                            f"当前需要修正的问题：{'；'.join(last_problems)}\n"
                            "禁止自行新增体验、评价、销量、检测、认证、机构、来源或数据。"
                            "用户原始提示词和原文中已提供的内容视为可用资料，无需另附证明，"
                            "自然化重写时必须保留原数值和核心信息；不得补造新内容或扩大结论。\n"
                            "不要添加“资料显示、资料标注、原始资料、研究显示、检测显示”等前缀。"
                            "产品数据直接自然表述，机构或检测名称仅作为正文事实保留。\n"
                            "提示词中的限制条件不能写进正文。删除“只在这款产品中出现、"
                            "不构成整个品类必选项、形成不同路线、代表不同思路、谁更全、"
                            "各有侧重”等编辑说明式句子，直接保留产品事实。\n"
                            "不得根据配料推断读者缺少某类营养，不写“取决于日常饮食缺什么”"
                            "或“补足饮食短板”等无资料判断。\n"
                            "不要解释修改过程，只输出改写后的完整正文。\n\n"
                            f"【原文】\n{text}"
                        ),
                    },
                ],
                temperature=min(float(generation["temperature"]), 0.35),
                max_tokens=int(generation["max_output_tokens"]),
            )
        except Exception as exc:  # noqa: BLE001
            last_problems = [f"自然化请求失败：{exc}"]
            if rewrite_index + 1 < max_rewrites:
                time.sleep(float(generation["retry_wait_seconds"]))
            continue
        rewritten = clean_model_output(response.choices[0].message.content or "")
        if not rewritten:
            last_problems = ["自然化重写返回空内容"]
            continue
        last_problems = _validate_humanized_article(
            original=text,
            rewritten=rewritten,
            config=config,
            expected_top10=expected_top10,
        )
        if not last_problems:
            return rewritten

    raise GenerationError("自然化重写未通过保护性复检，已停止生成 Word：" + "；".join(last_problems))
