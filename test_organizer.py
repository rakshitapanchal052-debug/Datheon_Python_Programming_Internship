import logging
import tempfile
import unittest
from pathlib import Path

from organizer import organize_directory


class OrganizeDirectoryTests(unittest.TestCase):
    def test_preview_does_not_move_files_or_create_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "report.PDF").write_text("document")

            summary = organize_directory(directory)

            self.assertEqual(summary.moved, 1)
            self.assertFalse((directory / "Documents").exists())
            self.assertTrue((directory / "report.PDF").exists())

    def test_moves_files_and_avoids_overwriting_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            documents = directory / "Documents"
            documents.mkdir()
            (directory / "report.pdf").write_text("new document")
            (documents / "report.pdf").write_text("existing document")
            (directory / "photo.jpg").write_text("image")

            summary = organize_directory(directory, dry_run=False)

            self.assertEqual(summary.moved, 2)
            self.assertEqual((documents / "report.pdf").read_text(), "existing document")
            self.assertEqual(
                (documents / "report (1).pdf").read_text(), "new document"
            )
            self.assertTrue((directory / "Images" / "photo.jpg").exists())

    def test_skips_unknown_extensions_and_does_not_recurse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "nested").mkdir()
            (directory / "nested" / "photo.jpg").write_text("image")
            (directory / "notes.unknown").write_text("unknown")

            with self.assertLogs("organizer", level=logging.INFO):
                summary = organize_directory(directory, dry_run=False)

            self.assertEqual(summary.skipped, 1)
            self.assertEqual(summary.moved, 0)
            self.assertTrue((directory / "nested" / "photo.jpg").exists())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()
