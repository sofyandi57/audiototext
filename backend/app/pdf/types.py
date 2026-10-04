from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    bold: bool
    page_no: int


@dataclass
class Block:
    lines: list[Line]
    page_no: int

    @property
    def x0(self) -> float:
        return min(l.x0 for l in self.lines)

    @property
    def y0(self) -> float:
        return min(l.y0 for l in self.lines)

    @property
    def x1(self) -> float:
        return max(l.x1 for l in self.lines)

    @property
    def y1(self) -> float:
        return max(l.y1 for l in self.lines)

    @property
    def text(self) -> str:
        return " ".join(l.text for l in self.lines)


@dataclass
class Page:
    page_no: int
    width: float
    height: float
    blocks: list[Block]
    text_source: str  # text | ocr | none
    has_images: bool
    needs_review: bool = False
    review_reason: str | None = None
    ocr_confidence: float | None = None

    @property
    def char_count(self) -> int:
        return sum(len(l.text.strip()) for b in self.blocks for l in b.lines)


@dataclass
class Element:
    kind: str  # heading | paragraph
    text: str
    page_no: int
    level: int = 1
    end_page: int | None = None


@dataclass
class Section:
    title: str
    level: int
    paragraphs: list[str] = field(default_factory=list)
    start_page: int | None = None
    end_page: int | None = None
    needs_review: bool = False

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)
