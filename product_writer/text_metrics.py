from __future__ import annotations

import re


def article_char_count(text: str) -> int:
    """Count正文有效字数，排除空白、标点和 Markdown 格式符号。"""
    return len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fffA-Za-z0-9]", text))
