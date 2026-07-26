from __future__ import annotations

import webbrowser
from collections.abc import Callable

import tkinter as tk
from tkinter import ttk

from . import APP_NAME, __version__
from .branding import (
    DEDICATION_PARAGRAPHS,
    DEVELOPER_LINE,
    FINNANDRE_URL,
    INDEPENDENCE_STATEMENT,
    RECOGNITION_LINES,
    VISUINO_URL,
    load_finnandre_logo,
)


COLORS = {
    "background": "#F3F6FA",
    "card": "#FFFFFF",
    "navy": "#102A43",
    "blue": "#1D4ED8",
    "text": "#182230",
    "muted": "#667085",
    "line": "#DCE3EC",
    "soft_blue": "#EFF6FF",
}


class AboutDedicationDialog(tk.Toplevel):
    """Scroll-safe product dedication and attribution view."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title(f"About & Dedication — {APP_NAME}")
        self.configure(bg=COLORS["background"])
        self.geometry("720x680")
        self.minsize(620, 540)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())

        self._logo_image: tk.PhotoImage | None = None
        self._build()
        self._center_over(parent)
        self.focus_set()

    def _build(self) -> None:
        header = tk.Frame(self, bg=COLORS["navy"], height=92)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="ABOUT & DEDICATION",
            bg=COLORS["navy"],
            fg="#8FB8FF",
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", padx=26, pady=(17, 0))
        tk.Label(
            header,
            text=APP_NAME,
            bg=COLORS["navy"],
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 20),
            anchor="w",
        ).pack(fill="x", padx=26, pady=(2, 0))

        outer = tk.Frame(self, bg=COLORS["background"])
        outer.pack(fill="both", expand=True, padx=18, pady=18)
        canvas = tk.Canvas(
            outer,
            bg=COLORS["card"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        content = tk.Frame(canvas, bg=COLORS["card"])
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window_id, width=event.width),
        )
        canvas.bind_all(
            "<MouseWheel>",
            lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"),
            add="+",
        )
        self.bind(
            "<Destroy>",
            lambda _event: canvas.unbind_all("<MouseWheel>"),
            add="+",
        )

        body = tk.Frame(content, bg=COLORS["card"])
        body.pack(fill="both", expand=True, padx=28, pady=24)
        self._add_logo(body)
        tk.Label(
            body,
            text="Dedicated to Visuino",
            bg=COLORS["card"],
            fg=COLORS["navy"],
            font=("Segoe UI Semibold", 18),
            anchor="w",
        ).pack(fill="x", pady=(0, 14))

        for paragraph in DEDICATION_PARAGRAPHS:
            tk.Label(
                body,
                text=paragraph,
                bg=COLORS["card"],
                fg=COLORS["text"],
                font=("Segoe UI", 10),
                justify="left",
                anchor="w",
                wraplength=600,
            ).pack(fill="x", pady=(0, 12))

        self._section_label(body, "RECOGNITION")
        for line in RECOGNITION_LINES:
            tk.Label(
                body,
                text=line,
                bg=COLORS["card"],
                fg=COLORS["text"],
                font=("Segoe UI Semibold", 10),
                anchor="w",
            ).pack(fill="x", pady=(0, 5))

        self._section_label(body, "DEVELOPMENT")
        tk.Label(
            body,
            text=DEVELOPER_LINE,
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill="x", pady=(0, 5))

        statement = tk.Frame(
            body,
            bg=COLORS["soft_blue"],
            highlightthickness=1,
            highlightbackground="#BFDBFE",
        )
        statement.pack(fill="x", pady=(18, 14))
        tk.Label(
            statement,
            text=INDEPENDENCE_STATEMENT,
            bg=COLORS["soft_blue"],
            fg=COLORS["navy"],
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=570,
            padx=14,
            pady=12,
        ).pack(fill="x")

        links = tk.Frame(body, bg=COLORS["card"])
        links.pack(fill="x", pady=(0, 14))
        self._link_button(
            links, "Visit Visuino", lambda: self._open_url(VISUINO_URL)
        ).pack(side="left")
        self._link_button(
            links, "Visit finnandre.no", lambda: self._open_url(FINNANDRE_URL)
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            body,
            text=f"Version {__version__}",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill="x")

        footer = tk.Frame(self, bg=COLORS["background"])
        footer.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Button(
            footer,
            text="Close",
            command=self.destroy,
        ).pack(side="right")

    def _add_logo(self, parent: tk.Misc) -> None:
        try:
            self._logo_image = load_finnandre_logo(128, master=self)
        except (OSError, ValueError, tk.TclError):
            return
        tk.Label(
            parent,
            image=self._logo_image,
            bg=COLORS["card"],
            borderwidth=0,
        ).pack(anchor="w", pady=(0, 10))

    @staticmethod
    def _section_label(parent: tk.Misc, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x", pady=(8, 8))

    @staticmethod
    def _link_button(
        parent: tk.Misc, text: str, command: Callable[[], None]
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=COLORS["soft_blue"],
            fg=COLORS["blue"],
            activebackground="#DBEAFE",
            activeforeground=COLORS["blue"],
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 9),
            padx=12,
            pady=7,
        )

    @staticmethod
    def _open_url(url: str) -> None:
        webbrowser.open(url, new=2)

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
