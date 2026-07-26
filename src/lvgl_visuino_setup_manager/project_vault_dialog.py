from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import tkinter as tk
from tkinter import messagebox, ttk

from . import APP_NAME
from .controller import ApplicationController
from .project_vault import (
    ActiveProjectLink,
    JunctionPlan,
    ProjectRevision,
    ProjectVaultError,
)
from .project_vault_import import ProjectVaultImportResult
from .project_vault_import_dialog import ProjectVaultImportDialog


COLORS = {
    "background": "#F3F6FA",
    "card": "#FFFFFF",
    "navy": "#102A43",
    "blue": "#1D4ED8",
    "text": "#182230",
    "muted": "#667085",
    "line": "#DCE3EC",
    "success": "#067647",
    "warning": "#B54708",
    "error": "#B42318",
    "soft_blue": "#EFF6FF",
}


class ProjectVaultDialog(tk.Toplevel):
    """Browse permanent project revisions and manage their owned junctions."""

    def __init__(
        self,
        parent: tk.Misc,
        controller: ApplicationController,
        append_activity: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.append_activity = append_activity
        self._revision_items: dict[str, ProjectRevision] = {}
        self._selected_revision: ProjectRevision | None = None
        self._selected_plan: JunctionPlan | None = None
        self._active_links: tuple[ActiveProjectLink, ...] = ()
        self._import_dialog: ProjectVaultImportDialog | None = None

        self.title(f"FAH Project Vault — {APP_NAME}")
        self.configure(bg=COLORS["background"])
        self.geometry("1040x800")
        self.minsize(860, 700)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())

        self._build()
        self._center_over(parent)
        self.refresh()
        self.focus_set()

    def _build(self) -> None:
        header = tk.Frame(self, bg=COLORS["navy"], height=92)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="PROJECT LIBRARY BROWSER",
            bg=COLORS["navy"],
            fg="#8FB8FF",
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", padx=26, pady=(12, 0))
        tk.Label(
            header,
            text="FAH Project Vault",
            bg=COLORS["navy"],
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 20),
            anchor="w",
        ).pack(fill="x", padx=26, pady=(2, 0))
        tk.Label(
            header,
            text=(
                "Permanent Client → Project → Revision storage with verified "
                "single-active switching in the normal Arduino libraries folder."
            ),
            bg=COLORS["navy"],
            fg="#D9E2EC",
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", padx=26, pady=(2, 0))

        outer = tk.Frame(self, bg=COLORS["background"])
        outer.pack(fill="both", expand=True, padx=18, pady=16)

        location = tk.Frame(
            outer,
            bg=COLORS["card"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        location.pack(fill="x", pady=(0, 12))
        location.grid_columnconfigure(1, weight=1)
        tk.Label(
            location,
            text="Vault",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
        ).grid(row=0, column=0, sticky="w", padx=(14, 8), pady=(11, 2))
        tk.Label(
            location,
            text="Arduino links",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
        ).grid(row=1, column=0, sticky="w", padx=(14, 8), pady=(2, 11))
        self.vault_path_var = tk.StringVar()
        self.libraries_path_var = tk.StringVar()
        for row, variable in (
            (0, self.vault_path_var),
            (1, self.libraries_path_var),
        ):
            tk.Label(
                location,
                textvariable=variable,
                bg=COLORS["card"],
                fg=COLORS["text"],
                font=("Segoe UI", 9),
                anchor="w",
            ).grid(
                row=row,
                column=1,
                sticky="ew",
                padx=(0, 12),
                pady=(11, 2) if row == 0 else (2, 11),
            )

        self.active_card = tk.Frame(
            outer,
            bg=COLORS["card"],
            highlightthickness=2,
            highlightbackground=COLORS["line"],
        )
        self.active_card.pack(fill="x", pady=(0, 12))
        self.active_heading_var = tk.StringVar(
            value="NO ACTIVE PROJECT VAULT REVISION"
        )
        self.active_heading_label = tk.Label(
            self.active_card,
            textvariable=self.active_heading_var,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        )
        self.active_heading_label.pack(fill="x", padx=14, pady=(10, 1))
        self.active_identity_var = tk.StringVar(
            value="Select a revision and activate it."
        )
        tk.Label(
            self.active_card,
            textvariable=self.active_identity_var,
            bg=COLORS["card"],
            fg=COLORS["navy"],
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).pack(fill="x", padx=14)
        self.active_meta_var = tk.StringVar(
            value="Arduino and Visuino currently have no Project Vault link."
        )
        tk.Label(
            self.active_card,
            textvariable=self.active_meta_var,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(1, 10))

        toolbar = tk.Frame(outer, bg=COLORS["background"])
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(
            toolbar,
            text="Initialize Vault",
            command=self._initialize,
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Open Vault Folder",
            command=self._open_folder,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="Import Standalone Project",
            command=self._open_import,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="Refresh",
            command=self.refresh,
        ).pack(side="left", padx=(8, 0))
        self.summary_var = tk.StringVar(value="Not scanned")
        tk.Label(
            toolbar,
            textvariable=self.summary_var,
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="e",
        ).pack(side="right", fill="x", expand=True)

        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)

        tree_card = tk.Frame(
            panes,
            bg=COLORS["card"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        details_card = tk.Frame(
            panes,
            bg=COLORS["card"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        panes.add(tree_card, weight=5)
        panes.add(details_card, weight=4)
        self._build_tree(tree_card)
        self._build_details(details_card)

        footer = tk.Frame(self, bg=COLORS["background"])
        footer.pack(fill="x", padx=18, pady=(0, 16))
        tk.Label(
            footer,
            text=(
                "Only one Project Vault revision is active. Switching removes "
                "only the old junction; every revision target remains in the vault."
            ),
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right")

    def _build_tree(self, parent: tk.Frame) -> None:
        tk.Label(
            parent,
            text="PROJECT REVISIONS",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 8))
        tree_frame = tk.Frame(parent, bg=COLORS["card"])
        tree_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("library", "status"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Client / Project / Revision")
        self.tree.heading("library", text="Library")
        self.tree.heading("status", text="Link")
        self.tree.column("#0", width=230, minwidth=170)
        self.tree.column("library", width=180, minwidth=120)
        self.tree.column("status", width=80, minwidth=70, anchor="center")
        self.tree.tag_configure("active", foreground=COLORS["success"])
        self.tree.tag_configure("inactive", foreground=COLORS["muted"])
        self.tree.tag_configure("broken", foreground=COLORS["warning"])
        self.tree.tag_configure("conflict", foreground=COLORS["error"])
        scrollbar = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)

    def _build_details(self, parent: tk.Frame) -> None:
        inner = tk.Frame(parent, bg=COLORS["card"])
        inner.pack(fill="both", expand=True, padx=18, pady=14)
        tk.Label(
            inner,
            text="SELECTED REVISION",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))
        self.selection_var = tk.StringVar(value="Select a revision in the browser.")
        tk.Label(
            inner,
            textvariable=self.selection_var,
            bg=COLORS["card"],
            fg=COLORS["navy"],
            font=("Segoe UI Semibold", 13),
            anchor="w",
            justify="left",
            wraplength=390,
        ).pack(fill="x", pady=(0, 12))

        self.detail_text = tk.Text(
            inner,
            height=13,
            bg="#F8FAFC",
            fg=COLORS["text"],
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
            font=("Consolas", 9),
            wrap="word",
        )
        self.detail_text.pack(fill="both", expand=True)
        self.detail_text.configure(state="disabled")

        self.status_var = tk.StringVar(value="No revision selected")
        tk.Label(
            inner,
            textvariable=self.status_var,
            bg=COLORS["soft_blue"],
            fg=COLORS["navy"],
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=390,
            padx=12,
            pady=9,
        ).pack(fill="x", pady=(12, 10))

        actions = tk.Frame(inner, bg=COLORS["card"])
        actions.pack(fill="x")
        self.activate_button = ttk.Button(
            actions,
            text="Activate This Revision",
            command=self._activate,
            state="disabled",
        )
        self.activate_button.pack(side="left")
        self.deactivate_button = ttk.Button(
            actions,
            text="Remove Library Link",
            command=self._deactivate,
            state="disabled",
        )
        self.deactivate_button.pack(side="left", padx=(8, 0))

        tk.Label(
            inner,
            text="VALIDATION ISSUES",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", pady=(16, 7))
        self.issues_var = tk.StringVar(value="None")
        tk.Label(
            inner,
            textvariable=self.issues_var,
            bg=COLORS["card"],
            fg=COLORS["error"],
            font=("Segoe UI", 8),
            anchor="w",
            justify="left",
            wraplength=390,
        ).pack(fill="x")

    def refresh(self) -> None:
        try:
            vault_root, libraries_path = self.controller.project_vault_locations()
            inventory = self.controller.project_vault_inventory()
            active_links = self.controller.project_vault_active_links()
        except Exception as error:
            self._show_error(error)
            return

        self._active_links = active_links
        self.vault_path_var.set(str(vault_root))
        self.libraries_path_var.set(str(libraries_path))
        self.tree.delete(*self.tree.get_children())
        self._revision_items.clear()
        self._selected_revision = None
        self._selected_plan = None

        clients: dict[str, str] = {}
        projects: dict[tuple[str, str], str] = {}
        for index, revision in enumerate(inventory.revisions):
            client_item = clients.get(revision.client_id)
            if client_item is None:
                client_item = f"client-{len(clients)}"
                clients[revision.client_id] = client_item
                self.tree.insert(
                    "",
                    "end",
                    iid=client_item,
                    text=revision.client_name,
                    open=True,
                )
            project_key = (revision.client_id, revision.project_id)
            project_item = projects.get(project_key)
            if project_item is None:
                project_item = f"project-{len(projects)}"
                projects[project_key] = project_item
                self.tree.insert(
                    client_item,
                    "end",
                    iid=project_item,
                    text=revision.project_name,
                    open=True,
                )
            item_id = f"revision-{index}"
            try:
                plan = self.controller.project_vault_link_plan(revision)
                status = plan.status
            except ProjectVaultError:
                status = "broken"
            self.tree.insert(
                project_item,
                "end",
                iid=item_id,
                text=revision.revision_id,
                values=(revision.library_name, status.title()),
                tags=(status,),
            )
            self._revision_items[item_id] = revision

        if not inventory.revisions:
            self.tree.insert(
                "",
                "end",
                text="No valid project revisions found",
                values=("", ""),
            )

        self.summary_var.set(
            f"{len(inventory.revisions)} revision(s) · "
            f"{len(inventory.issues)} issue(s)"
        )
        if inventory.issues:
            lines = [
                f"• {issue.path.name}: {issue.message}"
                for issue in inventory.issues[:4]
            ]
            if len(inventory.issues) > 4:
                lines.append(f"• …and {len(inventory.issues) - 4} more")
            self.issues_var.set("\n".join(lines))
        else:
            self.issues_var.set("None")
        self._show_active_summary(inventory.revisions, active_links)
        self._show_revision(None, None)

    def _show_active_summary(
        self,
        revisions: tuple[ProjectRevision, ...],
        active_links: tuple[ActiveProjectLink, ...],
    ) -> None:
        if not active_links:
            self.active_heading_var.set("NO ACTIVE PROJECT VAULT REVISION")
            self.active_identity_var.set("Select a revision and activate it.")
            self.active_meta_var.set(
                "Arduino and Visuino currently have no Project Vault link."
            )
            self.active_heading_label.configure(fg=COLORS["muted"])
            self.active_card.configure(highlightbackground=COLORS["line"])
            return
        if len(active_links) > 1:
            self.active_heading_var.set("LEGACY MULTIPLE-LINK STATE")
            self.active_identity_var.set(
                f"{len(active_links)} Project Vault links are recorded."
            )
            self.active_meta_var.set(
                "Select one revision and switch to it to retain exactly one "
                "active link."
            )
            self.active_heading_label.configure(fg=COLORS["warning"])
            self.active_card.configure(highlightbackground=COLORS["warning"])
            return

        active = active_links[0]
        revision = next(
            (
                candidate
                for candidate in revisions
                if candidate.client_id == active.client_id
                and candidate.project_id == active.project_id
                and candidate.revision_id == active.revision_id
                and candidate.library_name == active.library_name
            ),
            None,
        )
        identity = (
            f"{revision.client_name} / {revision.project_name} / "
            f"{revision.revision_id}"
            if revision is not None
            else f"{active.client_id} / {active.project_id} / {active.revision_id}"
        )
        verified_text = "Link verified" if active.verified else active.message
        self.active_heading_var.set(
            "ACTIVE PROJECT VAULT REVISION"
            if active.verified
            else "ACTIVE LINK NEEDS ATTENTION"
        )
        self.active_identity_var.set(identity)
        self.active_meta_var.set(
            f"Activated: {self._format_timestamp(active.linked_at)}  •  "
            f"{verified_text}  •  {active.library_name}"
        )
        color = COLORS["success"] if active.verified else COLORS["error"]
        self.active_heading_label.configure(fg=color)
        self.active_card.configure(highlightbackground=color)

    @staticmethod
    def _format_timestamp(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value
        return parsed.strftime("%Y-%m-%d %H:%M:%S %z")

    def _selection_changed(self, _event: tk.Event[tk.Misc]) -> None:
        selection = self.tree.selection()
        revision = self._revision_items.get(selection[0]) if selection else None
        if revision is None:
            self._show_revision(None, None)
            return
        try:
            plan = self.controller.project_vault_link_plan(revision)
        except Exception as error:
            self._show_revision(revision, None)
            self.status_var.set(str(error))
            return
        self._show_revision(revision, plan)

    def _show_revision(
        self,
        revision: ProjectRevision | None,
        plan: JunctionPlan | None,
    ) -> None:
        self._selected_revision = revision
        self._selected_plan = plan
        if revision is None:
            self.selection_var.set("Select a revision in the browser.")
            details = (
                "A revision is an immutable, self-contained project library.\n\n"
                "Creating a link makes that exact library visible in the normal "
                "Arduino libraries folder. The link remains available after "
                "closing this program."
            )
            self.status_var.set("No revision selected")
            self.activate_button.configure(text="Activate This Revision")
            self.activate_button.configure(state="disabled")
            self.deactivate_button.configure(state="disabled")
        else:
            self.selection_var.set(revision.display_path)
            details = (
                f"Library:  {revision.library_name}\n"
                f"LVGL:     {revision.lvgl_version} ({revision.lvgl_storage})\n"
                f"Revision: {revision.revision_path}\n"
                f"Target:   {revision.library_path}\n"
                f"Sketch:   {revision.root_ino_path.name}\n"
                f"Manifest: {revision.manifest_path.name}"
            )
            if plan is None:
                self.status_var.set("Link status could not be verified.")
                self.activate_button.configure(text="Activate This Revision")
                self.activate_button.configure(state="disabled")
                self.deactivate_button.configure(state="disabled")
            else:
                self.status_var.set(
                    f"{plan.status.title()}: {plan.message}\n"
                    f"Link: {plan.link_path}"
                )
                if plan.action == "switch":
                    self.activate_button.configure(
                        text="Switch Active Revision", state="normal"
                    )
                elif plan.action == "create":
                    self.activate_button.configure(
                        text="Activate This Revision", state="normal"
                    )
                else:
                    self.activate_button.configure(
                        text="Active Revision", state="disabled"
                    )
                self.deactivate_button.configure(
                    state="normal"
                    if plan.action == "unchanged" and plan.status == "active"
                    else "disabled"
                )

        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", details)
        self.detail_text.configure(state="disabled")

    def _initialize(self) -> None:
        try:
            root = self.controller.initialize_project_vault()
        except Exception as error:
            self._show_error(error)
            return
        self.append_activity(f"Initialized FAH Project Vault: {root}")
        self.refresh()
        messagebox.showinfo(
            "FAH Project Vault",
            (
                f"The permanent vault and normal Arduino libraries folder are ready.\n\n"
                f"Vault:\n{root}"
            ),
            parent=self,
        )

    def _open_folder(self) -> None:
        try:
            root = self.controller.open_project_vault_folder()
        except Exception as error:
            self._show_error(error)
            return
        self.append_activity(f"Opened FAH Project Vault: {root}")

    def _open_import(self) -> None:
        if (
            self._import_dialog is not None
            and self._import_dialog.winfo_exists()
        ):
            self._import_dialog.lift()
            self._import_dialog.focus_set()
            return
        self._import_dialog = ProjectVaultImportDialog(
            self,
            self.controller,
            self._import_completed,
        )

    def _import_completed(self, result: ProjectVaultImportResult) -> None:
        self.append_activity(
            "Imported immutable FAH Project Vault revision: "
            f"{result.revision.display_path}"
        )
        self.refresh()

    def _activate(self) -> None:
        revision = self._selected_revision
        plan = self._selected_plan
        if (
            revision is None
            or plan is None
            or plan.action not in {"create", "switch"}
        ):
            return
        switching = plan.action == "switch"
        current_active = "\n".join(
            self._active_identity(active) for active in self._active_links
        ) or "None"
        confirmed = messagebox.askyesno(
            "Switch Active Revision" if switching else "Activate Project Revision",
            (
                (
                    "Switch the one active Project Vault revision?\n\n"
                    f"Current active:\n{current_active}\n\n"
                    if switching
                    else "Activate this Project Vault revision?\n\n"
                )
                + f"New active:\n{revision.display_path}\n\n"
                f"Library link:\n{plan.link_path}\n\n"
                f"Permanent project target:\n{plan.target_path}\n\n"
                "The new link is verified before the previous FAH-owned link is "
                "removed. Every permanent project and UI file is preserved, and "
                "the previous link is restored if switching fails. Visuino must "
                "be closed."
            ),
            parent=self,
        )
        if not confirmed:
            return
        try:
            result = self.controller.activate_project_vault_revision(revision)
        except Exception as error:
            self._show_error(error)
            return
        self.append_activity(
            (
                f"Switched active Project Vault revision to: {result.library_name}"
                if result.action == "switched"
                else f"Activated Project Vault revision: {result.library_name}"
            )
        )
        self.refresh()
        messagebox.showinfo(
            "Library Link Ready",
            (
                f"{result.message}\n\n"
                f"Activated:\n{self._format_timestamp(result.linked_at or '')}\n\n"
                f"Link:\n{result.link_path}\n\n"
                f"Target:\n{result.target_path}"
            ),
            parent=self,
        )

    def _active_identity(self, active: ActiveProjectLink) -> str:
        revision = next(
            (
                candidate
                for candidate in self._revision_items.values()
                if candidate.client_id == active.client_id
                and candidate.project_id == active.project_id
                and candidate.revision_id == active.revision_id
                and candidate.library_name == active.library_name
            ),
            None,
        )
        if revision is not None:
            return (
                f"{revision.client_name} / {revision.project_name} / "
                f"{revision.revision_id}"
            )
        return f"{active.client_id} / {active.project_id} / {active.revision_id}"

    def _deactivate(self) -> None:
        revision = self._selected_revision
        plan = self._selected_plan
        if (
            revision is None
            or plan is None
            or plan.action != "unchanged"
            or plan.status != "active"
        ):
            return
        confirmed = messagebox.askyesno(
            "Remove Library Link",
            (
                "Remove only this FAH-owned junction from Arduino libraries?\n\n"
                f"Link:\n{plan.link_path}\n\n"
                f"Preserved project target:\n{plan.target_path}\n\n"
                "The permanent project revision and every file inside it will "
                "remain untouched. Visuino must be closed."
            ),
            parent=self,
        )
        if not confirmed:
            return
        try:
            result = self.controller.deactivate_project_vault_library(
                revision.library_name
            )
        except Exception as error:
            self._show_error(error)
            return
        self.append_activity(
            f"Removed Arduino library link; target preserved: {result.target_path}"
        )
        self.refresh()
        messagebox.showinfo(
            "Library Link Removed",
            (
                f"{result.message}\n\n"
                f"Preserved target:\n{result.target_path}"
            ),
            parent=self,
        )

    def _show_error(self, error: BaseException) -> None:
        messagebox.showerror(
            "FAH Project Vault",
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
