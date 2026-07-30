import csv
import json
import os
import queue
import threading
import traceback
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from h1_audit import audit_urls as audit_h1_urls
from h1_audit import results_to_tsv as h1_results_to_tsv
from meta_audit import audit_urls as audit_meta_urls
from meta_audit import results_to_tsv as meta_results_to_tsv
from sitemap_parser import load_sitemaps


APP_TITLE = "Maptive Desktop"
SETTINGS_FILE = "maptive_settings.json"

BG_APP = "#0B0F17"
BG_SIDEBAR = "#0E1420"
BG_PANEL = "#111827"
BG_CARD = "#101826"
BG_CARD_SOFT = "#0F172A"
BORDER = "#243041"
TEXT_MAIN = "#F8FAFC"
TEXT_SUB = "#94A3B8"
TEXT_MUTED = "#AAB2BF"
BLUE = "#2563EB"
BLUE_HOVER = "#1D4ED8"
GREEN = "#22C55E"
ORANGE = "#F97316"
YELLOW = "#EAB308"
RED = "#EF4444"
PURPLE = "#A855F7"
SOFT_BUTTON = "#1B2433"
SOFT_BUTTON_HOVER = "#253246"


class MaptiveDesktopApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1600x980")
        self.root.minsize(1320, 840)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.h1_results = []
        self.meta_results = []
        self.sitemap_result = None

        self.sidebar_buttons = {}
        self.current_page = None

        self.ui_queue = queue.Queue()

        self.h1_running = False
        self.meta_running = False
        self.sitemap_running = False

        self.h1_cancel_event = threading.Event()
        self.meta_cancel_event = threading.Event()
        self.sitemap_cancel_event = threading.Event()

        self.h1_sort_state = {}
        self.meta_sort_state = {}

        self.build_ui()
        self.setup_table_styles()
        self.build_context_menus()
        self.load_settings()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.process_ui_queue)

    # =========================
    # THREAD / UI QUEUE
    # =========================
    def post_ui(self, callback, *args, **kwargs):
        self.ui_queue.put((callback, args, kwargs))

    def process_ui_queue(self):
        try:
            while True:
                callback, args, kwargs = self.ui_queue.get_nowait()
                callback(*args, **kwargs)
        except queue.Empty:
            pass
        self.root.after(100, self.process_ui_queue)

    def run_in_background(self, target):
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    def set_widgets_state(self, widgets, state):
        for widget in widgets:
            try:
                widget.configure(state=state)
            except Exception:
                pass

    def refresh_dashboard_cards(self):
        if hasattr(self, "dashboard_stats_wrap"):
            for child in self.dashboard_stats_wrap.winfo_children():
                child.destroy()

            self.make_stat_card(self.dashboard_stats_wrap, "H1 Rows", len(self.h1_results), BLUE)
            self.make_stat_card(self.dashboard_stats_wrap, "Meta Rows", len(self.meta_results), GREEN)
            self.make_stat_card(
                self.dashboard_stats_wrap,
                "Loaded Sitemap URLs",
                len(self.sitemap_result.get("urls", [])) if self.sitemap_result else 0,
                YELLOW,
            )

    # =========================
    # SETTINGS
    # =========================
    def collect_settings(self):
        return {
            "window_geometry": self.root.geometry(),
            "current_page": self.current_page or "dashboard",
            "h1_timeout": self.h1_timeout_var.get(),
            "h1_delay": self.h1_delay_var.get(),
            "h1_filter": self.h1_filter_var.get(),
            "h1_search": self.h1_search_var.get(),
            "h1_urls": self.h1_url_text.get("1.0", "end").strip(),
            "meta_timeout": self.meta_timeout_var.get(),
            "meta_delay": self.meta_delay_var.get(),
            "meta_filter": self.meta_filter_var.get(),
            "meta_search": self.meta_search_var.get(),
            "meta_urls": self.meta_url_text.get("1.0", "end").strip(),
            "sitemap_domain": self.domain_var.get(),
            "sitemap_timeout": self.sitemap_timeout_var.get(),
            "sitemap_depth": self.sitemap_depth_var.get(),
            "sitemap_filter": self.sitemap_filter_var.get(),
            "sitemap_allow_external": self.allow_external_var.get(),
            "sitemap_pages_only": self.pages_only_var.get(),
        }

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.collect_settings(), f, indent=2)
        except Exception:
            pass

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            self.show_page("dashboard")
            return

        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)

            geometry = settings.get("window_geometry")
            if geometry:
                self.root.geometry(geometry)

            self.h1_timeout_var.set(settings.get("h1_timeout", "15"))
            self.h1_delay_var.set(settings.get("h1_delay", "0"))
            self.h1_filter_var.set(settings.get("h1_filter", "All"))
            self.h1_search_var.set(settings.get("h1_search", ""))
            self.h1_url_text.delete("1.0", "end")
            self.h1_url_text.insert("1.0", settings.get("h1_urls", ""))

            self.meta_timeout_var.set(settings.get("meta_timeout", "15"))
            self.meta_delay_var.set(settings.get("meta_delay", "0"))
            self.meta_filter_var.set(settings.get("meta_filter", "All"))
            self.meta_search_var.set(settings.get("meta_search", ""))
            self.meta_url_text.delete("1.0", "end")
            self.meta_url_text.insert("1.0", settings.get("meta_urls", ""))

            self.domain_var.set(settings.get("sitemap_domain", ""))
            self.sitemap_timeout_var.set(settings.get("sitemap_timeout", "15"))
            self.sitemap_depth_var.set(settings.get("sitemap_depth", "10"))
            self.sitemap_filter_var.set(settings.get("sitemap_filter", ""))
            self.allow_external_var.set(settings.get("sitemap_allow_external", False))
            self.pages_only_var.set(settings.get("sitemap_pages_only", True))

            self.show_page(settings.get("current_page", "dashboard"))
            self.refresh_h1_table()
            self.refresh_meta_table()
        except Exception:
            self.show_page("dashboard")

    def reset_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                os.remove(SETTINGS_FILE)
            messagebox.showinfo("Settings Reset", "Saved settings were deleted. Restart to fully reset the UI state.")
        except Exception as exc:
            messagebox.showerror("Settings Error", str(exc))

    def on_close(self):
        self.save_settings()
        self.root.destroy()

    # =========================
    # HELPERS
    # =========================
    def ask_save_tsv(self, title="Save TSV"):
        return filedialog.asksaveasfilename(
            title=title,
            defaultextension=".tsv",
            filetypes=[("TSV files", "*.tsv"), ("Text files", "*.txt"), ("All files", "*.*")],
        )

    def ask_open_urls_file(self):
        return filedialog.askopenfilename(
            title="Open URL File",
            filetypes=[
                ("Supported files", "*.txt *.csv"),
                ("Text files", "*.txt"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )

    def normalize_lines(self, lines):
        cleaned = []
        seen = set()
        for line in lines:
            value = (line or "").strip()
            if not value:
                continue
            if value in seen:
                continue
            seen.add(value)
            cleaned.append(value)
        return cleaned

    def read_urls_from_file(self, file_path):
        if not file_path:
            return []

        try:
            if file_path.lower().endswith(".txt"):
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    return self.normalize_lines(f.read().splitlines())

            if file_path.lower().endswith(".csv"):
                urls = []
                with open(file_path, "r", encoding="utf-8", errors="replace", newline="") as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                if not rows:
                    return []

                header = [str(col).strip().lower() for col in rows[0]]
                url_index = None

                for idx, col in enumerate(header):
                    if col in {"url", "urls", "link", "links", "page", "page_url"}:
                        url_index = idx
                        break

                if url_index is not None:
                    for row in rows[1:]:
                        if url_index < len(row):
                            urls.append(row[url_index].strip())
                else:
                    for row in rows:
                        for cell in row:
                            cell = (cell or "").strip()
                            if cell.startswith("http://") or cell.startswith("https://") or "." in cell:
                                urls.append(cell)

                return self.normalize_lines(urls)

            return []
        except Exception as exc:
            messagebox.showerror("Import Error", f"Failed to read file:\n{exc}")
            return []

    def get_text_lines(self, text_widget: ctk.CTkTextbox):
        raw = text_widget.get("1.0", "end").strip()
        if not raw:
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def set_text_lines(self, text_widget: ctk.CTkTextbox, lines):
        text_widget.delete("1.0", "end")
        if lines:
            text_widget.insert("1.0", "\n".join(lines))

    def append_text_lines(self, text_widget: ctk.CTkTextbox, new_lines):
        current = self.get_text_lines(text_widget)
        merged = self.normalize_lines(current + list(new_lines))
        self.set_text_lines(text_widget, merged)

    def card(self, parent, title=None, subtitle=None):
        frame = ctk.CTkFrame(
            parent,
            corner_radius=18,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER
        )
        if title:
            header_wrap = ctk.CTkFrame(frame, fg_color="transparent")
            header_wrap.pack(fill="x", padx=18, pady=(16, 6))

            header = ctk.CTkLabel(
                header_wrap,
                text=title,
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=TEXT_MAIN,
            )
            header.pack(anchor="w")

            if subtitle:
                ctk.CTkLabel(
                    header_wrap,
                    text=subtitle,
                    font=ctk.CTkFont(size=12),
                    text_color=TEXT_SUB,
                ).pack(anchor="w", pady=(4, 0))
        return frame

    def make_stat_card(self, parent, label, value, color=BLUE):
        frame = ctk.CTkFrame(
            parent,
            corner_radius=16,
            fg_color=BG_CARD_SOFT,
            border_width=1,
            border_color=BORDER
        )
        frame.pack(side="left", fill="x", expand=True, padx=6)

        ctk.CTkLabel(
            frame,
            text=label,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SUB,
        ).pack(anchor="w", padx=14, pady=(10, 2))

        ctk.CTkLabel(
            frame,
            text=str(value),
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=color,
        ).pack(anchor="w", padx=14, pady=(0, 12))

        return frame

    def make_tool_tile(self, parent, title, subtitle, button_text, command, accent=BLUE):
        tile = ctk.CTkFrame(
            parent,
            corner_radius=18,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER
        )
        tile.grid_columnconfigure(0, weight=1)

        top_line = ctk.CTkFrame(tile, height=4, fg_color=accent, corner_radius=999)
        top_line.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))

        ctk.CTkLabel(
            tile,
            text=title,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=TEXT_MAIN,
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 8))

        ctk.CTkLabel(
            tile,
            text=subtitle,
            justify="left",
            wraplength=340,
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SUB,
        ).grid(row=2, column=0, sticky="w", padx=18, pady=(0, 16))

        ctk.CTkButton(
            tile,
            text=button_text,
            height=40,
            corner_radius=12,
            fg_color=accent,
            hover_color=BLUE_HOVER,
            command=command,
        ).grid(row=3, column=0, sticky="w", padx=18, pady=(0, 18))

        return tile

    def tree_clear(self, tree):
        for item in tree.get_children():
            tree.delete(item)

    def show_about_dialog(self):
        messagebox.showinfo(
            "About Maptive Desktop",
            "Maptive Desktop\n\n"
            "A modern desktop SEO tool for:\n"
            "- H1 auditing\n"
            "- Sitemap loading\n"
            "- Meta title and description audits\n\n"
            "Built with Python and CustomTkinter."
        )

    def copy_text_to_clipboard(self, text: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def row_matches_search(self, row: dict, search_text: str) -> bool:
        if not search_text:
            return True
        haystack = " ".join(str(v) for v in row.values()).lower()
        return search_text.lower() in haystack

    def get_selected_tree_rows(self, tree, full_rows):
        selected_items = tree.selection()
        if not selected_items:
            return []

        results = []
        for item in selected_items:
            url = str(tree.item(item, "values")[0]).strip()
            for row in full_rows:
                if str(row.get("url", "")).strip() == url:
                    results.append(row)
                    break
        return results

    def export_rows_tsv(self, rows, formatter, title):
        if not rows:
            messagebox.showwarning("No Rows", "No rows available for export.")
            return
        file_path = self.ask_save_tsv(title)
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(formatter(rows))
        messagebox.showinfo("Exported", f"Saved {len(rows)} row(s) to:\n{file_path}")

    def safe_sort_value(self, value):
        if value is None:
            return (1, "")
        text = str(value).strip()
        if text == "":
            return (1, "")
        try:
            return (0, float(text))
        except Exception:
            return (0, text.lower())

    # =========================
    # CONTEXT MENUS / TABLE ACTIONS
    # =========================
    def build_context_menus(self):
        self.h1_menu = tk.Menu(self.root, tearoff=0)
        self.h1_menu.add_command(label="Copy URL", command=lambda: self.copy_selected_tree_url(self.h1_tree))
        self.h1_menu.add_command(label="Open URL in Browser", command=lambda: self.open_selected_tree_url(self.h1_tree))
        self.h1_menu.add_separator()
        self.h1_menu.add_command(label="Copy Selected Row(s)", command=self.copy_selected_h1_rows)
        self.h1_menu.add_command(label="Export Selected Row(s)", command=self.export_selected_h1_rows)

        self.meta_menu = tk.Menu(self.root, tearoff=0)
        self.meta_menu.add_command(label="Copy URL", command=lambda: self.copy_selected_tree_url(self.meta_tree))
        self.meta_menu.add_command(label="Open URL in Browser", command=lambda: self.open_selected_tree_url(self.meta_tree))
        self.meta_menu.add_separator()
        self.meta_menu.add_command(label="Copy Selected Row(s)", command=self.copy_selected_meta_rows)
        self.meta_menu.add_command(label="Export Selected Row(s)", command=self.export_selected_meta_rows)

    def show_tree_menu(self, event, tree, menu):
        item = tree.identify_row(event.y)
        if item:
            tree.selection_set(item)
            menu.tk_popup(event.x_root, event.y_root)

    def get_selected_tree_url(self, tree):
        selection = tree.selection()
        if not selection:
            return ""
        values = tree.item(selection[0], "values")
        if not values:
            return ""
        return str(values[0]).strip()

    def copy_selected_tree_url(self, tree):
        url = self.get_selected_tree_url(tree)
        if not url:
            messagebox.showwarning("No Row Selected", "Please select a row first.")
            return
        self.copy_text_to_clipboard(url)
        messagebox.showinfo("Copied", f"Copied URL:\n{url}")

    def open_selected_tree_url(self, tree):
        url = self.get_selected_tree_url(tree)
        if not url:
            messagebox.showwarning("No Row Selected", "Please select a row first.")
            return
        webbrowser.open(url)

    def on_tree_double_click_copy(self, tree):
        url = self.get_selected_tree_url(tree)
        if url:
            self.copy_text_to_clipboard(url)
            messagebox.showinfo("Copied", f"Copied URL:\n{url}")

    def sort_treeview(self, tree, col, backing_rows, refresh_callback, sort_state_dict):
        current_reverse = sort_state_dict.get(col, False)
        new_reverse = not current_reverse
        sort_state_dict[col] = new_reverse

        backing_rows.sort(key=lambda row: self.safe_sort_value(row.get(col, "")), reverse=new_reverse)
        refresh_callback()

    # =========================
    # MAIN LAYOUT
    # =========================
    def build_ui(self):
        self.root.configure(fg_color=BG_APP)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self.root, width=260, corner_radius=0, fg_color=BG_SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)

        self.content = ctk.CTkFrame(self.root, corner_radius=0, fg_color=BG_APP)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(1, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.build_sidebar()
        self.build_header()
        self.build_pages()

    def build_sidebar(self):
        logo_wrap = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_wrap.pack(fill="x", padx=18, pady=(22, 14))

        ctk.CTkLabel(
            logo_wrap,
            text="Maptive",
            font=ctk.CTkFont(size=30, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w")

        ctk.CTkLabel(
            logo_wrap,
            text="SEO desktop toolkit",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SUB,
        ).pack(anchor="w", pady=(2, 0))

        divider = ctk.CTkFrame(self.sidebar, height=1, fg_color="#1E293B")
        divider.pack(fill="x", padx=18, pady=(4, 14))

        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.pack(fill="x", padx=14, pady=(0, 0))

        self.sidebar_buttons["dashboard"] = ctk.CTkButton(
            nav, text="Dashboard", height=46, corner_radius=12,
            fg_color=SOFT_BUTTON, hover_color=BLUE, anchor="w",
            command=lambda: self.show_page("dashboard")
        )
        self.sidebar_buttons["dashboard"].pack(fill="x", pady=6)

        self.sidebar_buttons["h1"] = ctk.CTkButton(
            nav, text="H1 Audit", height=46, corner_radius=12,
            fg_color=SOFT_BUTTON, hover_color=BLUE, anchor="w",
            command=lambda: self.show_page("h1")
        )
        self.sidebar_buttons["h1"].pack(fill="x", pady=6)

        self.sidebar_buttons["sitemap"] = ctk.CTkButton(
            nav, text="Sitemap Loader", height=46, corner_radius=12,
            fg_color=SOFT_BUTTON, hover_color=BLUE, anchor="w",
            command=lambda: self.show_page("sitemap")
        )
        self.sidebar_buttons["sitemap"].pack(fill="x", pady=6)

        self.sidebar_buttons["meta"] = ctk.CTkButton(
            nav, text="Meta Scraper", height=46, corner_radius=12,
            fg_color=SOFT_BUTTON, hover_color=BLUE, anchor="w",
            command=lambda: self.show_page("meta")
        )
        self.sidebar_buttons["meta"].pack(fill="x", pady=6)

        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=14, pady=18)

        ctk.CTkButton(
            bottom, text="About", height=42, corner_radius=12,
            fg_color=SOFT_BUTTON, hover_color=SOFT_BUTTON_HOVER,
            command=self.show_about_dialog
        ).pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            bottom, text="Reset Saved Settings", height=42, corner_radius=12,
            fg_color="#3A1C1C", hover_color="#5B2323",
            command=self.reset_settings
        ).pack(fill="x")

        ctk.CTkLabel(
            bottom,
            text="v4 Results Upgrade",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SUB,
        ).pack(anchor="w", pady=(12, 0))

    def build_header(self):
        self.header = ctk.CTkFrame(
            self.content,
            height=92,
            corner_radius=18,
            fg_color=BG_PANEL,
            border_width=1,
            border_color=BORDER
        )
        self.header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 0))
        self.header.grid_columnconfigure(0, weight=1)

        self.page_title_label = ctk.CTkLabel(
            self.header,
            text="",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=TEXT_MAIN,
        )
        self.page_title_label.grid(row=0, column=0, sticky="w", padx=20, pady=(14, 0))

        self.page_subtitle_label = ctk.CTkLabel(
            self.header,
            text="",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SUB,
        )
        self.page_subtitle_label.grid(row=1, column=0, sticky="w", padx=20, pady=(4, 14))

    def build_pages(self):
        self.pages_wrap = ctk.CTkFrame(self.content, fg_color="transparent")
        self.pages_wrap.grid(row=1, column=0, sticky="nsew", padx=22, pady=(14, 20))
        self.pages_wrap.grid_rowconfigure(0, weight=1)
        self.pages_wrap.grid_columnconfigure(0, weight=1)

        self.dashboard_page = ctk.CTkFrame(self.pages_wrap, fg_color="transparent")
        self.h1_page = ctk.CTkFrame(self.pages_wrap, fg_color="transparent")
        self.sitemap_page = ctk.CTkFrame(self.pages_wrap, fg_color="transparent")
        self.meta_page = ctk.CTkFrame(self.pages_wrap, fg_color="transparent")

        for page in (self.dashboard_page, self.h1_page, self.sitemap_page, self.meta_page):
            page.grid(row=0, column=0, sticky="nsew")

        self.build_dashboard_page()
        self.build_h1_page()
        self.build_sitemap_page()
        self.build_meta_page()

    def show_page(self, page_name):
        self.current_page = page_name

        pages = {
            "dashboard": self.dashboard_page,
            "h1": self.h1_page,
            "sitemap": self.sitemap_page,
            "meta": self.meta_page,
        }
        titles = {
            "dashboard": ("Dashboard", "Overview of Maptive’s SEO desktop workflows."),
            "h1": ("H1 Audit", "Audit headings, detect issues, export selected rows, and copy issue sets."),
            "sitemap": ("Sitemap Loader", "Load sitemap URLs from a domain and send them into your audits."),
            "meta": ("Meta Scraper", "Audit titles and meta descriptions with search, sorting, and selected-row exports."),
        }

        for name, btn in self.sidebar_buttons.items():
            btn.configure(fg_color=BLUE if name == page_name else SOFT_BUTTON)

        pages[page_name].tkraise()
        title, subtitle = titles[page_name]
        self.page_title_label.configure(text=title)
        self.page_subtitle_label.configure(text=subtitle)

    # =========================
    # TABLE STYLES
    # =========================
    def setup_table_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Treeview",
            background="#0F172A",
            foreground="#F8FAFC",
            fieldbackground="#0F172A",
            bordercolor=BORDER,
            rowheight=30,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#162033",
            foreground="#F8FAFC",
            relief="flat",
            font=("Segoe UI Semibold", 10),
            padding=6
        )
        style.map("Treeview.Heading", background=[("active", "#22304A")])

    def apply_tree_tags(self, tree):
        tree.tag_configure("ok", foreground="#D1FAE5")
        tree.tag_configure("warn", foreground="#FDE68A")
        tree.tag_configure("error", foreground="#FECACA")

    # =========================
    # DASHBOARD PAGE
    # =========================
    def build_dashboard_page(self):
        outer = ctk.CTkScrollableFrame(self.dashboard_page, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        hero = self.card(
            outer,
            "Welcome to Maptive",
            "A cleaner desktop workspace for sitemap extraction, metadata auditing, and H1 analysis."
        )
        hero.pack(fill="x", pady=(0, 14))

        hero_body = ctk.CTkFrame(hero, fg_color="transparent")
        hero_body.pack(fill="x", padx=18, pady=(0, 18))
        hero_body.grid_columnconfigure(0, weight=1)
        hero_body.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(hero_body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ctk.CTkLabel(
            left,
            text="What you can do here",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w")

        ctk.CTkLabel(
            left,
            text=(
                "• Load sitemap URLs from a domain or exact sitemap file\n"
                "• Search H1 and Meta results instantly\n"
                "• Sort result columns\n"
                "• Copy selected rows or issues only\n"
                "• Export selected rows or issues only\n"
                "• Push sitemap URLs into H1 or Meta audits"
            ),
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SUB,
        ).pack(anchor="w", pady=(10, 0))

        right = ctk.CTkFrame(hero_body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        quick_row = ctk.CTkFrame(right, fg_color="transparent")
        quick_row.pack(fill="x")

        ctk.CTkButton(
            quick_row,
            text="Open H1 Audit",
            height=42,
            corner_radius=12,
            fg_color=BLUE,
            hover_color=BLUE_HOVER,
            command=lambda: self.show_page("h1"),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            quick_row,
            text="Open Sitemap Loader",
            height=42,
            corner_radius=12,
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_BUTTON_HOVER,
            command=lambda: self.show_page("sitemap"),
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            quick_row,
            text="Open Meta Scraper",
            height=42,
            corner_radius=12,
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_BUTTON_HOVER,
            command=lambda: self.show_page("meta"),
        ).pack(side="left", padx=8)

        self.dashboard_stats_wrap = ctk.CTkFrame(outer, fg_color="transparent")
        self.dashboard_stats_wrap.pack(fill="x", pady=(0, 14))
        self.refresh_dashboard_cards()

    # =========================
    # H1 PAGE
    # =========================
    def build_h1_page(self):
        self.h1_timeout_var = ctk.StringVar(value="15")
        self.h1_delay_var = ctk.StringVar(value="0")
        self.h1_filter_var = ctk.StringVar(value="All")
        self.h1_search_var = ctk.StringVar(value="")
        self.h1_status_var = ctk.StringVar(value="Ready")

        outer = ctk.CTkScrollableFrame(self.h1_page, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        top = self.card(
            outer,
            "Manual URL Input",
            "Paste URLs directly or import a TXT/CSV file for H1 auditing."
        )
        top.pack(fill="x", pady=(0, 14))

        controls = ctk.CTkFrame(top, fg_color="transparent")
        controls.pack(fill="x", padx=18, pady=(0, 10))

        ctk.CTkLabel(controls, text="Timeout", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.h1_timeout_entry = ctk.CTkEntry(controls, width=90, textvariable=self.h1_timeout_var)
        self.h1_timeout_entry.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(controls, text="Delay", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.h1_delay_entry = ctk.CTkEntry(controls, width=90, textvariable=self.h1_delay_var)
        self.h1_delay_entry.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(controls, text="Filter", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.h1_filter_menu = ctk.CTkOptionMenu(
            controls,
            values=["All", "Only Multiple H1s", "Only Missing H1", "Only Issues"],
            variable=self.h1_filter_var,
            width=180,
            command=lambda _: self.refresh_h1_table(),
        )
        self.h1_filter_menu.pack(side="left", padx=(0, 16))

        self.h1_run_btn = ctk.CTkButton(controls, text="Run H1 Audit", width=140, command=self.run_h1_audit)
        self.h1_run_btn.pack(side="left", padx=6)

        self.h1_cancel_btn = ctk.CTkButton(
            controls, text="Cancel", width=100,
            fg_color="#5B2323", hover_color="#7A2E2E",
            command=self.cancel_h1_audit
        )
        self.h1_cancel_btn.pack(side="left", padx=6)

        self.h1_import_replace_btn = ctk.CTkButton(controls, text="Import (Replace)", width=130, command=self.import_h1_urls_replace)
        self.h1_import_replace_btn.pack(side="left", padx=6)

        self.h1_import_append_btn = ctk.CTkButton(controls, text="Import (Append)", width=130, command=self.import_h1_urls_append)
        self.h1_import_append_btn.pack(side="left", padx=6)

        self.h1_clear_urls_btn = ctk.CTkButton(
            controls, text="Clear URLs", width=110,
            fg_color=SOFT_BUTTON, hover_color=SOFT_BUTTON_HOVER,
            command=self.clear_h1_urls
        )
        self.h1_clear_urls_btn.pack(side="left", padx=6)

        helper = ctk.CTkLabel(
            top,
            text="Tip: Search results below. Double-click row to copy URL. Right-click row for actions.",
            text_color=TEXT_SUB,
            font=ctk.CTkFont(size=12),
        )
        helper.pack(anchor="w", padx=18, pady=(0, 8))

        self.h1_url_text = ctk.CTkTextbox(top, height=180, corner_radius=12)
        self.h1_url_text.pack(fill="x", padx=18, pady=(0, 18))

        stats = ctk.CTkFrame(outer, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 14))
        self.h1_stat_wrap = stats
        self.make_stat_card(stats, "Total", 0, BLUE)
        self.make_stat_card(stats, "OK", 0, GREEN)
        self.make_stat_card(stats, "Missing H1", 0, ORANGE)
        self.make_stat_card(stats, "Multiple H1s", 0, YELLOW)
        self.make_stat_card(stats, "Errors", 0, RED)
        self.make_stat_card(stats, "Issue Rows", 0, PURPLE)

        action_card = self.card(outer, "Actions", "Copy, export, search, or isolate issue rows.")
        action_card.pack(fill="x", pady=(0, 14))

        search_row = ctk.CTkFrame(action_card, fg_color="transparent")
        search_row.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkLabel(search_row, text="Search", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.h1_search_entry = ctk.CTkEntry(search_row, textvariable=self.h1_search_var)
        self.h1_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.h1_search_entry.bind("<KeyRelease>", lambda event: self.refresh_h1_table())
        ctk.CTkButton(
            search_row, text="Clear Search", width=120,
            fg_color=SOFT_BUTTON, hover_color=SOFT_BUTTON_HOVER,
            command=self.clear_h1_search
        ).pack(side="left")

        action_row = ctk.CTkFrame(action_card, fg_color="transparent")
        action_row.pack(fill="x", padx=18, pady=(0, 18))

        self.h1_copy_btn = ctk.CTkButton(action_row, text="Copy Filtered TSV", width=150, command=self.copy_h1_results)
        self.h1_copy_btn.pack(side="left", padx=6)

        self.h1_copy_selected_btn = ctk.CTkButton(action_row, text="Copy Selected", width=130, command=self.copy_selected_h1_rows)
        self.h1_copy_selected_btn.pack(side="left", padx=6)

        self.h1_copy_issues_btn = ctk.CTkButton(action_row, text="Copy Issues Only", width=140, command=self.copy_h1_issues_rows)
        self.h1_copy_issues_btn.pack(side="left", padx=6)

        self.h1_export_btn = ctk.CTkButton(action_row, text="Export Filtered", width=130, command=self.export_h1_tsv)
        self.h1_export_btn.pack(side="left", padx=6)

        self.h1_export_selected_btn = ctk.CTkButton(action_row, text="Export Selected", width=130, command=self.export_selected_h1_rows)
        self.h1_export_selected_btn.pack(side="left", padx=6)

        self.h1_export_issues_btn = ctk.CTkButton(action_row, text="Export Issues", width=130, command=self.export_h1_issues_tsv)
        self.h1_export_issues_btn.pack(side="left", padx=6)

        self.h1_clear_results_btn = ctk.CTkButton(
            action_row, text="Clear Results", width=130,
            fg_color=SOFT_BUTTON, hover_color=SOFT_BUTTON_HOVER,
            command=self.clear_h1_results
        )
        self.h1_clear_results_btn.pack(side="left", padx=6)

        progress_card = self.card(outer, "Progress", "Audit progress and current processing state.")
        progress_card.pack(fill="x", pady=(0, 14))
        p_row = ctk.CTkFrame(progress_card, fg_color="transparent")
        p_row.pack(fill="x", padx=18, pady=(0, 18))
        self.h1_progressbar = ctk.CTkProgressBar(p_row, progress_color=GREEN)
        self.h1_progressbar.set(0)
        self.h1_progressbar.pack(side="left", fill="x", expand=True, padx=(0, 14))
        self.h1_status_label = ctk.CTkLabel(p_row, textvariable=self.h1_status_var, text_color="#D1D5DB")
        self.h1_status_label.pack(side="left")

        results_card = self.card(outer, "H1 Results", "Detailed output from the H1 audit module.")
        results_card.pack(fill="both", expand=True, pady=(0, 14))

        tree_wrap = ctk.CTkFrame(results_card, fg_color="transparent")
        tree_wrap.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        self.h1_columns = (
            "url", "status", "status_code", "title", "h1_count",
            "original_tags", "new_tags", "heading_texts", "change_templates",
            "note", "recommended_h1", "priority", "action_needed", "error"
        )

        self.h1_tree = ttk.Treeview(tree_wrap, columns=self.h1_columns, show="headings", selectmode="extended")

        headings = {
            "url": "URL",
            "status": "Status",
            "status_code": "Code",
            "title": "Title",
            "h1_count": "H1 Count",
            "original_tags": "Original Tags",
            "new_tags": "New Tags",
            "heading_texts": "Heading Texts",
            "change_templates": "Change Templates",
            "note": "Note",
            "recommended_h1": "Recommended H1",
            "priority": "Priority",
            "action_needed": "Action Needed",
            "error": "Error",
        }

        widths = {
            "url": 220,
            "status": 80,
            "status_code": 70,
            "title": 170,
            "h1_count": 80,
            "original_tags": 100,
            "new_tags": 90,
            "heading_texts": 180,
            "change_templates": 220,
            "note": 120,
            "recommended_h1": 170,
            "priority": 90,
            "action_needed": 210,
            "error": 150,
        }

        for col in self.h1_columns:
            self.h1_tree.heading(
                col,
                text=headings[col],
                command=lambda c=col: self.sort_treeview(self.h1_tree, c, self.h1_results, self.refresh_h1_table, self.h1_sort_state)
            )
            self.h1_tree.column(col, width=widths[col], anchor="w")

        h1_scroll_y = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.h1_tree.yview)
        h1_scroll_x = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.h1_tree.xview)
        self.h1_tree.configure(yscrollcommand=h1_scroll_y.set, xscrollcommand=h1_scroll_x.set)

        self.h1_tree.pack(side="top", fill="both", expand=True)
        h1_scroll_y.pack(side="right", fill="y")
        h1_scroll_x.pack(side="bottom", fill="x")
        self.apply_tree_tags(self.h1_tree)
        self.h1_tree.bind("<Double-1>", lambda event: self.on_tree_double_click_copy(self.h1_tree))
        self.h1_tree.bind("<Button-3>", lambda event: self.show_tree_menu(event, self.h1_tree, self.h1_menu))

        logs_card = self.card(outer, "Logs", "Runtime log messages from the H1 audit.")
        logs_card.pack(fill="x", pady=(0, 20))
        self.h1_log_text = ctk.CTkTextbox(logs_card, height=120, corner_radius=12)
        self.h1_log_text.pack(fill="x", padx=18, pady=(0, 18))

        self.h1_busy_widgets = [
            self.h1_run_btn,
            self.h1_import_replace_btn,
            self.h1_import_append_btn,
            self.h1_clear_urls_btn,
            self.h1_copy_btn,
            self.h1_copy_selected_btn,
            self.h1_copy_issues_btn,
            self.h1_export_btn,
            self.h1_export_selected_btn,
            self.h1_export_issues_btn,
            self.h1_clear_results_btn,
            self.h1_filter_menu,
            self.h1_timeout_entry,
            self.h1_delay_entry,
        ]

    def import_h1_urls_replace(self):
        file_path = self.ask_open_urls_file()
        urls = self.read_urls_from_file(file_path)
        if not urls:
            return
        self.set_text_lines(self.h1_url_text, urls)
        messagebox.showinfo("Imported", f"{len(urls)} URL(s) imported into H1 input.")

    def import_h1_urls_append(self):
        file_path = self.ask_open_urls_file()
        urls = self.read_urls_from_file(file_path)
        if not urls:
            return
        before = len(self.get_text_lines(self.h1_url_text))
        self.append_text_lines(self.h1_url_text, urls)
        after = len(self.get_text_lines(self.h1_url_text))
        messagebox.showinfo("Imported", f"{after - before} new URL(s) appended to H1 input.")

    def h1_log(self, message: str):
        self.h1_log_text.insert("end", message + "\n")
        self.h1_log_text.see("end")

    def get_h1_manual_urls(self):
        return self.get_text_lines(self.h1_url_text)

    def set_h1_progress(self, current: int, total: int, result: dict):
        percent = 0 if total == 0 else (current / total)
        self.h1_progressbar.set(percent)
        self.h1_status_var.set(f"Processed {current}/{total}")

    def h1_row_tag(self, row):
        status = str(row.get("status", "")).upper()
        note = str(row.get("note", "")).strip()
        if status in {"FETCH_FAILED", "TIMEOUT", "REDIRECT_ERROR", "INVALID", "NON_HTML"}:
            return "error"
        if note in {"Multiple H1s", "Missing H1"}:
            return "warn"
        return "ok"

    def get_h1_issue_rows(self):
        return [
            r for r in self.h1_results
            if r.get("note") in {"Multiple H1s", "Missing H1"}
            or str(r.get("status", "")).upper() in {"FETCH_FAILED", "TIMEOUT", "REDIRECT_ERROR", "INVALID", "NON_HTML"}
        ]

    def get_filtered_h1_results(self):
        mode = self.h1_filter_var.get()
        if mode == "Only Multiple H1s":
            rows = [r for r in self.h1_results if r.get("note") == "Multiple H1s"]
        elif mode == "Only Missing H1":
            rows = [r for r in self.h1_results if r.get("note") == "Missing H1"]
        elif mode == "Only Issues":
            rows = self.get_h1_issue_rows()
        else:
            rows = self.h1_results

        return [r for r in rows if self.row_matches_search(r, self.h1_search_var.get().strip())]

    def update_h1_stats(self):
        total = len(self.h1_results)
        ok = sum(1 for r in self.h1_results if r.get("note") == "OK" and str(r.get("status", "")).upper() == "OK")
        missing = sum(1 for r in self.h1_results if r.get("note") == "Missing H1")
        multiple = sum(1 for r in self.h1_results if r.get("note") == "Multiple H1s")
        errors = sum(1 for r in self.h1_results if str(r.get("status", "")).upper() in {"FETCH_FAILED", "TIMEOUT", "REDIRECT_ERROR", "INVALID", "NON_HTML"})
        issues = len(self.get_h1_issue_rows())

        for widget in self.h1_stat_wrap.winfo_children():
            widget.destroy()

        self.make_stat_card(self.h1_stat_wrap, "Total", total, BLUE)
        self.make_stat_card(self.h1_stat_wrap, "OK", ok, GREEN)
        self.make_stat_card(self.h1_stat_wrap, "Missing H1", missing, ORANGE)
        self.make_stat_card(self.h1_stat_wrap, "Multiple H1s", multiple, YELLOW)
        self.make_stat_card(self.h1_stat_wrap, "Errors", errors, RED)
        self.make_stat_card(self.h1_stat_wrap, "Issue Rows", issues, PURPLE)

    def refresh_h1_table(self):
        self.tree_clear(self.h1_tree)
        for row in self.get_filtered_h1_results():
            self.h1_tree.insert(
                "",
                "end",
                values=(
                    row.get("url", ""), row.get("status", ""), row.get("status_code", ""),
                    row.get("title", ""), row.get("h1_count", ""), row.get("original_tags", ""),
                    row.get("new_tags", ""), row.get("heading_texts", ""), row.get("change_templates", ""),
                    row.get("note", ""), row.get("recommended_h1", ""), row.get("priority", ""),
                    row.get("action_needed", ""), row.get("error", ""),
                ),
                tags=(self.h1_row_tag(row),),
            )
        self.update_h1_stats()
        self.refresh_dashboard_cards()

    def clear_h1_search(self):
        self.h1_search_var.set("")
        self.refresh_h1_table()

    def copy_selected_h1_rows(self):
        rows = self.get_selected_tree_rows(self.h1_tree, self.get_filtered_h1_results())
        if not rows:
            messagebox.showwarning("No Rows Selected", "Select one or more H1 rows first.")
            return
        self.copy_text_to_clipboard(h1_results_to_tsv(rows))
        messagebox.showinfo("Copied", f"{len(rows)} selected H1 row(s) copied as TSV.")

    def copy_h1_issues_rows(self):
        rows = [r for r in self.get_filtered_h1_results() if r in self.get_h1_issue_rows()]
        if not rows:
            messagebox.showwarning("No Issues", "No issue rows available in the current H1 view.")
            return
        self.copy_text_to_clipboard(h1_results_to_tsv(rows))
        messagebox.showinfo("Copied", f"{len(rows)} H1 issue row(s) copied as TSV.")

    def export_selected_h1_rows(self):
        rows = self.get_selected_tree_rows(self.h1_tree, self.get_filtered_h1_results())
        if not rows:
            messagebox.showwarning("No Rows Selected", "Select one or more H1 rows first.")
            return
        self.export_rows_tsv(rows, h1_results_to_tsv, "Save Selected H1 TSV")

    def set_h1_running_state(self, running: bool):
        self.h1_running = running
        self.set_widgets_state(self.h1_busy_widgets, "disabled" if running else "normal")
        self.h1_cancel_btn.configure(state="normal" if running else "disabled")

    def cancel_h1_audit(self):
        if self.h1_running:
            self.h1_cancel_event.set()
            self.h1_status_var.set("Cancelling...")

    def _h1_progress_from_worker(self, current, total, result):
        self.set_h1_progress(current, total, result)

    def _h1_log_from_worker(self, message):
        self.h1_log(message)

    def _h1_complete_from_worker(self, results):
        self.h1_results = results
        self.refresh_h1_table()
        if self.h1_cancel_event.is_set():
            self.h1_status_var.set(f"Cancelled - {len(self.h1_results)} URL(s) processed")
            self.h1_log("H1 audit cancelled.")
        else:
            self.h1_status_var.set(f"Done - {len(self.h1_results)} URL(s) audited")
            self.h1_log("Audit completed.")
        self.set_h1_running_state(False)

    def _h1_failed_from_worker(self, error_text):
        self.h1_status_var.set("Failed")
        self.h1_log(f"ERROR: {error_text}")
        self.set_h1_running_state(False)
        messagebox.showerror("Audit Error", error_text)

    def run_h1_audit(self):
        if self.h1_running:
            return

        urls = self.get_h1_manual_urls()
        if not urls:
            messagebox.showwarning("No URLs", "Please paste or import at least one URL.")
            return

        try:
            timeout = int(self.h1_timeout_var.get().strip())
            delay_ms = int(self.h1_delay_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Input", "Timeout and Delay must be numbers.")
            return

        self.h1_cancel_event.clear()
        self.h1_results = []
        self.refresh_h1_table()
        self.h1_log_text.delete("1.0", "end")
        self.h1_progressbar.set(0)
        self.h1_status_var.set("Running...")
        self.set_h1_running_state(True)

        def worker():
            try:
                results = audit_h1_urls(
                    urls=urls,
                    timeout=timeout,
                    delay_ms=delay_ms,
                    progress_callback=lambda current, total, result: self.post_ui(
                        self._h1_progress_from_worker, current, total, result
                    ),
                    log_callback=lambda message: self.post_ui(self._h1_log_from_worker, message),
                    cancel_event=self.h1_cancel_event,
                )
                self.post_ui(self._h1_complete_from_worker, results)
            except Exception as exc:
                error_text = f"{exc}\n\n{traceback.format_exc()}"
                self.post_ui(self._h1_failed_from_worker, error_text)

        self.run_in_background(worker)

    def copy_h1_results(self):
        filtered = self.get_filtered_h1_results()
        if not filtered:
            messagebox.showwarning("No Results", "There are no H1 results to copy.")
            return
        tsv = h1_results_to_tsv(filtered)
        self.copy_text_to_clipboard(tsv)
        messagebox.showinfo("Copied", f"{len(filtered)} filtered H1 row(s) copied as TSV.")

    def export_h1_tsv(self):
        filtered = self.get_filtered_h1_results()
        if not filtered:
            messagebox.showwarning("No Results", "There are no H1 results to export.")
            return
        self.export_rows_tsv(filtered, h1_results_to_tsv, "Save Filtered H1 TSV")

    def export_h1_issues_tsv(self):
        issues = [r for r in self.get_filtered_h1_results() if r in self.get_h1_issue_rows()]
        if not issues:
            messagebox.showwarning("No Issues", "There are no H1 issue rows to export.")
            return
        self.export_rows_tsv(issues, h1_results_to_tsv, "Save H1 Issues TSV")

    def clear_h1_urls(self):
        if self.h1_running:
            return
        self.h1_url_text.delete("1.0", "end")

    def clear_h1_results(self):
        if self.h1_running:
            return
        self.h1_results = []
        self.refresh_h1_table()
        self.h1_log_text.delete("1.0", "end")
        self.h1_progressbar.set(0)
        self.h1_status_var.set("Ready")

    # =========================
    # SITEMAP PAGE
    # =========================
    def build_sitemap_page(self):
        self.domain_var = ctk.StringVar()
        self.sitemap_timeout_var = ctk.StringVar(value="15")
        self.sitemap_depth_var = ctk.StringVar(value="10")
        self.sitemap_filter_var = ctk.StringVar()
        self.allow_external_var = tk.BooleanVar(value=False)
        self.pages_only_var = tk.BooleanVar(value=True)
        self.sitemap_status_var = ctk.StringVar(value="Ready")

        outer = ctk.CTkScrollableFrame(self.sitemap_page, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        top = self.card(
            outer,
            "Sitemap Loader",
            "Load either an exact sitemap file or a domain. Pages Only excludes image/file asset URLs."
        )
        top.pack(fill="x", pady=(0, 14))

        row1 = ctk.CTkFrame(top, fg_color="transparent")
        row1.pack(fill="x", padx=18, pady=(0, 10))

        ctk.CTkLabel(row1, text="Domain URL", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.domain_entry = ctk.CTkEntry(row1, textvariable=self.domain_var)
        self.domain_entry.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.sitemap_run_btn = ctk.CTkButton(row1, text="Load Sitemaps", width=150, command=self.run_sitemap_loader)
        self.sitemap_run_btn.pack(side="left", padx=(0, 6))
        self.sitemap_cancel_btn = ctk.CTkButton(
            row1, text="Cancel", width=100,
            fg_color="#5B2323", hover_color="#7A2E2E",
            command=self.cancel_sitemap_loader
        )
        self.sitemap_cancel_btn.pack(side="left")

        row2 = ctk.CTkFrame(top, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=(0, 10))

        self.allow_external_checkbox = ctk.CTkCheckBox(row2, text="Allow external URLs", variable=self.allow_external_var)
        self.allow_external_checkbox.pack(side="left", padx=(0, 20))

        self.pages_only_checkbox = ctk.CTkCheckBox(row2, text="Pages Only", variable=self.pages_only_var)
        self.pages_only_checkbox.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(row2, text="Timeout", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.sitemap_timeout_entry = ctk.CTkEntry(row2, width=90, textvariable=self.sitemap_timeout_var)
        self.sitemap_timeout_entry.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(row2, text="Max Depth", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.sitemap_depth_entry = ctk.CTkEntry(row2, width=90, textvariable=self.sitemap_depth_var)
        self.sitemap_depth_entry.pack(side="left", padx=(0, 16))

        row3 = ctk.CTkFrame(top, fg_color="transparent")
        row3.pack(fill="x", padx=18, pady=(0, 18))

        ctk.CTkLabel(row3, text="Filter", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.sitemap_filter_entry = ctk.CTkEntry(row3, textvariable=self.sitemap_filter_var)
        self.sitemap_filter_entry.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.sitemap_send_h1_btn = ctk.CTkButton(row3, text="Send to H1", width=120, command=self.send_sitemap_urls_to_h1)
        self.sitemap_send_h1_btn.pack(side="left", padx=6)
        self.sitemap_send_meta_btn = ctk.CTkButton(row3, text="Send to Meta", width=120, command=self.send_sitemap_urls_to_meta)
        self.sitemap_send_meta_btn.pack(side="left", padx=6)

        helper = ctk.CTkLabel(
            top,
            text="Examples: paste https://example.com for discovery mode, or paste https://example.com/sitemap_index.xml for exact sitemap mode.",
            text_color=TEXT_SUB,
            font=ctk.CTkFont(size=12),
        )
        helper.pack(anchor="w", padx=18, pady=(0, 12))

        status_card = self.card(outer, "Status", "Current sitemap loading state.")
        status_card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(status_card, textvariable=self.sitemap_status_var, text_color="#D1D5DB").pack(anchor="w", padx=18, pady=(0, 18))

        summary_card = self.card(outer, "Summary", "Copy, export, or inspect the loaded sitemap result.")
        summary_card.pack(fill="x", pady=(0, 14))
        action_row = ctk.CTkFrame(summary_card, fg_color="transparent")
        action_row.pack(fill="x", padx=18, pady=(0, 10))
        self.sitemap_copy_btn = ctk.CTkButton(action_row, text="Copy URLs", width=120, command=self.copy_sitemap_urls)
        self.sitemap_copy_btn.pack(side="left", padx=6)
        self.sitemap_export_btn = ctk.CTkButton(action_row, text="Export URLs TXT", width=140, command=self.export_sitemap_urls)
        self.sitemap_export_btn.pack(side="left", padx=6)
        self.sitemap_clear_btn = ctk.CTkButton(
            action_row, text="Clear Output", width=130,
            fg_color=SOFT_BUTTON, hover_color=SOFT_BUTTON_HOVER,
            command=self.clear_sitemap_output
        )
        self.sitemap_clear_btn.pack(side="left", padx=6)

        self.summary_text = ctk.CTkTextbox(summary_card, height=160, corner_radius=12)
        self.summary_text.pack(fill="x", padx=18, pady=(0, 18))

        results_card = self.card(outer, "Sitemap Results", "Separate views for filtered page URLs, sitemap sources, logs, and skipped assets.")
        results_card.pack(fill="both", expand=True, pady=(0, 14))

        tabs = ctk.CTkTabview(
            results_card,
            segmented_button_fg_color="#111318",
            segmented_button_selected_color=BLUE
        )
        tabs.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        tabs.add("URLs")
        tabs.add("Sitemaps")
        tabs.add("Logs")
        tabs.add("Skipped Assets")

        self.urls_text = ctk.CTkTextbox(tabs.tab("URLs"), corner_radius=12)
        self.urls_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.sitemaps_text = ctk.CTkTextbox(tabs.tab("Sitemaps"), corner_radius=12)
        self.sitemaps_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.sitemap_logs_text = ctk.CTkTextbox(tabs.tab("Logs"), corner_radius=12)
        self.sitemap_logs_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.skipped_assets_text = ctk.CTkTextbox(tabs.tab("Skipped Assets"), corner_radius=12)
        self.skipped_assets_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.sitemap_busy_widgets = [
            self.sitemap_run_btn,
            self.sitemap_copy_btn,
            self.sitemap_export_btn,
            self.sitemap_clear_btn,
            self.sitemap_send_h1_btn,
            self.sitemap_send_meta_btn,
            self.domain_entry,
            self.sitemap_timeout_entry,
            self.sitemap_depth_entry,
            self.sitemap_filter_entry,
            self.allow_external_checkbox,
            self.pages_only_checkbox,
        ]

    def sitemap_log(self, message: str):
        self.sitemap_logs_text.insert("end", message + "\n")
        self.sitemap_logs_text.see("end")

    def set_sitemap_running_state(self, running: bool):
        self.sitemap_running = running
        self.set_widgets_state(self.sitemap_busy_widgets, "disabled" if running else "normal")
        self.sitemap_cancel_btn.configure(state="normal" if running else "disabled")

    def cancel_sitemap_loader(self):
        if self.sitemap_running:
            self.sitemap_cancel_event.set()
            self.sitemap_status_var.set("Cancelling...")

    def _sitemap_log_from_worker(self, message):
        self.sitemap_log(message)

    def _sitemap_complete_from_worker(self, result):
        self.sitemap_result = result
        self.render_sitemap_result()
        if result.get("cancelled"):
            self.sitemap_status_var.set(f"Cancelled - {len(self.sitemap_result.get('urls', []))} URL(s) loaded")
        else:
            self.sitemap_status_var.set(f"Done - {len(self.sitemap_result.get('urls', []))} URL(s) loaded")
        self.set_sitemap_running_state(False)
        self.refresh_dashboard_cards()

    def _sitemap_failed_from_worker(self, error_text):
        self.sitemap_status_var.set("Failed")
        self.sitemap_log(f"ERROR: {error_text}")
        self.set_sitemap_running_state(False)
        messagebox.showerror("Sitemap Error", error_text)

    def run_sitemap_loader(self):
        if self.sitemap_running:
            return

        domain = self.domain_var.get().strip()
        if not domain:
            messagebox.showwarning("Missing Domain", "Please enter a domain URL.")
            return

        try:
            timeout = int(self.sitemap_timeout_var.get().strip())
            max_depth = int(self.sitemap_depth_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Input", "Timeout and Max depth must be numbers.")
            return

        self.sitemap_cancel_event.clear()
        self.clear_sitemap_output(clear_state=False, force=True)
        self.sitemap_status_var.set("Loading sitemaps...")
        self.set_sitemap_running_state(True)

        def worker():
            try:
                result = load_sitemaps(
                    domain_url=domain,
                    timeout=timeout,
                    max_depth=max_depth,
                    allow_external_urls=self.allow_external_var.get(),
                    filter_text=self.sitemap_filter_var.get().strip(),
                    log_callback=lambda message: self.post_ui(self._sitemap_log_from_worker, message),
                    cancel_event=self.sitemap_cancel_event,
                    pages_only=self.pages_only_var.get(),
                )
                self.post_ui(self._sitemap_complete_from_worker, result)
            except Exception as exc:
                error_text = f"{exc}\n\n{traceback.format_exc()}"
                self.post_ui(self._sitemap_failed_from_worker, error_text)

        self.run_in_background(worker)

    def render_sitemap_result(self):
        if not self.sitemap_result:
            return

        summary_lines = [
            f"Input: {self.sitemap_result.get('domain_url', '')}",
            f"Input Mode: {self.sitemap_result.get('input_mode', '')}",
            f"Pages Only: {self.sitemap_result.get('pages_only', False)}",
            f"Robots.txt: {self.sitemap_result.get('robots_url', '')}",
            f"Robots-declared sitemaps: {len(self.sitemap_result.get('robots_sitemaps', []))}",
            f"Candidate sitemaps: {len(self.sitemap_result.get('candidates', []))}",
            f"Visited sitemaps: {len(self.sitemap_result.get('visited_sitemaps', []))}",
            f"URLSET sitemaps: {len(self.sitemap_result.get('urlset_sitemaps', []))}",
            f"Extracted Page URLs: {len(self.sitemap_result.get('urls', []))}",
            f"Skipped Asset URLs: {self.sitemap_result.get('skipped_asset_count', 0)}",
            f"Errors: {len(self.sitemap_result.get('errors', []))}",
            f"Cancelled: {self.sitemap_result.get('cancelled', False)}",
        ]
        self.summary_text.insert("1.0", "\n".join(summary_lines))
        self.urls_text.insert("1.0", "\n".join(self.sitemap_result.get("urls", [])))

        sitemap_lines = []
        sitemap_lines.append("=== ROBOTS SITEMAPS ===")
        sitemap_lines.extend(self.sitemap_result.get("robots_sitemaps", []))
        sitemap_lines.append("")
        sitemap_lines.append("=== VISITED SITEMAPS ===")
        sitemap_lines.extend(self.sitemap_result.get("visited_sitemaps", []))
        sitemap_lines.append("")
        sitemap_lines.append("=== URLSET SITEMAPS ===")
        sitemap_lines.extend(self.sitemap_result.get("urlset_sitemaps", []))
        sitemap_lines.append("")
        sitemap_lines.append("=== ERRORS ===")
        sitemap_lines.extend(self.sitemap_result.get("errors", []))

        self.sitemaps_text.insert("1.0", "\n".join(sitemap_lines))
        self.skipped_assets_text.insert("1.0", "\n".join(self.sitemap_result.get("skipped_asset_urls", [])))

    def copy_sitemap_urls(self):
        if not self.sitemap_result or not self.sitemap_result.get("urls"):
            messagebox.showwarning("No URLs", "No loaded URLs to copy.")
            return
        text = "\n".join(self.sitemap_result["urls"])
        self.copy_text_to_clipboard(text)
        messagebox.showinfo("Copied", f"{len(self.sitemap_result['urls'])} loaded URL(s) copied to clipboard.")

    def export_sitemap_urls(self):
        if not self.sitemap_result or not self.sitemap_result.get("urls"):
            messagebox.showwarning("No URLs", "No loaded URLs to export.")
            return
        file_path = filedialog.asksaveasfilename(
            title="Save URLs",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.sitemap_result["urls"]))
        messagebox.showinfo("Exported", f"Saved to:\n{file_path}")

    def send_sitemap_urls_to_h1(self):
        if self.sitemap_running:
            return
        if not self.sitemap_result or not self.sitemap_result.get("urls"):
            messagebox.showwarning("No URLs", "Load sitemaps first.")
            return
        self.set_text_lines(self.h1_url_text, self.sitemap_result["urls"])
        self.show_page("h1")
        messagebox.showinfo("Done", f"{len(self.sitemap_result['urls'])} loaded URL(s) were sent to H1 Audit.")

    def send_sitemap_urls_to_meta(self):
        if self.sitemap_running:
            return
        if not self.sitemap_result or not self.sitemap_result.get("urls"):
            messagebox.showwarning("No URLs", "Load sitemaps first.")
            return
        self.set_text_lines(self.meta_url_text, self.sitemap_result["urls"])
        self.show_page("meta")
        messagebox.showinfo("Done", f"{len(self.sitemap_result['urls'])} loaded URL(s) were sent to Meta Scraper.")

    def clear_sitemap_output(self, clear_state=True, force=False):
        if self.sitemap_running and not force:
            return
        self.summary_text.delete("1.0", "end")
        self.urls_text.delete("1.0", "end")
        self.sitemaps_text.delete("1.0", "end")
        self.sitemap_logs_text.delete("1.0", "end")
        self.skipped_assets_text.delete("1.0", "end")
        self.sitemap_status_var.set("Ready")
        if clear_state:
            self.sitemap_result = None
            self.refresh_dashboard_cards()

    # =========================
    # META PAGE
    # =========================
    def build_meta_page(self):
        self.meta_timeout_var = ctk.StringVar(value="15")
        self.meta_delay_var = ctk.StringVar(value="0")
        self.meta_filter_var = ctk.StringVar(value="All")
        self.meta_search_var = ctk.StringVar(value="")
        self.meta_status_var = ctk.StringVar(value="Ready")

        outer = ctk.CTkScrollableFrame(self.meta_page, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        top = self.card(
            outer,
            "Manual URL Input",
            "Paste URLs directly or import a TXT/CSV file for metadata auditing."
        )
        top.pack(fill="x", pady=(0, 14))

        controls = ctk.CTkFrame(top, fg_color="transparent")
        controls.pack(fill="x", padx=18, pady=(0, 10))

        ctk.CTkLabel(controls, text="Timeout", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.meta_timeout_entry = ctk.CTkEntry(controls, width=90, textvariable=self.meta_timeout_var)
        self.meta_timeout_entry.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(controls, text="Delay", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.meta_delay_entry = ctk.CTkEntry(controls, width=90, textvariable=self.meta_delay_var)
        self.meta_delay_entry.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(controls, text="Filter", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.meta_filter_menu = ctk.CTkOptionMenu(
            controls,
            values=["All", "Only Missing Meta", "Only Title Issues", "Only Meta Issues", "Only Any Issues"],
            variable=self.meta_filter_var,
            width=180,
            command=lambda _: self.refresh_meta_table(),
        )
        self.meta_filter_menu.pack(side="left", padx=(0, 16))

        self.meta_run_btn = ctk.CTkButton(controls, text="Run Meta Audit", width=150, command=self.run_meta_audit)
        self.meta_run_btn.pack(side="left", padx=6)

        self.meta_cancel_btn = ctk.CTkButton(
            controls, text="Cancel", width=100,
            fg_color="#5B2323", hover_color="#7A2E2E",
            command=self.cancel_meta_audit
        )
        self.meta_cancel_btn.pack(side="left", padx=6)

        self.meta_import_replace_btn = ctk.CTkButton(controls, text="Import (Replace)", width=130, command=self.import_meta_urls_replace)
        self.meta_import_replace_btn.pack(side="left", padx=6)

        self.meta_import_append_btn = ctk.CTkButton(controls, text="Import (Append)", width=130, command=self.import_meta_urls_append)
        self.meta_import_append_btn.pack(side="left", padx=6)

        self.meta_clear_urls_btn = ctk.CTkButton(
            controls, text="Clear URLs", width=110,
            fg_color=SOFT_BUTTON, hover_color=SOFT_BUTTON_HOVER,
            command=self.clear_meta_urls
        )
        self.meta_clear_urls_btn.pack(side="left", padx=6)

        helper = ctk.CTkLabel(
            top,
            text="Tip: Search results below. Double-click row to copy URL. Right-click row for actions.",
            text_color=TEXT_SUB,
            font=ctk.CTkFont(size=12),
        )
        helper.pack(anchor="w", padx=18, pady=(0, 8))

        self.meta_url_text = ctk.CTkTextbox(top, height=180, corner_radius=12)
        self.meta_url_text.pack(fill="x", padx=18, pady=(0, 18))

        stats = ctk.CTkFrame(outer, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 14))
        self.meta_stat_wrap = stats
        self.make_stat_card(stats, "Total", 0, BLUE)
        self.make_stat_card(stats, "OK", 0, GREEN)
        self.make_stat_card(stats, "Missing Title", 0, ORANGE)
        self.make_stat_card(stats, "Missing Meta", 0, YELLOW)
        self.make_stat_card(stats, "Errors", 0, RED)
        self.make_stat_card(stats, "Issue Rows", 0, PURPLE)

        action_card = self.card(outer, "Actions", "Copy, export, search, or isolate issue rows.")
        action_card.pack(fill="x", pady=(0, 14))

        search_row = ctk.CTkFrame(action_card, fg_color="transparent")
        search_row.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkLabel(search_row, text="Search", text_color=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.meta_search_entry = ctk.CTkEntry(search_row, textvariable=self.meta_search_var)
        self.meta_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.meta_search_entry.bind("<KeyRelease>", lambda event: self.refresh_meta_table())
        ctk.CTkButton(
            search_row, text="Clear Search", width=120,
            fg_color=SOFT_BUTTON, hover_color=SOFT_BUTTON_HOVER,
            command=self.clear_meta_search
        ).pack(side="left")

        action_row = ctk.CTkFrame(action_card, fg_color="transparent")
        action_row.pack(fill="x", padx=18, pady=(0, 18))

        self.meta_copy_btn = ctk.CTkButton(action_row, text="Copy Filtered TSV", width=150, command=self.copy_meta_results)
        self.meta_copy_btn.pack(side="left", padx=6)

        self.meta_copy_selected_btn = ctk.CTkButton(action_row, text="Copy Selected", width=130, command=self.copy_selected_meta_rows)
        self.meta_copy_selected_btn.pack(side="left", padx=6)

        self.meta_copy_issues_btn = ctk.CTkButton(action_row, text="Copy Issues Only", width=140, command=self.copy_meta_issues_rows)
        self.meta_copy_issues_btn.pack(side="left", padx=6)

        self.meta_export_btn = ctk.CTkButton(action_row, text="Export Filtered", width=130, command=self.export_meta_tsv)
        self.meta_export_btn.pack(side="left", padx=6)

        self.meta_export_selected_btn = ctk.CTkButton(action_row, text="Export Selected", width=130, command=self.export_selected_meta_rows)
        self.meta_export_selected_btn.pack(side="left", padx=6)

        self.meta_export_issues_btn = ctk.CTkButton(action_row, text="Export Issues", width=130, command=self.export_meta_issues_tsv)
        self.meta_export_issues_btn.pack(side="left", padx=6)

        self.meta_clear_results_btn = ctk.CTkButton(
            action_row, text="Clear Results", width=130,
            fg_color=SOFT_BUTTON, hover_color=SOFT_BUTTON_HOVER,
            command=self.clear_meta_results
        )
        self.meta_clear_results_btn.pack(side="left", padx=6)

        progress_card = self.card(outer, "Progress", "Audit progress and current processing state.")
        progress_card.pack(fill="x", pady=(0, 14))
        p_row = ctk.CTkFrame(progress_card, fg_color="transparent")
        p_row.pack(fill="x", padx=18, pady=(0, 18))
        self.meta_progressbar = ctk.CTkProgressBar(p_row, progress_color=GREEN)
        self.meta_progressbar.set(0)
        self.meta_progressbar.pack(side="left", fill="x", expand=True, padx=(0, 14))
        self.meta_status_label = ctk.CTkLabel(p_row, textvariable=self.meta_status_var, text_color="#D1D5DB")
        self.meta_status_label.pack(side="left")

        results_card = self.card(outer, "Meta Results", "Detailed output from the metadata audit module.")
        results_card.pack(fill="both", expand=True, pady=(0, 14))

        tree_wrap = ctk.CTkFrame(results_card, fg_color="transparent")
        tree_wrap.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        self.meta_columns = (
            "url", "status", "status_code", "title", "title_length", "title_status",
            "meta_description", "meta_length", "meta_status",
            "recommended_title", "recommended_meta_description",
            "priority", "action_needed", "error"
        )

        self.meta_tree = ttk.Treeview(tree_wrap, columns=self.meta_columns, show="headings", selectmode="extended")

        headings = {
            "url": "URL",
            "status": "Status",
            "status_code": "Code",
            "title": "Title",
            "title_length": "Title Length",
            "title_status": "Title Status",
            "meta_description": "Meta Description",
            "meta_length": "Meta Length",
            "meta_status": "Meta Status",
            "recommended_title": "Recommended Title",
            "recommended_meta_description": "Recommended Meta Description",
            "priority": "Priority",
            "action_needed": "Action Needed",
            "error": "Error",
        }

        widths = {
            "url": 210,
            "status": 80,
            "status_code": 70,
            "title": 170,
            "title_length": 95,
            "title_status": 120,
            "meta_description": 220,
            "meta_length": 95,
            "meta_status": 130,
            "recommended_title": 170,
            "recommended_meta_description": 220,
            "priority": 90,
            "action_needed": 210,
            "error": 150,
        }

        for col in self.meta_columns:
            self.meta_tree.heading(
                col,
                text=headings[col],
                command=lambda c=col: self.sort_treeview(self.meta_tree, c, self.meta_results, self.refresh_meta_table, self.meta_sort_state)
            )
            self.meta_tree.column(col, width=widths[col], anchor="w")

        meta_scroll_y = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.meta_tree.yview)
        meta_scroll_x = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.meta_tree.xview)
        self.meta_tree.configure(yscrollcommand=meta_scroll_y.set, xscrollcommand=meta_scroll_x.set)

        self.meta_tree.pack(side="top", fill="both", expand=True)
        meta_scroll_y.pack(side="right", fill="y")
        meta_scroll_x.pack(side="bottom", fill="x")
        self.apply_tree_tags(self.meta_tree)
        self.meta_tree.bind("<Double-1>", lambda event: self.on_tree_double_click_copy(self.meta_tree))
        self.meta_tree.bind("<Button-3>", lambda event: self.show_tree_menu(event, self.meta_tree, self.meta_menu))

        logs_card = self.card(outer, "Logs", "Runtime log messages from the metadata audit.")
        logs_card.pack(fill="x", pady=(0, 20))
        self.meta_log_text = ctk.CTkTextbox(logs_card, height=120, corner_radius=12)
        self.meta_log_text.pack(fill="x", padx=18, pady=(0, 18))

        self.meta_busy_widgets = [
            self.meta_run_btn,
            self.meta_import_replace_btn,
            self.meta_import_append_btn,
            self.meta_clear_urls_btn,
            self.meta_copy_btn,
            self.meta_copy_selected_btn,
            self.meta_copy_issues_btn,
            self.meta_export_btn,
            self.meta_export_selected_btn,
            self.meta_export_issues_btn,
            self.meta_clear_results_btn,
            self.meta_filter_menu,
            self.meta_timeout_entry,
            self.meta_delay_entry,
        ]

    def import_meta_urls_replace(self):
        file_path = self.ask_open_urls_file()
        urls = self.read_urls_from_file(file_path)
        if not urls:
            return
        self.set_text_lines(self.meta_url_text, urls)
        messagebox.showinfo("Imported", f"{len(urls)} URL(s) imported into Meta input.")

    def import_meta_urls_append(self):
        file_path = self.ask_open_urls_file()
        urls = self.read_urls_from_file(file_path)
        if not urls:
            return
        before = len(self.get_text_lines(self.meta_url_text))
        self.append_text_lines(self.meta_url_text, urls)
        after = len(self.get_text_lines(self.meta_url_text))
        messagebox.showinfo("Imported", f"{after - before} new URL(s) appended to Meta input.")

    def meta_log(self, message: str):
        self.meta_log_text.insert("end", message + "\n")
        self.meta_log_text.see("end")

    def get_meta_urls(self):
        return self.get_text_lines(self.meta_url_text)

    def set_meta_progress(self, current: int, total: int, result: dict):
        percent = 0 if total == 0 else (current / total)
        self.meta_progressbar.set(percent)
        self.meta_status_var.set(f"Processed {current}/{total}")

    def meta_row_tag(self, row):
        status = str(row.get("status", "")).upper()
        title_status = str(row.get("title_status", ""))
        meta_status = str(row.get("meta_status", ""))
        if status in {"FETCH_FAILED", "TIMEOUT", "REDIRECT_ERROR", "INVALID", "NON_HTML"}:
            return "error"
        if title_status == "Missing Title" or meta_status == "Missing Meta Description":
            return "error"
        if title_status in {"Title Too Short", "Title Too Long"} or meta_status in {"Meta Too Short", "Meta Too Long"}:
            return "warn"
        return "ok"

    def get_meta_issue_rows(self):
        return [
            r for r in self.meta_results
            if str(r.get("status", "")).upper() in {"FETCH_FAILED", "TIMEOUT", "REDIRECT_ERROR", "INVALID", "NON_HTML"}
            or r.get("title_status") in {"Missing Title", "Title Too Short", "Title Too Long"}
            or r.get("meta_status") in {"Missing Meta Description", "Meta Too Short", "Meta Too Long"}
        ]

    def get_filtered_meta_results(self):
        mode = self.meta_filter_var.get()
        if mode == "Only Missing Meta":
            rows = [r for r in self.meta_results if r.get("meta_status") == "Missing Meta Description"]
        elif mode == "Only Title Issues":
            rows = [r for r in self.meta_results if r.get("title_status") in {"Missing Title", "Title Too Short", "Title Too Long"}]
        elif mode == "Only Meta Issues":
            rows = [r for r in self.meta_results if r.get("meta_status") in {"Missing Meta Description", "Meta Too Short", "Meta Too Long"}]
        elif mode == "Only Any Issues":
            rows = self.get_meta_issue_rows()
        else:
            rows = self.meta_results

        return [r for r in rows if self.row_matches_search(r, self.meta_search_var.get().strip())]

    def update_meta_stats(self):
        total = len(self.meta_results)
        ok = sum(1 for r in self.meta_results if str(r.get("status", "")).upper() == "OK" and r.get("title_status") == "OK" and r.get("meta_status") == "OK")
        missing_title = sum(1 for r in self.meta_results if r.get("title_status") == "Missing Title")
        missing_meta = sum(1 for r in self.meta_results if r.get("meta_status") == "Missing Meta Description")
        errors = sum(1 for r in self.meta_results if str(r.get("status", "")).upper() in {"FETCH_FAILED", "TIMEOUT", "REDIRECT_ERROR", "INVALID", "NON_HTML"})
        issues = len(self.get_meta_issue_rows())

        for widget in self.meta_stat_wrap.winfo_children():
            widget.destroy()

        self.make_stat_card(self.meta_stat_wrap, "Total", total, BLUE)
        self.make_stat_card(self.meta_stat_wrap, "OK", ok, GREEN)
        self.make_stat_card(self.meta_stat_wrap, "Missing Title", missing_title, ORANGE)
        self.make_stat_card(self.meta_stat_wrap, "Missing Meta", missing_meta, YELLOW)
        self.make_stat_card(self.meta_stat_wrap, "Errors", errors, RED)
        self.make_stat_card(self.meta_stat_wrap, "Issue Rows", issues, PURPLE)

    def refresh_meta_table(self):
        self.tree_clear(self.meta_tree)
        for row in self.get_filtered_meta_results():
            self.meta_tree.insert(
                "",
                "end",
                values=(
                    row.get("url", ""), row.get("status", ""), row.get("status_code", ""),
                    row.get("title", ""), row.get("title_length", ""), row.get("title_status", ""),
                    row.get("meta_description", ""), row.get("meta_length", ""), row.get("meta_status", ""),
                    row.get("recommended_title", ""), row.get("recommended_meta_description", ""),
                    row.get("priority", ""), row.get("action_needed", ""), row.get("error", ""),
                ),
                tags=(self.meta_row_tag(row),),
            )
        self.update_meta_stats()
        self.refresh_dashboard_cards()

    def clear_meta_search(self):
        self.meta_search_var.set("")
        self.refresh_meta_table()

    def copy_selected_meta_rows(self):
        rows = self.get_selected_tree_rows(self.meta_tree, self.get_filtered_meta_results())
        if not rows:
            messagebox.showwarning("No Rows Selected", "Select one or more Meta rows first.")
            return
        self.copy_text_to_clipboard(meta_results_to_tsv(rows))
        messagebox.showinfo("Copied", f"{len(rows)} selected Meta row(s) copied as TSV.")

    def copy_meta_issues_rows(self):
        rows = [r for r in self.get_filtered_meta_results() if r in self.get_meta_issue_rows()]
        if not rows:
            messagebox.showwarning("No Issues", "No issue rows available in the current Meta view.")
            return
        self.copy_text_to_clipboard(meta_results_to_tsv(rows))
        messagebox.showinfo("Copied", f"{len(rows)} Meta issue row(s) copied as TSV.")

    def export_selected_meta_rows(self):
        rows = self.get_selected_tree_rows(self.meta_tree, self.get_filtered_meta_results())
        if not rows:
            messagebox.showwarning("No Rows Selected", "Select one or more Meta rows first.")
            return
        self.export_rows_tsv(rows, meta_results_to_tsv, "Save Selected Meta TSV")

    def set_meta_running_state(self, running: bool):
        self.meta_running = running
        self.set_widgets_state(self.meta_busy_widgets, "disabled" if running else "normal")
        self.meta_cancel_btn.configure(state="normal" if running else "disabled")

    def cancel_meta_audit(self):
        if self.meta_running:
            self.meta_cancel_event.set()
            self.meta_status_var.set("Cancelling...")

    def _meta_progress_from_worker(self, current, total, result):
        self.set_meta_progress(current, total, result)

    def _meta_log_from_worker(self, message):
        self.meta_log(message)

    def _meta_complete_from_worker(self, results):
        self.meta_results = results
        self.refresh_meta_table()
        if self.meta_cancel_event.is_set():
            self.meta_status_var.set(f"Cancelled - {len(self.meta_results)} URL(s) processed")
            self.meta_log("Meta audit cancelled.")
        else:
            self.meta_status_var.set(f"Done - {len(self.meta_results)} URL(s) audited")
            self.meta_log("Meta audit completed.")
        self.set_meta_running_state(False)

    def _meta_failed_from_worker(self, error_text):
        self.meta_status_var.set("Failed")
        self.meta_log(f"ERROR: {error_text}")
        self.set_meta_running_state(False)
        messagebox.showerror("Meta Audit Error", error_text)

    def run_meta_audit(self):
        if self.meta_running:
            return

        urls = self.get_meta_urls()
        if not urls:
            messagebox.showwarning("No URLs", "Please paste or import at least one URL.")
            return

        try:
            timeout = int(self.meta_timeout_var.get().strip())
            delay_ms = int(self.meta_delay_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Input", "Timeout and Delay must be numbers.")
            return

        self.meta_cancel_event.clear()
        self.meta_results = []
        self.refresh_meta_table()
        self.meta_log_text.delete("1.0", "end")
        self.meta_progressbar.set(0)
        self.meta_status_var.set("Running...")
        self.set_meta_running_state(True)

        def worker():
            try:
                results = audit_meta_urls(
                    urls=urls,
                    timeout=timeout,
                    delay_ms=delay_ms,
                    progress_callback=lambda current, total, result: self.post_ui(
                        self._meta_progress_from_worker, current, total, result
                    ),
                    log_callback=lambda message: self.post_ui(self._meta_log_from_worker, message),
                    cancel_event=self.meta_cancel_event,
                )
                self.post_ui(self._meta_complete_from_worker, results)
            except Exception as exc:
                error_text = f"{exc}\n\n{traceback.format_exc()}"
                self.post_ui(self._meta_failed_from_worker, error_text)

        self.run_in_background(worker)

    def copy_meta_results(self):
        filtered = self.get_filtered_meta_results()
        if not filtered:
            messagebox.showwarning("No Results", "There are no meta results to copy.")
            return
        tsv = meta_results_to_tsv(filtered)
        self.copy_text_to_clipboard(tsv)
        messagebox.showinfo("Copied", f"{len(filtered)} filtered Meta row(s) copied as TSV.")

    def export_meta_tsv(self):
        filtered = self.get_filtered_meta_results()
        if not filtered:
            messagebox.showwarning("No Results", "There are no meta results to export.")
            return
        self.export_rows_tsv(filtered, meta_results_to_tsv, "Save Filtered Meta TSV")

    def export_meta_issues_tsv(self):
        issues = [r for r in self.get_filtered_meta_results() if r in self.get_meta_issue_rows()]
        if not issues:
            messagebox.showwarning("No Issues", "There are no Meta issue rows to export.")
            return
        self.export_rows_tsv(issues, meta_results_to_tsv, "Save Meta Issues TSV")

    def clear_meta_urls(self):
        if self.meta_running:
            return
        self.meta_url_text.delete("1.0", "end")

    def clear_meta_results(self):
        if self.meta_running:
            return
        self.meta_results = []
        self.refresh_meta_table()
        self.meta_log_text.delete("1.0", "end")
        self.meta_progressbar.set(0)
        self.meta_status_var.set("Ready")


def set_app_icon(root):
    icon_path = "maptive.ico"
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass


def main():
    root = ctk.CTk()
    # set_app_icon(root)
    app = MaptiveDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()