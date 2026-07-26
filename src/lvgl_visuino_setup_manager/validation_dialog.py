from __future__ import annotations

from typing import Any

import tkinter as tk
from tkinter import ttk


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
    "warning": "#B54708",
    "warning_bg": "#FFFAEB",
}

SOURCE_MISSING_MESSAGE = (
    "Mitov is required, but no trusted source was found. Choose your normal "
    "Arduino libraries folder to continue."
)
SOURCE_EXPLANATION = (
    "Visuino needs the Mitov library to load its normal component set. The "
    "selected folder is used only as a source for missing Mitov and optional "
    "VisuinoPro. Existing setup folders and all other libraries remain unchanged."
)


def invalid_baseline_badges(
    warnings: list[str] | tuple[str, ...],
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Return honest baseline badges for an invalid persisted validation."""
    combined = " ".join(warnings).casefold()
    setup_unavailable = any(
        phrase in combined
        for phrase in (
            "does not exist",
            "filesystem root",
            "missing or unsafe",
            "must be a normal folder",
            "already an arduino libraries directory",
        )
    )
    if setup_unavailable:
        return (
            ("invalid", "Mitov · unavailable"),
            ("unknown", "VisuinoPro · unavailable"),
        )
    mitov_missing = "mitov" in combined
    visuino_pro_missing = "visuinopro" in combined
    return (
        (
            "invalid" if mitov_missing else "valid",
            "Mitov · missing" if mitov_missing else "Mitov · ready",
        ),
        (
            "unknown" if visuino_pro_missing else "valid",
            "VisuinoPro · optional"
            if visuino_pro_missing
            else "VisuinoPro · ready",
        ),
    )


def format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / (1024 * 1024):.1f} MiB"


def repair_heading(plan: Any) -> str:
    names = {item.name for item in plan.copies}
    if "Mitov" in names:
        return "Mitov is missing. This setup can be fixed safely."
    return "Optional VisuinoPro is available for this setup."


def repair_summary_lines(plan: Any) -> tuple[str, str, str]:
    names = ", ".join(item.name for item in plan.copies)
    return (
        f"Will add: {names}",
        "Will keep: Every existing library and folder",
        "Changes now: None — nothing changes until you confirm",
    )


def repair_details(plan: Any) -> str:
    copy_lines = "\n".join(
        f"  • {item.name}: {item.file_count:,} files, "
        f"{format_bytes(item.total_bytes)}"
        for item in plan.copies
    )
    retained = ", ".join(plan.retained) if plan.retained else "None"
    unavailable = ", ".join(plan.unavailable) if plan.unavailable else "None"
    return (
        f"Source\n{plan.source_path}\n\n"
        f"Setup\n{plan.setup_path}\n\n"
        f"Missing libraries to copy\n{copy_lines}\n\n"
        f"Existing baseline libraries retained\n  {retained}\n\n"
        f"Unavailable optional libraries\n  {unavailable}\n\n"
        "Safety policy\n"
        "  Only missing Mitov and optional VisuinoPro are eligible. Existing "
        "folders and all other libraries remain unchanged."
    )


class BaselineRepairDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, plan: Any) -> None:
        super().__init__(parent)
        self.plan = plan
        self.confirmed = False
        self._details_visible = False
        self.title("Fix Setup")
        self.configure(bg=COLORS["background"])
        self.geometry("660x500")
        self.minsize(590, 450)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _event: self._cancel())
        self._build()
        self._center_over(parent)
        self.focus_set()

    def _build(self) -> None:
        card = tk.Frame(
            self,
            bg=COLORS["card"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        card.pack(fill="both", expand=True, padx=18, pady=18)
        body = tk.Frame(card, bg=COLORS["card"])
        body.pack(fill="both", expand=True, padx=24, pady=22)

        tk.Label(
            body,
            text="SAFE BASELINE REPAIR",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            text=repair_heading(self.plan),
            bg=COLORS["card"],
            fg=COLORS["navy"],
            font=("Segoe UI Semibold", 16),
            justify="left",
            anchor="w",
            wraplength=570,
        ).pack(fill="x", pady=(4, 16))

        summary = tk.Frame(
            body,
            bg=COLORS["success_bg"],
            highlightthickness=1,
            highlightbackground="#ABEFC6",
        )
        summary.pack(fill="x")
        for line in repair_summary_lines(self.plan):
            tk.Label(
                summary,
                text=f"✓  {line}",
                bg=COLORS["success_bg"],
                fg=COLORS["success"],
                font=("Segoe UI", 10),
                anchor="w",
                justify="left",
                wraplength=550,
            ).pack(fill="x", padx=14, pady=5)

        self.details_button = tk.Button(
            body,
            text="Show details",
            command=self._toggle_details,
            bg=COLORS["card"],
            fg=COLORS["blue"],
            activebackground=COLORS["card"],
            activeforeground=COLORS["blue_hover"],
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 9),
            padx=0,
            pady=8,
        )
        self.details_button.pack(anchor="w", pady=(8, 0))

        self.details_frame = tk.Frame(body, bg="#F8FAFC")
        self.details_text = tk.Text(
            self.details_frame,
            height=12,
            bg="#F8FAFC",
            fg=COLORS["text"],
            font=("Consolas", 8),
            wrap="word",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=9,
        )
        scrollbar = ttk.Scrollbar(
            self.details_frame,
            orient="vertical",
            command=self.details_text.yview,
        )
        self.details_text.configure(yscrollcommand=scrollbar.set)
        self.details_text.insert("1.0", repair_details(self.plan))
        self.details_text.configure(state="disabled")
        self.details_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        buttons = tk.Frame(body, bg=COLORS["card"])
        buttons.pack(side="bottom", fill="x", pady=(14, 0))
        ttk.Button(
            buttons,
            text="Not Now",
            command=self._cancel,
        ).pack(side="right")
        primary = tk.Button(
            buttons,
            text="Copy Missing Libraries",
            command=self._confirm,
            bg=COLORS["blue"],
            fg="#FFFFFF",
            activebackground=COLORS["blue_hover"],
            activeforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
            padx=16,
            pady=9,
        )
        primary.pack(side="right", padx=(0, 8))
        primary.focus_set()

    def _toggle_details(self) -> None:
        self._details_visible = not self._details_visible
        if self._details_visible:
            self.details_frame.pack(fill="both", expand=True, pady=(0, 4))
            self.details_button.configure(text="Hide details")
            self.geometry("660x650")
        else:
            self.details_frame.pack_forget()
            self.details_button.configure(text="Show details")
            self.geometry("660x500")

    def _confirm(self) -> None:
        self.confirmed = True
        self.destroy()

    def _cancel(self) -> None:
        self.confirmed = False
        self.destroy()

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


class BaselineSourceDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.choose_source = False
        self._explanation_visible = False
        self.title("Choose Mitov Source")
        self.configure(bg=COLORS["background"])
        self.geometry("610x390")
        self.minsize(560, 360)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _event: self._cancel())
        self._build()
        self._center_over(parent)
        self.focus_set()

    def _build(self) -> None:
        card = tk.Frame(
            self,
            bg=COLORS["card"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        card.pack(fill="both", expand=True, padx=18, pady=18)
        body = tk.Frame(card, bg=COLORS["card"])
        body.pack(fill="both", expand=True, padx=24, pady=22)
        tk.Label(
            body,
            text="MITOV SOURCE NEEDED",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            text=SOURCE_MISSING_MESSAGE,
            bg=COLORS["card"],
            fg=COLORS["navy"],
            font=("Segoe UI Semibold", 15),
            justify="left",
            anchor="w",
            wraplength=520,
        ).pack(fill="x", pady=(5, 14))
        tk.Label(
            body,
            text=(
                "Choose the Arduino libraries folder you normally use with "
                "Visuino. Nothing will be copied until you review and confirm "
                "the repair plan."
            ),
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=("Segoe UI", 10),
            justify="left",
            anchor="w",
            wraplength=520,
        ).pack(fill="x")

        self.why_button = tk.Button(
            body,
            text="Why is this needed?",
            command=self._toggle_explanation,
            bg=COLORS["card"],
            fg=COLORS["blue"],
            activebackground=COLORS["card"],
            activeforeground=COLORS["blue_hover"],
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 9),
            padx=0,
            pady=9,
        )
        self.why_button.pack(anchor="w")
        self.explanation = tk.Label(
            body,
            text=SOURCE_EXPLANATION,
            bg=COLORS["warning_bg"],
            fg=COLORS["warning"],
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=500,
            padx=12,
            pady=10,
        )

        buttons = tk.Frame(body, bg=COLORS["card"])
        buttons.pack(side="bottom", fill="x", pady=(14, 0))
        ttk.Button(
            buttons,
            text="Not Now",
            command=self._cancel,
        ).pack(side="right")
        primary = tk.Button(
            buttons,
            text="Choose Library Folder",
            command=self._choose,
            bg=COLORS["blue"],
            fg="#FFFFFF",
            activebackground=COLORS["blue_hover"],
            activeforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
            padx=16,
            pady=9,
        )
        primary.pack(side="right", padx=(0, 8))
        primary.focus_set()

    def _toggle_explanation(self) -> None:
        self._explanation_visible = not self._explanation_visible
        if self._explanation_visible:
            self.explanation.pack(fill="x", pady=(0, 6))
            self.why_button.configure(text="Hide explanation")
            self.geometry("610x470")
        else:
            self.explanation.pack_forget()
            self.why_button.configure(text="Why is this needed?")
            self.geometry("610x390")

    def _choose(self) -> None:
        self.choose_source = True
        self.destroy()

    def _cancel(self) -> None:
        self.choose_source = False
        self.destroy()

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


def ask_baseline_repair(parent: tk.Misc, plan: Any) -> bool:
    dialog = BaselineRepairDialog(parent, plan)
    parent.wait_window(dialog)
    return dialog.confirmed


def ask_baseline_source(parent: tk.Misc) -> bool:
    dialog = BaselineSourceDialog(parent)
    parent.wait_window(dialog)
    return dialog.choose_source
