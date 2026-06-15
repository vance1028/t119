"""
生成模拟素材目录，用于测试 ai-watermark 工具。
用法: python scripts/generate_samples.py [输出目录]

生成内容:
- images/   : 若干小 PNG/JPG 图片（纯色块、渐变、简单图形）
- texts/    : 若干 .txt / .md / .json / .py / .csv 文本文件
- audio/    : 1-2 个假占位的音频文件（用于测试跳过逻辑）
- mixed/    : 混合目录，模拟平台素材
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


SAMPLE_TOOLS = ["GPT-4o", "Midjourney", "DALL-E 3", "Stable Diffusion", "Claude-3", "unknown"]
SAMPLE_AI_TOOL = random.choice(SAMPLE_TOOLS)

COLOR_PALETTES = [
    [(66, 133, 244), (234, 67, 53), (251, 188, 5), (52, 168, 83)],
    [(255, 107, 107), (255, 230, 109), (106, 216, 147), (78, 205, 196)],
    [(131, 96, 195), (46, 204, 113), (241, 196, 15), (231, 76, 60)],
    [(0, 172, 193), (225, 242, 254), (162, 230, 255), (255, 167, 82)],
    [(255, 154, 162), (250, 227, 183), (181, 234, 215), (199, 206, 234)],
]


def _make_random_image(size: tuple[int, int], seed: int) -> "Image.Image":
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    palette = rng.choice(COLOR_PALETTES)

    mode = rng.randint(0, 4)
    if mode == 0:
        for i, color in enumerate(palette):
            x0 = (i % 2) * (w // 2)
            y0 = (i // 2) * (h // 2)
            draw.rectangle([x0, y0, x0 + w // 2, y0 + h // 2], fill=color)
    elif mode == 1:
        for i in range(rng.randint(3, 8)):
            x = rng.randint(0, w)
            y = rng.randint(0, h)
            r = rng.randint(5, min(w, h) // 4)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=rng.choice(palette))
    elif mode == 2:
        c1 = rng.choice(palette)
        c2 = rng.choice(palette)
        for y in range(h):
            t = y / max(h - 1, 1)
            r = int(c1[0] * (1 - t) + c2[0] * t)
            g = int(c1[1] * (1 - t) + c2[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            draw.line([(0, y), (w, y)], fill=(r, g, b))
    elif mode == 3:
        for i in range(rng.randint(5, 15)):
            x1 = rng.randint(0, w)
            y1 = rng.randint(0, h)
            x2 = rng.randint(0, w)
            y2 = rng.randint(0, h)
            draw.line([(x1, y1), (x2, y2)], fill=rng.choice(palette), width=rng.randint(1, 4))
    else:
        for i in range(rng.randint(3, 10)):
            x1 = rng.randint(0, w - 5)
            y1 = rng.randint(0, h - 5)
            x2 = rng.randint(x1 + 2, w)
            y2 = rng.randint(y1 + 2, h)
            draw.rectangle([x1, y1, x2, y2], outline=rng.choice(palette), width=rng.randint(1, 3))

    try:
        draw.text((10, 10), f"AI-SAMPLE-{seed}", fill=(0, 0, 0))
    except Exception:
        pass

    return img


def generate_images(out_dir: Path, count: int = 6):
    if not _PIL_AVAILABLE:
        print("  [警告] Pillow 未安装，跳过图片生成。请先 pip install Pillow", file=sys.stderr)
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = [(128, 128), (256, 192), (192, 256), (320, 240), (200, 200)]
    for i in range(count):
        size = random.choice(sizes)
        seed = random.randint(1, 99999)
        img = _make_random_image(size, seed)
        name = f"ai_image_{i+1:02d}"
        fmt = random.choice(["png", "png", "jpeg", "png"])
        if fmt == "png":
            path = out_dir / f"{name}.png"
            img.save(path, format="PNG")
        else:
            path = out_dir / f"{name}.jpg"
            img.convert("RGB").save(path, format="JPEG", quality=92)
        print(f"  生成图片: {path}")


def generate_texts(out_dir: Path, count: int = 8):
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = [
        ("article_01.txt", "txt", """
# 关于人工智能在内容创作中的应用

近年来，人工智能技术在内容创作领域取得了显著进展。
从文本生成到图像创作，AI正在重塑我们生产和消费内容的方式。

本文将探讨以下几个方面：
1. 大语言模型的能力边界
2. 多模态生成的应用场景
3. 内容溯源与合规标识的重要性
4. 未来发展趋势展望

随着监管要求的日益严格，AI生成内容的可追溯性变得愈发重要。
""".strip()),
        ("readme.md", "md", """
# 示例项目

这是一个模拟的项目 README 文件。

## 功能

