from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .controller import ApplicationController
from .implementation import (
    DEFAULT_LIBRARY_NAME,
    ImportPlan,
    UiElementVariable,
)
from .shared_gpt import (
    SHARED_GPT_NAME,
    SHARED_GPT_START_STEPS,
    SHARED_GPT_URL,
    validate_shared_gpt_url,
)


COLORS = {
    "background": "#F3F6FA",
    "card": "#FFFFFF",
    "navy": "#102A43",
    "blue": "#1D4ED8",
    "text": "#182230",
    "muted": "#667085",
    "line": "#DCE3EC",
    "success": "#067647",
    "error": "#B42318",
    "warning": "#B54708",
    "soft_blue": "#EFF6FF",
}


def format_ui_element_details(element: UiElementVariable) -> str:
    if element.bridge_namespace:
        namespace = element.bridge_namespace
        namespace_help = (
            f"Keep {namespace}::; it tells C++ where the bridge function lives. "
            "Please do not remove it."
        )
    else:
        namespace = "— (not declared by this legacy import)"
        namespace_help = (
            "Project bridge calls should include their complete namespace. "
            "Global LVGL functions beginning with lv_ do not use one."
        )

    return (
        f"Namespace:      {namespace}\n"
        f"Required:       {namespace_help}\n"
        f"Visuino Input:  {element.visuino_input_code or '—'}\n"
        f"Visuino loop:   {element.visuino_loop_code or '—'}\n"
        f"ID / object:    {element.id} / {element.lvgl_object}\n"
        f"Range / events: {element.range_text} / {element.events_text}\n"
        f"Raw Read API:   {element.read_api or '—'}\n"
        f"Raw Write API:  {element.write_api or '—'}\n"
        f"Description:    {element.description}"
    )


class CustomCodeDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        controller: ApplicationController,
        setup: dict[str, Any],
        run_worker: Callable[
            [str, Callable[[], Any], Callable[[Any], None] | None], None
        ],
        registry_changed: Callable[[], None],
        append_activity: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setup = setup
        self.run_worker = run_worker
        self.registry_changed = registry_changed
        self.append_activity = append_activity
        self._plan: ImportPlan | None = None
        self._ui_element_rows: dict[str, UiElementVariable] = {}

        package = setup.get("devicePackage") or {}
        self.source_var = tk.StringVar(value=package.get("sourcePath", ""))
        self.library_var = tk.StringVar(
            value=package.get("libraryFolder", DEFAULT_LIBRARY_NAME)
        )
        self.package_status = tk.StringVar(value=self._package_status_text(package))
        self.sketch_origin_var = tk.StringVar(value="Setup-local Arduino sketch")
        self.ui_elements_status_var = tk.StringVar(
            value="No UI element registry loaded."
        )
        self.shared_gpt_url_var = tk.StringVar(value=SHARED_GPT_URL)

        self.title(f"Device & Custom Code — {setup['name']}")
        self.geometry("1040x760")
        self.minsize(880, 650)
        self.configure(bg=COLORS["background"])
        self.transient(parent)
        self._build()
        self._load_sketch()
        self._load_ui_elements()

    @staticmethod
    def _package_status_text(package: dict[str, Any]) -> str:
        if not package:
            return "No implementation has been registered for this setup."
        status = package.get("status", "unknown")
        return (
            f"{package.get('libraryFolder', 'Implementation')} · {status} · "
            f"{package.get('id', 'external')}"
        )

    def _build(self) -> None:
        header = tk.Frame(self, bg=COLORS["navy"], height=76)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="DEVICE & CUSTOM CODE",
            bg=COLORS["navy"],
            fg="#8FB8FF",
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", padx=24, pady=(12, 0))
        tk.Label(
            header,
            text=self.setup["name"],
            bg=COLORS["navy"],
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 17),
            anchor="w",
        ).pack(fill="x", padx=24)

        summary = tk.Frame(self, bg=COLORS["card"])
        summary.pack(fill="x", padx=18, pady=(16, 10))
        tk.Label(
            summary,
            textvariable=self.package_status,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", padx=14, pady=10)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        import_tab = tk.Frame(self.notebook, bg=COLORS["card"])
        elements_tab = tk.Frame(self.notebook, bg=COLORS["card"])
        hook_tab = tk.Frame(self.notebook, bg=COLORS["card"])
        shared_gpt_tab = tk.Frame(self.notebook, bg=COLORS["card"])
        self.notebook.add(import_tab, text="Standalone Import")
        self.notebook.add(elements_tab, text="UI Element Variables")
        self.notebook.add(hook_tab, text="Visuino Custom Code")
        self.notebook.add(shared_gpt_tab, text="Shared GPT")
        self.hook_tab = hook_tab
        self._build_import_tab(import_tab)
        self._build_elements_tab(elements_tab)
        self._build_hook_tab(hook_tab)
        self._build_shared_gpt_tab(shared_gpt_tab)

    def _build_import_tab(self, tab: tk.Frame) -> None:
        form = tk.Frame(tab, bg=COLORS["card"])
        form.pack(fill="x", padx=18, pady=16)

        tk.Label(
            form,
            text="STANDALONE SOURCE FOLDER",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x")
        source_row = tk.Frame(form, bg=COLORS["card"])
        source_row.pack(fill="x", pady=(4, 12))
        ttk.Entry(source_row, textvariable=self.source_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            source_row,
            text="Browse…",
            style="Secondary.TButton",
            command=self._browse_source,
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            form,
            text="SETUP-LOCAL IMPLEMENTATION LIBRARY",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x")
        ttk.Entry(form, textvariable=self.library_var).pack(fill="x", pady=(4, 12))

        button_row = tk.Frame(form, bg=COLORS["card"])
        button_row.pack(fill="x")
        ttk.Button(
            button_row,
            text="Analyze & Import…",
            style="Primary.TButton",
            command=self._analyze_import,
        ).pack(side="left")
        ttk.Button(
            button_row,
            text="Validate Installed",
            style="Secondary.TButton",
            command=self._validate_installed,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            button_row,
            text="Open Setup Folder",
            style="Quiet.TButton",
            command=self._open_setup,
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            form,
            text=(
                "The dry run recognizes libraries/, Arduino/libraries, an Arduino "
                "library, or loose src/include/ui source. Exactly one root .ino "
                "is required and loaded unchanged into Visuino Custom Code; all "
                "source files are also preserved as originals. A root "
                "ui-elements.json is validated and listed separately."
            ),
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            justify="left",
            wraplength=900,
        ).pack(fill="x", pady=(12, 8))

        self.plan_output = tk.Text(
            tab,
            bg="#F8FAFC",
            fg=COLORS["text"],
            font=("Consolas", 9),
            wrap="word",
            relief="flat",
            padx=10,
            pady=10,
            state="disabled",
        )
        self.plan_output.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self._set_plan_output(
            "Select a standalone Arduino/LVGL source folder, then analyze it. "
            "No setup files are changed before the dry-run confirmation."
        )

    def _build_elements_tab(self, tab: tk.Frame) -> None:
        intro = tk.Label(
            tab,
            text=(
                "Select an element and copy its complete Visuino example. "
                "Project bridge functions require their namespace before ::, "
                "for example waveshare43_example::set_test_slider_value(AValue); "
                "Keep that prefix exactly as shown. AValue is the value received "
                "by a Visuino Custom Code Input."
            ),
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=900,
        )
        intro.pack(fill="x", padx=18, pady=(14, 4))
        tk.Label(
            tab,
            textvariable=self.ui_elements_status_var,
            bg=COLORS["card"],
            fg=COLORS["blue"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 8))

        table_frame = tk.Frame(tab, bg=COLORS["card"])
        table_frame.pack(fill="both", expand=True, padx=18)
        columns = (
            "id",
            "name",
            "screen",
            "type",
            "object",
            "direction",
            "value",
        )
        self.ui_elements_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=8,
        )
        headings = {
            "id": ("Stable ID", 115),
            "name": ("Name", 140),
            "screen": ("Screen", 95),
            "type": ("Type", 80),
            "object": ("LVGL object", 150),
            "direction": ("Direction", 145),
            "value": ("Value", 75),
        }
        for column, (label, width) in headings.items():
            self.ui_elements_tree.heading(column, text=label)
            self.ui_elements_tree.column(
                column,
                width=width,
                minwidth=60,
                stretch=column in {"name", "object"},
            )
        elements_scroll_y = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.ui_elements_tree.yview,
        )
        elements_scroll_x = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.ui_elements_tree.xview,
        )
        self.ui_elements_tree.configure(
            yscrollcommand=elements_scroll_y.set,
            xscrollcommand=elements_scroll_x.set,
        )
        self.ui_elements_tree.grid(row=0, column=0, sticky="nsew")
        elements_scroll_y.grid(row=0, column=1, sticky="ns")
        elements_scroll_x.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        self.ui_elements_tree.bind(
            "<<TreeviewSelect>>",
            self._ui_element_selected,
        )

        details_frame = tk.LabelFrame(
            tab,
            text="Manual binding details",
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 9),
            padx=8,
            pady=6,
        )
        details_frame.pack(fill="x", padx=18, pady=(10, 0))
        self.ui_element_details = tk.Text(
            details_frame,
            height=7,
            bg="#F8FAFC",
            fg=COLORS["text"],
            font=("Consolas", 8),
            wrap="word",
            relief="flat",
            padx=8,
            pady=6,
            state="disabled",
        )
        details_scroll = ttk.Scrollbar(
            details_frame,
            orient="vertical",
            command=self.ui_element_details.yview,
        )
        self.ui_element_details.configure(yscrollcommand=details_scroll.set)
        self.ui_element_details.pack(side="left", fill="both", expand=True)
        details_scroll.pack(side="right", fill="y")
        self._set_ui_element_details(
            "Select an element to see its required namespace and complete "
            "Visuino Input and loop examples."
        )

        footer = tk.Frame(tab, bg=COLORS["card"])
        footer.pack(fill="x", padx=18, pady=12)
        tk.Label(
            footer,
            text=(
                "Copy the complete example. Keep namespace:: on project bridge "
                "calls; replace Integer1 or Digital1 only when your Visuino "
                "connector has another name."
            ),
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            anchor="w",
            justify="left",
            wraplength=900,
        ).pack(fill="x", pady=(0, 6))
        button_row = tk.Frame(footer, bg=COLORS["card"])
        button_row.pack(fill="x")
        ttk.Button(
            button_row,
            text="Reload from Setup",
            style="Secondary.TButton",
            command=self._load_ui_elements,
        ).pack(side="left")
        ttk.Button(
            button_row,
            text="Copy LVGL Object",
            style="Primary.TButton",
            command=self._copy_selected_lvgl_object,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            button_row,
            text="Copy Visuino Loop",
            style="Secondary.TButton",
            command=self._copy_selected_read_api,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            button_row,
            text="Copy Visuino Input",
            style="Secondary.TButton",
            command=self._copy_selected_write_api,
        ).pack(side="left", padx=(8, 0))

    def _build_hook_tab(self, tab: tk.Frame) -> None:
        intro = tk.Label(
            tab,
            text=(
                "This editor contains only the one complete root .ino from the "
                "selected import folder, ready to copy as a single value into a "
                "Visuino Custom Code component."
            ),
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=900,
        )
        intro.pack(fill="x", padx=18, pady=(14, 8))

        origin = tk.Label(
            tab,
            textvariable=self.sketch_origin_var,
            bg=COLORS["card"],
            fg=COLORS["blue"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        )
        origin.pack(fill="x", padx=18, pady=(0, 6))

        editor_frame = tk.LabelFrame(
            tab,
            text="Complete Arduino .ino",
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 9),
            padx=8,
            pady=8,
        )
        editor_frame.pack(fill="both", expand=True, padx=18)
        self.sketch_editor = tk.Text(
            editor_frame,
            bg="#0F172A",
            fg="#E2E8F0",
            insertbackground="#FFFFFF",
            font=("Consolas", 9),
            wrap="none",
            relief="flat",
            padx=10,
            pady=9,
            undo=True,
        )
        sketch_scroll_y = ttk.Scrollbar(
            editor_frame,
            orient="vertical",
            command=self.sketch_editor.yview,
        )
        sketch_scroll_x = ttk.Scrollbar(
            editor_frame,
            orient="horizontal",
            command=self.sketch_editor.xview,
        )
        self.sketch_editor.configure(
            yscrollcommand=sketch_scroll_y.set,
            xscrollcommand=sketch_scroll_x.set,
        )
        self.sketch_editor.grid(row=0, column=0, sticky="nsew")
        sketch_scroll_y.grid(row=0, column=1, sticky="ns")
        sketch_scroll_x.grid(row=1, column=0, sticky="ew")
        editor_frame.grid_rowconfigure(0, weight=1)
        editor_frame.grid_columnconfigure(0, weight=1)

        footer = tk.Frame(tab, bg=COLORS["card"])
        footer.pack(fill="x", padx=18, pady=14)
        ttk.Button(
            footer,
            text="Save Arduino Code",
            style="Primary.TButton",
            command=self._save_sketch,
        ).pack(side="left")
        ttk.Button(
            footer,
            text="Reload from Setup",
            style="Secondary.TButton",
            command=self._load_sketch,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            footer,
            text="Copy to Clipboard",
            style="Secondary.TButton",
            command=self._copy_sketch,
        ).pack(side="left", padx=(8, 0))
        tk.Label(
            footer,
            text="The sketch is stored as a file and is never executed by this app.",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(side="right")

    def _build_shared_gpt_tab(self, tab: tk.Frame) -> None:
        tk.Label(
            tab,
            text="Create an LVGL screen project with the shared assistant",
            bg=COLORS["card"],
            fg=COLORS["navy"],
            font=("Segoe UI Semibold", 16),
            anchor="w",
        ).pack(fill="x", padx=24, pady=(22, 4))
        tk.Label(
            tab,
            text=(
                "The complete project guide is already built into the shared "
                f"{SHARED_GPT_NAME} GPT. You do not need to copy or edit a prompt."
            ),
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
            justify="left",
            anchor="w",
            wraplength=880,
        ).pack(fill="x", padx=24, pady=(0, 16))

        link_frame = tk.LabelFrame(
            tab,
            text="Shared ChatGPT link",
            bg=COLORS["soft_blue"],
            fg=COLORS["navy"],
            font=("Segoe UI Semibold", 10),
            padx=14,
            pady=12,
        )
        link_frame.pack(fill="x", padx=24)
        tk.Label(
            link_frame,
            text=SHARED_GPT_NAME,
            bg=COLORS["soft_blue"],
            fg=COLORS["navy"],
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).pack(fill="x")
        link_row = tk.Frame(link_frame, bg=COLORS["soft_blue"])
        link_row.pack(fill="x", pady=(8, 0))
        ttk.Entry(
            link_row,
            textvariable=self.shared_gpt_url_var,
            state="readonly",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            link_row,
            text="Open Shared GPT",
            style="Primary.TButton",
            command=self._open_shared_gpt,
        ).pack(side="left", padx=(10, 0))
        ttk.Button(
            link_row,
            text="Copy Link",
            style="Secondary.TButton",
            command=self._copy_shared_gpt_link,
        ).pack(side="left", padx=(8, 0))

        steps_frame = tk.LabelFrame(
            tab,
            text="Getting started",
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 10),
            padx=14,
            pady=10,
        )
        steps_frame.pack(fill="both", expand=True, padx=24, pady=(18, 12))
        for number, (title, detail) in enumerate(SHARED_GPT_START_STEPS, start=1):
            row = tk.Frame(steps_frame, bg=COLORS["card"])
            row.pack(fill="x", pady=(4, 8))
            tk.Label(
                row,
                text=str(number),
                bg=COLORS["blue"],
                fg="#FFFFFF",
                font=("Segoe UI Semibold", 9),
                width=3,
                padx=2,
                pady=4,
            ).pack(side="left", anchor="n", padx=(0, 10))
            copy = tk.Frame(row, bg=COLORS["card"])
            copy.pack(side="left", fill="x", expand=True)
            tk.Label(
                copy,
                text=title,
                bg=COLORS["card"],
                fg=COLORS["text"],
                font=("Segoe UI Semibold", 10),
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                copy,
                text=detail,
                bg=COLORS["card"],
                fg=COLORS["muted"],
                font=("Segoe UI", 9),
                justify="left",
                anchor="w",
                wraplength=790,
            ).pack(fill="x", pady=(1, 0))

        tk.Label(
            tab,
            text=(
                "The desktop application opens the link only when you choose "
                "Open Shared GPT. ChatGPT runs in your default browser."
            ),
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill="x", padx=24, pady=(0, 16))

    def _browse_source(self) -> None:
        selected = filedialog.askdirectory(
            parent=self,
            title="Select standalone Arduino/LVGL source folder",
            mustexist=True,
        )
        if selected:
            self.source_var.set(selected)

    def _analyze_import(self) -> None:
        source = self.source_var.get().strip()
        library = self.library_var.get().strip()
        if not source:
            messagebox.showwarning(
                "Source Required",
                "Select a standalone source folder first.",
                parent=self,
            )
            return
        self._set_plan_output("Analyzing import without changing the setup…")
        self.run_worker(
            "Analyzing standalone implementation",
            lambda: self.controller.plan_implementation_import(
                self.setup["id"],
                source,
                library,
            ),
            self._plan_ready,
        )

    def _plan_ready(self, plan: ImportPlan) -> None:
        self._plan = plan
        self._set_sketch_text(plan.arduino_sketch)
        self._set_ui_elements(plan.ui_elements, plan.ui_elements_origin)
        self.sketch_origin_var.set(
            f"Arduino sketch origin: {plan.sketch_origin}"
        )
        warning_text = (
            "\n".join(f"  - {warning}" for warning in plan.warnings)
            if plan.warnings
            else "  none"
        )
        roots = "\n".join(f"  - {name}" for name in plan.target_roots)
        summary = (
            "DRY RUN — no setup files changed\n\n"
            f"Source: {plan.source_path}\n"
            f"Mode: {plan.mode}\n"
            f"Implementation library: {plan.library_name}\n"
            f"Arduino sketch: {plan.sketch_origin}\n"
            f"UI elements: {len(plan.ui_elements)} ({plan.ui_elements_origin})\n"
            f"Files: {len(plan.files)} ({plan.total_bytes / 1024:.1f} KiB)\n"
            f"Add: {plan.add_count}\n"
            f"Replace: {plan.replace_count}\n"
            f"Unchanged: {plan.unchanged_count}\n\n"
            f"Top-level setup targets:\n{roots}\n\n"
            f"Warnings:\n{warning_text}"
        )
        self._set_plan_output(summary)
        confirmed = messagebox.askyesno(
            "Install Standalone Implementation",
            (
                f"{summary}\n\n"
                "Existing targets will be backed up and restored automatically "
                "if verification fails. Visuino Pro must be closed before "
                "installation. Install this plan?"
            ),
            parent=self,
        )
        if confirmed:
            self.run_worker(
                "Installing standalone implementation",
                lambda: self.controller.install_implementation(plan),
                self._install_complete,
            )

    def _install_complete(self, result: Any) -> None:
        self.library_var.set(result.library_name)
        self.source_var.set(str(result.source_path))
        self.package_status.set(
            f"{result.library_name} · valid · external standalone"
        )
        self._set_plan_output(
            f"Import installed and verified.\n\n"
            f"Library: {result.library_path}\n"
            f"Manifest: {result.manifest_path}\n"
            f"Arduino sketch: {result.sketch_path}\n"
            f"Files: {result.file_count}\n"
            f"Backup: {result.backup_path}"
        )
        self.registry_changed()
        self._load_sketch()
        self._load_ui_elements()
        self.notebook.select(self.hook_tab)
        self.append_activity(
            f"Imported standalone implementation: {result.library_name}"
        )
        messagebox.showinfo(
            "Implementation Installed",
            (
                "The standalone implementation was installed and verified.\n\n"
                f"Backup:\n{result.backup_path}\n\n"
                "The complete Arduino .ino sketch is ready in the Visuino "
                "Custom Code tab."
            ),
            parent=self,
        )

    def _validate_installed(self) -> None:
        self.run_worker(
            "Validating standalone implementation",
            lambda: self.controller.validate_implementation(self.setup["id"]),
            self._validation_complete,
        )

    def _validation_complete(self, result: Any) -> None:
        state = "valid" if result.is_valid else "invalid"
        details = (
            f"Implementation validation: {state}\n"
            f"Checked files: {result.checked_files}\n"
            f"Manifest: {result.manifest_path or 'missing'}"
        )
        if result.warnings:
            details += "\n\n" + "\n".join(f"- {item}" for item in result.warnings)
        self._set_plan_output(details)
        self.package_status.set(
            f"{result.library_name or 'Implementation'} · {state}"
        )
        self.registry_changed()
        self.append_activity(f"Implementation validation: {state}")

    def _load_sketch(self) -> None:
        try:
            sketch = self.controller.load_visuino_arduino_code(
                self.setup["id"],
                self.library_var.get().strip() or DEFAULT_LIBRARY_NAME,
            )
        except Exception as error:
            messagebox.showerror("Custom Code", str(error), parent=self)
            return
        self._set_sketch_text(sketch)
        self.sketch_origin_var.set("Arduino sketch origin: setup-local file")

    def _load_ui_elements(self) -> None:
        library = self.library_var.get().strip() or DEFAULT_LIBRARY_NAME
        try:
            elements = self.controller.load_ui_element_variables(
                self.setup["id"],
                library,
            )
        except Exception as error:
            self._set_ui_elements((), f"Error: {error}")
            return
        origin = (
            "setup-local ui-elements.json"
            if elements
            else "no installed ui-elements.json"
        )
        self._set_ui_elements(elements, origin)

    def _set_ui_elements(
        self,
        elements: tuple[UiElementVariable, ...],
        origin: str,
    ) -> None:
        self.ui_elements_tree.delete(*self.ui_elements_tree.get_children())
        self._ui_element_rows.clear()
        for index, element in enumerate(elements, start=1):
            row_id = f"element-{index}"
            self._ui_element_rows[row_id] = element
            self.ui_elements_tree.insert(
                "",
                "end",
                iid=row_id,
                values=(
                    element.id,
                    element.name,
                    element.screen,
                    element.type,
                    element.lvgl_object,
                    element.direction,
                    element.value_type,
                ),
            )
        self.ui_elements_status_var.set(
            f"{len(elements)} UI element{'s' if len(elements) != 1 else ''} · {origin}"
        )
        self._set_ui_element_details(
            "Select an element to see its required namespace and complete "
            "Visuino Input and loop examples."
            if elements
            else "No UI element variables are available for this implementation."
        )

    def _ui_element_selected(self, _event: tk.Event[Any]) -> None:
        selected = self.ui_elements_tree.selection()
        element = self._ui_element_rows.get(selected[0]) if selected else None
        if element is None:
            return
        self._set_ui_element_details(format_ui_element_details(element))

    def _copy_selected_lvgl_object(self) -> None:
        selected = self.ui_elements_tree.selection()
        element = self._ui_element_rows.get(selected[0]) if selected else None
        if element is None:
            messagebox.showwarning(
                "UI Element Variables",
                "Select one UI element first.",
                parent=self,
            )
            return
        self.clipboard_clear()
        self.clipboard_append(element.lvgl_object)
        self.update_idletasks()
        self.append_activity(
            f"Copied UI element LVGL object: {element.lvgl_object}"
        )

    def _copy_selected_read_api(self) -> None:
        self._copy_selected_ui_api("read")

    def _copy_selected_write_api(self) -> None:
        self._copy_selected_ui_api("write")

    def _copy_selected_ui_api(self, direction: str) -> None:
        selected = self.ui_elements_tree.selection()
        element = self._ui_element_rows.get(selected[0]) if selected else None
        if element is None:
            messagebox.showwarning(
                "UI Element Variables",
                "Select one UI element first.",
                parent=self,
            )
            return

        api = (
            element.read_copy_text
            if direction == "read"
            else element.write_copy_text
        )
        if not api:
            purpose = "loop example or Read API" if direction == "read" else (
                "Input example or Write API"
            )
            messagebox.showinfo(
                "UI Element Variables",
                f"The selected element does not define a Visuino {purpose}.",
                parent=self,
            )
            return

        self.clipboard_clear()
        self.clipboard_append(api)
        self.update_idletasks()
        copied_kind = (
            "loop example"
            if direction == "read" and element.visuino_loop_code
            else "Input example"
            if direction == "write" and element.visuino_input_code
            else f"{direction} API"
        )
        self.append_activity(
            f"Copied UI element {copied_kind}: {element.id}"
        )

    def _save_sketch(self) -> None:
        library = self.library_var.get().strip() or DEFAULT_LIBRARY_NAME
        try:
            path = self.controller.save_visuino_arduino_code(
                self.setup["id"],
                library,
                self._sketch_text(),
            )
        except Exception as error:
            messagebox.showerror("Custom Code", str(error), parent=self)
            return
        self.library_var.set(library)
        self.registry_changed()
        self.package_status.set(f"{library} · Arduino code saved")
        self.sketch_origin_var.set("Arduino sketch origin: setup-local file")
        self.append_activity(f"Saved Visuino Arduino sketch: {path}")
        messagebox.showinfo(
            "Arduino Code Saved",
            f"The complete Arduino sketch was saved to:\n{path}",
            parent=self,
        )

    def _copy_sketch(self) -> None:
        value = self._sketch_text()
        if not value.strip():
            messagebox.showwarning(
                "Arduino Code",
                "The Arduino sketch is empty.",
                parent=self,
            )
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update_idletasks()
        self.append_activity("Copied complete Visuino Arduino sketch")

    def _open_shared_gpt(self) -> None:
        try:
            url = validate_shared_gpt_url(self.shared_gpt_url_var.get())
            opened = webbrowser.open(url, new=2)
        except (OSError, ValueError, webbrowser.Error) as error:
            messagebox.showwarning(
                "Open Shared GPT",
                f"Could not open the shared GPT:\n{error}\n\nCopy the link instead.",
                parent=self,
            )
            return
        if not opened:
            messagebox.showwarning(
                "Open Shared GPT",
                "The default browser did not accept the link. Copy the link and "
                "open it manually.",
                parent=self,
            )
            return
        self.append_activity("Opened shared LVGL Library Swapper GPT")

    def _copy_shared_gpt_link(self) -> None:
        url = validate_shared_gpt_url(self.shared_gpt_url_var.get())
        self.clipboard_clear()
        self.clipboard_append(url)
        self.update_idletasks()
        self.append_activity("Copied shared LVGL Library Swapper GPT link")

    def _sketch_text(self) -> str:
        return self.sketch_editor.get("1.0", "end-1c")

    def _set_sketch_text(self, value: str) -> None:
        self.sketch_editor.delete("1.0", "end")
        self.sketch_editor.insert("1.0", value)

    def _set_ui_element_details(self, value: str) -> None:
        self.ui_element_details.configure(state="normal")
        self.ui_element_details.delete("1.0", "end")
        self.ui_element_details.insert("1.0", value)
        self.ui_element_details.configure(state="disabled")

    def _set_plan_output(self, value: str) -> None:
        self.plan_output.configure(state="normal")
        self.plan_output.delete("1.0", "end")
        self.plan_output.insert("1.0", value)
        self.plan_output.configure(state="disabled")

    def _open_setup(self) -> None:
        try:
            self.controller.setup_service.open_folder(self.setup["folderPath"])
        except Exception as error:
            messagebox.showerror("Open Setup", str(error), parent=self)
