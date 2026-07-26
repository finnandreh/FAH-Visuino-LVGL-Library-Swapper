from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME
from .controller import ApplicationController
from .project_vault import ProjectVaultError
from .project_vault_import import (
    ProjectVaultImportPlan,
    ProjectVaultImportRequest,
    ProjectVaultImportResult,
)


COLORS = {
    "background": "#F3F6FA",
    "card": "#FFFFFF",
    "navy": "#102A43",
    "text": "#182230",
    "muted": "#667085",
    "line": "#DCE3EC",
    "soft_blue": "#EFF6FF",
}


class ProjectVaultImportDialog(tk.Toplevel):
    """Analyze and confirm one immutable standalone-project import."""

    def __init__(
        self,
        parent: tk.Misc,
        controller: ApplicationController,
        on_imported: Callable[[ProjectVaultImportResult], None],
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.on_imported = on_imported
        self._plan: ProjectVaultImportPlan | None = None

        self.title(f"Import Project Revision — {APP_NAME}")
        self.configure(bg=COLORS["background"])
        self.geometry("780x690")
        self.minsize(700, 620)
        self.transient(parent)
        self.bind("<Escape>", lambda _event: self.destroy())

        self.source_var = tk.StringVar()
        self.client_id_var = tk.StringVar(value="client_fah")
        self.client_name_var = tk.StringVar(value="FAH")
        self.project_id_var = tk.StringVar(value="project_waveshare43b_demo")
        self.project_name_var = tk.StringVar(value="Waveshare 4.3B Demo")
        self.revision_id_var = tk.StringVar(value="r001")
        self.library_name_var = tk.StringVar(
            value="FAH_Waveshare43B_Demo_r001"
        )
        self.summary_var = tk.StringVar(
            value=(
                "Choose a complete standalone project folder, then analyze it. "
                "No files are written during analysis."
            )
        )
        self._build()
        for variable in (
            self.source_var,
            self.client_id_var,
            self.client_name_var,
            self.project_id_var,
            self.project_name_var,
            self.revision_id_var,
            self.library_name_var,
        ):
            variable.trace_add("write", self._invalidate_plan)
        self._center_over(parent)
        self.focus_set()

    def _build(self) -> None:
        header = tk.Frame(self, bg=COLORS["navy"], height=90)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="CONTROLLED IMMUTABLE IMPORT",
            bg=COLORS["navy"],
            fg="#8FB8FF",
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", padx=26, pady=(16, 0))
        tk.Label(
            header,
            text="Import Standalone Project",
            bg=COLORS["navy"],
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 19),
            anchor="w",
        ).pack(fill="x", padx=26, pady=(2, 0))
        tk.Label(
            header,
            text=(
                "Analyze first, then create one new Client → Project → Revision. "
                "Existing revisions are never replaced."
            ),
            bg=COLORS["navy"],
            fg="#D9E2EC",
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", padx=26, pady=(2, 0))

        card = tk.Frame(
            self,
            bg=COLORS["card"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        card.pack(fill="both", expand=True, padx=18, pady=16)
        card.grid_columnconfigure(1, weight=1)

        row = 0
        tk.Label(
            card,
            text="STANDALONE SOURCE FOLDER",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).grid(row=row, column=0, columnspan=3, sticky="ew", padx=16, pady=(16, 6))
        row += 1
        ttk.Entry(card, textvariable=self.source_var).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=(16, 8)
        )
        ttk.Button(card, text="Browse...", command=self._browse).grid(
            row=row, column=2, sticky="e", padx=(0, 16)
        )
        row += 1

        fields = (
            ("Client ID", self.client_id_var, "Client name", self.client_name_var),
            (
                "Project ID",
                self.project_id_var,
                "Project name",
                self.project_name_var,
            ),
            (
                "Revision ID",
                self.revision_id_var,
                "Unique library name",
                self.library_name_var,
            ),
        )
        for left_label, left_var, right_label, right_var in fields:
            left = tk.Frame(card, bg=COLORS["card"])
            right = tk.Frame(card, bg=COLORS["card"])
            left.grid(
                row=row,
                column=0,
                sticky="ew",
                padx=(16, 8),
                pady=(15, 0),
            )
            right.grid(
                row=row,
                column=1,
                columnspan=2,
                sticky="ew",
                padx=(8, 16),
                pady=(15, 0),
            )
            card.grid_columnconfigure(0, weight=1)
            for frame, label, variable in (
                (left, left_label, left_var),
                (right, right_label, right_var),
            ):
                tk.Label(
                    frame,
                    text=label.upper(),
                    bg=COLORS["card"],
                    fg=COLORS["muted"],
                    font=("Segoe UI Semibold", 8),
                    anchor="w",
                ).pack(fill="x", pady=(0, 5))
                ttk.Entry(frame, textvariable=variable).pack(fill="x")
            row += 1

        tk.Label(
            card,
            text=(
                "IDs become permanent folder segments. Use letters, numbers, "
                "underscores, and dashes. Display names may be changed in a later "
                "revision; an existing revision ID remains immutable."
            ),
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            justify="left",
            wraplength=690,
            anchor="w",
        ).grid(
            row=row,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=16,
            pady=(12, 0),
        )
        row += 1

        summary = tk.Label(
            card,
            textvariable=self.summary_var,
            bg=COLORS["soft_blue"],
            fg=COLORS["navy"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=690,
            anchor="nw",
            padx=12,
            pady=11,
        )
        summary.grid(
            row=row,
            column=0,
            columnspan=3,
            sticky="nsew",
            padx=16,
            pady=(16, 12),
        )
        card.grid_rowconfigure(row, weight=1)
        row += 1

        actions = tk.Frame(card, bg=COLORS["card"])
        actions.grid(
            row=row,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=16,
            pady=(0, 16),
        )
        ttk.Button(actions, text="Analyze", command=self._analyze).pack(
            side="left"
        )
        self.import_button = ttk.Button(
            actions,
            text="Import Immutable Revision",
            command=self._import,
            state="disabled",
        )
        self.import_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")

    def _browse(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose standalone project folder",
            parent=self,
            mustexist=True,
        )
        if selected:
            self.source_var.set(selected)

    def _request(self) -> ProjectVaultImportRequest:
        source_text = self.source_var.get().strip()
        if not source_text:
            raise ProjectVaultError("Choose a standalone project folder first.")
        return ProjectVaultImportRequest(
            source_path=Path(source_text),
            client_id=self.client_id_var.get(),
            client_name=self.client_name_var.get(),
            project_id=self.project_id_var.get(),
            project_name=self.project_name_var.get(),
            revision_id=self.revision_id_var.get(),
            library_name=self.library_name_var.get(),
        )

    def _analyze(self) -> None:
        try:
            plan = self.controller.plan_project_vault_import(self._request())
        except Exception as error:
            self._show_error(error)
            return
        self._plan = plan
        self.import_button.configure(state="normal")
        dependencies = ", ".join(plan.dependency_names)
        self.summary_var.set(
            "Ready to import\n\n"
            f"Source: {plan.source_path}\n"
            f"Destination: {plan.revision_path}\n"
            f"Library: {plan.request.library_name}\n"
            f"LVGL: {plan.lvgl_version} (private vendored copy)\n"
            f"Dependencies: {dependencies}\n"
            f"Inventory: {plan.file_count:,} files, "
            f"{plan.total_bytes:,} bytes\n\n"
            "The source remains unchanged. The destination must not already "
            "exist. Import uses staging and final manifest validation."
        )

    def _import(self) -> None:
        plan = self._plan
        if plan is None:
            return
        confirmed = messagebox.askyesno(
            "Import Immutable Revision",
            (
                "Create this new immutable project revision?\n\n"
                f"Source:\n{plan.source_path}\n\n"
                f"Destination:\n{plan.revision_path}\n\n"
                f"Library:\n{plan.request.library_name}\n\n"
                "The source will remain unchanged. An existing revision is never "
                "overwritten."
            ),
            parent=self,
        )
        if not confirmed:
            return
        try:
            result = self.controller.import_project_vault_revision(plan)
        except Exception as error:
            self._show_error(error)
            return
        self.on_imported(result)
        messagebox.showinfo(
            "Project Revision Imported",
            (
                "The immutable revision is ready in FAH Project Vault.\n\n"
                f"{result.revision.display_path}\n\n"
                "Select it in the browser to review or create its Arduino "
                "library link."
            ),
            parent=self,
        )
        self.destroy()

    def _invalidate_plan(self, *_args: object) -> None:
        self._plan = None
        self.import_button.configure(state="disabled")

    def _show_error(self, error: BaseException) -> None:
        messagebox.showerror(
            "Import Standalone Project",
            str(error) if str(error) else error.__class__.__name__,
            parent=self,
        )

    def _center_over(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        parent.update_idletasks()
        x = parent.winfo_rootx() + max(
            0, (parent.winfo_width() - self.winfo_width()) // 2
        )
        y = parent.winfo_rooty() + max(
            0, (parent.winfo_height() - self.winfo_height()) // 2
        )
        self.geometry(f"+{x}+{y}")
