"""Organize files in a directory by extension."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


EXTENSION_CATEGORIES = {
    ".pdf": "Documents",
    ".doc": "Documents",
    ".docx": "Documents",
    ".odt": "Documents",
    ".rtf": "Documents",
    ".txt": "Documents",
    ".xls": "Documents",
    ".xlsx": "Documents",
    ".ppt": "Documents",
    ".pptx": "Documents",
    ".jpg": "Images",
    ".jpeg": "Images",
    ".png": "Images",
    ".gif": "Images",
    ".bmp": "Images",
    ".tif": "Images",
    ".tiff": "Images",
    ".webp": "Images",
    ".svg": "Images",
    ".mp4": "Videos",
    ".mkv": "Videos",
    ".mov": "Videos",
    ".avi": "Videos",
    ".wmv": "Videos",
    ".flv": "Videos",
    ".webm": "Videos",
    ".zip": "Archives",
    ".rar": "Archives",
    ".7z": "Archives",
    ".tar": "Archives",
    ".gz": "Archives",
    ".bz2": "Archives",
    ".xz": "Archives",
    ".py": "Code",
    ".js": "Code",
    ".ts": "Code",
    ".jsx": "Code",
    ".tsx": "Code",
    ".html": "Code",
    ".css": "Code",
    ".java": "Code",
    ".c": "Code",
    ".h": "Code",
    ".cpp": "Code",
    ".cs": "Code",
    ".go": "Code",
    ".rs": "Code",
    ".php": "Code",
    ".rb": "Code",
    ".swift": "Code",
    ".sh": "Code",
}

LOGGER = logging.getLogger("organizer")


@dataclass
class OrganizationSummary:
    moved: int = 0
    skipped: int = 0
    failed: int = 0


def _available_destination(folder: Path, filename: str) -> Path:
    destination = folder / filename
    if not destination.exists():
        return destination

    source = Path(filename)
    suffix = source.suffix
    stem = source.name[: -len(suffix)] if suffix else source.name
    index = 1
    while True:
        destination = folder / f"{stem} ({index}){suffix}"
        if not destination.exists():
            return destination
        index += 1


def organize_directory(directory: Path, dry_run: bool = True) -> OrganizationSummary:
    """Organize supported files directly inside directory, without recursing."""
    summary = OrganizationSummary()

    try:
        with os.scandir(directory) as scan:
            entries = list(scan)
    except (PermissionError, OSError) as error:
        LOGGER.error("Cannot read directory %s: %s", directory, error)
        summary.failed += 1
        return summary

    for entry in entries:
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
        except OSError as error:
            LOGGER.error("Cannot inspect %s: %s", entry.path, error)
            summary.failed += 1
            continue

        source = Path(entry.path)
        category = EXTENSION_CATEGORIES.get(source.suffix.lower())
        if category is None:
            LOGGER.info("Skipping unsupported file: %s", source.name)
            summary.skipped += 1
            continue

        target_directory = directory / category
        destination = _available_destination(target_directory, source.name)
        if dry_run:
            LOGGER.info("Would move %s -> %s", source, destination)
            summary.moved += 1
            continue

        try:
            target_directory.mkdir(exist_ok=True)
            # Re-check after creating the directory in case it already existed.
            destination = _available_destination(target_directory, source.name)
            shutil.move(str(source), str(destination))
        except FileExistsError:
            # Retry with a fresh collision-safe name if another process won the race.
            try:
                destination = _available_destination(target_directory, source.name)
                shutil.move(str(source), str(destination))
            except (FileExistsError, PermissionError, OSError) as error:
                LOGGER.error("Cannot move %s: %s", source, error)
                summary.failed += 1
                continue
        except (PermissionError, OSError) as error:
            LOGGER.error("Cannot move %s: %s", source, error)
            summary.failed += 1
            continue

        LOGGER.info("Moved %s -> %s", source.name, destination)
        summary.moved += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sort files in a directory into folders by file type."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path.home() / "Downloads",
        help="directory to organize (default: ~/Downloads)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform moves; without this option, only preview them",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    directory = args.directory.expanduser()
    if not directory.exists() or not directory.is_dir():
        LOGGER.error("Not a readable directory: %s", directory)
        return 2

    summary = organize_directory(directory, dry_run=not args.apply)
    action = "relocated" if args.apply else "would be relocated"
    LOGGER.info(
        "Summary: %d files %s, %d skipped, %d failed",
        summary.moved,
        action,
        summary.skipped,
        summary.failed,
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
