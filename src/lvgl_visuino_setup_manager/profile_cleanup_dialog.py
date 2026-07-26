from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, ttk

from .profile_cleanup import (
    CLEAR_CONTENTS,
    DELETE_WITH_FOLDER,
    ProfileCleanupPlan,
    ProfileCleanupResult,
)


RunWorker = Callable[[str, Callable[[], Any], Callable[[Any], None] | None], None]


@dataclass(frozen=True)
class _WorkerOutcome:
    result: Any | None = None
    error: BaseException | None = None


class ProfileCleanupDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        client_name: str,
        project_name: str,
        setup: dict[str, Any],
        active_setup_id: str | None,
        run_worker: RunWorker,
        preview_action: Callable[[str], ProfileCleanupPlan],
        execute_action: Callable[[ProfileCleanupPlan, str], ProfileCleanupResult],
        on_complete: Callable[[ProfileCleanupResult], None],
        show_error: Callable[[BaseException], None],
        append_activity: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self._run_worker = run_worker
        self._preview_action = preview_action
        self._execute_action = execute_action
        self._on_complete = on_complete
        self._show_error = show_error
        self._append_activity = append_activity
        self._setup = setup
        self._plan: ProfileCleanupPlan | None = None
        self._working = False

        self.title("Clear or Delete Selected Profile")
        self.geometry("720x760")
        self.minsize(660, 700)
        self.configure(bg="#F3F6FA")
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._action = tk.StringVar(value=CLEAR_CONTENTS)
        self._confirmation = tk.StringVar()
        self._status = tk.StringVar(value="Choose an action, then preview it.")
        self._preview_summary = tk.StringVar(value="No files have been changed.")

        path_exists = Path(setup["folderPath"]).is_dir()
        is_active = setup["id"] == active_setup_id
        self._eligible = path_exists and not is_active
        if is_active:
            self._status.set(
                "This profile is active. Restore the default setup before "
                "changing its folder."
            )
        elif not path_exists:
            self._status.set(
                "The folder does not exist. Use Remove Profile in the main "
                "window to remove only the saved profile."
            )

        self._build(
            client_name=client_name,
            project_name=project_name,
            is_active=is_active,
        )
        self._action.trace_add("write", self._selection_changed)
        self._confirmation.trace_add("write", self._confirmation_changed)
        self._update_buttons()
        self.grab_set()
        self.focus_set()

    def _build(
        self,
        *,
        client_name: str,
        project_name: str,
        is_active: bool,
    ) -> None:
        header = tk.Frame(self, bg="#7A271A", height=78)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="Selected profile storage",
            bg="#7A271A",
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 18),
            anchor="w",
        ).pack(fill="x", padx=24, pady=(15, 0))
        tk.Label(
            header,
            text="Recoverable actions only · Windows Recycle Bin",
            bg="#7A271A",
            fg="#FECDCA",
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", padx=24, pady=(2, 0))

        body = tk.Frame(self, bg="#F3F6FA")
        body.pack(fill="both", expand=True, padx=22, pady=18)

        context = self._card(body)
        context.pack(fill="x")
        tk.Label(
            context,
            text=self._setup["name"],
            bg="#FFFFFF",
            fg="#182230",
            font=("Segoe UI Semibold", 13),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            context,
            text=f"{client_name}  →  {project_name}",
            bg="#FFFFFF",
            fg="#667085",
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(2, 8))
        tk.Label(
            context,
            text=self._setup["folderPath"],
            bg="#F8FAFC",
            fg="#344054",
            font=("Consolas", 9),
            anchor="w",
            justify="left",
            wraplength=620,
            padx=10,
            pady=8,
        ).pack(fill="x")
        tk.Label(
            context,
            text="ACTIVE — action blocked" if is_active else "Inactive profile",
            bg="#FFFFFF",
            fg="#B42318" if is_active else "#067647",
            font=("Segoe UI Semibold", 9),
            anchor="w",
        ).pack(fill="x", pady=(8, 0))

        action_card = self._card(body)
        action_card.pack(fill="x", pady=(12, 0))
        tk.Label(
            action_card,
            text="1. Choose what should happen",
            bg="#FFFFFF",
            fg="#182230",
            font=("Segoe UI Semibold", 11),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))
        self._radio(
            action_card,
            value=CLEAR_CONTENTS,
            title="Clear Folder Contents",
            detail=(
                "Keep the profile. Move its current content to the Recycle Bin, "
                "then recreate an empty libraries folder."
            ),
        )
        self._radio(
            action_card,
            value=DELETE_WITH_FOLDER,
            title="Delete Profile and Folder",
            detail=(
                "Move the complete folder to the Recycle Bin, then remove only "
                "this setup profile from the registry."
            ),
        )

        preview_card = self._card(body)
        preview_card.pack(fill="x", pady=(12, 0))
        preview_header = tk.Frame(preview_card, bg="#FFFFFF")
        preview_header.pack(fill="x")
        tk.Label(
            preview_header,
            text="2. Preview the exact target",
            bg="#FFFFFF",
            fg="#182230",
            font=("Segoe UI Semibold", 11),
            anchor="w",
        ).pack(side="left")
        self.preview_button = ttk.Button(
            preview_header,
            text="Preview Selected Action",
            style="Secondary.TButton",
            command=self._request_preview,
        )
        self.preview_button.pack(side="right")
        tk.Label(
            preview_card,
            textvariable=self._status,
            bg="#FFFFFF",
            fg="#667085",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=610,
        ).pack(fill="x", pady=(9, 3))
        tk.Label(
            preview_card,
            textvariable=self._preview_summary,
            bg="#FFFFFF",
            fg="#344054",
            font=("Segoe UI Semibold", 9),
            anchor="w",
            justify="left",
            wraplength=610,
        ).pack(fill="x")

        self.confirm_card = self._card(body)
        tk.Label(
            self.confirm_card,
            text="3. Confirm after a successful preview",
            bg="#FFFFFF",
            fg="#182230",
            font=("Segoe UI Semibold", 11),
            anchor="w",
        ).pack(fill="x")
        self.confirm_instruction = tk.Label(
            self.confirm_card,
            text="",
            bg="#FFFFFF",
            fg="#667085",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=610,
        )
        self.confirm_instruction.pack(fill="x", pady=(7, 5))
        self.confirm_entry = ttk.Entry(
            self.confirm_card,
            textvariable=self._confirmation,
            font=("Consolas", 10),
        )
        self.confirm_entry.pack(fill="x")

        footer = tk.Frame(body, bg="#F3F6FA")
        footer.pack(fill="x", pady=(14, 0))
        ttk.Button(
            footer,
            text="Cancel",
            style="Quiet.TButton",
            command=self._close,
        ).pack(side="left")
        self.execute_button = ttk.Button(
            footer,
            text="Move Contents to Recycle Bin",
            style="Danger.TButton",
            command=self._request_execute,
        )
        self.execute_button.pack(side="right")

    @staticmethod
    def _card(parent: tk.Misc) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg="#FFFFFF",
            highlightthickness=1,
            highlightbackground="#DCE3EC",
            bd=0,
        )
        frame.configure(padx=16, pady=13)
        return frame

    def _radio(
        self,
        parent: tk.Misc,
        *,
        value: str,
        title: str,
        detail: str,
    ) -> None:
        row = tk.Frame(parent, bg="#FFFFFF")
        row.pack(fill="x", pady=(1, 7))
        ttk.Radiobutton(
            row,
            variable=self._action,
            value=value,
        ).pack(side="left", anchor="n", pady=(2, 0))
        text = tk.Frame(row, bg="#FFFFFF")
        text.pack(side="left", fill="x", expand=True, padx=(7, 0))
        tk.Label(
            text,
            text=title,
            bg="#FFFFFF",
            fg="#182230",
            font=("Segoe UI Semibold", 9),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            text,
            text=detail,
            bg="#FFFFFF",
            fg="#667085",
            font=("Segoe UI", 8),
            anchor="w",
            justify="left",
            wraplength=570,
        ).pack(fill="x", pady=(1, 0))

    def _selection_changed(self, *_: object) -> None:
        self._plan = None
        self._confirmation.set("")
        self._preview_summary.set("No files have been changed.")
        if self._eligible:
            self._status.set("Preview is required before confirmation.")
        self.confirm_card.pack_forget()
        self._update_buttons()

    def _confirmation_changed(self, *_: object) -> None:
        self._update_buttons()

    def _request_preview(self) -> None:
        if self._working or not self._eligible:
            return
        action = self._action.get()
        self._working = True
        self._status.set("Inspecting the selected folder safely…")
        self._update_buttons()
        self._run_worker(
            "Previewing selected profile cleanup",
            lambda: self._capture(lambda: self._preview_action(action)),
            self._preview_complete,
        )

    def _preview_complete(self, outcome: _WorkerOutcome) -> None:
        self._working = False
        if outcome.error is not None:
            self._plan = None
            self._status.set("Nothing changed. Correct the issue and preview again.")
            self._preview_summary.set("No files have been changed.")
            self._append_activity(f"Profile cleanup preview blocked: {outcome.error}")
            self._show_error(outcome.error)
            self._update_buttons()
            return

        plan = outcome.result
        if not isinstance(plan, ProfileCleanupPlan):
            self._show_error(RuntimeError("The cleanup preview returned no plan."))
            self._update_buttons()
            return
        self._plan = plan
        self._status.set(
            "Preview passed all path, overlap, process, and reparse-point checks."
        )
        self._preview_summary.set(
            f"{plan.inventory.file_count:,} files · "
            f"{plan.inventory.folder_count:,} folders · "
            f"{self._format_bytes(plan.inventory.total_bytes)}"
        )
        self.confirm_instruction.configure(
            text=(
                "Type this exact phrase to unlock the action:\n"
                f"{plan.confirmation_phrase}"
            )
        )
        self.confirm_card.pack(fill="x", pady=(12, 0), before=self.execute_button.master)
        self.confirm_entry.focus_set()
        self._update_buttons()

    def _request_execute(self) -> None:
        if self._working or self._plan is None:
            return
        confirmation = self._confirmation.get()
        plan = self._plan
        self._working = True
        self._status.set("Rechecking every safety gate before the folder changes…")
        self._update_buttons()
        self._run_worker(
            "Applying selected profile cleanup",
            lambda: self._capture(
                lambda: self._execute_action(plan, confirmation)
            ),
            self._execute_complete,
        )

    def _execute_complete(self, outcome: _WorkerOutcome) -> None:
        self._working = False
        if outcome.error is not None:
            self._plan = None
            self._confirmation.set("")
            self.confirm_card.pack_forget()
            self._status.set("Review the message, then run a fresh preview.")
            self._append_activity(f"Profile cleanup failed: {outcome.error}")
            self._show_error(outcome.error)
            self._update_buttons()
            return

        result = outcome.result
        if not isinstance(result, ProfileCleanupResult):
            self._show_error(RuntimeError("The cleanup operation returned no result."))
            self._update_buttons()
            return
        if result.profile_removed:
            title = "Profile Removed"
            message = (
                "Profile removed. Its folder is in the Windows Recycle Bin."
            )
        else:
            title = "Folder Cleared"
            message = (
                "Folder cleared. The previous contents are in the Windows "
                "Recycle Bin.\n\nAn empty libraries folder is ready."
            )
        self._append_activity(message.replace("\n", " "))
        self.grab_release()
        self._on_complete(result)
        messagebox.showinfo(title, message, parent=self.master)
        self.destroy()

    def _update_buttons(self) -> None:
        self.preview_button.configure(
            state="normal" if self._eligible and not self._working else "disabled"
        )
        valid_confirmation = bool(
            self._plan is not None
            and self._confirmation.get() == self._plan.confirmation_phrase
        )
        self.execute_button.configure(
            text=(
                "Remove Profile & Recycle Folder"
                if self._action.get() == DELETE_WITH_FOLDER
                else "Move Contents to Recycle Bin"
            ),
            state=(
                "normal"
                if self._eligible and not self._working and valid_confirmation
                else "disabled"
            ),
        )

    @staticmethod
    def _capture(function: Callable[[], Any]) -> _WorkerOutcome:
        try:
            return _WorkerOutcome(result=function())
        except BaseException as error:
            return _WorkerOutcome(error=error)

    @staticmethod
    def _format_bytes(value: int) -> str:
        if value < 1024:
            return f"{value} B"
        if value < 1024 * 1024:
            return f"{value / 1024:.1f} KiB"
        if value < 1024 * 1024 * 1024:
            return f"{value / (1024 * 1024):.1f} MiB"
        return f"{value / (1024 * 1024 * 1024):.2f} GiB"

    def _close(self) -> None:
        if self._working:
            messagebox.showwarning(
                "Operation in Progress",
                "Wait for the protected operation to finish before closing.",
                parent=self,
            )
            return
        self.grab_release()
        self.destroy()
