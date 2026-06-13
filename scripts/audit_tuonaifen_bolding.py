from __future__ import annotations

import json
import re
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "tuonaifen"

LABEL_PREFIXES = (
    "核心",
    "奶源",
    "配料",
    "工艺",
    "口感",
    "营养",
    "认证",
    "安全",
    "适用",
    "适合",
    "人群",
    "优势",
    "亮点",
    "特点",
    "标准",
    "维度",
    "建议",
    "提醒",
    "注意",
    "判断",
    "辨别",
    "选购",
    "冲调",
    "饮用",
    "总结",
    "结语",
    "答疑",
    "问答",
)


def has_image(paragraph) -> bool:
    return bool(paragraph._element.xpath(".//w:drawing | .//w:pict"))


def all_text_bold(paragraph) -> bool:
    runs = [run for run in paragraph.runs if run.text]
    return bool(runs) and all(bool(run.bold) for run in runs)


def looks_like_missing_heading(text: str, next_text: str) -> bool:
    stripped = text.strip().strip("【】[]")
    if not stripped or len(stripped) > 36:
        return False
    if any(mark in stripped for mark in "。！？!?，,；;"):
        return False
    if re.match(r"^TOP\s*\d+", stripped, flags=re.IGNORECASE):
        return True
    if stripped.endswith(("：", ":")):
        return True
    if any(stripped.startswith(prefix) for prefix in LABEL_PREFIXES):
        return len(next_text.strip()) >= 35
    return False


def main() -> int:
    findings = []
    for path in sorted(OUTPUT_DIR.glob("*.docx")):
        document = Document(path)
        paragraphs = list(document.paragraphs)
        for index, paragraph in enumerate(paragraphs):
            if has_image(paragraph) or all_text_bold(paragraph):
                continue
            text = paragraph.text.strip()
            next_text = paragraphs[index + 1].text.strip() if index + 1 < len(paragraphs) else ""
            if looks_like_missing_heading(text, next_text):
                findings.append(
                    {
                        "file": path.name,
                        "paragraph": index,
                        "text": text,
                        "next": next_text[:60],
                    }
                )
    print(json.dumps({"count": len(findings), "findings": findings}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
