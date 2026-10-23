"""Tkinter desktop interface for the file organizer."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from organizer import OrganizationSummary, organize_directory


class QueueLogHandler(logging.Handler):
    def __init__(self, events: queue.Queue[tuple[str, object]]) -> None:
        super().__init__()
        self.events = events

    def emit(self, record: logging.LogRecord) -> None:
        self.events.put(("log", self.format(record)))


class OrganizerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Smart File Organizer")
        self.root.geometry("760x520")
        self.root.minsize(600, 400)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.folder = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.status = tk.StringVar(value="Choose a folder, then preview its files.")

        self.logger = logging.getLogger("organizer")
        self.logger.setLevel(logging.INFO)
        self.log_handler = QueueLogHandler(self.events)
        self.log_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        self.logger.addHandler(self.log_handler)

        self._build_interface()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._process_events)

    def _build_interface(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        ttk.Label(
            container,
            text="Smart File Organizer",
            font=("Segoe UI", 18, "bold"),
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            container,
            text="Sort supported files into Documents, Images, Videos, Archives, and Code.",
        ).grid(row=1, column=0, sticky=tk.W, pady=(4, 16))

        folder_row = ttk.Frame(container)
        folder_row.grid(row=2, column=0, sticky=tk.EW, pady=(0, 12))
        folder_row.columnconfigure(0, weight=1)
        self.folder_entry = ttk.Entry(folder_row, textvariable=self.folder)
        self.folder_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 8))
        self.browse_button = ttk.Button(
            folder_row, text="Browse...", command=self._browse
        )
        self.browse_button.grid(row=0, column=1)

        log_frame = ttk.LabelFrame(container, text="Activity", padding=8)
        log_frame.grid(row=3, column=0, sticky=tk.NSEW)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.activity = tk.Text(
            log_frame,
            height=12,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 10),
        )
        self.activity.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar = ttk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.activity.yview
        )
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.activity.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Frame(container)
        footer.grid(row=4, column=0, sticky=tk.EW, pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status).grid(
            row=0, column=0, sticky=tk.W
        )
        self.preview_button = ttk.Button(
            footer, text="Preview", command=self._preview
        )
        self.preview_button.grid(row=0, column=1, padx=(8, 0))
        self.organize_button = ttk.Button(
            footer, text="Organize files", command=self._organize
        )
        self.organize_button.grid(row=0, column=2, padx=(8, 0))

    def _browse(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose a folder to organize",
            initialdir=self.folder.get() or str(Path.home()),
        )
        if selected:
            self.folder.set(selected)

    def _preview(self) -> None:
        self._start_organization(dry_run=True)

    def _organize(self) -> None:
        directory = Path(self.folder.get()).expanduser()
        if not directory.is_dir():
            messagebox.showerror(
                "Invalid folder", f"Please choose an existing folder:\n{directory}"
            )
            return
        if not messagebox.askyesno(
            "Confirm organization",
            "Move supported files into category folders in this location?",
            parent=self.root,
        ):
            return
        self._start_organization(dry_run=False)

    def _start_organization(self, dry_run: bool) -> None:
        if self.busy:
            return
        directory = Path(self.folder.get()).expanduser()
        if not directory.is_dir():
            messagebox.showerror(
                "Invalid folder", f"Please choose an existing folder:\n{directory}"
            )
            return

        self.busy = True
        self._set_controls_enabled(False)
        self.status.set("Preparing preview..." if dry_run else "Organizing files...")
        self._append_activity(
            f"\n{'Preview' if dry_run else 'Organization'}: {directory}"
        )

        def work() -> None:
            try:
                summary = organize_directory(directory, dry_run=dry_run)
                self.events.put(("result", (summary, dry_run)))
            except Exception as error:
                self.logger.exception("Unexpected organizer error")
                self.events.put(("error", str(error)))

        threading.Thread(target=work, name="file-organizer", daemon=True).start()

    def _process_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "log":
                self._append_activity(str(payload))
            elif event == "result":
                summary, dry_run = payload
                self._show_summary(summary, dry_run)
            elif event == "error":
                self.busy = False
                self._set_controls_enabled(True)
                self.status.set("The operation failed.")
                messagebox.showerror("Organizer error", str(payload), parent=self.root)

        self.root.after(100, self._process_events)

    def _show_summary(
        self, summary: OrganizationSummary, dry_run: bool
    ) -> None:
        self.busy = False
        self._set_controls_enabled(True)
        action = "would be moved" if dry_run else "moved"
        self.status.set(
            f"{summary.moved} files {action} | "
            f"{summary.skipped} skipped | {summary.failed} failed"
        )
        self._append_activity(
            f"Summary: {summary.moved} files {action}, "
            f"{summary.skipped} skipped, {summary.failed} failed."
        )
        if summary.failed:
            messagebox.showwarning(
                "Completed with errors",
                f"{summary.failed} item(s) could not be processed. "
                "See Activity for details.",
                parent=self.root,
            )

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for control in (
            self.folder_entry,
            self.browse_button,
            self.preview_button,
            self.organize_button,
        ):
            control.configure(state=state)

    def _append_activity(self, text: str) -> None:
        self.activity.configure(state=tk.NORMAL)
        self.activity.insert(tk.END, f"{text}\n")
        self.activity.see(tk.END)
        self.activity.configure(state=tk.DISABLED)

    def _close(self) -> None:
        if self.busy:
            messagebox.showinfo(
                "Operation in progress",
                "Please wait for the current operation to finish before closing.",
                parent=self.root,
            )
            return
        self.logger.removeHandler(self.log_handler)
        self.log_handler.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    OrganizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()