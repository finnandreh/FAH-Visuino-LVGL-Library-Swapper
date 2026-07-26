from __future__ import annotations

import queue
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import APP_NAME
from .about_dialog import AboutDedicationDialog
from .activation import ActivationError
from .branding import (
    DEVELOPER_LINE,
    HEADER_DEDICATION,
    finnandre_logo_path,
    load_finnandre_logo,
)
from .controller import ApplicationController
from .custom_code_dialog import CustomCodeDialog
from .implementation import ImplementationError
from .profile_cleanup import ProfileCleanupError, ProfileCleanupResult
from .profile_cleanup_dialog import ProfileCleanupDialog
from .project_vault import ProjectVaultError
from .project_vault_dialog import ProjectVaultDialog
from .registry import RegistryError
from .setup_service import BaselineRepairError
from .validation_dialog import (
    SOURCE_MISSING_MESSAGE,
    ask_baseline_repair,
    ask_baseline_source,
    invalid_baseline_badges,
)


COLORS = {
    "background": "#F3F6FA",
    "card": "#FFFFFF",
    "navy": "#102A43",
    "blue": "#1D4ED8",
    "blue_hover": "#1E40AF",
    "text": "#182230",
    "muted": "#667085",
    "line": "#DCE3EC",
    "success": "#067647",
    "success_bg": "#ECFDF3",
    "error": "#B42318",
    "error_bg": "#FEF3F2",
    "warning": "#B54708",
    "warning_bg": "#FFFAEB",
    "neutral": "#475467",
    "neutral_bg": "#F2F4F7",
}


