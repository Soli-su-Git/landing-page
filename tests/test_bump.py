"""La versione della pagina: il titolo più recente di CHANGELOG.md."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("bump", ROOT / "bump.py")
bump = importlib.util.module_from_spec(_spec)
sys.modules["bump"] = bump
_spec.loader.exec_module(bump)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("feat: nuova sezione", "minor"),
        ("fix: link rotto", "patch"),
        ("docs: spiegazione", "patch"),
        ("refactor!: rifatto il template", "major"),
        ("fix: x\n\nBREAKING CHANGE: percorsi diversi", "major"),
    ],
)
def test_part_for(message, expected):
    assert bump.part_for(message) == expected


def test_changelog_version_reads_the_newest_heading(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## 2.3.1 — 2026-10-01\n\n- x\n\n## 2.3.0 — 2026-09-30\n")
    assert bump.changelog_version(changelog) == "2.3.1"


def test_changelog_version_of_a_missing_file_is_zero(tmp_path):
    assert bump.changelog_version(tmp_path / "manca.md") == "0.0.0"


def test_main_writes_the_new_section(tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog della pagina\n\n## 1.0.0 — 2026-10-01\n\n- feat: prima\n")

    code = bump.main(
        ["--repo", str(tmp_path), "--changelog", str(changelog), "--message", "feat: seconda"]
    )

    assert code == 0
    assert capsys.readouterr().out.strip() == "1.1.0"
    testo = changelog.read_text()
    assert "## 1.1.0" in testo
    assert testo.index("## 1.1.0") < testo.index("## 1.0.0")


def test_main_stops_when_there_is_nothing_to_release(tmp_path, capsys):
    assert bump.main(["--repo", str(tmp_path)]) == 1
    assert "niente da rilasciare" in capsys.readouterr().err


def test_the_script_runs_as_a_program():
    """Il guardiano del guardiano: `python bump.py` dev'essere eseguibile.

    Una prima versione aveva `if __name__ == "__main__"` prima di `def main`:
    importarla funzionava, lanciarla no.
    """
    done = subprocess.run(
        [sys.executable, str(ROOT / "bump.py"), "--help"], capture_output=True, text=True
    )
    assert done.returncode == 0
    assert "versione della pagina" in done.stdout
