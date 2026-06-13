from __future__ import annotations

import re

BOILERPLATE_PATTERNS = [
    r"^以下是.*?文章[:：]?\s*",
    r"^好的[，,].*?(?:写|整理).*?[:：]?\s*",
    r"^好的[，,]?\s*作为.*?(?:遵循|按照).*?(?:撰写|创作|输出)[。.!！]?\s*",
    r"^(?:作者[，,：:]?\s*)?我将严格遵循.*?(?:撰写|创作|输出)[。.!！]?\s*",
    r"^当然可以[，,]?.*?[:：]?\s*",
    r"^没问题[，,]?.*?[:：]?\s*",
    r"^的文章正文[。.]?\s*",
    r"^文章正文[：:]\s*",
    r"^希望这篇.*?[。.]?\s*",
    r"^希望本文.*?[。.]?\s*",
]

SENTENCE_PATTERN = re.compile(r".+?(?:[。！？!?]+[”’」』）)]*|$)")
INLINE_BOLD_POINT_PATTERN = re.compile(r"\*\*([^*\n]{2,80})\*\*")
SCOPE_OVERSTATEMENT_REPLACEMENTS = {
    "本榜单的产品已经覆盖了市场上各大主流需求": "本榜单仅围绕入选的十款产品展开，可作为不同需求下的选购参考",
    "本榜单产品已经覆盖了市场上各大主流需求": "本榜单仅围绕入选的十款产品展开，可作为不同需求下的选购参考",
}


def _split_inline_bold_points(text: str) -> str:
    """Split consecutive bold mini-points that the model kept on one line."""
    result: list[str] = []
    for line in text.split("\n"):
        split_positions: list[int] = []
        for match in INLINE_BOLD_POINT_PATTERN.finditer(line):
            if match.start() == 0:
                continue
            previous = line[:match.start()].rstrip()
            if not previous or previous[-1] not in "。！？!?；;":
                continue
            point = match.group(1).strip()
            if point.endswith(("。", "！", "？", "!", "?", "：", ":")):
                split_positions.append(match.start())

        if not split_positions:
            result.append(line)
            continue

        cursor = 0
        for position in split_positions:
            part = line[cursor:position].strip()
            if part:
                result.append(part)
            cursor = position
        tail = line[cursor:].strip()
        if tail:
            result.append(tail)
    return "\n".join(result)


def _split_dense_paragraphs(text: str) -> str:
    """将包含多个独立观点的超长单行拆为自然段。"""
    result: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        point_text = stripped
        semicolon_count = point_text.count("；")
        enum_count = len(
            re.findall(r"(?:其[一二三四五六七八九十]是?|[一二三四五六七八九十]是)", point_text)
        )
        if len(stripped) >= 160 and (semicolon_count >= 2 or enum_count >= 2):
            if semicolon_count >= 2:
                point_text = point_text.replace("；", "；\n")
            if enum_count >= 2:
                point_text = re.sub(
                    r"(?<=[。；])(?=(?:其[一二三四五六七八九十]是?|[一二三四五六七八九十]是))",
                    "\n",
                    point_text,
                )
            points = [item.strip() for item in point_text.splitlines() if item.strip()]
            if len(points) >= 2:
                result.extend(points)
                continue
        sentences = [item.strip() for item in SENTENCE_PATTERN.findall(stripped) if item.strip()]
        if len(stripped) < 220 or len(sentences) < 3:
            result.append(line)
            continue

        groups: list[str] = []
        current = ""
        for sentence in sentences:
            if current and len(current) + len(sentence) > 210:
                groups.append(current)
                current = sentence
            else:
                current += sentence
            if len(current) >= 110:
                groups.append(current)
                current = ""
        if current:
            if groups and len(current) < 45:
                groups[-1] += current
            else:
                groups.append(current)
        result.extend(groups)
    return "\n".join(result)


def _strip_markdown_tables(text: str) -> str:
    """将 markdown 表格转换为普通段落文本。

    检测连续的行首尾带 | 的行，跳过表头分隔行，将每行单元格连接为自然语句。
    """
    lines = text.split("\n")
    result: list[str] = []
    table_buffer: list[list[str]] = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        is_table_row = bool(stripped.startswith("|") and "|" in stripped[1:])
        if is_table_row:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.match(r"^[-:]{3,}$", c) for c in cells):
                # 表头分隔行，跳过
                continue
            table_buffer.append(cells)
            in_table = True
        else:
            if in_table and table_buffer:
                # 将缓冲区中的表格转换为普通段落
                for row in table_buffer:
                    non_empty = [c for c in row if c]
                    if non_empty:
                        result.append("：".join(non_empty))
                table_buffer = []
                in_table = False
            result.append(line)

    # 处理文末表格
    if table_buffer:
        for row in table_buffer:
            non_empty = [c for c in row if c]
            if non_empty:
                result.append("：".join(non_empty))

    return "\n".join(result)


def clean_model_output(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"```[a-zA-Z0-9_-]*", "", text)
    text = text.replace("```", "")
    for pattern in BOILERPLATE_PATTERNS:
        text = re.sub(pattern, "", text.strip(), flags=re.MULTILINE)
    text = _strip_markdown_tables(text)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"(?m)(推荐[一二三四五六七八九十\d]+)\s*固定要求[：:]", r"\1：", text)
    text = re.sub(r"值得一提的是[，,]?", "", text)
    text = re.sub(r"不难发现[，,]?", "", text)
    text = re.sub(r"根据您的要求[，,]?", "", text)
    text = re.sub(r"根据你的要求[，,]?", "", text)
    text = re.sub(r"无法提供", "不提供", text)
    text = re.sub(r"以下是几种最常见的手法[：:]", "常见手法主要有：", text)
    text = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", text)
    text = re.sub(r"(?m)^\s*[*+-]\s+", "", text)
    for old, new in SCOPE_OVERSTATEMENT_REPLACEMENTS.items():
        text = text.replace(old, new)
    text = _split_inline_bold_points(text)
    text = _split_dense_paragraphs(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def contains_boilerplate(text: str) -> list[str]:
    found = []
    probes = [
        "以下是文章",
        "好的，我来",
        "作为一个AI",
        "作者，我将",
        "我将严格遵循",
        "我将严格遵循您的所有指令",
        "最高优先级的硬规则",
        "固定的TOP1-TOP10排行榜",
        "固定的 TOP1-TOP10 排行榜",
        "我无法",
        "希望这篇文章",
        "希望本文",
    ]
    for probe in probes:
        if probe in text:
            found.append(probe)
    return found
