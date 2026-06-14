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
    repeated_numeric_claim_warnings,
    recommendation_layout_warnings,
    top10_ranking_warnings,
)
from product_writer.bolding import is_structure_line
from product_writer.text_metrics import article_char_count

LOCKED_DEEPSEEK_MODEL = "deepseek-v4-pro"


class GenerationError(RuntimeError):
    pass


def should_humanize_article(text: str, config: dict[str, Any]) -> tuple[bool, list[str]]:
    settings = config.get("humanizer") or {}
    if not settings.get("enabled", True):
        return False, []
    findings = humanizer_warnings(text, config)
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
                structure_warnings.extend(repeated_numeric_claim_warnings(cleaned_content))
                structure_warnings.extend(
                    recommendation_layout_warnings(cleaned_content, config)
                )
                humanizer_settings = config.get("humanizer") or {}
                if not (
                    humanizer_settings.get("enabled", True)
                    and humanizer_settings.get("auto_rewrite", True)
                ):
                    structure_warnings.extend(humanizer_warnings(cleaned_content, config))
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


def _restore_numeric_lines(original: str, rewritten: str) -> str:
    original_lines = [line for line in original.splitlines() if line.strip()]
    rewritten_lines = [line for line in rewritten.splitlines() if line.strip()]
    if len(original_lines) != len(rewritten_lines):
        return rewritten

    protected_lines = []
    for original_line, rewritten_line in zip(original_lines, rewritten_lines):
        if _numeric_tokens(original_line) != _numeric_tokens(rewritten_line):
            protected_lines.append(original_line)
        else:
            protected_lines.append(rewritten_line)
    return "\n".join(protected_lines)


def _is_locked_humanizer_line(line: str, config: dict[str, Any]) -> bool:
    stripped = line.strip().lstrip("#* ")
    configured_headings = {
        str(value).strip()
        for value in (config.get("article_structure") or {}).get("headings") or []
        if str(value).strip()
    }
    return bool(
        stripped in configured_headings
        or is_structure_line(stripped)
        or re.match(
            r"^(?:推荐\s*[一二三四五六七八九十\d]+|TOP\s*\d+|"
            r"第[一二三四五六七八九十\d]+(?:名|款|位))\s*[：:]",
            stripped,
            flags=re.IGNORECASE,
        )
    )


