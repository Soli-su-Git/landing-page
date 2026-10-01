#!/usr/bin/env python3
"""Alza la versione della pagina e scrive il CHANGELOG.

La versione non sta in nessun campo: **è** il titolo della sezione più recente
di `CHANGELOG.md`, che `build_page.py` rilegge per stamparla nel footer. Una
fonte sola, come nel repo del bot — dove però la versione del bot sta in
`pyproject.toml`, perché lì c'è un pacchetto da pubblicare.

Lo script guarda i commit fatti dall'ultimo che ha toccato il CHANGELOG, più
l'oggetto che gli si passa, e da quelli decide di quanto crescere:

- `tipo!:` nell'oggetto, o `BREAKING CHANGE` → major
- `feat:`                                    → minor
- tutto il resto (fix, docs, chore, ci, ...)  → patch

    make bump MESSAGE="feat: nuova sezione"
    python bump.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path

VERSION_LINE = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

_BREAKING = re.compile(r"^\w+(\([^)]*\))?!:", re.MULTILINE)
_FEAT = re.compile(r"^feat(\([^)]*\))?:", re.MULTILINE | re.IGNORECASE)

#: Commit di servizio: non sono novità da raccontare.
_NOISE = re.compile(r"^(Merge |Revert |chore\(versione\)|bump versione)", re.IGNORECASE)

#: La versione della pagina: il titolo della sezione più recente del changelog.
CHANGELOG_HEADING = re.compile(r"^## (\d+\.\d+\.\d+)", re.MULTILINE)

CHANGELOG_HEADER = "# Changelog della pagina\n"


# -- decisioni -----------------------------------------------------------------


def part_for(message: str) -> str:
    """Quale parte incrementare, dati uno o più oggetti di commit."""
    if "BREAKING CHANGE" in message or _BREAKING.search(message):
        return "major"
    if _FEAT.search(message):
        return "minor"
    return "patch"


def next_version(current: str, part: str) -> str:
    match = SEMVER.match(current.strip())
    if match is None:
        raise ValueError(f"versione non semver: {current!r}")
    major, minor, patch = (int(g) for g in match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"parte sconosciuta: {part!r}")


# -- storia git ----------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _pathspec(repo: Path, path: Path) -> str:
    """Il percorso come lo vuole `git log --`: relativo alla radice del repo.

    Col solo nome del file un changelog in una sottocartella non viene trovato
    (`CHANGELOG-sito.md` non combacia con `docs/CHANGELOG-sito.md`), git non
    trova nessun commit e lo script ricade su tutta la storia — rifacendo ogni
    volta l'elenco completo.
    """
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.name


def subjects_since_last_release(repo: Path, changelog: Path) -> list[str]:
    """Oggetti dei commit dall'ultima release (l'ultimo che ha toccato il CHANGELOG)."""
    spec = _pathspec(repo, changelog)
    base = _git(repo, "log", "-1", "--format=%H", "--", spec)
    span = f"{base}..HEAD" if base else "HEAD"
    log = _git(repo, "log", span, "--format=%s", "--no-merges")
    if not base:
        print(
            f"attenzione: nessun commit ha mai toccato {spec}, uso tutta la storia.",
            file=sys.stderr,
        )
    return clean_subjects(log.splitlines())


def clean_subjects(subjects: Iterable[str]) -> list[str]:
    """Toglie i commit di servizio e i doppioni, mantenendo l'ordine."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in subjects:
        subject = raw.strip()
        if not subject or _NOISE.match(subject) or subject in seen:
            continue
        seen.add(subject)
        out.append(subject)
    return out


# -- scrittura -----------------------------------------------------------------


def render_entry(version: str, subjects: Iterable[str], when: date | None = None) -> str:
    """La sezione da mettere in cima al CHANGELOG."""
    lines = [f"## {version} — {(when or date.today()).isoformat()}", ""]
    lines += [f"- {subject}" for subject in subjects] or ["- manutenzione varia"]
    return "\n".join(lines) + "\n"


def prepend_entry(path: Path, entry: str, *, dry_run: bool = False) -> str:
    """Inserisce la sezione prima della piu' recente, sotto l'intestazione.

    L'intestazione e' tutto quello che sta prima della prima riga `## `: il
    titolo e le righe di spiegazione, che restano dove sono.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = CHANGELOG_HEADER
    body = text.lstrip("\n")
    if body.startswith("## "):
        head, rest = CHANGELOG_HEADER.rstrip("\n"), body
    else:
        cut = body.find("\n## ")
        head = (body if cut == -1 else body[:cut]).rstrip("\n")
        rest = "" if cut == -1 else body[cut:].lstrip("\n")

    new_text = f"{head}\n\n{entry}" + (f"\n{rest}" if rest else "")
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return new_text


# -- cli -----------------------------------------------------------------------


def changelog_version(path: Path) -> str:
    """La versione corrente: il titolo della sezione più recente, o 0.0.0."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    match = CHANGELOG_HEADING.search(text)
    return match.group(1) if match else "0.0.0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--changelog", type=Path, default=None)
    parser.add_argument("--part", choices=["auto", "major", "minor", "patch"], default="auto")
    parser.add_argument("--message", default="", help="oggetto del commit che stai per fare")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    changelog = args.changelog or args.repo / "CHANGELOG.md"

    subjects = subjects_since_last_release(args.repo, changelog)
    if args.message.strip():
        subjects = clean_subjects([args.message, *subjects])
    if not subjects:
        print("niente da rilasciare: nessun commit dall'ultima versione.", file=sys.stderr)
        return 1

    part = part_for("\n".join(subjects)) if args.part == "auto" else args.part
    current = changelog_version(changelog)
    try:
        new = next_version(current, part)
        prepend_entry(changelog, render_entry(new, subjects), dry_run=args.dry_run)
    except (OSError, ValueError) as exc:
        print(f"bump fallito: {exc}", file=sys.stderr)
        return 1

    print(new)
    print(f"{current} → {new} ({part})", file=sys.stderr)
    for subject in subjects:
        print(f"  - {subject}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
