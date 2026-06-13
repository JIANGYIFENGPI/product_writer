from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from product_writer.bolding import is_structure_line
from product_writer.config import load_project_config
from product_writer.prompt_loader import load_terms
from product_writer.renderer import (
    add_formatted_text,
    fix_normal_style,
    set_para,
    set_run_font,
)


def has_image(paragraph) -> bool:
    return bool(paragraph._element.xpath(".//w:drawing | .//w:pict"))


def main() -> int:
    output_dir = ROOT / "output" / "tuonaifen"
    config = load_project_config(ROOT, "tuonaifen")
    terms = load_terms(ROOT / "projects" / "tuonaifen", config)
    documents = sorted(output_dir.glob("*.docx"))
    backup_dir = ROOT / "tmp" / f"tuonaifen_before_bolding_fix_{datetime.now():%Y%m%d_%H%M%S}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for path in documents:
        shutil.copy2(path, backup_dir / path.name)

    changed_paragraphs = 0
    for path in documents:
        document = Document(path)
        fix_normal_style(document)
        for index, paragraph in enumerate(document.paragraphs):
            paragraph.style = document.styles["Normal"]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            set_para(paragraph)
            if has_image(paragraph):
                continue
            text = paragraph.text
            bold_all = index == 0 or is_structure_line(text.strip())
            before = [(run.text, bool(run.bold)) for run in paragraph.runs]
            for run in list(paragraph.runs):
                run._element.getparent().remove(run._element)
            add_formatted_text(paragraph, text, terms, bold_all=bold_all)
            for run in paragraph.runs:
                set_run_font(run, bold=bool(run.bold))
            after = [(run.text, bool(run.bold)) for run in paragraph.runs]
            if before != after:
                changed_paragraphs += 1
        document.save(path)

    print(f"backup={backup_dir}")
    print(f"documents={len(documents)}")
    print(f"changed_paragraphs={changed_paragraphs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
