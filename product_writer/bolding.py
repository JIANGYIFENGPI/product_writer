from __future__ import annotations

import re

STRUCTURE_PATTERNS = [
    r"^[一二三四五六七八九十]+[、.．]\s*.+",
    r"^（[一二三四五六七八九十]+）\s*.+",
    r"^\([一二三四五六七八九十]+\)\s*.+",
    r"^\d+[、.．]\s*.+",
    r"^第[一二三四五六七八九十\d]+章[：:].+",
    r"^终章[：:].+",
    r"^.{2,30}[:：]$",
    r"^(推荐[一二三四五六七八九十\d]+|TOP\s*\d+|Top\s*\d+|top\s*\d+|NO\.?\s*\d+|No\.?\s*\d+|no\.?\s*\d+).+",
    r"^(第[一二三四五六七八九十\d]+名|首推|次推).+",
    r"^(标签|测评总结|推荐总结|选购总结|综合推荐|写在最后|结语)[:：]?.*",
]
STRUCTURE_HINTS = [
    "章",
    "篇",
    "节",
    "榜单",
    "排行",
    "排行榜",
    "推荐",
    "测评",
    "评测",
    "盘点",
    "指南",
    "基础",
    "科普",
    "概念",
    "知识",
    "选购",
    "选择",
    "购买",
    "判断",
    "核验",
    "核对",
    "问题",
    "常见",
    "技巧",
    "法则",
    "标准",
    "标尺",
    "逻辑",
    "方法",
    "避坑",
    "总结",
    "结论",
    "声明",
    "人群",
    "适用",
    "答疑",
    "问答",
    "解答",
    "详解",
    "核心",
    "优势",
    "亮点",
    "特点",
    "配料",
    "原料",
    "专利",
    "工艺",
    "口感",
    "营养",
    "认证",
    "安全",
    "冲调",
    "饮用",
    "销量",
    "复购",
    "结尾",
    "收束",
]
BODY_PUNCTUATION = set("。！？!?")
def _looks_like_heading(text: str) -> bool:
    stripped = text.strip().strip("【】[]")
    if not stripped:
        return False
    length = len(stripped)
    if length > 60:
        return False
    if any(mark in stripped for mark in BODY_PUNCTUATION):
        return False
    comma_count = sum(stripped.count(mark) for mark in "，,；;")
    if comma_count >= 2:
        return False

    has_heading_punctuation = any(mark in stripped for mark in "：:——-·")
    has_hint = any(hint in stripped for hint in STRUCTURE_HINTS)
    has_rank_or_section = bool(
        re.match(
            r"^(第[一二三四五六七八九十\d]+|[一二三四五六七八九十\d]+[、.．]|TOP\s*\d+|No\.?\s*\d+|NO\.?\s*\d+|推荐[一二三四五六七八九十\d]+|终章|结语|总结|声明)",
            stripped,
            flags=re.IGNORECASE,
        )
    )
    if has_rank_or_section:
        return True
    if has_heading_punctuation and has_hint:
        return True
    if length <= 24 and has_hint:
        return True
    return False


def is_structure_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > 80:
        return False
    if any(re.match(pattern, stripped) for pattern in STRUCTURE_PATTERNS):
        return True
    if _looks_like_heading(stripped):
        return True
    return stripped.startswith(("推荐", "TOP", "Top", "No.", "NO.", "首推", "次推"))


def leading_emphasis_end(text: str) -> int:
    """Return the end offset of a short leading label that should be bold."""
    stripped = text.lstrip()
    leading_spaces = len(text) - len(stripped)
    qa_match = re.match(r"^(?:Q\d+|问|答)[：:]", stripped, flags=re.IGNORECASE)
    if qa_match:
        # FAQ questions are short structural lines; bold the complete question.
        if len(stripped) <= 60 and stripped.endswith(("？", "?")):
            return len(text)
        return leading_spaces + qa_match.end()

    colon_positions = [position for position in (stripped.find("："), stripped.find(":")) if position >= 0]
    if not colon_positions:
        return 0
    colon = min(colon_positions)
    label = stripped[:colon].strip()
    if not 1 <= len(label) <= 16:
        return 0
    return leading_spaces + colon + 1


def strip_markdown_bold(text: str) -> str:
    return re.sub(r"\*\*(.*?)\*\*", r"\1", text)


def split_markdown_bold(text: str) -> list[tuple[str, bool]]:
    parts: list[tuple[str, bool]] = []
    cursor = 0
    for match in re.finditer(r"\*\*(.+?)\*\*", text):
        if match.start() > cursor:
            parts.append((text[cursor:match.start()], False))
        parts.append((match.group(1), True))
        cursor = match.end()
    if cursor < len(text):
        parts.append((text[cursor:], False))
    if not parts:
        parts.append((text, False))
    return [(chunk.replace("*", ""), bold) for chunk, bold in parts if chunk.replace("*", "")]


def split_by_terms(text: str, terms: list[str]) -> list[tuple[str, bool]]:
    if not text or not terms:
        return [(text, False)]

    matches: list[tuple[int, int]] = []
    occupied: list[tuple[int, int]] = []
    for term in sorted({term for term in terms if term}, key=len, reverse=True):
        start = 0
        while True:
            index = text.find(term, start)
            if index == -1:
                break
            end = index + len(term)
            if not any(index < used_end and end > used_start for used_start, used_end in occupied):
                matches.append((index, end))
                occupied.append((index, end))
            start = index + 1

    if not matches:
        return [(text, False)]

    matches.sort()
    parts: list[tuple[str, bool]] = []
    cursor = 0
    for start, end in matches:
        if start > cursor:
            parts.append((text[cursor:start], False))
        parts.append((text[start:end], True))
        cursor = end
    if cursor < len(text):
        parts.append((text[cursor:], False))
    return parts
