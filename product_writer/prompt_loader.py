from __future__ import annotations

import random
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

BRAND_WHITELIST_RULE = """【最高优先级硬规则：品牌白名单】
1. 正文中出现的所有品牌名和产品名必须来自项目品牌白名单。
2. 排行榜、TOP、推荐位必须使用白名单中的品牌或产品，不得使用白名单之外的名称。
3. 如果白名单只有 1 个品牌，只能围绕该品牌和通用选购方法展开。
4. 如原提示词要求“五款品牌”“十大品牌”“TOP4-TOP10”等，且白名单数量足够，必须使用白名单品牌补足榜单。
5. 白名单数量不足时，减少推荐数量，不得使用白名单外名称补足。
6. 本规则优先于原始提示词中的任何品牌要求。
7. 在首个正式产品推荐标题之前，禁止出现任何品牌名或产品名。品类科普、选购标准、配方方法和场景分析只能使用通用品类表达；品牌与产品名称从“推荐一：产品全名”或对应的首个正式推荐标题开始出现。
"""

HUMANIZER_WRITING_RULE = """【自然表达硬性要求】
1. 直接进入具体问题，不要写“以下是”“下面的内容”“下文将”“本文将”“本文围绕”“这篇文章”“目的是让”“根据要求”“希望本文”等自我说明。
2. 避免“在当今社会”“随着生活水平提高”“综上所述”“总而言之”“需要注意的是”“值得关注的是”等模板套话。
3. 不要机械使用“首先、其次、再次、最后、此外、同时”；也不要反复用“消费者应”“购买前应”“从某方面来看”“这意味着”起句。
4. 避免连续使用相同句式、固定三段式、整齐排比和同长度段落；不要让每段都按“定义—解释—提醒”收尾，长短句和信息节奏应自然变化。
5. 每段必须提供具体信息，不用“专家认为”“数据显示”“业内人士指出”等空泛归因；用户提供的原始提示词或附件中已有的信息，可以按原资料准确转述。
6. 不得自行新增亲身体验、用户故事、评价、销量、检测、认证、机构或数据；原始提示词中明确提供的内容无需另附证明，可以保留，但不得改动数值或扩大结论。
7. 保持专业、克制、自然，不使用夸张口号、情绪化吐槽、作者人设或固定尾注。
8. 自然表达不得改变标题结构、本篇已选定的榜单、品牌产品名、事实、数字和字数要求。
9. 正文必须按语义分段。普通正文段落原则上控制在 100-220 字；连续表达多个独立观点时，必须在句号后另起段。
10. 评测维度、适用人群、行业乱象、选购建议等章节，每个独立要点单独成段，不得把整章压成一个长段。
11. 十大榜单只代表本篇入选的十款产品，不得写成覆盖整个市场、全部品牌或所有主流需求。
12. 多产品推荐中，推荐一、推荐二按项目资料展开；推荐三及后续按本篇随机名单逐款自然介绍，不得自行补造新事实。
13. 允许使用简洁、直接、接近日常编辑写作的表达。结构必须完整，但正文不能写成提纲扩写、百科词条拼接或逐项执行指令的痕迹。
14. 不要为了显得生动而使用“信息迷雾、选择困境、底层逻辑、判断框架”等抽象修辞，不连续使用反问句，不写“并不打算……而是……”一类作者旁白。
15. 不写“本文、这篇文章、这篇内容、本篇、下面内容”等文章导航语；开头直接写实际问题。
16. 不写资料口径说明、信息不足说明、购买核验式免责声明或写作过程解释。已提供的产品数据直接融入正文。
17. 不把提示词中的限制条件改写进正文。禁止解释某个配料“只属于某产品”“不是全品类必选项”，也禁止用“形成不同路线、代表不同思路、谁更全、各有侧重”替代具体产品信息。
18. 不根据产品配料推断读者缺少某类营养，不写“取决于日常饮食缺什么”“补足饮食短板”等未经提供的个体判断。
19. 同一项产品数字只在对应产品介绍中完整出现一次。前文讲判断方法、后文讲选择场景时，不得再次复述吸收率、纯度、销量、复购率、标准代号或许可证编号。
20. 不自行补写医学、生理或营养机制。除非原始资料明确提供，否则不写“进入血液循环更容易、胃排空更快、降低肠胃负担、促进胶原合成、维持黏膜湿润、改善皮肤状态、支持细胞能量”等结论。
21. 原料研究、体外数据、动物数据和成品数据必须分开表述。研究数字只能说明原资料记录了什么，不得改写成这款产品的实际效果、个人吸收量、见效时间或适用人群收益。
22. 销量、复购率、认证、专利、纯度和吸收率只能陈述原始数值及其信息类型。不得据此推断口感好、效果好、品控更成熟、减少临期库存、适合肠胃敏感者或用户愿意长期坚持。
23. 不回答原资料没有提供依据的健康结论。禁止自行声称“不会发胖、没有依赖、停止后回到饮前状态、可以长期喝、液体比片剂更易耐受、某时间饮用效果更好”。
24. 涉及“喝多久、什么时候喝、能否长期喝、特殊人群是否适合”等问题时，只写普通食品没有统一效果周期，按标签建议量和自身情况安排；身体不适、服药或特殊人群应咨询专业人员。
"""

