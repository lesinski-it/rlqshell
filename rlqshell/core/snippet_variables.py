"""Variable extraction and resolution for snippet scripts."""

from __future__ import annotations

import re

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def extract_variables(script: str) -> list[str]:
    """Return unique variable names in order of first appearance."""
    seen: set[str] = set()
    result: list[str] = []
    for match in _VAR_PATTERN.finditer(script):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def resolve_variables(script: str, values: dict[str, str]) -> str:
    """Replace ``{{name}}`` placeholders with their values."""
    def _replacer(m: re.Match) -> str:
        return values.get(m.group(1), m.group(0))
    return _VAR_PATTERN.sub(_replacer, script)
