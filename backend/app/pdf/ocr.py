"""Optional Tesseract OCR fallback for scanned / image-only pages.

Uses the ``tesseract`` CLI (TSV output) so we get line bounding boxes, which
lets header/footer cleaning work on OCR'd pages too. If the binary or the
requested language data is missing, ``available()`` returns False and pages
are flagged for review instead of being silently skipped.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .types import Block, Line


@dataclass
class OcrResult:
    blocks: list[Block]
    mean_confidence: float


class TesseractOCR:
    def __init__(self, languages: str = "ind+eng", dpi: int = 300, binary: str = "tesseract"):
        self.requested = languages
        self.dpi = dpi
        self.binary = shutil.which(binary)
        self.languages = self._resolve_languages()

    def _installed_languages(self) -> set[str]:
        if not self.binary:
            return set()
        try:
            out = subprocess.run(
                [self.binary, "--list-langs"], capture_output=True, text=True, timeout=20
            )
        except (OSError, subprocess.TimeoutExpired):
            return set()
        lines = (out.stdout + out.stderr).splitlines()
        return {ln.strip() for ln in lines if ln.strip() and " " not in ln.strip()}

    def _resolve_languages(self) -> str | None:
        installed = self._installed_languages()
        wanted = [l for l in self.requested.split("+") if l in installed]
        return "+".join(wanted) if wanted else None

    def available(self) -> bool:
        return bool(self.binary and self.languages)

    def describe(self) -> dict:
        return {
            "available": self.available(),
            "binary": bool(self.binary),
            "languages": self.languages,
            "requested": self.requested,
        }

    def ocr_page(self, page, page_no: int) -> OcrResult:
        """OCR a PyMuPDF page. Coordinates are mapped back to PDF points."""
        scale = self.dpi / 72.0
        pix = page.get_pixmap(dpi=self.dpi, colorspace="gray")
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "page.png"
            pix.save(img)
            proc = subprocess.run(
                [self.binary, str(img), "stdout", "-l", self.languages, "--psm", "3", "tsv"],
                capture_output=True, text=True, timeout=300,
            )
        if proc.returncode != 0:
            raise RuntimeError("tesseract failed")
        return parse_tsv(proc.stdout, page_no, scale)


def parse_tsv(tsv: str, page_no: int, scale: float) -> OcrResult:
    lines: dict[tuple, dict] = {}
    confs: list[float] = []
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        text = (row.get("text") or "").strip()
        if row.get("level") != "5" or not text:
            continue
        conf = float(row.get("conf") or -1)
        if conf >= 0:
            confs.append(conf)
        key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        x0, y0 = int(row["left"]) / scale, int(row["top"]) / scale
        x1, y1 = x0 + int(row["width"]) / scale, y0 + int(row["height"]) / scale
        entry = lines.setdefault(key, {"words": [], "bbox": [x0, y0, x1, y1]})
        entry["words"].append(text)
        b = entry["bbox"]
        entry["bbox"] = [min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)]

    blocks: dict[tuple, list[Line]] = {}
    for (blk, par, _), entry in sorted(lines.items()):
        x0, y0, x1, y1 = entry["bbox"]
        # Line height approximates font size for heading detection.
        blocks.setdefault((blk, par), []).append(
            Line(" ".join(entry["words"]), x0, y0, x1, y1, size=round((y1 - y0) * 0.8, 1),
                 bold=False, page_no=page_no)
        )
    result = [Block(ls, page_no) for _, ls in sorted(blocks.items())]
    mean = sum(confs) / len(confs) if confs else 0.0
    return OcrResult(result, mean)
