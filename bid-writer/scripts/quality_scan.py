"""Scan bid drafts for common quality risks without modifying the source file."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


INTERNAL_MARKERS = (
    "根据资料显示", "本节这样写", "建议写成", "以下为优化版本",
    "支撑材料汇编", "响应细化", "自查结论", "废标风险自查",
    "图片来源", "帮助中心剪藏", "用于证明本节要求", "资料内容不作为",
)

TEMPLATE_MARKERS = (
    "责任角色", "输入资料", "处理步骤", "输出成果", "建立稳定关系",
    "按照招标人确认口径执行", "业务对象、流程对象、数据对象、权限对象", "验收关注",
)

ABSTRACT_MARKERS = (
    "形成闭环", "全面赋能", "全生命周期", "一体化", "高质量推进", "提升管理效能",
)


def read_docx(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", ns):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns)).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def read_paragraphs(path: Path) -> list[str]:
    if path.suffix.lower() == ".docx":
        return read_docx(path)
    if path.suffix.lower() in {".txt", ".md"}:
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    raise ValueError("Only .docx, .txt and .md files are supported")


def normalize(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[，。；：、“”‘’（）()\[\]【】,.!！?？;:]", "", text)


def load_config(path: Path | None) -> dict:
    if not path:
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def add_hits(paragraphs: list[str], markers: tuple[str, ...] | list[str]) -> list[dict]:
    hits = []
    for index, paragraph in enumerate(paragraphs, 1):
        for marker in markers:
            if marker and marker in paragraph:
                hits.append({"paragraph": index, "marker": marker, "text": paragraph[:240]})
    return hits


def scan(path: Path, config: dict) -> dict:
    paragraphs = read_paragraphs(path)
    normalized = [normalize(p) for p in paragraphs]
    duplicate_counts = Counter(p for p in normalized if len(p) >= 24)
    duplicates = [
        {"count": count, "text": key[:200]}
        for key, count in duplicate_counts.most_common()
        if count >= 2
    ]

    allowed = set(config.get("allowed_terms", []))
    forbidden = [term for term in config.get("forbidden_terms", []) if term not in allowed]
    heading_pattern = re.compile(r"^(?:[一二三四五六七八九十]+、|\d+(?:\.\d+){1,5}\s+)\S")
    manual_headings = [
        {"paragraph": index, "text": paragraph[:200]}
        for index, paragraph in enumerate(paragraphs, 1)
        if heading_pattern.match(paragraph)
    ]

    return {
        "file": str(path.resolve()),
        "paragraph_count": len(paragraphs),
        "internal_markers": add_hits(paragraphs, INTERNAL_MARKERS),
        "template_markers": add_hits(paragraphs, TEMPLATE_MARKERS),
        "abstract_markers": add_hits(paragraphs, ABSTRACT_MARKERS),
        "forbidden_terms": add_hits(paragraphs, forbidden),
        "duplicate_paragraphs": duplicates[:100],
        "manual_heading_candidates": manual_headings[:200],
        "notes": [
            "Manual heading candidates require Word-style inspection; visible numbering may be required by the tender.",
            "Keyword hits are risk clues and require human review.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan bid draft quality risks")
    parser.add_argument("input", type=Path)
    parser.add_argument("--config", type=Path, help="JSON with forbidden_terms and allowed_terms")
    parser.add_argument("--output", type=Path, help="Write JSON report to this path")
    args = parser.parse_args()

    report = scan(args.input, load_config(args.config))
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())