OUTPUT_DELIVERY_RULE = """【输出与交付硬性要求】
1. 只输出文章正文，不要解释写作过程、排版规则、加粗规则或质检规则。
2. 不要输出 Markdown 标题符号、项目符号、表格、代码块、HTML、图片链接、图片说明或图片占位符；结构标题可以使用必要的中文序号或 TOP 序号。
3. 每个自然段单独一行；标题行、结构标题和推荐行必须独立成行，正文从下一行开始。
4. 不要使用空行制造版面间距，不要在行首输入空格或全角空格模拟首行缩进。
5. 不要自行添加星号加粗。文章标题、结构标题、推荐行和项目关键词由程序统一加粗。
6. 不要描述字体、字号、颜色、居中、行距、段距等 Word 格式；程序会统一生成宋体 12pt、左对齐、单倍行距、段前段后 0 pt 的普通段落。
7. 当前阶段不插图。不得输出“此处插图”“图片位置”“配图建议”等任何图片相关文字。
"""

OUTPUT_DELIVERY_IMAGE_RULE = """【输出与交付硬性要求】
1. 只输出文章正文，不要解释写作过程、排版规则、加粗规则、插图规则或质检规则。
2. 不要输出 Markdown 标题符号、项目符号、表格、代码块、HTML、图片链接、图片说明或图片占位符；结构标题可以使用必要的中文序号或 TOP 序号。
3. 每个自然段单独一行；标题行、结构标题和推荐行必须独立成行，正文从下一行开始。
4. 不要使用空行制造版面间距，不要在行首输入空格或全角空格模拟首行缩进。
5. 不要自行添加星号加粗。文章标题、结构标题、推荐行和项目关键词由程序统一加粗。
6. 不要描述字体、字号、颜色、居中、行距、段距等 Word 格式；程序会统一生成宋体 12pt、左对齐、单倍行距、段前段后 0 pt 的普通段落。
7. 图片由程序从项目素材槽位自动选择并插入。正文不得输出“此处插图”“图片位置”“配图建议”、图片标题、图注或任何图片相关说明。
"""


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip().lstrip("\ufeff") for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def load_titles(project_path: Path, config: dict[str, Any]) -> list[str]:
    project_config = config["project"]
    titles_path = project_path / project_config["titles_file"]
    titles = read_lines(titles_path)
    filename_lines = [title for title in titles if title.lower().endswith(".docx")]
    if filename_lines:
        raise ValueError(
            f"标题文件混入了 Word 文件名：{titles_path}。"
            "请恢复纯标题文本，程序不会把 .docx 文件名当作标题。"
        )

    source_file = str(project_config.get("title_source_file") or "").strip()
    if project_config.get("lock_titles") and source_file:
        source_path = project_path / source_file
        source_titles = read_lines(source_path)
        if not source_titles:
            raise ValueError(f"标题锁定底稿为空：{source_path}")
        if titles != source_titles:
            raise ValueError(
                f"标题已偏离锁定底稿：{titles_path}。"
                f"请以 {source_path} 为准恢复，程序已停止运行。"
            )
    return titles


