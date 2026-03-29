"""
Unit tests for src/obsidian.py.

All tests use a tmp_path fixture (a real temporary directory) so no mocking
of the filesystem is needed.  The Fitbit client is never called here — we
construct HealthData directly.
"""
import pytest
from pathlib import Path

from src.fitbit_client import HealthData
from src.obsidian import write_health_data


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    """Return a temporary vault root with the daily-notes directory pre-created."""
    (tmp_path / "01 - Daily Notes").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def full_data() -> HealthData:
    """A fully-populated HealthData object for 2026-03-29."""
    return HealthData(
        date="2026-03-29",
        weight=80.5,
        workout="Running",
        sleep="7h 30m",
        steps=10_000,
        calories_burned=2_500,
        resting_hr=60,
        azm=45,
    )


# ---------------------------------------------------------------------------
# Test 1: Create a brand-new daily note
# ---------------------------------------------------------------------------

def test_creates_new_note(vault: Path, full_data: HealthData) -> None:
    """Writing to a non-existent note should create one with all health fields,
    YAML frontmatter, and default Tasks / Notes sections."""
    path = write_health_data(vault, full_data)

    assert path.exists(), "Note file was not created"
    content = path.read_text(encoding="utf-8")

    # Frontmatter
    assert "---" in content
    assert "date: 2026-03-29" in content

    # Health block
    assert "## 📊 Health Summary" in content
    assert "Weight:: 80.5 kg" in content
    assert "Workout:: Running" in content
    assert "Sleep:: 7h 30m" in content
    assert "Steps:: 10,000" in content
    assert "CaloriesBurned:: 2,500" in content
    assert "RestingHR:: 60 bpm" in content
    assert "AZM:: 45" in content

    # Default sections
    assert "## Tasks" in content
    assert "## Notes" in content


# ---------------------------------------------------------------------------
# Test 2: Replace an existing health block
# ---------------------------------------------------------------------------

def test_replaces_existing_health_block(vault: Path, full_data: HealthData) -> None:
    """When the note already contains a health block, only that block should be
    replaced.  Old values must disappear; new values must appear exactly once."""
    note_path = vault / "01 - Daily Notes" / "2026-03-29.md"
    note_path.write_text(
        "---\n"
        "date: 2026-03-29\n"
        "---\n\n"
        "# 2026-03-29\n\n"
        "## 📊 Health Summary\n\n"
        "Weight:: 75.0 kg\n"
        "Steps:: 5,000\n\n"
        "## Tasks\n\n"
        "- [ ] Old task\n",
        encoding="utf-8",
    )

    write_health_data(vault, full_data)
    content = note_path.read_text(encoding="utf-8")

    # Old values gone
    assert "Weight:: 75.0 kg" not in content
    assert "Steps:: 5,000" not in content

    # New values present
    assert "Weight:: 80.5 kg" in content
    assert "Steps:: 10,000" in content

    # Block appears exactly once
    assert content.count("## 📊 Health Summary") == 1


# ---------------------------------------------------------------------------
# Test 3: Append a health block to a note that has none
# ---------------------------------------------------------------------------

def test_appends_health_block_when_missing(vault: Path, full_data: HealthData) -> None:
    """If the note exists but has no health block, one should be inserted
    (before existing sections or at the end)."""
    note_path = vault / "01 - Daily Notes" / "2026-03-29.md"
    note_path.write_text(
        "---\n"
        "date: 2026-03-29\n"
        "---\n\n"
        "# 2026-03-29\n\n"
        "## Tasks\n\n"
        "- [ ] Do something\n\n"
        "## Notes\n\n"
        "Some notes here.\n",
        encoding="utf-8",
    )

    write_health_data(vault, full_data)
    content = note_path.read_text(encoding="utf-8")

    assert "## 📊 Health Summary" in content
    assert "Weight:: 80.5 kg" in content
    assert "Steps:: 10,000" in content


# ---------------------------------------------------------------------------
# Test 4: Preserve Mood, Tasks, and Notes sections
# ---------------------------------------------------------------------------

def test_preserves_other_sections(vault: Path, full_data: HealthData) -> None:
    """Replacing the health block must not touch Mood, Tasks, or Notes content."""
    note_path = vault / "01 - Daily Notes" / "2026-03-29.md"
    note_path.write_text(
        "---\n"
        "date: 2026-03-29\n"
        "---\n\n"
        "# 2026-03-29\n\n"
        "## 📊 Health Summary\n\n"
        "Weight:: 75.0 kg\n\n"
        "## Mood\n\n"
        "Feeling great today.\n\n"
        "## Tasks\n\n"
        "- [x] Completed task\n"
        "- [ ] Pending task\n\n"
        "## Notes\n\n"
        "Important note that must not be lost.\n",
        encoding="utf-8",
    )

    write_health_data(vault, full_data)
    content = note_path.read_text(encoding="utf-8")

    # Sections that must survive untouched
    assert "Feeling great today." in content
    assert "- [x] Completed task" in content
    assert "- [ ] Pending task" in content
    assert "Important note that must not be lost." in content

    # Old health data replaced, new data present
    assert "Weight:: 75.0 kg" not in content
    assert "Weight:: 80.5 kg" in content


# ---------------------------------------------------------------------------
# Test 5: Every write produces a file ending with exactly one newline
# ---------------------------------------------------------------------------

def test_file_ends_with_single_newline(vault: Path, full_data: HealthData) -> None:
    """Every code path in write_health_data must produce a file that ends with
    exactly one newline — no double-newline, no missing newline."""
    # Path 1: new note created from scratch
    path = write_health_data(vault, full_data)
    raw = path.read_bytes()
    assert raw.endswith(b"\n"), "New note does not end with a newline"
    assert not raw.endswith(b"\n\n"), "New note ends with more than one newline"

    # Path 2: health block replaced in existing note
    write_health_data(vault, full_data)
    raw = path.read_bytes()
    assert raw.endswith(b"\n"), "Updated note does not end with a newline"
    assert not raw.endswith(b"\n\n"), "Updated note ends with more than one newline"


# ---------------------------------------------------------------------------
# Test 6: Replace health block when it is the last section in the file
# ---------------------------------------------------------------------------

def test_replaces_health_block_at_end_of_file(vault: Path, full_data: HealthData) -> None:
    """When the health block is the last content in the file (no trailing ## sections),
    replacement must produce correct values and the file must end with exactly one newline.

    This exercises the \\Z branch of _HEALTH_BLOCK_RE where rstrip() would previously
    leave the file without a terminating newline.
    """
    note_path = vault / "01 - Daily Notes" / "2026-03-29.md"
    note_path.write_text(
        "---\n"
        "date: 2026-03-29\n"
        "---\n\n"
        "# 2026-03-29\n\n"
        "## 📊 Health Summary\n\n"
        "Weight:: 75.0 kg\n"
        "Steps:: 5,000\n",
        encoding="utf-8",
    )

    write_health_data(vault, full_data)
    content = note_path.read_text(encoding="utf-8")
    raw = note_path.read_bytes()

    # Old values replaced, new values present
    assert "Weight:: 75.0 kg" not in content
    assert "Weight:: 80.5 kg" in content
    assert "Steps:: 10,000" in content

    # Block appears exactly once
    assert content.count("## 📊 Health Summary") == 1

    # File must end with exactly one newline
    assert raw.endswith(b"\n"), "File does not end with a newline"
    assert not raw.endswith(b"\n\n"), "File ends with more than one newline"