def _prepare_humanizer_blocks(
    text: str,
    config: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    protected_names = sorted(
        _protected_brands(text, config),
        key=len,
        reverse=True,
    )
    blocks: list[dict[str, Any]] = []
    rendered: list[str] = []
    token_index = 0
    for block_index, raw_line in enumerate(
        (line.strip() for line in text.splitlines() if line.strip()),
        1,
    ):
        masked = raw_line
        tokens: dict[str, str] = {}
        protected_values = [
            *protected_names,
            *re.findall(r"\d+(?:\.\d+)?%?", raw_line),
        ]
        for value in protected_values:
            if not value or value not in masked:
                continue
            while value in masked:
                token_index += 1
                token = f"__LOCK_{token_index:04d}__"
                masked = masked.replace(value, token, 1)
                tokens[token] = value
        block_id = f"{block_index:04d}"
        locked = _is_locked_humanizer_line(raw_line, config)
        blocks.append(
            {
                "id": block_id,
                "original": raw_line,
                "masked": masked,
                "tokens": tokens,
                "locked": locked,
            }
        )
        rendered.append(f"<P{block_id}>{masked}</P{block_id}>")
    return "\n".join(rendered), blocks


def _restore_humanizer_blocks(
    response_text: str,
    blocks: list[dict[str, Any]],
) -> str:
    returned = {
        match.group(1): match.group(2).strip()
        for match in re.finditer(
            r"<P(\d{4})>(.*?)</P\1>",
            response_text,
            flags=re.DOTALL,
        )
    }
    restored: list[str] = []
    for block in blocks:
        original = str(block["original"])
        if block["locked"]:
            restored.append(original)
            continue
        candidate = returned.get(str(block["id"]), "")
        if not candidate:
            restored.append(original)
            continue
        candidate = re.sub(r"\s*\n+\s*", "", candidate).strip()
        tokens = dict(block["tokens"])
        if any(token not in candidate for token in tokens):
            restored.append(original)
            continue
        for token, value in tokens.items():
            candidate = candidate.replace(token, value)
        if "__LOCK_" in candidate:
            restored.append(original)
            continue
        if _numeric_tokens(candidate) != _numeric_tokens(original):
            restored.append(original)
            continue
        if is_structure_line(candidate) and not is_structure_line(original):
            restored.append(original)
            continue
        if (
            article_char_count(original) >= 80
            and article_char_count(candidate) < article_char_count(original) * 0.65
        ):
            restored.append(original)
            continue
        restored.append(candidate)
    return "\n".join(restored)


def _remove_rejected_humanizer_sentences(text: str) -> str:
    rejected_sentence_probes = (
        "序号不代表市场排名",
        "序号不代表排名",
        "不代表市场排名或优劣",
        "不代表产品优劣",
        "不是商业排名",
        "仅为陈列顺序",
        "仅作选购信息参考",
        "不存在依赖性问题",
        "回到饮前状态",
        "高复购率至少说明",
    )
    phrase_replacements = {
        "核对标签": "查看配料和规格",
        "名称本身": "产品信息",
        "产品名称直接突出": "产品信息包括",
        "产品名称直接": "产品信息",
        "产品名称突出": "产品信息包括",
        "名称直接突出": "产品信息包括",
        "从产品名称": "从配方信息",
        "信息完整度": "可查信息",
        "资料说明": "产品信息显示",
        "目的是让": "便于",
    }
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        parts = re.findall(r".+?(?:[。！？!?]+|$)", line)
        kept = [
            part
            for part in parts
            if part.strip()
            and not any(probe in part for probe in rejected_sentence_probes)
        ]
        cleaned = "".join(kept).strip()
        cleaned = re.sub(r"(?:数据|资料)显示[，,]?", "", cleaned)
        cleaned = re.sub(r"本质上[，,]?", "", cleaned)
        cleaned = re.sub(r"这意味着[，,]?", "", cleaned)
        cleaned = re.sub(r"真正关键(?:的是|在于)?", "关键", cleaned)
        for old, new in phrase_replacements.items():
            cleaned = cleaned.replace(old, new)
        if cleaned:
            cleaned_lines.append(cleaned)
    return "\n".join(cleaned_lines)


def _remove_conflicting_leading_subtitles(text: str, title: str) -> str:
    if not title:
        return text
    lines = text.splitlines()
    cleaned: list[str] = []
    for index, line in enumerate(lines):
        if index < 5 and conflicting_title_warnings(line, title):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


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
    problems.extend(humanizer_warnings(rewritten, config))
    problems.extend(complete_structure_warnings(rewritten, config))
    problems.extend(paragraph_structure_warnings(rewritten))
    problems.extend(repeated_numeric_claim_warnings(rewritten))
    problems.extend(recommendation_layout_warnings(rewritten, config))
    return problems


def humanize_article(
    root,
    text: str,
    config: dict[str, Any],
    expected_top10: list[str],
    title: str = "",
) -> str:
    settings = config.get("humanizer") or {}
    should_rewrite, findings = should_humanize_article(text, config)
    if not should_rewrite:
        return text
    if not settings.get("auto_rewrite", True):
        return text

    generation = config["generation"]
    min_chars = int(generation["min_generated_chars"])
    max_rewrites = max(1, int(settings.get("max_rewrites") or 1))
    protected_brands = sorted(_protected_brands(text, config), key=len, reverse=True)
    protected_numbers = sorted(_numeric_tokens(text).elements())
    protected_source, protected_blocks = _prepare_humanizer_blocks(text, config)
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
                            "原文已用<P0001>...</P0001>逐段编号。必须保留每一个编号及其先后"
                            "顺序，每个编号只能输出一次，不得合并、删除、新增或交换段落。"
                            "只修改标签内部的中文表达，不得改动P编号。\n"
                            "__LOCK_0001__一类占位符代表受保护的品牌、产品名或数字，必须逐字"
                            "原样保留在原段，不得删除、改写、调序或移到其他段。\n"
                            "语言要直接、平实、有具体信息，不要为了显得生动而增加抽象比喻、"
                            "连续反问、作者旁白或“信息迷雾、选择困境、底层逻辑、判断框架”"
                            "一类故作自然的修辞。\n"
                            "禁止出现“本文、这篇文章、接下来我们”等讲述写作过程的表达。\n"
                            "开头直接写消费者遇到的具体问题和判断要点，不介绍下文安排，"
                            "不解释写作目的。\n"
                            "必须保留原有章节结构、推荐行、推荐顺序和有资料支撑的产品事实。"
                            "相邻段落表达接近时，通过调整角度、删掉段内重复句来避免复述，"
                            "但不得合并或删除整段。\n"
                            "结构标题和“推荐一/推荐二”等推荐行保持原样；正文句式、段落开头和"
                            "信息顺序可以调整。\n"
                            "不要把各章节都写成相同的开场、三点展开和一句提醒；允许有的段落先给"
                            "结论，有的先写场景，有的直接解释数字。相邻段落长短、句式和"
                            "信息密度要有自然差异。\n"
                            "没有独立资料的普通白名单产品只保留产品全名，不生成介绍段、购买提醒"
                            "或资料不足说明。\n"
                            f"有效字数不得少于 {min_chars} 字。不要追求原文长度，也不要为达到"
                            "目标字数补写泛泛解释；自然删重后的文章可以短于原文。\n"
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
                            "删除把数字强行解释成效果、体验或购买结论的句子。除非原资料明确"
                            "提供因果关系，否则销量、复购率、纯度、吸收率、认证、配料排序只"
                            "陈述其本身，不写“这意味着”“至少说明”“可以证明”。\n"
                            "减少“不是……而是……”“真正关键”“本质上”“最后一公里”“试金石”"
                            "等常见机器转折和抽象总结，优先改成直接陈述。\n"
                            "原文已有的结构标题必须全部保留。不得把小标题合并进正文或删除；"
                            "末尾的总结、结语或写在最后必须保持为独立标题，并在其下给出简短、"
                            "可执行的收束，不写比喻和口号。\n"
                            "删除“以上这些判断方法没有绑定具体品牌”“把这些维度套到具体产品”"
                            "“逐一推敲”等写作导航句，结构标题已经足够承担转场作用。\n"
                            "删除原资料没有明确提供的医学、生理或营养机制，包括进入血液、"
                            "胃排空、降低肠胃负担、促进胶原合成、改善皮肤、维持黏膜、"
                            "细胞能量支持等解释。不要用常识补齐资料缺口。\n"
                            "原料研究、体外数据和成品信息必须分开。研究数字只能陈述原资料，"
                            "不得外推为产品效果、个人吸收量、适用人群收益或见效周期。\n"
                            "销量、复购率、认证、专利、纯度和吸收率不得解释成口感、效果、"
                            "品控成熟度、库存新鲜度、长期坚持意愿或肠胃适配性。\n"
                            "删除“不会发胖、没有依赖、停止后回到饮前状态、可以长期喝、"
                            "液体比片剂更易耐受、某时间喝效果更好”等无资料健康结论。\n"
                            "不要解释修改过程，只输出改写后的完整正文。\n\n"
                            f"【原文】\n{protected_source}"
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
        response_text = response.choices[0].message.content or ""
        if not response_text.strip():
            last_problems = ["自然化重写返回空内容"]
            continue
        rewritten = clean_model_output(
            _remove_conflicting_leading_subtitles(
                _remove_rejected_humanizer_sentences(
                    _restore_humanizer_blocks(response_text, protected_blocks)
                ),
                title,
            )
        )
        last_problems = _validate_humanized_article(
            original=text,
            rewritten=rewritten,
            config=config,
            expected_top10=expected_top10,
        )
        if not last_problems:
            return rewritten

    raise GenerationError("自然化重写未通过保护性复检，已停止生成 Word：" + "；".join(last_problems))
