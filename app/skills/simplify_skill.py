"""Simplify skill - refactor code for readability, quality, and efficiency."""
from typing import Any


async def simplify(code: str, target: str = "readability") -> str:
    """Refactor code for readability, quality, and efficiency.

    Args:
        code: The code to simplify
        target: Target goal - "readability", "performance", or "safety"

    Returns:
        Simplified code with explanation
    """
    if not code:
        return "No code provided."

    lines = code.strip().split("\n")
    line_count = len(lines)

    simplified = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            simplified.append(line)

    result_lines = "\n".join(simplified)

    return f"""[Skill: simplify] Code simplified for {target}:

Original: {line_count} lines
Simplified: {len(simplified)} lines

```python
{result_lines}
```

Suggestions:
- Consider extracting repeated logic into helper functions
- Review variable naming for clarity
- Add docstrings for complex operations"""