class MainApplication(tk.Tk):
    def __init__(self, controller: ApplicationController) -> None:
        super().__init__()
        self.controller = controller
        self.title(APP_NAME)
        self.geometry("1120x780")
        self.minsize(960, 700)
        self.configure(bg=COLORS["background"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.selected_client_id: str | None = None
        self.selected_project_id: str | None = None
        self.selected_setup_id: str | None = None
        self._client_records: list[dict[str, Any]] = []
        self._project_records: list[dict[str, Any]] = []
        self._setup_records: list[dict[str, Any]] = []
        self._busy = False
        self._custom_code_dialog: CustomCodeDialog | None = None
        self._profile_cleanup_dialog: ProfileCleanupDialog | None = None
        self._project_vault_dialog: ProjectVaultDialog | None = None
        self._about_dialog: AboutDedicationDialog | None = None
        self._brand_icon: tk.PhotoImage | None = None
        self._header_logo: tk.PhotoImage | None = None
        self._baseline_plan: Any | None = None
        self._validation_action: str | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="visuino-gui")
        self._results: queue.Queue[
            tuple[str, Callable[[Any], None] | None, Any, BaseException | None]
        ] = queue.Queue()

        self._configure_styles()
        self._load_brand_images()
        self._build_window()
        self._load_registry()
        self.after(100, self._poll_worker_results)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(
            "TCombobox",
            font=("Segoe UI", 10),
            padding=(8, 7),
            fieldbackground=COLORS["card"],
            background=COLORS["card"],
            bordercolor=COLORS["line"],
            lightcolor=COLORS["line"],
            darkcolor=COLORS["line"],
            arrowcolor=COLORS["navy"],
        )
        style.map(
            "TCombobox",
            bordercolor=[("focus", COLORS["blue"])],
            fieldbackground=[("readonly", COLORS["card"])],
            selectbackground=[("readonly", COLORS["card"])],
            selectforeground=[("readonly", COLORS["text"])],
        )
        style.configure(
            "Primary.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(15, 9),
            foreground="#FFFFFF",
            background=COLORS["blue"],
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", COLORS["blue_hover"]),
                ("disabled", "#A8B5C8"),
            ],
            foreground=[("disabled", "#F3F6FA")],
        )
        style.configure(
            "Secondary.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(11, 7),
            foreground=COLORS["navy"],
            background="#EEF3F8",
            bordercolor=COLORS["line"],
            borderwidth=1,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#E1E8F0"), ("disabled", "#F2F4F7")],
            foreground=[("disabled", "#98A2B3")],
        )
        style.configure(
            "Quiet.TButton",
            font=("Segoe UI", 9),
            padding=(8, 6),
            foreground=COLORS["blue"],
            background=COLORS["card"],
            borderwidth=0,
        )
        style.map(
            "Quiet.TButton",
            background=[("active", "#EFF6FF")],
            foreground=[("disabled", "#98A2B3")],
        )
        style.configure(
            "Danger.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(11, 7),
            foreground="#FFFFFF",
            background=COLORS["error"],
            borderwidth=0,
        )
        style.map(
            "Danger.TButton",
            background=[
                ("active", "#912018"),
                ("disabled", "#D0D5DD"),
            ],
            foreground=[("disabled", "#F9FAFB")],
        )

    def _build_window(self) -> None:
        self._build_header()
        self._build_footer()

        content = tk.Frame(self, bg=COLORS["background"])
        content.pack(fill="both", expand=True, padx=24, pady=(20, 14))
        content.grid_columnconfigure(0, weight=11, uniform="content")
        content.grid_columnconfigure(1, weight=9, uniform="content")
        content.grid_rowconfigure(1, weight=1)

        selection_card = self._card(content)
        selection_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 12))
        self._build_selection_card(selection_card)

        details_card = self._card(content)
        details_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 12))
        self._build_details_card(details_card)

        actions_card = self._card(content)
        actions_card.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self._build_actions_card(actions_card)

        activity_card = self._card(content)
        activity_card.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        self._build_activity_card(activity_card)

    def _build_footer(self) -> None:
        footer = tk.Frame(self, bg=COLORS["navy"], height=28)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self.footer_status = tk.StringVar(value="Ready")
        tk.Label(
            footer,
            textvariable=self.footer_status,
            bg=COLORS["navy"],
            fg="#D9E2EC",
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(side="left", fill="both", expand=True, padx=(24, 8))
        tk.Label(
            footer,
            text=DEVELOPER_LINE,
            bg=COLORS["navy"],
            fg="#9FB3C8",
            font=("Segoe UI", 8),
            anchor="e",
        ).pack(side="right", fill="y", padx=(8, 24))

    def _load_brand_images(self) -> None:
        try:
            self._brand_icon = tk.PhotoImage(file=str(finnandre_logo_path()))
            self.iconphoto(True, self._brand_icon)
            self._header_logo = load_finnandre_logo(68, master=self)
        except (OSError, ValueError, tk.TclError):
            self._brand_icon = None
            self._header_logo = None

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=COLORS["navy"], height=96)
        header.pack(fill="x")
        header.pack_propagate(False)
        if self._header_logo is not None:
            tk.Label(
                header,
                image=self._header_logo,
                bg=COLORS["navy"],
                borderwidth=0,
            ).pack(side="left", padx=(18, 0))
        text_area = tk.Frame(header, bg=COLORS["navy"])
        text_area.pack(side="left", fill="y", padx=(14, 26), pady=14)
        tk.Label(
            text_area,
            text=HEADER_DEDICATION,
            bg=COLORS["navy"],
            fg="#8FB8FF",
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            text_area,
            text=APP_NAME,
            bg=COLORS["navy"],
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 20),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        header_actions = tk.Frame(header, bg=COLORS["navy"])
        header_actions.pack(side="right", fill="y", padx=(10, 26), pady=14)
        action_row = tk.Frame(header_actions, bg=COLORS["navy"])
        action_row.pack(anchor="e")
        tk.Button(
            action_row,
            text="FAH Project Vault",
            command=self._open_project_vault,
            bg=COLORS["navy"],
            fg="#D9E2EC",
            activebackground="#163A5F",
            activeforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 9),
            padx=5,
            pady=3,
        ).pack(side="left")
        tk.Button(
            action_row,
            text="About & Dedication",
            command=self._open_about_dedication,
            bg=COLORS["navy"],
            fg="#D9E2EC",
            activebackground="#163A5F",
            activeforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 9),
            padx=5,
            pady=3,
        ).pack(side="left", padx=(12, 0))
        tk.Label(
            header_actions,
            text="Client → Project → Setup",
            bg=COLORS["navy"],
            fg="#9FB3C8",
            font=("Segoe UI", 9),
        ).pack(anchor="e", pady=(5, 0))

    def _open_project_vault(self) -> None:
        if (
            self._project_vault_dialog is not None
            and self._project_vault_dialog.winfo_exists()
        ):
            self._project_vault_dialog.lift()
            self._project_vault_dialog.focus_set()
            return
        self._project_vault_dialog = ProjectVaultDialog(
            self,
            self.controller,
            self._append_activity,
        )

    def _open_about_dedication(self) -> None:
        if (
            self._about_dialog is not None
            and self._about_dialog.winfo_exists()
        ):
            self._about_dialog.lift()
            self._about_dialog.focus_set()
            return
        self._about_dialog = AboutDedicationDialog(self)

    @staticmethod
    def _card(parent: tk.Widget) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=COLORS["card"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
            bd=0,
        )

    @staticmethod
    def _section_title(parent: tk.Widget, title: str, subtitle: str) -> None:
        tk.Label(
            parent,
            text=title,
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 13),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            parent,
            text=subtitle,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(2, 14))

    def _build_selection_card(self, card: tk.Frame) -> None:
        inner = tk.Frame(card, bg=COLORS["card"])
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        self._section_title(
            inner,
            "Setup library",
            "Choose the customer context and the exact Visuino library setup.",
        )

        self.client_combo, client_buttons = self._selector_row(
            inner, "Client", self._new_client, self._rename_client
        )
        self.project_combo, project_buttons = self._selector_row(
            inner, "Project", self._new_project, self._rename_project
        )
        self.setup_combo, setup_buttons = self._selector_row(
            inner, "Setup", self._new_setup, self._rename_setup, add_label="New Setup"
        )
        self.client_new_button, self.client_rename_button = client_buttons
        self.project_new_button, self.project_rename_button = project_buttons
        self.setup_new_button, self.setup_rename_button = setup_buttons

        setup_tools = tk.Frame(inner, bg=COLORS["card"])
        setup_tools.pack(fill="x", pady=(5, 0))
        self.link_button = ttk.Button(
            setup_tools,
            text="Link Folder",
            style="Secondary.TButton",
            command=self._link_setup,
        )
        self.link_button.pack(side="left")
        self.open_button = ttk.Button(
            setup_tools,
            text="Open Folder",
            style="Quiet.TButton",
            command=self._open_setup_folder,
        )
        self.open_button.pack(side="left", padx=(8, 0))
        self.remove_setup_button = ttk.Button(
            setup_tools,
            text="Remove Profile",
            style="Quiet.TButton",
            command=self._remove_setup,
        )
        self.remove_setup_button.pack(side="left", padx=(8, 0))

        cleanup_tools = tk.Frame(inner, bg=COLORS["card"])
        cleanup_tools.pack(fill="x", pady=(6, 0))
        self.profile_cleanup_button = ttk.Button(
            cleanup_tools,
            text="Clear / Delete…",
            style="Danger.TButton",
            command=self._open_profile_cleanup,
        )
        self.profile_cleanup_button.pack(side="left")
        self.custom_code_button = ttk.Button(
            cleanup_tools,
            text="Device & Custom Code",
            style="Secondary.TButton",
            command=self._open_custom_code,
        )
        self.custom_code_button.pack(side="right")

        self.client_combo.bind("<<ComboboxSelected>>", self._on_client_selected)
        self.project_combo.bind("<<ComboboxSelected>>", self._on_project_selected)
        self.setup_combo.bind("<<ComboboxSelected>>", self._on_setup_selected)

    def _selector_row(
        self,
        parent: tk.Widget,
        label: str,
        add_command: Callable[[], None],
        rename_command: Callable[[], None] | None,
        *,
        add_label: str = "New",
    ) -> tuple[ttk.Combobox, tuple[ttk.Button, ttk.Button | None]]:
        container = tk.Frame(parent, bg=COLORS["card"])
        container.pack(fill="x", pady=(0, 9))
        tk.Label(
            container,
            text=label,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", pady=(0, 3))
        row = tk.Frame(container, bg=COLORS["card"])
        row.pack(fill="x")
        combo = ttk.Combobox(row, state="readonly")
        combo.pack(side="left", fill="x", expand=True)
        add_button = ttk.Button(
            row, text=add_label, style="Secondary.TButton", command=add_command
        )
        add_button.pack(side="left", padx=(7, 0))
        rename_button: ttk.Button | None = None
        if rename_command:
            rename_button = ttk.Button(
                row, text="Rename", style="Quiet.TButton", command=rename_command
            )
            rename_button.pack(side="left", padx=(3, 0))
        return combo, (add_button, rename_button)

    def _build_details_card(self, card: tk.Frame) -> None:
        inner = tk.Frame(card, bg=COLORS["card"])
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        self._section_title(
            inner,
            "Setup readiness",
            "Activation requires Mitov and a resolved setup path; VisuinoPro is optional.",
        )

        self.setup_title = tk.StringVar(value="No setup selected")
        tk.Label(
            inner,
            textvariable=self.setup_title,
            bg=COLORS["card"],
            fg=COLORS["navy"],
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).pack(fill="x", pady=(0, 9))

        tk.Label(
            inner,
            text="FOLDER PATH",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x")
        self.path_value = tk.StringVar(value="—")
        path_label = tk.Label(
            inner,
            textvariable=self.path_value,
            bg="#F8FAFC",
            fg=COLORS["text"],
            font=("Consolas", 8),
            anchor="w",
            justify="left",
            wraplength=390,
            padx=9,
            pady=7,
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        path_label.pack(fill="x", pady=(3, 12))

        badge_row = tk.Frame(inner, bg=COLORS["card"])
        badge_row.pack(fill="x")
        self.mitov_badge = self._badge(badge_row, "Mitov · unknown")
        self.mitov_badge.pack(side="left", padx=(0, 7))
        self.pro_badge = self._badge(badge_row, "VisuinoPro · unknown")
        self.pro_badge.pack(side="left")

        self.validation_badge = self._badge(inner, "Not validated")
        self.validation_badge.pack(anchor="w", pady=(10, 0))
        self.active_label = tk.Label(
            inner,
            text="",
            bg=COLORS["card"],
            fg=COLORS["blue"],
            font=("Segoe UI Semibold", 9),
            anchor="w",
        )
        self.active_label.pack(fill="x", pady=(10, 0))

        self.validation_guidance = tk.Frame(
            inner,
            bg=COLORS["warning_bg"],
            highlightthickness=1,
            highlightbackground="#FEDF89",
        )
        self.validation_guidance_message = tk.StringVar(value="")
        self.validation_guidance_label = tk.Label(
            self.validation_guidance,
            textvariable=self.validation_guidance_message,
            bg=COLORS["warning_bg"],
            fg=COLORS["warning"],
            font=("Segoe UI Semibold", 9),
            justify="left",
            anchor="w",
            wraplength=400,
        )
        self.validation_guidance_label.pack(
            fill="x", padx=11, pady=(9, 6)
        )
        guidance_actions = tk.Frame(
            self.validation_guidance,
            bg=COLORS["warning_bg"],
        )
        guidance_actions.pack(fill="x", padx=8, pady=(0, 8))
        self.validation_fix_button = ttk.Button(
            guidance_actions,
            text="Fix Setup",
            style="Secondary.TButton",
            command=self._validation_fix_requested,
        )
        self.validation_fix_button.pack(side="left")
        self.validation_not_now_button = ttk.Button(
            guidance_actions,
            text="Not Now",
            style="Quiet.TButton",
            command=self._dismiss_validation_guidance,
        )
        self.validation_not_now_button.pack(side="left", padx=(4, 0))

    @staticmethod
    def _badge(parent: tk.Widget, text: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=COLORS["neutral_bg"],
            fg=COLORS["neutral"],
            font=("Segoe UI Semibold", 8),
            padx=8,
            pady=4,
        )

    def _build_actions_card(self, card: tk.Frame) -> None:
        inner = tk.Frame(card, bg=COLORS["card"])
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        self._section_title(
            inner,
            "Protected actions",
            "Validate first. Activation backs up both Visuino settings and rolls back on failure.",
        )
        self.validate_button = ttk.Button(
            inner,
            text="Validate Setup",
            style="Secondary.TButton",
            command=self._validate_setup,
        )
        self.validate_button.pack(fill="x", pady=(0, 8))
        self.activate_button = ttk.Button(
            inner,
            text="Activate & Start Visuino",
            style="Primary.TButton",
            command=self._activate_setup,
        )
        self.activate_button.pack(fill="x", pady=(0, 8))
        self.restore_button = ttk.Button(
            inner,
            text="Restore Recorded Default",
            style="Secondary.TButton",
            command=self._restore_default,
        )
        self.restore_button.pack(fill="x")

    def _build_activity_card(self, card: tk.Frame) -> None:
        inner = tk.Frame(card, bg=COLORS["card"])
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        self._section_title(
            inner,
            "Activity",
            "Local status for this session. Full structured history is stored in the audit log.",
        )
        self.activity = tk.Text(
            inner,
            height=10,
            bg="#F8FAFC",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            font=("Consolas", 8),
            relief="flat",
            borderwidth=0,
            padx=9,
            pady=8,
            wrap="word",
            state="disabled",
        )
        self.activity.pack(fill="both", expand=True)
        self._append_activity("Application ready.")

    def _load_registry(
        self,
        *,
        preferred_client: str | None = None,
        preferred_project: str | None = None,
        preferred_setup: str | None = None,
    ) -> None:
        data = self.controller.registry_snapshot()
        self._client_records = data["clients"]
        self.client_combo["values"] = [item["name"] for item in self._client_records]
        client_id = preferred_client or self.selected_client_id
        client_index = self._index_for_id(self._client_records, client_id)
        if client_index is None and self._client_records:
            client_index = 0
        if client_index is None:
            self.client_combo.set("")
            self.selected_client_id = None
            self._project_records = []
            self.project_combo["values"] = []
            self.setup_combo["values"] = []
            self.selected_project_id = None
            self.selected_setup_id = None
        else:
            self.client_combo.current(client_index)
            self.selected_client_id = self._client_records[client_index]["id"]
            self._load_projects(preferred_project, preferred_setup)
        self._refresh_details()
        self._update_command_states()

    def _load_projects(
        self, preferred_project: str | None = None, preferred_setup: str | None = None
    ) -> None:
        client = self._record_for_id(self._client_records, self.selected_client_id)
        self._project_records = client["projects"] if client else []
        self.project_combo["values"] = [item["name"] for item in self._project_records]
        project_id = preferred_project or self.selected_project_id
        project_index = self._index_for_id(self._project_records, project_id)
        if project_index is None and self._project_records:
            project_index = 0
        if project_index is None:
            self.project_combo.set("")
            self.selected_project_id = None
            self._setup_records = []
            self.setup_combo["values"] = []
            self.setup_combo.set("")
            self.selected_setup_id = None
        else:
            self.project_combo.current(project_index)
            self.selected_project_id = self._project_records[project_index]["id"]
            self._load_setups(preferred_setup)

    def _load_setups(self, preferred_setup: str | None = None) -> None:
        project = self._record_for_id(self._project_records, self.selected_project_id)
        self._setup_records = project["setups"] if project else []
        active_id = self.controller.registry_snapshot().get("activeSetupId")
        values = [
            f"{item['name']}  • active" if item["id"] == active_id else item["name"]
            for item in self._setup_records
        ]
        self.setup_combo["values"] = values
        setup_id = preferred_setup or self.selected_setup_id
        setup_index = self._index_for_id(self._setup_records, setup_id)
        if setup_index is None and self._setup_records:
            setup_index = 0
        if setup_index is None:
            self.setup_combo.set("")
            self.selected_setup_id = None
        else:
            self.setup_combo.current(setup_index)
            self.selected_setup_id = self._setup_records[setup_index]["id"]

    @staticmethod
    def _index_for_id(records: list[dict[str, Any]], record_id: str | None) -> int | None:
        if record_id is None:
            return None
        for index, record in enumerate(records):
            if record["id"] == record_id:
                return index
        return None

    @staticmethod
    def _record_for_id(
        records: list[dict[str, Any]], record_id: str | None
    ) -> dict[str, Any] | None:
        if record_id is None:
            return None
        return next((item for item in records if item["id"] == record_id), None)

    def _on_client_selected(self, _event: object = None) -> None:
        self._dismiss_validation_guidance()
        index = self.client_combo.current()
        self.selected_client_id = (
            self._client_records[index]["id"] if index >= 0 else None
        )
        self.selected_project_id = None
        self.selected_setup_id = None
        self._load_projects()
        self._refresh_details()
        self._update_command_states()

    def _on_project_selected(self, _event: object = None) -> None:
        self._dismiss_validation_guidance()
        index = self.project_combo.current()
        self.selected_project_id = (
            self._project_records[index]["id"] if index >= 0 else None
        )
        self.selected_setup_id = None
        self._load_setups()
        self._refresh_details()
        self._update_command_states()

    def _on_setup_selected(self, _event: object = None) -> None:
        self._dismiss_validation_guidance()
        index = self.setup_combo.current()
        self.selected_setup_id = (
            self._setup_records[index]["id"] if index >= 0 else None
        )
        self._refresh_details()
        self._update_command_states()

    def _refresh_details(self) -> None:
        setup = self._record_for_id(self._setup_records, self.selected_setup_id)
        if not setup:
            self.setup_title.set("No setup selected")
            self.path_value.set("—")
            self._set_badge(self.mitov_badge, "unknown", "Mitov · unknown")
            self._set_badge(self.pro_badge, "unknown", "VisuinoPro · unknown")
            self._set_badge(self.validation_badge, "unknown", "Not validated")
            self.active_label.configure(text="")
            return

        self.setup_title.set(setup["name"])
        self.path_value.set(setup["folderPath"])
        validation = setup["validation"]
        state = validation["status"]
        warnings = validation.get("warnings", [])
        missing_pro = any("VisuinoPro" in warning for warning in warnings)

        if state == "valid":
            self._set_badge(self.mitov_badge, "valid", "Mitov · ready")
            self._set_badge(
                self.pro_badge,
                "unknown" if missing_pro else "valid",
                "VisuinoPro · optional" if missing_pro else "VisuinoPro · ready",
            )
            checked = validation.get("lastValidatedAt") or ""
            self._set_badge(
                self.validation_badge,
                "valid",
                f"Validated · {self._short_time(checked)}",
            )
        elif state == "invalid":
            mitov_presentation, pro_presentation = invalid_baseline_badges(
                warnings
            )
            self._set_badge(self.mitov_badge, *mitov_presentation)
            self._set_badge(self.pro_badge, *pro_presentation)
            self._set_badge(self.validation_badge, "invalid", "Validation failed")
        elif state == "busy":
            self._set_badge(self.validation_badge, "busy", "Validating…")
        else:
            self._set_badge(self.mitov_badge, "unknown", "Mitov · unknown")
            self._set_badge(self.pro_badge, "unknown", "VisuinoPro · unknown")
            self._set_badge(self.validation_badge, "unknown", "Not validated")

        active_id = self.controller.registry_snapshot().get("activeSetupId")
        self.active_label.configure(
            text="● Active Visuino setup" if setup["id"] == active_id else ""
        )

    @staticmethod
    def _short_time(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.strftime("%d %b %H:%M")
        except ValueError:
            return "ready"

    @staticmethod
    def _set_badge(widget: tk.Label, state: str, text: str) -> None:
        palette = {
            "valid": (COLORS["success_bg"], COLORS["success"]),
            "invalid": (COLORS["error_bg"], COLORS["error"]),
            "busy": (COLORS["warning_bg"], COLORS["warning"]),
            "unknown": (COLORS["neutral_bg"], COLORS["neutral"]),
        }
        background, foreground = palette.get(state, palette["unknown"])
        widget.configure(text=text, bg=background, fg=foreground)

    def _update_command_states(self) -> None:
        idle = not self._busy
        has_client = self.selected_client_id is not None
        has_project = self.selected_project_id is not None
        has_setup = self.selected_setup_id is not None
        setup = self._record_for_id(self._setup_records, self.selected_setup_id)
        valid = bool(setup and setup["validation"]["status"] == "valid")
        active_id = self.controller.registry_snapshot().get("activeSetupId")

        self._set_state(self.client_new_button, idle)
        self._set_state(self.client_rename_button, idle and has_client)
        self._set_state(self.project_new_button, idle and has_client)
        self._set_state(self.project_rename_button, idle and has_project)
        self._set_state(self.setup_new_button, idle and has_project)
        self._set_state(self.setup_rename_button, idle and has_setup)
        self._set_state(
            self.remove_setup_button,
            idle and has_setup and self.selected_setup_id != active_id,
        )
        self._set_state(self.link_button, idle and has_project)
        self._set_state(self.open_button, idle and has_setup)
        self._set_state(self.profile_cleanup_button, idle and has_setup)
        self._set_state(self.custom_code_button, idle and has_setup)
        self._set_state(self.validate_button, idle and has_setup)
        self._set_state(
            self.validation_fix_button,
            idle and self._validation_action is not None,
        )
        self._set_state(
            self.validation_not_now_button,
            idle and self.validation_guidance.winfo_manager() == "pack",
        )
        self._set_state(self.activate_button, idle and valid)
        self._set_state(
            self.restore_button,
            idle and self.controller.activation_service.default_snapshot_exists,
        )
        combo_state = "readonly" if idle else "disabled"
        self.client_combo.configure(state=combo_state)
        self.project_combo.configure(state=combo_state)
        self.setup_combo.configure(state=combo_state)

    @staticmethod
    def _set_state(widget: ttk.Button | None, enabled: bool) -> None:
        if widget is not None:
            widget.configure(state="normal" if enabled else "disabled")

    def _new_client(self) -> None:
        name = simpledialog.askstring(
            "New Client", "Client name:", parent=self
        )
        if not name:
            return
        try:
            client_id = self.controller.create_client(name)
            self._load_registry(preferred_client=client_id)
            self._append_activity(f"Created client: {name.strip()}")
        except Exception as error:
            self._show_error(error)

    def _rename_client(self) -> None:
        client = self._record_for_id(self._client_records, self.selected_client_id)
        if not client:
            return
        name = simpledialog.askstring(
            "Rename Client",
            "Client name:",
            initialvalue=client["name"],
            parent=self,
        )
        if not name or name.strip() == client["name"]:
            return
        try:
            self.controller.rename_client(client["id"], name)
            self._load_registry(preferred_client=client["id"])
            self._append_activity(f"Renamed client to: {name.strip()}")
        except Exception as error:
            self._show_error(error)

    def _new_project(self) -> None:
        if not self.selected_client_id:
            return
        name = simpledialog.askstring(
            "New Project", "Project name:", parent=self
        )
        if not name:
            return
        try:
            project_id = self.controller.create_project(self.selected_client_id, name)
            self._load_registry(
                preferred_client=self.selected_client_id,
                preferred_project=project_id,
            )
            self._append_activity(f"Created project: {name.strip()}")
        except Exception as error:
            self._show_error(error)

    def _rename_project(self) -> None:
        project = self._record_for_id(self._project_records, self.selected_project_id)
        if not project or not self.selected_client_id:
            return
        name = simpledialog.askstring(
            "Rename Project",
            "Project name:",
            initialvalue=project["name"],
            parent=self,
        )
        if not name or name.strip() == project["name"]:
            return
        try:
            self.controller.rename_project(
                self.selected_client_id, project["id"], name
            )
            self._load_registry(
                preferred_client=self.selected_client_id,
                preferred_project=project["id"],
            )
            self._append_activity(f"Renamed project to: {name.strip()}")
        except Exception as error:
            self._show_error(error)

    def _new_setup(self) -> None:
        if not self.selected_client_id or not self.selected_project_id:
            return
        name = simpledialog.askstring(
            "New Setup", "Setup name:", parent=self
        )
        if not name:
            return
        parent_folder = filedialog.askdirectory(
            parent=self,
            title="Choose the parent folder for the new setup",
            mustexist=True,
        )
        if not parent_folder:
            return
        try:
            setup_id = self.controller.create_setup(
                self.selected_client_id,
                self.selected_project_id,
                name,
                parent_folder,
            )
            self._load_registry(
                preferred_client=self.selected_client_id,
                preferred_project=self.selected_project_id,
                preferred_setup=setup_id,
            )
            self._append_activity(f"Created setup folder: {name.strip()}")
        except Exception as error:
            self._show_error(error)

    def _link_setup(self) -> None:
        if not self.selected_client_id or not self.selected_project_id:
            return
        folder = filedialog.askdirectory(
            parent=self,
            title="Select an existing Visuino setup folder",
            mustexist=True,
        )
        if not folder:
            return
        default_name = Path(folder).name
        name = simpledialog.askstring(
            "Link Setup",
            "Setup name:",
            initialvalue=default_name,
            parent=self,
        )
        if not name:
            return
        try:
            setup_id = self.controller.link_setup(
                self.selected_client_id,
                self.selected_project_id,
                name,
                folder,
            )
            self._load_registry(
                preferred_client=self.selected_client_id,
                preferred_project=self.selected_project_id,
                preferred_setup=setup_id,
            )
            self._append_activity(f"Linked setup folder: {folder}")
        except Exception as error:
            self._show_error(error)

    def _rename_setup(self) -> None:
        setup = self._record_for_id(self._setup_records, self.selected_setup_id)
        if (
            not setup
            or not self.selected_client_id
            or not self.selected_project_id
        ):
            return
        name = simpledialog.askstring(
            "Rename Setup Profile",
            "Setup profile name:",
            initialvalue=setup["name"],
            parent=self,
        )
        if not name or name.strip() == setup["name"]:
            return
        try:
            self.controller.rename_setup(
                self.selected_client_id,
                self.selected_project_id,
                setup["id"],
                name,
            )
            self._load_registry(
                preferred_client=self.selected_client_id,
                preferred_project=self.selected_project_id,
                preferred_setup=setup["id"],
            )
            self._append_activity(f"Renamed setup profile to: {name.strip()}")
        except Exception as error:
            self._show_error(error)

    def _remove_setup(self) -> None:
        setup = self._record_for_id(self._setup_records, self.selected_setup_id)
        if (
            not setup
            or not self.selected_client_id
            or not self.selected_project_id
        ):
            return
        confirmed = messagebox.askyesno(
            "Remove Setup Profile",
            (
                f"Remove this setup profile from {APP_NAME}?\n\n"
                f"Profile: {setup['name']}\n"
                f"Folder: {setup['folderPath']}\n\n"
                "The folder and every file inside it will be preserved. "
                "You can link the folder again later."
            ),
            parent=self,
        )
        if not confirmed:
            return
        try:
            preserved_path = self.controller.remove_setup(
                self.selected_client_id,
                self.selected_project_id,
                setup["id"],
            )
            setup_name = setup["name"]
            self.selected_setup_id = None
            self._load_registry(
                preferred_client=self.selected_client_id,
                preferred_project=self.selected_project_id,
            )
            self._append_activity(
                f"Removed setup profile; folder preserved: {preserved_path}"
            )
            messagebox.showinfo(
                "Setup Profile Removed",
                (
                    f"The profile '{setup_name}' was removed from the registry.\n\n"
                    f"The folder was preserved:\n{preserved_path}"
                ),
                parent=self,
            )
        except Exception as error:
            self._show_error(error)

    def _open_setup_folder(self) -> None:
        setup = self._record_for_id(self._setup_records, self.selected_setup_id)
        if not setup:
            return
        try:
            self.controller.setup_service.open_folder(setup["folderPath"])
            self._append_activity(f"Opened folder: {setup['folderPath']}")
        except Exception as error:
            self._show_error(error)

    def _open_profile_cleanup(self) -> None:
        setup = self._record_for_id(self._setup_records, self.selected_setup_id)
        client = self._record_for_id(
            self._client_records,
            self.selected_client_id,
        )
        project = self._record_for_id(
            self._project_records,
            self.selected_project_id,
        )
        if (
            not setup
            or not client
            or not project
            or not self.selected_client_id
            or not self.selected_project_id
        ):
            return
        if (
            self._custom_code_dialog is not None
            and self._custom_code_dialog.winfo_exists()
        ):
            self._custom_code_dialog.lift()
            messagebox.showinfo(
                "Close Device & Custom Code",
                "Close Device & Custom Code before changing profile storage.",
                parent=self._custom_code_dialog,
            )
            return
        if (
            self._profile_cleanup_dialog is not None
            and self._profile_cleanup_dialog.winfo_exists()
        ):
            self._profile_cleanup_dialog.lift()
            self._profile_cleanup_dialog.focus_set()
            return

        client_id = self.selected_client_id
        project_id = self.selected_project_id
        setup_id = setup["id"]
        active_setup_id = self.controller.registry_snapshot().get("activeSetupId")
        self._profile_cleanup_dialog = ProfileCleanupDialog(
            self,
            client_name=client["name"],
            project_name=project["name"],
            setup=setup,
            active_setup_id=active_setup_id,
            run_worker=self._run_worker,
            preview_action=lambda action: self.controller.plan_profile_cleanup(
                client_id,
                project_id,
                setup_id,
                action,
            ),
            execute_action=self.controller.execute_profile_cleanup,
            on_complete=self._profile_cleanup_complete,
            show_error=self._show_error,
            append_activity=self._append_activity,
        )

    def _profile_cleanup_complete(self, result: ProfileCleanupResult) -> None:
        preferred_setup = None if result.profile_removed else result.setup_id
        if result.profile_removed:
            self.selected_setup_id = None
        self._load_registry(
            preferred_client=result.client_id,
            preferred_project=result.project_id,
            preferred_setup=preferred_setup,
        )
        if result.profile_removed:
            self._append_activity(
                f"Removed profile and recycled its folder: {result.setup_name}"
            )
        else:
            self._append_activity(
                f"Cleared setup folder and recreated libraries: {result.setup_path}"
            )

    def _open_custom_code(self) -> None:
        setup = self._record_for_id(self._setup_records, self.selected_setup_id)
        if not setup:
            return
        if (
            self._profile_cleanup_dialog is not None
            and self._profile_cleanup_dialog.winfo_exists()
        ):
            self._profile_cleanup_dialog.lift()
            messagebox.showinfo(
                "Close Profile Storage",
                "Close the profile storage dialog before editing device files.",
                parent=self._profile_cleanup_dialog,
            )
            return
        if (
            self._custom_code_dialog is not None
            and self._custom_code_dialog.winfo_exists()
        ):
            self._custom_code_dialog.destroy()
        self._custom_code_dialog = CustomCodeDialog(
            self,
            self.controller,
            setup,
            self._run_worker,
            lambda: self._load_registry(
                preferred_client=self.selected_client_id,
                preferred_project=self.selected_project_id,
                preferred_setup=setup["id"],
            ),
            self._append_activity,
        )

    def _validate_setup(self) -> None:
        setup_id = self.selected_setup_id
        if not setup_id:
            return
        self._dismiss_validation_guidance()
        self._set_badge(self.validation_badge, "busy", "Validating…")
        self._run_worker(
            "Validating setup",
            lambda: self.controller.validate_setup(setup_id),
            self._validation_complete,
        )

    def _validation_complete(self, result: Any) -> None:
        self._load_registry(
            preferred_client=self.selected_client_id,
            preferred_project=self.selected_project_id,
            preferred_setup=self.selected_setup_id,
        )
        if result.libraries_created:
            self._append_activity(
                f"Created Arduino libraries folder: {result.libraries_path}"
            )
        if result.legacy_entries_copied:
            self._append_activity(
                "Copied legacy flat-layout entries into libraries: "
                + ", ".join(result.legacy_entries_copied)
            )
        if result.is_valid:
            self._set_badge(
                self.validation_badge,
                "valid",
                "Setup ready · Mitov verified",
            )
            if result.visuino_pro_present:
                self._append_activity(
                    "Validation passed: Mitov and optional VisuinoPro are ready."
                )
            else:
                self._append_activity(
                    "Validation passed: Mitov is ready; VisuinoPro is optional."
                )
        else:
            self._append_activity(f"Validation failed: {' '.join(result.warnings)}")
        self._offer_baseline_repair(result)

    def _show_validation_guidance(
        self,
        message: str,
        *,
        action: str | None,
        primary_text: str | None,
    ) -> None:
        self._validation_action = action
        self.validation_guidance_message.set(message)
        if primary_text is None:
            self.validation_fix_button.pack_forget()
        else:
            self.validation_fix_button.configure(text=primary_text)
            if self.validation_fix_button.winfo_manager() != "pack":
                self.validation_fix_button.pack(
                    side="left",
                    before=self.validation_not_now_button,
                )
        if self.validation_guidance.winfo_manager() != "pack":
            self.validation_guidance.pack(
                fill="x",
                pady=(12, 0),
            )
        self._update_command_states()

    def _dismiss_validation_guidance(self) -> None:
        self._validation_action = None
        self._baseline_plan = None
        if hasattr(self, "validation_guidance"):
            self.validation_guidance.pack_forget()

    def _validation_fix_requested(self) -> None:
        if self._validation_action == "source":
            self._ask_for_baseline_source()
            return
        if self._validation_action != "repair" or self._baseline_plan is None:
            return
        plan = self._baseline_plan
        if not ask_baseline_repair(self, plan):
            self._append_activity("Baseline repair left unchanged after review.")
            return
        self._dismiss_validation_guidance()
        self._run_worker(
            "Repairing setup baseline",
            lambda: self.controller.repair_setup_baseline(plan),
            self._baseline_repair_complete,
        )

    def _offer_baseline_repair(self, validation: Any) -> None:
        setup_id = self.selected_setup_id
        if not setup_id:
            return
        if not validation.exists:
            self._show_validation_guidance(
                "The setup folder could not be found. Choose another profile "
                "or link the folder again.",
                action=None,
                primary_text=None,
            )
            return
        source = self.controller.find_default_baseline_source(setup_id)
        if source is None:
            if not validation.mitov_present:
                self._show_validation_guidance(
                    SOURCE_MISSING_MESSAGE,
                    action="source",
                    primary_text="Choose Library Folder",
                )
            return
        self._run_worker(
            "Planning baseline repair",
            lambda: self.controller.plan_baseline_repair(setup_id, source),
            self._baseline_plan_ready,
        )

    def _ask_for_baseline_source(self) -> None:
        if not ask_baseline_source(self):
            self._append_activity("Mitov source selection postponed.")
            return
        source = filedialog.askdirectory(
            parent=self,
            title="Select the default Arduino libraries folder",
            mustexist=True,
        )
        if not source or not self.selected_setup_id:
            return
        setup_id = self.selected_setup_id
        self._show_validation_guidance(
            "Checking the selected library folder…",
            action=None,
            primary_text=None,
        )
        self._run_worker(
            "Planning baseline repair",
            lambda: self.controller.plan_baseline_repair(setup_id, source),
            self._baseline_plan_ready,
        )

    def _baseline_plan_ready(self, plan: Any) -> None:
        if not plan.required_available:
            self._show_validation_guidance(
                "The selected folder does not contain Mitov. Choose your normal "
                "Arduino libraries folder and try again.",
                action="source",
                primary_text="Choose Another Folder",
            )
            self._append_activity(
                f"Selected baseline source does not contain Mitov: {plan.source_path}"
            )
            return
        if not plan.copies:
            self._dismiss_validation_guidance()
            if "VisuinoPro" in plan.unavailable:
                self._append_activity(
                    "Mitov retained; optional VisuinoPro is not available "
                    "in the default source."
                )
            return

        self._baseline_plan = plan
        names = {item.name for item in plan.copies}
        message = (
            "Mitov is missing. This setup can be fixed safely."
            if "Mitov" in names
            else "Optional VisuinoPro is available and can be added safely."
        )
        self._show_validation_guidance(
            message,
            action="repair",
            primary_text="Fix Setup",
        )

    def _baseline_repair_complete(self, result: Any) -> None:
        self._dismiss_validation_guidance()
        copied = ", ".join(result.copied)
        self._append_activity(
            f"Baseline copied and verified: {copied} "
            f"({result.file_count} files, {self._format_bytes(result.total_bytes)})."
        )
        self._run_worker(
            "Revalidating setup",
            lambda: self.controller.validate_setup(result.setup_id),
            self._validation_after_repair,
        )

    def _validation_after_repair(self, result: Any) -> None:
        self._load_registry(
            preferred_client=self.selected_client_id,
            preferred_project=self.selected_project_id,
            preferred_setup=self.selected_setup_id,
        )
        if result.is_valid:
            self._set_badge(
                self.validation_badge,
                "valid",
                "Setup ready · Mitov verified",
            )
            pro_status = (
                "VisuinoPro copied and ready"
                if result.visuino_pro_present
                else "VisuinoPro optional and not installed"
            )
            self._append_activity(
                f"Baseline validation passed: Mitov ready; {pro_status}."
            )
        else:
            self._append_activity(
                f"Baseline validation failed: {' '.join(result.warnings)}"
            )

    @staticmethod
    def _format_bytes(value: int) -> str:
        if value < 1024:
            return f"{value} B"
        if value < 1024 * 1024:
            return f"{value / 1024:.1f} KiB"
        return f"{value / (1024 * 1024):.1f} MiB"

    def _activate_setup(self) -> None:
        setup = self._record_for_id(self._setup_records, self.selected_setup_id)
        if not setup:
            return
        cache_path = (
            self.controller.activation_service.paths.caches / setup["id"]
        ).resolve()
        confirmed = messagebox.askyesno(
            "Activate Visuino Setup",
            (
                f"Dry-run summary\n\n"
                f"{setup['name']}\n{setup['folderPath']}\n\n"
                "The guarded transaction will:\n"
                "• back up the current Pro registry value and Arduino15 YAML\n"
                "• set both values to the selected setup\n"
                f"• rebuild the isolated cache at {cache_path}\n"
                "• start and verify Visuino Pro\n"
                "• restore the backup automatically if verification fails\n\n"
                "Visuino must be closed. Continue?"
            ),
            parent=self,
        )
        if not confirmed:
            return
        setup_id = setup["id"]
        self._run_worker(
            "Activating Visuino setup",
            lambda: self.controller.activate_setup(setup_id),
            self._activation_complete,
        )

    def _activation_complete(self, result: Any) -> None:
        self._load_registry(
            preferred_client=self.selected_client_id,
            preferred_project=self.selected_project_id,
            preferred_setup=self.selected_setup_id,
        )
        self._append_activity(
            f"Activation verified. Visuino PID {result.process_id}; "
            f"cache: {result.cache_path}"
        )
        messagebox.showinfo(
            "Setup Activated",
            f"{result.message}\n\nBackup:\n{result.backup_path}",
            parent=self,
        )

    def _restore_default(self) -> None:
        confirmed = messagebox.askyesno(
            "Restore Recorded Default",
            (
                "Restore the Visuino configuration captured before the first activation "
                "and start Visuino Pro?\n\nVisuino must be closed."
            ),
            parent=self,
        )
        if not confirmed:
            return
        self._run_worker(
            "Restoring default Visuino setup",
            self.controller.restore_default,
            self._restore_complete,
        )

    def _restore_complete(self, result: Any) -> None:
        self._load_registry(
            preferred_client=self.selected_client_id,
            preferred_project=self.selected_project_id,
            preferred_setup=self.selected_setup_id,
        )
        self._append_activity(
            f"Recorded default restored. Visuino PID {result.process_id}."
        )
        messagebox.showinfo(
            "Default Restored",
            f"{result.message}\n\nSafety backup:\n{result.backup_path}",
            parent=self,
        )

    def _run_worker(
        self,
        label: str,
        function: Callable[[], Any],
        on_success: Callable[[Any], None] | None,
    ) -> None:
        if self._busy:
            return
        self._busy = True
        self.footer_status.set(f"{label}…")
        self._append_activity(f"{label}…")
        self._update_command_states()
        future = self._executor.submit(function)

        def complete(completed: Any) -> None:
            try:
                result = completed.result()
            except BaseException as error:
                self._results.put((label, on_success, None, error))
            else:
                self._results.put((label, on_success, result, None))

        future.add_done_callback(complete)

    def _poll_worker_results(self) -> None:
        try:
            while True:
                label, on_success, result, error = self._results.get_nowait()
                self._busy = False
                self.footer_status.set("Ready")
                if error is not None:
                    self._append_activity(f"{label} failed: {error}")
                    self._show_error(error)
                    self._load_registry(
                        preferred_client=self.selected_client_id,
                        preferred_project=self.selected_project_id,
                        preferred_setup=self.selected_setup_id,
                    )
                elif on_success is not None:
                    on_success(result)
                self._update_command_states()
        except queue.Empty:
            pass
        self.after(100, self._poll_worker_results)

    def _append_activity(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.activity.configure(state="normal")
        self.activity.insert("end", f"{timestamp}  {message}\n")
        self.activity.see("end")
        self.activity.configure(state="disabled")

    def _show_error(self, error: BaseException) -> None:
        if isinstance(
            error,
            (
                RegistryError,
                ActivationError,
                ImplementationError,
                BaselineRepairError,
                ProfileCleanupError,
                ProjectVaultError,
                ValueError,
                OSError,
            ),
        ):
            message = str(error)
        else:
            message = f"Unexpected error: {error}"
        messagebox.showerror(APP_NAME, message, parent=self)

    def _on_close(self) -> None:
        if self._busy:
            messagebox.showwarning(
                "Operation in Progress",
                "A protected operation is still running. Wait for it to finish before closing.",
                parent=self,
            )
            return
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()
