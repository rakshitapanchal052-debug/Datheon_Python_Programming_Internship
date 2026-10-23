# Smart File Organizer

A small desktop utility for sorting files in a selected folder by extension.
It handles files directly in that folder (it does not scan nested folders),
keeps unsupported file types in place, and avoids overwriting existing files
by adding a numbered suffix to collisions.

## Desktop application

Run the application with Python 3:

```powershell
python app.py
```

Choose a folder with **Browse...**, then select **Preview** to see which files
would be moved without creating folders or changing files. Select **Organize
files** to apply the moves; the app asks for confirmation first. The Activity
panel and status line show progress, skipped files, and any errors.

Supported categories are Documents, Images, Videos, Archives, and Code. The
extension-to-category mapping is maintained in `organizer.py`.

## Command line

The command-line interface also previews by default:

```powershell
python organizer.py "C:\path\to\folder"
```

Add `--apply` to perform the moves:

```powershell
python organizer.py "C:\path\to\folder" --apply
```

## Tests

Run the organizer tests with:

```powershell
python -m unittest -v test_organizer
```