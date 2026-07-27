"""Block document model. Markdown and HTML render from this same structure
(toolkit D-029, re-implemented): converting one format into the other would
need a parser, and two hand-maintained outputs would drift — with one model
they cannot. A section in one is a section in the other.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Heading:
    text: str
    level: int = 2


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class KeyValues:
    items: tuple  # ((key, value), ...) — order preserved

    def __post_init__(self):
        for pair in self.items:
            if len(pair) != 2:
                raise ValueError("KeyValues items must be (key, value) pairs")


@dataclass(frozen=True)
class Table:
    headers: tuple
    rows: tuple      # tuple of row-tuples, all matching len(headers)
    caption: str = ""

    def __post_init__(self):
        for row in self.rows:
            if len(row) != len(self.headers):
                raise ValueError(
                    f"row width {len(row)} != header width {len(self.headers)}"
                )


@dataclass(frozen=True)
class ListBlock:
    items: tuple


@dataclass(frozen=True)
class Document:
    title: str
    blocks: tuple = field(default_factory=tuple)

    def texts(self):
        """Every human-readable string in the document, for guards."""
        out = [self.title]
        for b in self.blocks:
            if isinstance(b, (Heading, Paragraph)):
                out.append(b.text)
            elif isinstance(b, KeyValues):
                for k, v in b.items:
                    out.append(str(k))
                    out.append(str(v))
            elif isinstance(b, Table):
                out.extend(str(h) for h in b.headers)
                if b.caption:
                    out.append(b.caption)
                for row in b.rows:
                    out.extend(str(c) for c in row)
            elif isinstance(b, ListBlock):
                out.extend(str(i) for i in b.items)
            else:
                raise TypeError(f"unknown block type: {type(b).__name__}")
        return out
