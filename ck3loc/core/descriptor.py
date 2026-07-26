"""Разбор descriptor.mod (и .mod-файлов лаунчера).

Формат Paradox: строки key="value", допускаются блоки tags={...},
комментарии и произвольный порядок. Читаем терпимо, только нужные поля.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_FIELD_RE = re.compile(r'^\s*([a-z_]+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*$', re.MULTILINE)


@dataclass
class Descriptor:
    name: str = ""
    version: str = ""
    supported_version: str = ""
    remote_file_id: str = ""
    path: str = ""
    raw_fields: dict[str, str] = field(default_factory=dict)
    exists: bool = False

    @classmethod
    def load(cls, mod_dir: Path) -> "Descriptor":
        p = Path(mod_dir) / "descriptor.mod"
        if not p.exists():
            return cls(exists=False)
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return cls(exists=False)
        d = cls(exists=True)
        for m in _FIELD_RE.finditer(text):
            key, value = m.group(1), m.group(2).replace('\\"', '"')
            d.raw_fields[key] = value
            if key == "name":
                d.name = value
            elif key == "version":
                d.version = value
            elif key == "supported_version":
                d.supported_version = value
            elif key == "remote_file_id":
                d.remote_file_id = value
            elif key == "path":
                d.path = value
        return d


def render_descriptor(
    name: str,
    version: str,
    supported_version: str,
    tags: list[str] | None = None,
    path: str | None = None,
) -> str:
    """Собрать текст descriptor.mod / .mod для патч-мода."""
    esc = lambda s: s.replace('"', '\\"')
    lines = [f'version="{esc(version)}"']
    if tags:
        lines.append("tags={")
        for t in tags:
            lines.append(f'\t"{esc(t)}"')
        lines.append("}")
    lines.append(f'name="{esc(name)}"')
    lines.append(f'supported_version="{esc(supported_version)}"')
    if path:
        lines.append(f'path="{esc(path)}"')
    return "\n".join(lines) + "\n"