def load_terms(project_path: Path, config: dict[str, Any]) -> list[str]:
    terms = read_lines(project_path / config["project"].get("terms_file", "terms.txt"))
    for item in config.get("brand_whitelist") or []:
        if item.get("brand"):
            terms.append(item["brand"])
        if item.get("product_name"):
            terms.append(item["product_name"])
    for item in config.get("promoted_products") or []:
        terms.extend(item.get("bold_terms") or [])
        terms.extend(item.get("aliases") or [])
        if item.get("brand"):
            terms.append(item["brand"])
        if item.get("product_name"):
            terms.append(item["product_name"])
    unique = {term.strip() for term in terms if term and term.strip()}
    return sorted(unique, key=len, reverse=True)


def load_prompts(project_path: Path, config: dict[str, Any]) -> list[tuple[Path, str]]:
    prompts_dir = project_path / config["project"]["prompts_dir"]
    common_file = config["project"].get("common_prompt_file")
    common_text = ""
    if common_file:
        common_path = project_path / common_file
        if common_path.exists():
            common_text = common_path.read_text(encoding="utf-8").strip()
    included_config = config["project"].get("included_prompts") or []
    if isinstance(included_config, str):
        included = {item.strip() for item in included_config.split(",") if item.strip()}
    else:
        included = {str(item).strip() for item in included_config if str(item).strip()}
    excluded_config = config["project"].get("excluded_prompts") or []
    if isinstance(excluded_config, str):
        excluded = {item.strip() for item in excluded_config.split(",") if item.strip()}
    else:
        excluded = set(excluded_config)
    prompts = []
    for path in sorted(prompts_dir.glob("*.txt")):
        if included and path.name not in included:
            continue
        if path.name in excluded:
            continue
        text = path.read_text(encoding="utf-8").strip()
        if text:
            if common_text:
                text = f"{common_text}\n\n【本篇专用写作角度】\n{text}"
            prompts.append((path, text))
    if not prompts:
        raise FileNotFoundError(f"没有找到可用提示词：{prompts_dir}/*.txt")
    return prompts


def promoted_products_text(config: dict[str, Any]) -> str:
    promoted = config.get("promoted_products") or []
    if not promoted:
        return ""
    return json.dumps(promoted, ensure_ascii=False, indent=2)


def requested_product_count(title: str) -> int:
    number_words = {
        "五款": 5,
        "六款": 6,
        "七款": 7,
        "八款": 8,
        "九款": 9,
        "十款": 10,
        "十大": 10,
    }
    for marker, count in number_words.items():
        if marker in title:
            return count
    match = re.search(r"([5-9]|10)\s*款", title)
    return int(match.group(1)) if match else 10


