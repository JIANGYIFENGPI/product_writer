from __future__ import annotations

import csv
import hashlib
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tmp" / "baifanqie_image_extract_20260611"
PROJECT = ROOT / "projects" / "baifanqie_yanxianan"
IMAGES = PROJECT / "images"
MANIFEST = ROOT / "tmp" / "baifanqie_contact_sheet.txt"

# Neutral images must contain no brand, logo, recognizable bottle, package,
# or product-holding scene. Keep only ingredient/education/skin-context art.
NEUTRAL = set(range(1, 13)) | set(range(15, 27)) | {62, 63}
CHIDASHI = {29, 65, 66}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def main() -> int:
    if IMAGES.exists():
        shutil.rmtree(IMAGES)
    indexed: dict[int, Path] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        number, relative = line.split("\t", 1)
        indexed[int(number)] = SOURCE / Path(relative)

    rows: list[dict[str, str]] = []
    for index, source in sorted(indexed.items()):
        if index in NEUTRAL:
            slot = "neutral"
            brand = "中性素材"
        elif index in CHIDASHI:
            slot = "chidashi"
            brand = "赤大师"
        else:
            slot = "xianfangsi"
            brand = "仙芳思"

        target_dir = IMAGES / slot
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower()
        target_name = f"{slot}_{index:02d}_{digest(source)}{suffix}"
        target = target_dir / target_name
        shutil.copy2(source, target)
        rows.append(
            {
                "file": target_name,
                "brand": brand,
                "slot": slot,
                "source": str(source.relative_to(SOURCE)),
                "sha256_12": digest(source),
            }
        )

    catalog = PROJECT / "image_catalog.csv"
    with catalog.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["file", "brand", "slot", "source", "sha256_12"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"imported={len(rows)}")
    for slot in ("neutral", "xianfangsi", "chidashi"):
        print(f"{slot}={len(list((IMAGES / slot).glob('*')))}")
    print("jiaoxiaoyan=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