- 批量处理素材
- 支持多种文件格式
- 元数据标注

## 使用

```bash
python run.py --input ./data
```

## 许可

MIT License
""".strip()),
        ("config.json", "json", """
{
  "project": "sample-content",
  "version": "1.2.0",
  "features": {
    "batch": true,
    "retry": 3,
    "timeout": 30
  },
  "tags": ["demo", "sample", "ai"],
  "description": "这是一个用于测试的示例配置文件，包含JSON格式的结构化数据。"
}
""".strip()),
        ("utils.py", "py", """
\"\"\"工具函数集合。\"\"\"
from __future__ import annotations

import hashlib
from typing import Iterable


def compute_hash(data: bytes, algo: str = "sha256") -> str:
    \"\"\"计算数据的哈希摘要。\"\"\"
    h = hashlib.new(algo)
    h.update(data)
    return h.hexdigest()


def chunked(seq: Iterable, size: int):
    \"\"\"将序列按固定大小分块。\"\"\"
    buf = []
    for item in seq:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


if __name__ == "__main__":
    print(compute_hash(b"hello world"))
""".strip()),
        ("report.csv", "csv", """
id,name,category,score,date
1,用户调研白皮书,市场,92,2026-06-10
2,产品设计图稿,设计,88,2026-06-11
3,营销文案初稿,市场,75,2026-06-12
4,API接口文档,技术,95,2026-06-13
5,客户反馈汇总,运营,80,2026-06-14
""".strip()),
        ("poem.txt", "txt", """
夏夜星

晚风轻拂旧城墙，
一盏孤灯映寒窗。
星河欲转千帆舞，
人间烟火入梦长。
""".strip()),
        ("notes.xml", "xml", """
<?xml version="1.0" encoding="UTF-8"?>
<notes>
  <note id="1">
    <title>项目启动</title>
    <author>AI Assistant</author>
    <content>制定项目计划，明确阶段性目标。</content>
  </note>
  <note id="2">
    <title>中期检查</title>
    <author>AI Assistant</author>
    <content>按时完成80%任务，启动下一阶段工作。</content>
  </note>
</notes>
""".strip()),
        ("data.yaml", "yaml", """
dataset: sample_dataset
version: 2
description: >
  这是一个示例数据集配置文件，使用 YAML 格式定义。
columns:
  - name: id
    type: integer
  - name: label
    type: string
  - name: value
    type: float
train_test_split:
  ratio: 0.8
  seed: 42
""".strip()),
    ]

    for i in range(count):
        idx = i % len(samples)
        base_name, ext, content = samples[idx]
        if i >= len(samples):
            content = content + f"\n\n--- 副本 {i + 1} ---\n"
        path = out_dir / base_name if i == samples.index(samples[idx]) else out_dir / f"{Path(base_name).stem}_{i:02d}{Path(base_name).suffix}"
        try:
            path = out_dir / f"{Path(base_name).stem}_{i+1:02d}.{ext}"
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  生成文本: {path}")
        except Exception as e:
            print(f"  [错误] {path}: {e}")


def generate_audio_placeholders(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    placeholders = [
        ("podcast_ep01.mp3", b"FAKEMP3" + b"\x00" * 1024),
        ("music_bg.wav", b"RIFF" + b"\x00" * 512),
    ]
    for name, data in placeholders:
        path = out_dir / name
        with open(path, "wb") as f:
            f.write(data)
        print(f"  生成占位文件: {path}")


def generate_mixed(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    sub1 = out_dir / "campaign_summer"
    sub2 = out_dir / "campaign_autumn" / "assets"
    sub1.mkdir(parents=True, exist_ok=True)
    sub2.mkdir(parents=True, exist_ok=True)

    with open(sub1 / "brief.txt", "w", encoding="utf-8") as f:
        f.write("夏季营销活动素材需求文档\n\n目标用户：年轻消费群体\n素材格式：图片+文案\n")
    with open(sub2 / "caption.txt", "w", encoding="utf-8") as f:
        f.write("秋季新品推广文案 - 温暖上市\n")
    print(f"  生成目录结构: {out_dir}")


def main():
    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).resolve()
    else:
        root = Path(__file__).resolve().parent.parent / "samples"
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    print(f"将在以下目录生成模拟素材: {root}")

    random.seed(42)
    generate_images(root / "images", count=6)
    generate_texts(root / "texts", count=10)
    generate_audio_placeholders(root / "audio")
    generate_mixed(root / "mixed")

    print(f"\n完成！模拟素材已生成到: {root}")
    print("  建议用以下命令快速开始:")
    print(f"    set AI_WATERMARK_KEY=my-secret-key")
    print(f"    python -m ai_watermark scan \"{root}\"")


if __name__ == "__main__":
    main()