def article_brand_plan(title: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    promoted = [deepcopy(item) for item in config.get("promoted_products") or []]
    total = max(len(promoted), requested_product_count(title))
    fixed_brands = {
        str(item.get("brand") or "").strip()
        for item in promoted
    }
    candidates = [
        deepcopy(item)
        for item in config.get("brand_whitelist") or []
        if str(item.get("brand") or "").strip() not in fixed_brands
    ]
    needed = min(max(0, total - len(promoted)), len(candidates))
    selected = random.sample(candidates, needed) if needed else []
    profiles = {
        (
            str(item.get("brand") or "").strip(),
            str(item.get("product_name") or "").strip(),
        ): item
        for item in config.get("brand_profiles") or []
    }
    for item in selected:
        profile = profiles.get(
            (
                str(item.get("brand") or "").strip(),
                str(item.get("product_name") or "").strip(),
            )
        )
        if profile:
            item["profile"] = deepcopy(profile)
    plan = promoted + selected
    inject_writing_modes = bool(
        config.get("project", {}).get("inject_brand_writing_modes", True)
    )
    writing_modes = (
        "先写入口风味，再自然带出配方与规格",
        "从通勤或外出携带切入，再补充配方信息",
        "先写配方组合，再用一句话交代口感",
        "从单次容量切入，连接实际饮用场景",
        "先写包装和携带感受，再落到风味",
        "从口味接受度切入，收束到日常安排",
        "先写复配成分之间的区别，再补充规格",
        "用简短判断开头，随后给出两项具体事实",
    )
    for rank, item in enumerate(plan, 1):
        item["rank"] = rank
        if inject_writing_modes:
            item["writing_mode"] = writing_modes[(rank - 1) % len(writing_modes)]
    return plan


def article_brand_plan_text(plan: list[dict[str, Any]]) -> str:
    if not plan:
        return ""
    chinese = {
        1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
        6: "六", 7: "七", 8: "八", 9: "九", 10: "十",
    }
    lines = ["【本篇产品推荐顺序】"]
    lines.append("本篇顺序已经随机确定，正文不得换位、替换或重复产品。")
    for item in plan:
        rank = int(item["rank"])
        product = item.get("product_name") or item.get("brand")
        lines.append(f"推荐{chinese.get(rank, str(rank))}：{product}")
        profile = item.get("profile") or {}
        if profile:
            formula = "、".join(str(value) for value in profile.get("formula") or [])
            lines.append(
                "内部素材（只供改写，禁止照抄字段名）："
                f"配方={formula}；规格={profile.get('format')}；"
                f"风味={profile.get('flavor')}；包装={profile.get('packaging', '')}；"
                f"场景={profile.get('scene')}"
            )
            if item.get("writing_mode"):
                lines.append(f"本款组织方式：{item['writing_mode']}")
    lines.append("每个推荐标题下只写一个正文自然段，不得拆成两段或多段。")
    lines.append("每款从对应内部素材中选择2至3项展开，不要逐项复述，不要五项全部写满。")
    lines.append("“内部素材、配方=、规格=、风味=、包装=、场景=”等提示字段绝对不能出现在正文中。")
    lines.append("各款不得连续使用相同的信息顺序，不得写成同长度、同句式的产品卡片。")
    lines.append("不得解释产品名称，不得用名称中的词语反推配方或卖点。")
    lines.append("禁止使用“名称突出、名称直接、从名称看、产品定位、产品路线、属于某类”等凑字句。")
    lines.append("没有独立品牌资料时不得编写品牌详情，必须停止本篇生成并报告资料缺口。")
    return "\n".join(lines)


def _rank_marker(line: str, *, include_numbered: bool = True) -> int | None:
    plain = line.replace("*", "").replace("#", "").strip()
    patterns = (
        r"\bTOP\s*([123])\b",
        r"推荐\s*([123])",
        r"推荐\s*([一二三])",
        r"固定推荐\s*([123])",
        r"固定推荐\s*([一二三])",
        r"第\s*([一二三123])\s*(?:名|款|位)",
        r"主体\s*([一二三])",
    )
    chinese = {"一": 1, "二": 2, "三": 3}
    for pattern in patterns:
        match = re.search(pattern, plain, flags=re.IGNORECASE)
        if match:
            value = match.group(1)
            return int(value) if value.isdigit() else chinese[value]
    if "主推款" in plain:
        return 1
    if include_numbered:
        match = re.search(r"^\s*([123])\s*[.、．)]", plain)
        if match:
            return int(match.group(1))
    return None


def config_with_prompt_promoted_order(template: str, config: dict[str, Any]) -> dict[str, Any]:
    """Return a per-article config whose promoted ranks come from the prompt."""
    ranking = config.get("ranking") or {}
    if ranking.get("promoted_order_source", "project") != "prompt":
        return config

    promoted = config.get("promoted_products") or []
    by_rank: dict[int, dict[str, Any]] = {}
    used_brands: set[str] = set()
    lines = template.splitlines()
    for include_numbered in (False, True):
        for line in lines:
            rank = _rank_marker(line, include_numbered=include_numbered)
            if rank not in {1, 2, 3} or rank in by_rank:
                continue
            matches = []
            for item in promoted:
                names = [
                    item.get("brand"),
                    item.get("product_name"),
                    *(item.get("aliases") or []),
                ]
                if any(name and str(name) in line for name in names):
                    matches.append(item)
            unique = {
                str(item.get("brand") or item.get("product_name")): item
                for item in matches
            }
            if len(unique) == 1:
                item = next(iter(unique.values()))
                identity = str(item.get("brand") or item.get("product_name"))
                if identity not in used_brands:
                    by_rank[rank] = item
                    used_brands.add(identity)

    expected = min(3, len(promoted))
    if len(by_rank) != expected or sorted(by_rank) != list(range(1, expected + 1)):
        raise ValueError(
            "提示词未能明确识别完整的主推产品 TOP1-TOP"
            f"{expected} 顺序，请在提示词中分别写明推荐位和品牌名"
        )

    article_config = deepcopy(config)
    ordered = []
    for rank in range(1, expected + 1):
        item = deepcopy(by_rank[rank])
        item["rank"] = rank
        ordered.append(item)
    article_config["promoted_products"] = ordered
    return article_config


def config_with_expected_promoted_order(
    expected_top10: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Restore a prior article's promoted order from its saved ranking."""
    if not expected_top10:
        return config
    promoted = config.get("promoted_products") or []
    ordered = []
    used: set[str] = set()
    for rank, expected_name in enumerate(expected_top10[:len(promoted)], 1):
        matches = []
        for item in promoted:
            names = [
                item.get("brand"),
                item.get("product_name"),
                *(item.get("aliases") or []),
            ]
            if any(name and str(name) in expected_name for name in names):
                matches.append(item)
        if len(matches) != 1:
            return config
        identity = str(matches[0].get("brand") or matches[0].get("product_name"))
        if identity in used:
            return config
        item = deepcopy(matches[0])
        item["rank"] = rank
        ordered.append(item)
        used.add(identity)
    if len(ordered) != min(3, len(promoted)):
        return config
    restored = deepcopy(config)
    restored["promoted_products"] = ordered
    return restored


def allowed_brand_names_text(config: dict[str, Any]) -> str:
    names: set[str] = set()
    for item in config.get("brand_whitelist") or []:
        for key in ("brand", "product_name"):
            value = item.get(key)
            if value:
                names.add(str(value).strip())
    if not names:
        return "未配置。停止生成并补充 brands.txt。"
    return "、".join(sorted(names, key=len, reverse=True))


def top10_brand_ranking(config: dict[str, Any]) -> list[str]:
    """生成主推位固定、其余推荐位每篇随机的 TOP10 榜单。

    仅 ranking.enabled=true 的产品启用。固定推荐位数量和榜单总数
    均由项目配置决定，其余推荐位可按项目配置随机生成。
    """
    ranking_config = config.get("ranking") or {}
    if not ranking_config.get("enabled", False):
        return []

    ranking_size = max(1, int(ranking_config.get("size") or 10))
    fixed_count = max(0, int(ranking_config.get("fixed_promoted_count") or 0))
    promoted = config.get("promoted_products") or []
    whitelist = config.get("brand_whitelist") or []

    fixed_names: set[str] = set()
    fixed_lines: list[str] = []
    for item in promoted[:fixed_count]:
        name = item.get("product_name") or item.get("brand") or ""
        if name:
            fixed_lines.append(name)
            fixed_names.add(name)
            fixed_names.add(item.get("brand", ""))

    remaining = []
    for item in whitelist:
        name = item.get("product_name") or item.get("brand") or ""
        brand = item.get("brand") or ""
        if brand not in fixed_names and name not in fixed_names:
            remaining.append(name)

    if len(fixed_lines) + len(remaining) < ranking_size:
        return []

    needed = ranking_size - len(fixed_lines)
    if ranking_config.get("randomize_others", True):
        selected = random.sample(remaining, needed)
    else:
        selected = remaining[:needed]
    return fixed_lines + selected


def top10_brand_ranking_text(ranking: list[str]) -> str:
    if not ranking:
        return ""
    lines: list[str] = []
    for i, name in enumerate(ranking, 1):
        lines.append(f"TOP{i}：{name}")
    return "\n".join(lines)


def brand_section_lengths_text(config: dict[str, Any]) -> str:
    rules = config.get("brand_section_lengths") or {}
    if not rules:
        return ""
    promoted_rules = rules.get("promoted") or []
    other_rules = rules.get("others") or {}
    lines = ["【品牌详情篇幅硬性要求】"]
    for item in promoted_rules:
        rank = item.get("rank")
        min_chars = item.get("min_chars")
        max_chars = item.get("max_chars")
        if rank and min_chars and max_chars:
            lines.append(f"TOP{rank}/推荐{rank} 品牌详情正文控制在 {min_chars}-{max_chars} 字。")
    if other_rules.get("min_chars") and other_rules.get("max_chars"):
        first_other_rank = max(
            [int(item.get("rank") or 0) for item in promoted_rules] or [0]
        ) + 1
        ranking_size = max(1, int((config.get("ranking") or {}).get("size") or 10))
        label = "TOP" if (config.get("ranking") or {}).get("enabled", False) else "推荐"
        lines.append(
            f"{label}{first_other_rank}-{label}{ranking_size} 每个品牌详情正文控制在 "
            f"{other_rules['min_chars']}-{other_rules['max_chars']} 字。"
        )
    lines.append("以上字数只统计对应品牌详情介绍正文，不含标题、简榜、总述、FAQ、结尾。")
    lines.append("不得把推荐二、推荐三写成一句话短评；前三个产品均需有完整介绍段。")
    return "\n".join(lines)


def choose_prompt(
    prompts: list[tuple[Path, str]],
    title: str = "",
    config: dict[str, Any] | None = None,
) -> tuple[Path, str]:
    title_rules = (config or {}).get("project", {}).get("prompt_selection_rules") or []
    if isinstance(title_rules, dict):
        title_rules = [
            {
                "prompt_prefixes": [prefix],
                "keywords": [
                    keyword.strip()
                    for keyword in str(keywords).split("|")
                    if keyword.strip()
                ],
            }
            for prefix, keywords in title_rules.items()
        ]
    for rule in title_rules:
        keywords = tuple(str(value) for value in rule.get("keywords") or [])
        prefixes = tuple(str(value) for value in rule.get("prompt_prefixes") or [])
        if not any(keyword in title for keyword in keywords):
            continue
        candidates = [
            item
            for item in prompts
            if any(item[0].name.startswith(prefix) for prefix in prefixes)
        ]
        if candidates:
            index = sum(ord(char) for char in title) % len(candidates)
            return candidates[index]

    default_config = (config or {}).get("project", {}).get("default_prompt_prefixes") or []
    if isinstance(default_config, str):
        default_config = [value.strip() for value in default_config.split("|") if value.strip()]
    default_prefixes = tuple(str(value) for value in default_config)
    if default_prefixes:
        candidates = [
            item
            for item in prompts
            if any(item[0].name.startswith(prefix) for prefix in default_prefixes)
        ]
        if candidates:
            index = sum(ord(char) for char in title) % len(candidates) if title else 0
            return candidates[index]

    index = sum(ord(char) for char in title) % len(prompts) if title else random.randrange(len(prompts))
    return prompts[index]


def extract_fixed_top10(prompt: str) -> list[str]:
    lines = prompt.splitlines()
    ranking: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(
            (
                "【本篇 TOP1-TOP10 排行榜",
                "【本篇产品推荐顺序】",
            )
        ):
            in_section = True
            continue
        if in_section and stripped.startswith("【"):
            break
        if in_section and stripped.startswith("TOP") and "：" in stripped:
            _, name = stripped.split("：", 1)
            if name.strip():
                ranking.append(name.strip())
        elif in_section and re.match(r"^推荐[一二三四五六七八九十\d]+：", stripped):
            _, name = stripped.split("：", 1)
            if name.strip():
                ranking.append(name.strip())
    return ranking


def render_prompt(template: str, title: str, config: dict[str, Any]) -> str:
    promoted = config.get("promoted_products") or []
    primary = promoted[0] if promoted else {}
    secondary = promoted[1] if len(promoted) > 1 else {}
    values = {
        "title": title,
        "project_name": config["project"]["name"],
        "promoted_products": promoted_products_text(config),
        "primary_product": json.dumps(primary, ensure_ascii=False, indent=2) if primary else "",
        "secondary_product": json.dumps(secondary, ensure_ascii=False, indent=2) if secondary else "",
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    allowed = json.dumps(config["brand_whitelist"], ensure_ascii=False, indent=2)
    allowed_names = allowed_brand_names_text(config)
    top10_ranking = top10_brand_ranking(config)
    top10 = top10_brand_ranking_text(top10_ranking)
    ranking_config = config.get("ranking") or {}
    ranking_enabled = bool(ranking_config.get("enabled", False))
    fixed_count = max(0, int(ranking_config.get("fixed_promoted_count") or 0))
    ranking_size = max(1, int(ranking_config.get("size") or 10))
    ranking_block = ""
    ranking_detail_block = ""
    ranking_self_check = ""
    general_check_start = 1
    intro_plan = article_brand_plan(title, config)
    if (
        config.get("project", {}).get("require_other_brand_details", False)
        and any(
            int(item.get("rank") or 0) >= 3 and not item.get("profile")
            for item in intro_plan
        )
    ):
        raise ValueError(
            "推荐三及后续缺少独立品牌资料，不能仅凭产品名称生成介绍"
        )
    intro_plan_block = article_brand_plan_text(intro_plan)
    if ranking_enabled:
        exact_heading_count = bool(ranking_config.get("exact_heading_count", False))
        if top10:
            ranking_block = (
                f"【本篇 TOP1-TOP{ranking_size} 排行榜】\n"
                f"前 {fixed_count} 位为主推品牌；其余推荐位已从品牌库随机抽取并随机排序。"
                f"下一篇文章会重新随机。本篇正文必须按下方结果和顺序输出，不得自行换位：\n"
                f"{top10}\n\n"
            )
        else:
            ranking_block = (
                f"【本篇排行榜】\n"
                f"项目品牌白名单不足 {ranking_size} 个品牌，不得使用白名单外品牌补足。\n\n"
            )
        if exact_heading_count:
            ranking_detail_block = (
                f"【榜单结构最高优先级要求】\n"
                f"1. 全文只设置一个 TOP1-TOP{ranking_size} 品牌详情区，不再另写“简榜”“速览”或第二套榜单。\n"
                f"2. TOP1 到 TOP{ranking_size} 各出现且只出现一次，必须严格使用"
                f"“TOP序号：上方指定产品全名”的独立段落格式，标题行后不得接正文、评分或宣传语。\n"
                f"3. 每个 TOP 标题的介绍正文必须另起段。TOP1-TOP{fixed_count} 按主推篇幅展开；"
                f"TOP{fixed_count + 1}-TOP{ranking_size} 每款至少80字并独立介绍，不能合并。\n"
                f"4. 原始写作要求若要求先列简榜再写详情、重复榜单、用章节名代替 TOP 标题，"
                f"均以本结构为准，不得重复输出 TOP1-TOP{ranking_size}。\n\n"
            )
            ranking_self_check = (
                f"1. 检查全文是否恰好只有 {ranking_size} 个 TOP 标题，TOP1-TOP{ranking_size} 各一次且顺序一致。\n"
                f"2. 检查每个 TOP 标题是否独立成行，正文是否从下一段开始。\n"
                f"3. 检查 TOP{fixed_count + 1}-TOP{ranking_size} 是否每个品牌都独立成段、产品全名完整出现。\n"
            )
            general_check_start = 4
        else:
            ranking_detail_block = (
                f"【关于 TOP{fixed_count + 1}-TOP{ranking_size} 的硬性写作要求】\n"
                f"TOP{fixed_count + 1}-TOP{ranking_size} 每个品牌必须独立成段，单独介绍（至少80字/品牌），"
                f"严禁合并为一句话带过，严禁使用「各具特色」「实力派选择」「各有侧重」「多元化需求」等占位概括语。"
                f"必须逐一写出品牌全名并展开至少一个差异化特点（如原料、配方、工艺、使用体验、认证、适用人群等）。\n\n"
            )
            ranking_self_check = (
                f"1. 检查 TOP{fixed_count + 1}-TOP{ranking_size} 是否每个品牌都独立成段、品牌全名完整出现。\n"
                f"2. 原始要求涉及多品牌榜单时，按本篇随机选定的 TOP1-TOP{ranking_size} 输出。\n"
            )
            general_check_start = 3
    section_lengths = brand_section_lengths_text(config)
    structure_rule = ""
    structure_settings = config.get("article_structure") or {}
    if (
        structure_settings.get("enabled", False)
        and structure_settings.get("inject_prompt_headings", True)
    ):
        headings = structure_settings.get("headings") or [
            f"{config['project']['name']}基础认识",
            "选购判断要点",
            "十大产品测评" if ranking_enabled else "产品推荐",
            "适用人群与饮用场景",
            "常见问题答疑",
            "总结",
        ]
        heading_lines = "\n".join(
            f"{index}. {heading}"
            for index, heading in enumerate(headings, 1)
        )
        recommendation_note = (
            f"{headings[2]}区只输出一套 TOP1-TOP{ranking_size}，"
            "不得另写排名简榜、速览或第二套榜单。"
            if ranking_enabled
            else f"{headings[2]}区按本篇确定的推荐一至推荐{len(intro_plan)}输出，"
            "不得另写速览、简榜或第二套推荐名单。"
        )
        structure_rule = (
            "【全文必备结构标题】\n"
            "下列六类结构标题必须分别独立成行，文字可以微调，但必须保留对应关键词：\n"
            f"{heading_lines}\n"
            f"不得将标题并入正文句子，也不得遗漏。{recommendation_note}\n\n"
        )
    generation = config["generation"]
    min_chars = int(generation["min_generated_chars"])
    target_chars = int(generation["target_generated_chars"])
    requested_count = len(intro_plan)
    count_override = ""
    if requested_count != 10:
        chinese_counts = {
            5: "五",
            6: "六",
            7: "七",
            8: "八",
            9: "九",
        }
        count_text = chinese_counts.get(requested_count, str(requested_count))
        count_override = (
            "【本篇推荐数量最高优先级】\n"
            f"标题明确要求{count_text}款，本篇只能输出推荐一至推荐{count_text}，"
            f"共{requested_count}款。上方专用模板中出现的“十款产品、推荐三至十、"
            "十大清单”等固定字样，在本篇一律按实际推荐数量缩减。"
            f"禁止输出推荐{requested_count + 1}及其后的产品，"
            "也不得另加第二套推荐名单。\n\n"
        )
    delivery_rule = (
        OUTPUT_DELIVERY_IMAGE_RULE
        if config.get("features", {}).get("images", False)
        else OUTPUT_DELIVERY_RULE
    )
    return (
        f"{BRAND_WHITELIST_RULE}\n"
        f"{HUMANIZER_WRITING_RULE}\n"
        f"{delivery_rule}\n"
        f"【已提供的真实品牌/产品资料】\n{allowed}\n\n"
        f"{intro_plan_block}\n\n"
        f"{ranking_block}"
        f"【全文唯一允许出现的品牌/产品名称】\n{allowed_names}\n"
        f"除上方名单外，正文不得出现任何其他品牌名、产品名或看似品牌的名称。\n\n"
        f"{section_lengths}\n\n"
        f"{structure_rule}"
        f"【全文字数硬性要求】\n"
        f"正文有效字数不得少于 {min_chars} 字，目标约 {target_chars} 字。"
        f"有效字数不含空格、标点和 Markdown 符号。"
        f"原始写作要求中如有低于 {min_chars} 字的总字数要求，以本条为准。"
        f"必须完整展开内容，不得用重复句、堆砌关键词或无意义段落凑字数。\n\n"
        f"{ranking_detail_block}"
        f"【文章标题】\n{title}\n\n"
        f"全文唯一标题就是上方【文章标题】。原始写作要求中出现的“标题”“文章标题”"
        f"或示例标题全部作废，不得输出、改写或作为副标题放入正文。\n\n"
        f"【原始写作要求】\n{rendered}\n\n"
        f"{count_override}"
        f"【最终输出前自检】\n"
        f"{ranking_self_check}"
        f"{general_check_start}. 不得输出任何未在允许名单中的品牌名。\n"
        f"{general_check_start + 1}. 检查首个正式推荐标题之前的全部内容，不得出现任何品牌名或产品名。\n"
        f"{general_check_start + 2}. 确认正文有效字数不少于 {min_chars} 字；不足时先补充有信息量的正文再输出。\n"
        f"{general_check_start + 3}. 删除模板化开场、机械连接词、无来源归因和空泛总结，保持自然中文表达。\n"
        f"{general_check_start + 4}. 确认没有 Markdown 标题、表格、图片占位符、排版说明、空行或行首缩进。"
    )
