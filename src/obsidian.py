"""
Obsidian daily-note writer.

Writes a `## 📊 Health Summary` block into the appropriate daily note under
`{VAULT_DIR}/01 - Daily Notes/YYYY-MM-DD.md`.

Behaviour:
  - Note doesn't exist → create from scratch (frontmatter + health block +
    default Tasks/Notes sections).
  - Note exists, has a health block → replace only that block, leave everything
    else (Mood, Tasks, Notes, …) untouched.
  - Note exists, no health block → insert before the first ## section, or
    append if there are no sections.

All written files are guaranteed to end with exactly one newline character.
"""
import re
from pathlib import Path
from typing import Union

from src.fitbit_client import HealthData

_HEALTH_HEADER = "## 📊 Health Summary"

# Matches the health block from its header up to (but not including) the
# newline that precedes the next ## section, or to end-of-string.
# re.DOTALL lets . match newlines so .*? spans the whole block.
_HEALTH_BLOCK_RE = re.compile(
    r"## 📊 Health Summary.*?(?=\n## |\Z)",
    re.DOTALL,
)


def _format_health_block(data: HealthData) -> str:
    """Return the full health block string, ending with a single newline."""
    lines = [_HEALTH_HEADER, ""]

    unit = data.weight_unit or "kg"
    if data.weight is not None:
        lines.append(f"Weight:: {data.weight} {unit}")
    if data.workout is not None:
        lines.append(f"Workout:: {data.workout}")
    if data.sleep is not None:
        lines.append(f"Sleep:: {data.sleep}")
    if data.steps is not None:
        lines.append(f"Steps:: {data.steps:,}")
    if data.calories_burned is not None:
        lines.append(f"CaloriesBurned:: {data.calories_burned:,}")
    if data.resting_hr is not None:
        lines.append(f"RestingHR:: {data.resting_hr} bpm")
    if data.azm is not None:
        lines.append(f"AZM:: {data.azm}")

    lines.append("")  # trailing blank line → ends with \n after join
    return "\n".join(lines)


def _create_new_note(data: HealthData) -> str:
    """Build a complete daily note from scratch."""
    health_block = _format_health_block(data)
    return (
        f"---\n"
        f"date: {data.date}\n"
        f"tags:\n"
        f"  - daily-note\n"
        f"---\n\n"
        f"# {data.date}\n\n"
        f"{health_block}\n"
        f"## Tasks\n\n"
        f"- [ ] \n\n"
        f"## Notes\n\n"
    )


def write_health_data(vault_dir: Union[str, Path], data: HealthData) -> Path:
    """Write `data` into the appropriate daily note.

    Returns the path of the note that was written.
    All written files end with exactly one newline.
    """
    note_path = Path(vault_dir) / "01 - Daily Notes" / f"{data.date}.md"
    health_block = _format_health_block(data)

    if not note_path.exists():
        note_path.parent.mkdir(parents=True, exist_ok=True)
        new_content = _create_new_note(data)
    else:
        existing = note_path.read_text(encoding="utf-8")

        if _HEALTH_BLOCK_RE.search(existing):
            # Replace existing block.  Strip trailing newline from the
            # replacement string so the regex match boundary controls spacing.
            new_content = _HEALTH_BLOCK_RE.sub(health_block.rstrip("\n"), existing)
        else:
            # Insert before the first ## section heading, or append at end.
            # We look for \n## to find the boundary just before a section heading.
            section_match = re.search(r"\n## ", existing)
            if section_match:
                pos = section_match.start()
                # Strip trailing newlines from the part before so we control spacing.
                before = existing[:pos].rstrip("\n")
                after = existing[pos:].lstrip("\n")
                new_content = (
                    before
                    + "\n\n"
                    + health_block.rstrip("\n")
                    + "\n\n"
                    + after
                )
            else:
                new_content = existing.rstrip("\n") + "\n\n" + health_block

    # Guarantee exactly one trailing newline regardless of which path was taken.
    # This handles the edge case where the health block is the last thing in the
    # file (the \Z branch of the regex) and rstrip removed its trailing newline.
    new_content = new_content.rstrip("\n") + "\n"

    note_path.write_text(new_content, encoding="utf-8")
    return note_path
