from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--columns", type=int, default=4)
    args = parser.parse_args()

    files = sorted(
        path
        for path in args.source.rglob("*")
        if path.is_file() and path.suffix.lower() in EXTENSIONS
    )
    cell_width = 360
    image_height = 270
    label_height = 54
    rows = (len(files) + args.columns - 1) // args.columns
    sheet = Image.new(
        "RGB",
        (cell_width * args.columns, (image_height + label_height) * rows),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for index, path in enumerate(files):
        row, column = divmod(index, args.columns)
        x = column * cell_width
        y = row * (image_height + label_height)
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((cell_width - 12, image_height - 12))
            image_x = x + (cell_width - image.width) // 2
            image_y = y + (image_height - image.height) // 2
            sheet.paste(image, (image_x, image_y))
        relative = path.relative_to(args.source)
        label = f"{index + 1:02d} {relative}"
        draw.rectangle((x, y + image_height, x + cell_width, y + image_height + label_height), fill="white")
        draw.text((x + 6, y + image_height + 5), label, fill="black", font=font)
        draw.rectangle((x, y, x + cell_width - 1, y + image_height + label_height - 1), outline="#999999")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    manifest = args.output.with_suffix(".txt")
    manifest.write_text(
        "\n".join(f"{index + 1:02d}\t{path.relative_to(args.source)}" for index, path in enumerate(files)),
        encoding="utf-8",
    )
    print(f"images={len(files)}")
    print(f"sheet={args.output}")
    print(f"manifest={manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
