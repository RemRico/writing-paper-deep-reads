#!/usr/bin/env python3
"""
crop_figure.py — 从 PDF 页面渲染 + 可选按命名区域粗裁，输出到 images/。

设计目标：
  用户精读论文时最常见的需求是"拿到某一页的某一块图"。精细 crop 成本高
  （反复目测 + 调坐标）；本脚本提供"命名区域"快捷裁剪，90% 情况一把过。
  如果命名区域不够精确，用户自己用图片工具再微调即可。

用法：
  crop_figure.py PDF PAGE [--region REGION] [--out PATH] [--dpi DPI]

支持的 region（默认 full-page）：
  full-page
  top-half, bottom-half, left-half, right-half
  top-third, middle-third, bottom-third
  top-left, top-right, bottom-left, bottom-right
  top-quarter, bottom-quarter
  center (中间 60% × 60%)

示例：
  crop_figure.py paper.pdf 3 --out images/paper-fig1.png
  crop_figure.py paper.pdf 5 --region top-half --out images/paper-fig2.png
  crop_figure.py paper.pdf 7 --region bottom-third --dpi 300

依赖：pdftoppm (poppler), PIL / Pillow
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("❌ 需要 PIL: pip install Pillow")


REGIONS = {
    "full-page": (0, 0, 1.0, 1.0),
    "top-half": (0, 0, 1.0, 0.5),
    "bottom-half": (0, 0.5, 1.0, 1.0),
    "left-half": (0, 0, 0.5, 1.0),
    "right-half": (0.5, 0, 1.0, 1.0),
    "top-third": (0, 0, 1.0, 0.34),
    "middle-third": (0, 0.33, 1.0, 0.67),
    "bottom-third": (0, 0.66, 1.0, 1.0),
    "top-quarter": (0, 0, 1.0, 0.27),
    "bottom-quarter": (0, 0.73, 1.0, 1.0),
    "top-left": (0, 0, 0.5, 0.5),
    "top-right": (0.5, 0, 1.0, 0.5),
    "bottom-left": (0, 0.5, 0.5, 1.0),
    "bottom-right": (0.5, 0.5, 1.0, 1.0),
    "center": (0.2, 0.2, 0.8, 0.8),
}


def render_page(pdf_path: Path, page: int, dpi: int, out_prefix: Path) -> Path:
    """渲染指定物理页到 PNG。返回渲染出的文件路径。"""
    subprocess.run(
        [
            "pdftoppm", "-png",
            "-r", str(dpi),
            "-f", str(page),
            "-l", str(page),
            str(pdf_path),
            str(out_prefix),
        ],
        check=True,
    )
    # pdftoppm 输出 `{prefix}-{page}.png` 或 `{prefix}-0{page}.png`
    for suffix in [f"-{page}.png", f"-{page:02d}.png", f"-{page:03d}.png"]:
        candidate = out_prefix.parent / f"{out_prefix.name}{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"pdftoppm 未输出预期文件，prefix={out_prefix}")


def crop_region(png_path: Path, region: str) -> Image.Image:
    """按命名区域裁剪。"""
    if region not in REGIONS:
        raise ValueError(f"未知区域 {region}，可选：{list(REGIONS.keys())}")
    img = Image.open(png_path)
    w, h = img.size
    x0, y0, x1, y1 = REGIONS[region]
    box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
    return img.crop(box)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pdf", type=Path, help="PDF 路径")
    p.add_argument("page", type=int, help="物理页码（从 1 开始，注意 arXiv PDF 物理页常被打乱）")
    p.add_argument("--region", default="full-page", help=f"命名区域，默认 full-page。可选：{list(REGIONS.keys())}")
    p.add_argument("--out", type=Path, required=True, help="输出 PNG 路径（建议 images/{paper-slug}-fig{N}.png）")
    p.add_argument("--dpi", type=int, default=200, help="渲染 DPI，默认 200（250-300 可获得更清晰结果）")
    args = p.parse_args()

    if not args.pdf.exists():
        sys.exit(f"❌ PDF 不存在：{args.pdf}")

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # 用带时间戳的临时前缀，避免 Read 工具的 PNG 渲染缓存错位（见 SKILL.md Pitfalls）
    import time
    stamp = int(time.time() * 1000)
    with tempfile.TemporaryDirectory() as tmpdir:
        prefix = Path(tmpdir) / f"render-{stamp}"
        rendered = render_page(args.pdf, args.page, args.dpi, prefix)
        if args.region == "full-page":
            # 直接重命名，避免多一次 decode/encode
            import shutil
            shutil.copy(rendered, args.out)
        else:
            cropped = crop_region(rendered, args.region)
            cropped.save(args.out)

    size_kb = args.out.stat().st_size / 1024
    print(f"✅ 写入 {args.out} ({size_kb:.1f} KB, region={args.region}, page={args.page}, dpi={args.dpi})")

    # 打印 md5，校验时用这个做 ground truth，不要信 Read 的 preview
    try:
        md5_cmd = ["md5", "-q", str(args.out)] if sys.platform == "darwin" else ["md5sum", str(args.out)]
        md5_out = subprocess.check_output(md5_cmd, text=True).strip().split()[0]
        print(f"   md5: {md5_out}")
    except Exception:
        pass
    print(f"   ⚠️ 校验时用 md5 / file size，不要信 Read 的 image preview（有缓存错位风险）")


if __name__ == "__main__":
    main()
