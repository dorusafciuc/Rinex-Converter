# -*- coding: utf-8 -*-
"""
RINEX Hot Folder Converter (GFZRNX) - POSPac
- RINEX 3 (.rnx) -> RINEX 2 (.obs) cu GFZRNX
- Hot folder + Drag&Drop
- ZIP + ZIP in ZIP (recursiv)
- Fara fereastra CMD la rularea GFZRNX (Windows)
"""

import os
import sys
import time
import shutil
import queue
import threading
import subprocess
import traceback
import zipfile
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# Drag&Drop
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:
    HAS_DND = False
    DND_FILES = None
    TkinterDnD = None

# Hot folder watcher
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


APP_TITLE = "RINEX Hot Folder Converter (GFZRNX) - POSPac"
DEFAULT_GFZ_NAME = "gfzrnx_2.2.0_win11_64.exe"

INBOX_DIRNAME = "INBOX_DROP"
OUTBOX_DIRNAME = "OUTBOX_CONVERTED"
PROCESSED_DIRNAME = "PROCESSED"
ERRORS_DIRNAME = "ERRORS"
LOGS_DIRNAME = "LOGS"
EXTRACTED_DIRNAME = "_EXTRACTED"


def get_app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def safe_makedirs(path):
    os.makedirs(path, exist_ok=True)


def timestamp_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_rnx_file(path: str):
    return os.path.isfile(path) and path.lower().endswith(".rnx")


def is_zip_archive(path: str):
    return os.path.isfile(path) and path.lower().endswith(".zip")


def is_mo_rnx_file(path: str):
    # Filtru recomandat pentru POSPac (fisier observatii)
    # Exemple: ..._MO.rnx, ..._0x_MO.rnx
    return is_rnx_file(path) and os.path.basename(path).lower().endswith("_mo.rnx")


def parse_dropped_paths(root_widget, raw_data: str):
    try:
        return [p for p in root_widget.tk.splitlist(raw_data) if p]
    except Exception:
        return [raw_data] if raw_data else []


class InboxEventHandler(FileSystemEventHandler):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def on_created(self, event):
        if not event.is_directory:
            self.app.on_inbox_file_seen(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.app.on_inbox_file_seen(event.dest_path)


class RinexHotFolderApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1080x800")
        self.root.minsize(960, 680)

        # Foldere aplicatie (langa .py / .exe)
        self.base_dir = get_app_base_dir()
        self.inbox_dir = os.path.join(self.base_dir, INBOX_DIRNAME)
        self.outbox_dir = os.path.join(self.base_dir, OUTBOX_DIRNAME)
        self.processed_dir = os.path.join(self.base_dir, PROCESSED_DIRNAME)
        self.errors_dir = os.path.join(self.base_dir, ERRORS_DIRNAME)
        self.logs_dir = os.path.join(self.base_dir, LOGS_DIRNAME)
        self.extracted_root_dir = os.path.join(self.inbox_dir, EXTRACTED_DIRNAME)

        for p in [self.inbox_dir, self.outbox_dir, self.processed_dir, self.errors_dir, self.logs_dir, self.extracted_root_dir]:
            safe_makedirs(p)

        # UI vars
        self.gfzrnx_path_var = tk.StringVar()
        self.satsys_var = tk.StringVar(value="GR")
        self.auto_watch_var = tk.BooleanVar(value=True)
        self.move_processed_var = tk.BooleanVar(value=True)
        self.overwrite_var = tk.BooleanVar(value=True)
        self.only_mo_var = tk.BooleanVar(value=True)  # recomandat POSPac
        self.status_var = tk.StringVar(value="Pregătit.")
        self.queue_count_var = tk.StringVar(value="0 în lucru/coadă")

        # Threading / queue
        self.ui_queue = queue.Queue()
        self.work_queue = queue.Queue()
        self.queued_set = set()
        self.processing_set = set()
        self.stop_worker = False
        self.observer = None

        self._build_ui()
        self._init_defaults()

        self._start_worker_thread()
        self._start_watchdog_if_enabled()
        self._poll_ui_queue()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ==========================================================
    # UI
    # ==========================================================
    def _build_ui(self):
        pad = 8
        main = ttk.Frame(self.root, padding=pad)
        main.pack(fill="both", expand=True)

        cfg = ttk.LabelFrame(main, text="Setări aplicație", padding=pad)
        cfg.pack(fill="x", pady=(0, pad))

        ttk.Label(cfg, text="Folder aplicație:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        self.base_dir_entry = ttk.Entry(cfg)
        self.base_dir_entry.grid(row=0, column=1, columnspan=4, sticky="ew", pady=4)
        self.base_dir_entry.insert(0, self.base_dir)
        self.base_dir_entry.configure(state="readonly")

        ttk.Label(cfg, text="GFZRNX exe:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(cfg, textvariable=self.gfzrnx_path_var).grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)
        ttk.Button(cfg, text="Browse...", command=self.browse_gfzrnx).grid(row=1, column=4, sticky="ew", padx=(6, 0), pady=4)

        ttk.Label(cfg, text="SatSys (GFZRNX -satsys):").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(cfg, textvariable=self.satsys_var, width=10).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Checkbutton(cfg, text="Auto monitorizare INBOX_DROP", variable=self.auto_watch_var,
                        command=self.toggle_watchdog).grid(row=2, column=2, sticky="w", pady=4)
        ttk.Checkbutton(cfg, text="Mută sursa în PROCESSED la succes", variable=self.move_processed_var)\
            .grid(row=2, column=3, columnspan=2, sticky="w", pady=4)

        ttk.Label(cfg, text="Hot folder (INBOX_DROP):").grid(row=3, column=0, sticky="w", padx=(0, 6), pady=4)
        self.inbox_entry = ttk.Entry(cfg)
        self.inbox_entry.grid(row=3, column=1, sticky="ew", pady=4)
        self.inbox_entry.insert(0, self.inbox_dir)
        self.inbox_entry.configure(state="readonly")

        ttk.Checkbutton(cfg, text="Suprascrie output (-f)", variable=self.overwrite_var)\
            .grid(row=3, column=2, sticky="w", pady=4)
        ttk.Checkbutton(cfg, text="Doar fișiere observații *_MO.rnx (recomandat POSPac)", variable=self.only_mo_var)\
            .grid(row=3, column=3, columnspan=2, sticky="w", pady=4)

        cfg.columnconfigure(1, weight=1)
        cfg.columnconfigure(2, weight=1)
        cfg.columnconfigure(3, weight=1)

        # Foldere locale
        folders = ttk.LabelFrame(main, text="Foldere locale", padding=pad)
        folders.pack(fill="x", pady=(0, pad))

        ttk.Button(folders, text="Deschide INBOX_DROP", command=lambda: self.open_folder(self.inbox_dir)).pack(side="left")
        ttk.Button(folders, text="Deschide OUTBOX_CONVERTED", command=lambda: self.open_folder(self.outbox_dir)).pack(side="left", padx=(6, 0))
        ttk.Button(folders, text="Deschide PROCESSED", command=lambda: self.open_folder(self.processed_dir)).pack(side="left", padx=(6, 0))
        ttk.Button(folders, text="Deschide ERRORS", command=lambda: self.open_folder(self.errors_dir)).pack(side="left", padx=(6, 0))
        ttk.Button(folders, text="Deschide LOGS", command=lambda: self.open_folder(self.logs_dir)).pack(side="left", padx=(6, 0))

        # Coada
        qf = ttk.LabelFrame(main, text="Coadă conversie (drag & drop + scan folder)", padding=pad)
        qf.pack(fill="both", expand=True, pady=(0, pad))

        q_top = ttk.Frame(qf)
        q_top.pack(fill="x", pady=(0, 6))

        ttk.Button(q_top, text="Adaugă fișiere...", command=self.add_files_dialog).pack(side="left")
        ttk.Button(q_top, text="Scanează INBOX acum", command=self.scan_inbox_now).pack(side="left", padx=(6, 0))
        ttk.Button(q_top, text="Șterge selectate din coadă", command=self.remove_selected_queue_items).pack(side="left", padx=(6, 0))
        ttk.Button(q_top, text="Golește coada", command=self.clear_queue_view_only).pack(side="left", padx=(6, 0))
        ttk.Label(q_top, textvariable=self.queue_count_var).pack(side="right")

        list_wrap = ttk.Frame(qf)
        list_wrap.pack(fill="both", expand=True)

        self.queue_list = tk.Listbox(list_wrap, selectmode=tk.EXTENDED)
        self.queue_list.pack(side="left", fill="both", expand=True)

        yscroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.queue_list.yview)
        yscroll.pack(side="right", fill="y")
        self.queue_list.configure(yscrollcommand=yscroll.set)

        self.drop_label = ttk.Label(
            qf,
            text=("Trage aici fișiere .rnx / .zip sau foldere (drag & drop)"
                  if HAS_DND else
                  "Drag & drop indisponibil (tkinterdnd2 nu este disponibil)"),
            relief="groove",
            anchor="center"
        )
        self.drop_label.pack(fill="x", pady=(6, 0), ipady=10)

        if HAS_DND:
            for w in (self.drop_label, self.queue_list):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self.on_drop)

        # Procesare
        runf = ttk.LabelFrame(main, text="Procesare", padding=pad)
        runf.pack(fill="x", pady=(0, pad))

        self.progress = ttk.Progressbar(runf, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 8))

        run_top = ttk.Frame(runf)
        run_top.pack(fill="x")
        ttk.Button(run_top, text="Procesează coada acum", command=self.kick_worker_hint).pack(side="left")
        ttk.Button(run_top, text="Testează GFZRNX", command=self.test_gfzrnx).pack(side="left", padx=(6, 0))
        ttk.Label(run_top, textvariable=self.status_var).pack(side="right")

        # Log
        logf = ttk.LabelFrame(main, text="Log", padding=pad)
        logf.pack(fill="both", expand=True)

        self.log_text = ScrolledText(logf, height=14, wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _init_defaults(self):
        preferred = os.path.join(self.base_dir, DEFAULT_GFZ_NAME)
        if os.path.isfile(preferred):
            self.gfzrnx_path_var.set(preferred)
        else:
            try:
                exes = [f for f in os.listdir(self.base_dir) if f.lower().startswith("gfzrnx") and f.lower().endswith(".exe")]
                if exes:
                    self.gfzrnx_path_var.set(os.path.join(self.base_dir, exes[0]))
            except Exception:
                pass

        self._ui_log(f"Folder aplicație: {self.base_dir}")
        self._ui_log(f"INBOX_DROP: {self.inbox_dir}")
        self._ui_log(f"OUTBOX_CONVERTED: {self.outbox_dir}")
        self._ui_log(f"ERRORS: {self.errors_dir}")
        self._ui_log(f"LOGS: {self.logs_dir}")
        self._ui_log(f"PROCESSED: {self.processed_dir}")
        self._ui_log(f"EXTRACTED temp: {self.extracted_root_dir}")

    # ==========================================================
    # Logging
    # ==========================================================
    def _log_file_path(self):
        safe_makedirs(self.logs_dir)
        return os.path.join(self.logs_dir, datetime.now().strftime("%Y-%m-%d") + ".log")

    def _write_log_file(self, line):
        try:
            with open(self._log_file_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _ui_log(self, msg):
        line = f"[{timestamp_str()}] {msg}"
        self._write_log_file(line)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def enqueue_ui(self, kind, payload=None):
        self.ui_queue.put((kind, payload))

    def _poll_ui_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "log":
                    self._ui_log(payload)
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "queue_refresh":
                    self.refresh_queue_list()
                elif kind == "progress_start":
                    self.progress.start(10)
                elif kind == "progress_stop":
                    self.progress.stop()
                elif kind == "error_dialog":
                    messagebox.showerror("Eroare", payload)
                elif kind == "info_dialog":
                    messagebox.showinfo("Info", payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_ui_queue)

    # ==========================================================
    # Helpers queue / file
    # ==========================================================
    def normp(self, path):
        return os.path.normcase(os.path.abspath(path))

    def queue_count(self):
        return self.work_queue.qsize() + len(self.processing_set)

    def refresh_queue_list(self):
        self.queue_list.delete(0, "end")
        for p in sorted(self.queued_set):
            self.queue_list.insert("end", p)
        self.queue_count_var.set(f"{self.queue_count()} în lucru/coadă")

    def rnx_passes_current_filter(self, path):
        if not is_rnx_file(path):
            return False
        if self.only_mo_var.get():
            return is_mo_rnx_file(path)
        return True

    def add_to_queue(self, file_path, source_tag="manual"):
        if not is_rnx_file(file_path):
            return False, "Nu este fișier .rnx"

        if not self.rnx_passes_current_filter(file_path):
            return False, "Filtrat (nu e *_MO.rnx)"

        npath = self.normp(file_path)
        if not os.path.exists(npath):
            return False, "Fișierul nu există"

        if npath in self.queued_set or npath in self.processing_set:
            return False, "Deja în coadă/procesare"

        self.queued_set.add(npath)
        self.work_queue.put((npath, source_tag))
        self.enqueue_ui("queue_refresh")
        self.enqueue_ui("log", f"➕ În coadă [{source_tag}]: {npath}")
        return True, "Adăugat"

    def add_files_dialog(self):
        paths = filedialog.askopenfilenames(
            title="Selectează fișiere RINEX/ZIP",
            filetypes=[("RINEX/ZIP", "*.rnx *.zip"), ("RINEX", "*.rnx"), ("ZIP", "*.zip"), ("Toate fișierele", "*.*")]
        )
        if not paths:
            return

        added = 0
        zips = 0
        skipped = 0

        for p in paths:
            if is_rnx_file(p):
                ok, _ = self.add_to_queue(p, source_tag="DIALOG")
                if ok:
                    added += 1
                else:
                    skipped += 1
            elif is_zip_archive(p):
                zips += 1
                self.extract_zip_and_queue(p, source_tag="DIALOG")

        self.enqueue_ui("log", f"📥 Dialog: .rnx adăugate {added}, ignorate {skipped}, ZIP procesate {zips}")

    def remove_selected_queue_items(self):
        sel = list(self.queue_list.curselection())
        if not sel:
            return
        items = [self.queue_list.get(i) for i in sel]
        removed = 0
        for p in items:
            np = self.normp(p)
            if np in self.queued_set:
                self.queued_set.remove(np)
                removed += 1
        self.refresh_queue_list()
        self.enqueue_ui("log", f"🗑️ Scoase din coadă: {removed}")

    def clear_queue_view_only(self):
        count = len(self.queued_set)
        self.queued_set.clear()
        self.refresh_queue_list()
        self.enqueue_ui("log", f"🧹 Coada a fost golită (logic): {count}")

    def kick_worker_hint(self):
        self.enqueue_ui("log", "▶️ Worker activ; procesează automat coada existentă.")

    def open_folder(self, folder):
        safe_makedirs(folder)
        try:
            os.startfile(folder)
        except Exception as e:
            messagebox.showerror("Eroare", f"Nu pot deschide folderul:\n{e}")

    # ==========================================================
    # Scan / watch / drag&drop
    # ==========================================================
    def scan_inbox_now(self):
        count_rnx = 0
        count_zip = 0
        skipped_filter = 0

        try:
            for name in os.listdir(self.inbox_dir):
                fp = os.path.join(self.inbox_dir, name)
                if os.path.isdir(fp):
                    continue  # ignoram subfoldere (ex: _EXTRACTED)

                if is_rnx_file(fp):
                    ok, msg = self.add_to_queue(fp, source_tag="INBOX_SCAN")
                    if ok:
                        count_rnx += 1
                    elif "Filtrat" in msg:
                        skipped_filter += 1
                elif is_zip_archive(fp):
                    count_zip += 1
                    self.extract_zip_and_queue(fp, source_tag="INBOX_SCAN")

            self.enqueue_ui("log", f"📂 Scan INBOX: .rnx adăugate {count_rnx} | filtrate {skipped_filter} | ZIP procesate {count_zip}")
        except Exception as e:
            self.enqueue_ui("log", f"❌ Eroare scan INBOX: {e}")

    def on_inbox_file_seen(self, path):
        if not self.auto_watch_var.get():
            return

        if is_rnx_file(path):
            self.add_to_queue(path, source_tag="INBOX_WATCH")
        elif is_zip_archive(path):
            self.extract_zip_and_queue(path, source_tag="INBOX_WATCH")

    def on_drop(self, event):
        paths = parse_dropped_paths(self.root, event.data)
        scanned = 0
        added_rnx = 0
        zips = 0
        skipped = 0

        for item in paths:
            item = item.strip()
            if not item:
                continue

            if os.path.isdir(item):
                for root, _, files in os.walk(item):
                    for fn in files:
                        fp = os.path.join(root, fn)
                        scanned += 1
                        if is_rnx_file(fp):
                            ok, _ = self.add_to_queue(fp, source_tag="DRAGDROP")
                            if ok:
                                added_rnx += 1
                            else:
                                skipped += 1
                        elif is_zip_archive(fp):
                            zips += 1
                            self.extract_zip_and_queue(fp, source_tag="DRAGDROP")

            elif os.path.isfile(item):
                scanned += 1
                if is_rnx_file(item):
                    ok, _ = self.add_to_queue(item, source_tag="DRAGDROP")
                    if ok:
                        added_rnx += 1
                    else:
                        skipped += 1
                elif is_zip_archive(item):
                    zips += 1
                    self.extract_zip_and_queue(item, source_tag="DRAGDROP")

        self.enqueue_ui("log", f"🖱️ Drag&Drop: scanate {scanned}, ZIP procesate {zips}, .rnx adăugate {added_rnx}, ignorate {skipped}")

    # ==========================================================
    # ZIP extraction (recursiv ZIP in ZIP)
    # ==========================================================
    def _unique_extract_dir_for_zip(self, zip_path):
        base_name = os.path.splitext(os.path.basename(zip_path))[0]
        safe_base = "".join(c if c not in r'<>:"/\|?*' else "_" for c in base_name).strip() or "ZIP"
        safe_makedirs(self.extracted_root_dir)

        candidate = os.path.join(self.extracted_root_dir, safe_base)
        if not os.path.exists(candidate):
            return candidate

        idx = 1
        while True:
            alt = os.path.join(self.extracted_root_dir, f"{safe_base}_{idx}")
            if not os.path.exists(alt):
                return alt
            idx += 1

    def _extract_zip_recursive(self, zip_path, extract_dir, depth=0, max_depth=5):
        extracted_roots = []

        if depth > max_depth:
            self.enqueue_ui("log", f"⚠️ Limită recursivitate ZIP atinsă (max_depth={max_depth}) la: {zip_path}")
            return extracted_roots

        safe_makedirs(extract_dir)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            extracted_roots.append(extract_dir)
            self.enqueue_ui("log", f"📦 ZIP dezarhivat (nivel {depth}): {os.path.basename(zip_path)} -> {extract_dir}")
        except Exception as e:
            self.enqueue_ui("log", f"❌ Eroare dezarhivare ZIP (nivel {depth}): {zip_path} | {e}")
            return extracted_roots

        for root, dirs, files in os.walk(extract_dir):
            dirs[:] = [d for d in dirs if not d.startswith("_EXTRACTED_")]
            for fn in files:
                inner_fp = os.path.join(root, fn)
                if is_zip_archive(inner_fp):
                    inner_base = os.path.splitext(os.path.basename(inner_fp))[0]
                    inner_safe = "".join(c if c not in r'<>:"/\|?*' else "_" for c in inner_base).strip() or "ZIP"
                    inner_extract_dir = os.path.join(root, "_EXTRACTED_" + inner_safe)
                    extracted_roots.extend(
                        self._extract_zip_recursive(
                            inner_fp,
                            inner_extract_dir,
                            depth=depth + 1,
                            max_depth=max_depth
                        )
                    )
        return extracted_roots

    def extract_zip_and_queue(self, zip_path, source_tag="ZIP"):
        if not os.path.exists(zip_path):
            self.enqueue_ui("log", f"⚠️ ZIP dispărut înainte de procesare: {zip_path}")
            return

        # Daca vine din INBOX, asteapta sa se termine copierea
        if self.normp(os.path.dirname(zip_path)) == self.normp(self.inbox_dir):
            stable = self.wait_until_file_stable(zip_path)
            if not stable:
                self.enqueue_ui("log", f"❌ Timeout la copiere ZIP: {zip_path}")
                try:
                    moved = self.move_to_folder_unique(zip_path, self.errors_dir)
                    self.enqueue_ui("log", f"🚫 ZIP mutat în ERRORS: {moved}")
                except Exception as e:
                    self.enqueue_ui("log", f"⚠️ Nu pot muta ZIP în ERRORS: {e}")
                return

        extract_dir = self._unique_extract_dir_for_zip(zip_path)
        extracted_roots = self._extract_zip_recursive(zip_path, extract_dir, depth=0, max_depth=5)

        if not extracted_roots:
            if self.normp(os.path.dirname(zip_path)) == self.normp(self.inbox_dir):
                try:
                    moved = self.move_to_folder_unique(zip_path, self.errors_dir)
                    self.enqueue_ui("log", f"🚫 ZIP mutat în ERRORS: {os.path.basename(moved)}")
                except Exception as ex:
                    self.enqueue_ui("log", f"⚠️ Nu pot muta ZIP în ERRORS: {ex}")
            return

        scanned = 0
        found_rnx = 0
        added = 0
        filtered = 0

        for root, _, files in os.walk(extract_dir):
            for fn in files:
                fp = os.path.join(root, fn)
                scanned += 1
                if is_rnx_file(fp):
                    found_rnx += 1
                    ok, msg = self.add_to_queue(fp, source_tag=f"{source_tag}_ZIP")
                    if ok:
                        added += 1
                    elif "Filtrat" in msg:
                        filtered += 1

        self.enqueue_ui("log", f"📥 Din ZIP (recursiv): scanate {scanned}, găsite {found_rnx} .rnx, adăugate {added}, filtrate {filtered}")

        # Muta ZIP-ul original in PROCESSED daca vine din INBOX
        if self.normp(os.path.dirname(zip_path)) == self.normp(self.inbox_dir):
            try:
                moved = self.move_to_folder_unique(zip_path, self.processed_dir)
                self.enqueue_ui("log", f"📦 ZIP mutat în PROCESSED: {os.path.basename(moved)}")
            except Exception as e:
                self.enqueue_ui("log", f"⚠️ Nu pot muta ZIP în PROCESSED: {e}")

    # ==========================================================
    # GFZRNX / processing
    # ==========================================================
    def _run_hidden_subprocess(self, cmd, check=False):
        """
        Ruleaza subprocess fara fereastra CMD pe Windows.
        """
        kwargs = dict(
            capture_output=True,
            text=True,
            errors="replace"
        )

        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if creationflags:
                kwargs["creationflags"] = creationflags

            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs["startupinfo"] = startupinfo
            except Exception:
                pass

        return subprocess.run(cmd, check=check, **kwargs)

    def build_gfz_cmd(self, infile, outfile):
        gfz = self.gfzrnx_path_var.get().strip()
        satsys = (self.satsys_var.get().strip() or "GR")

        cmd = [
            gfz,
            "-finp", infile,
            "-fout", outfile,
            "-vo", "2",
            "-satsys", satsys,
        ]
        if self.overwrite_var.get():
            cmd.append("-f")
        return cmd

    def output_name_for(self, infile):
        base = os.path.splitext(os.path.basename(infile))[0]
        return base + "_POSPAC.obs"

    def test_gfzrnx(self):
        gfz = self.gfzrnx_path_var.get().strip()
        if not gfz:
            messagebox.showerror("Eroare", "Nu este setat GFZRNX exe.")
            return
        if not os.path.isfile(gfz):
            messagebox.showerror("Eroare", f"Fișierul GFZRNX nu există:\n{gfz}")
            return

        try:
            result = self._run_hidden_subprocess([gfz], check=False)
            self.enqueue_ui("log", f"✅ GFZRNX executabil detectat: {gfz}")
            if result.stdout and result.stdout.strip():
                self.enqueue_ui("log", "GFZRNX stdout: " + " | ".join(result.stdout.splitlines()[:3]))
            elif result.stderr and result.stderr.strip():
                self.enqueue_ui("log", "GFZRNX stderr: " + " | ".join(result.stderr.splitlines()[:3]))
        except Exception as e:
            messagebox.showerror("Eroare", f"Nu pot porni GFZRNX:\n{e}")

    def wait_until_file_stable(self, path, timeout_sec=120, stable_checks=3, check_interval=1.0):
        start = time.time()
        last_size = None
        stable_count = 0

        while time.time() - start < timeout_sec:
            if not os.path.exists(path):
                time.sleep(check_interval)
                continue

            try:
                size = os.path.getsize(path)
                with open(path, "rb"):
                    pass
            except Exception:
                time.sleep(check_interval)
                continue

            if size == last_size and size > 0:
                stable_count += 1
                if stable_count >= stable_checks:
                    return True
            else:
                stable_count = 0
                last_size = size

            time.sleep(check_interval)
        return False

    def move_to_folder_unique(self, src, target_dir):
        safe_makedirs(target_dir)
        name = os.path.basename(src)
        base, ext = os.path.splitext(name)
        dst = os.path.join(target_dir, name)

        idx = 1
        while os.path.exists(dst):
            dst = os.path.join(target_dir, f"{base}_{idx}{ext}")
            idx += 1

        shutil.move(src, dst)
        return dst

    # ==========================================================
    # Worker
    # ==========================================================
    def _start_worker_thread(self):
        th = threading.Thread(target=self.worker_loop, daemon=True)
        th.start()
        self.enqueue_ui("progress_start")

    def worker_loop(self):
        while not self.stop_worker:
            try:
                file_path, source_tag = self.work_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            npath = self.normp(file_path)

            # Daca a fost scos logic din coada
            if npath not in self.queued_set:
                self.work_queue.task_done()
                self.enqueue_ui("queue_refresh")
                continue

            self.queued_set.discard(npath)
            self.processing_set.add(npath)
            self.enqueue_ui("queue_refresh")

            try:
                self.process_one_file(npath, source_tag)
            except Exception as e:
                self.enqueue_ui("log", f"❌ Eroare internă la procesare: {npath} | {e}")
                self.enqueue_ui("log", traceback.format_exc())
            finally:
                self.processing_set.discard(npath)
                self.work_queue.task_done()
                self.enqueue_ui("queue_refresh")

        self.enqueue_ui("progress_stop")

    def process_one_file(self, infile, source_tag):
        self.enqueue_ui("status", f"Procesez: {os.path.basename(infile)}")

        gfz = self.gfzrnx_path_var.get().strip()
        if not gfz or not os.path.isfile(gfz):
            self.enqueue_ui("error_dialog", "GFZRNX exe nu este setat corect.")
            self.enqueue_ui("status", "Pregătit.")
            return

        if not os.path.exists(infile):
            self.enqueue_ui("log", f"⚠️ Fișier dispărut înainte de procesare: {infile}")
            self.enqueue_ui("status", "Pregătit.")
            return

        if not is_rnx_file(infile):
            self.enqueue_ui("log", f"⚠️ Ignorat (nu e .rnx): {infile}")
            self.enqueue_ui("status", "Pregătit.")
            return

        # filtru activ (in caz ca utilizatorul schimba filtrul dupa ce deja s-a pus in coada)
        if not self.rnx_passes_current_filter(infile):
            self.enqueue_ui("log", f"⏭️ Filtrat (nu e *_MO.rnx): {os.path.basename(infile)}")
            self.enqueue_ui("status", "Pregătit.")
            return

        # asteapta stabilizarea daca e direct in INBOX
        if self.normp(os.path.dirname(infile)) == self.normp(self.inbox_dir):
            stable = self.wait_until_file_stable(infile)
            if not stable:
                self.enqueue_ui("log", f"❌ Timeout copiere/stabilizare fișier: {infile}")
                try:
                    moved = self.move_to_folder_unique(infile, self.errors_dir)
                    self.enqueue_ui("log", f"🚫 Mutat în ERRORS: {moved}")
                except Exception as e:
                    self.enqueue_ui("log", f"⚠️ Nu pot muta în ERRORS: {e}")
                self.enqueue_ui("status", "Pregătit.")
                return

        outfile_name = self.output_name_for(infile)
        outfile = os.path.join(self.outbox_dir, outfile_name)
        cmd = self.build_gfz_cmd(infile, outfile)

        self.enqueue_ui("log", f"[{source_tag}] {os.path.basename(infile)} -> {outfile_name}")
        self.enqueue_ui("log", "CMD: " + " ".join(f'"{c}"' if " " in c else c for c in cmd))

        try:
            result = self._run_hidden_subprocess(cmd, check=True)

            self.enqueue_ui("log", "✅ Conversie reușită")
            if result.stdout and result.stdout.strip():
                self.enqueue_ui("log", "   stdout: " + " | ".join(result.stdout.splitlines()[:3]))
            elif result.stderr and result.stderr.strip():
                self.enqueue_ui("log", "   stderr: " + " | ".join(result.stderr.splitlines()[:3]))

            if self.move_processed_var.get() and self.normp(os.path.dirname(infile)) == self.normp(self.inbox_dir):
                try:
                    moved = self.move_to_folder_unique(infile, self.processed_dir)
                    self.enqueue_ui("log", f"📦 Sursa mutată în PROCESSED: {os.path.basename(moved)}")
                except Exception as e:
                    self.enqueue_ui("log", f"⚠️ Nu pot muta în PROCESSED: {e}")

        except subprocess.CalledProcessError as e:
            self.enqueue_ui("log", f"❌ Eroare conversie: {os.path.basename(infile)}")
            if e.stdout:
                self.enqueue_ui("log", "   [stdout] " + " | ".join(e.stdout.splitlines()[:5]))
            if e.stderr:
                self.enqueue_ui("log", "   [stderr] " + " | ".join(e.stderr.splitlines()[:5]))

            if self.normp(os.path.dirname(infile)) == self.normp(self.inbox_dir):
                try:
                    moved = self.move_to_folder_unique(infile, self.errors_dir)
                    self.enqueue_ui("log", f"🚫 Sursa mutată în ERRORS: {os.path.basename(moved)}")
                except Exception as ex:
                    self.enqueue_ui("log", f"⚠️ Nu pot muta în ERRORS: {ex}")

        except Exception as e:
            self.enqueue_ui("log", f"❌ Excepție la procesare: {e}")

        self.enqueue_ui("status", "Pregătit.")

    # ==========================================================
    # Watchdog
    # ==========================================================
    def _start_watchdog_if_enabled(self):
        if self.auto_watch_var.get():
            self.start_watchdog()

    def start_watchdog(self):
        if self.observer is not None:
            return
        try:
            handler = InboxEventHandler(self)
            self.observer = Observer()
            self.observer.schedule(handler, self.inbox_dir, recursive=False)
            self.observer.start()
            self.enqueue_ui("log", "👀 Monitorizare INBOX_DROP: PORNITĂ")
        except Exception as e:
            self.observer = None
            self.enqueue_ui("log", f"❌ Nu pot porni monitorizarea folderului: {e}")

    def stop_watchdog(self):
        if self.observer is None:
            return
        try:
            self.observer.stop()
            self.observer.join(timeout=2)
        except Exception:
            pass
        self.observer = None
        self.enqueue_ui("log", "⏹️ Monitorizare INBOX_DROP: OPRITĂ")

    def toggle_watchdog(self):
        if self.auto_watch_var.get():
            self.start_watchdog()
        else:
            self.stop_watchdog()

    # ==========================================================
    # Misc
    # ==========================================================
    def browse_gfzrnx(self):
        path = filedialog.askopenfilename(
            title="Selectează GFZRNX executable",
            filetypes=[("Executabile", "*.exe"), ("Toate fișierele", "*.*")]
        )
        if path:
            self.gfzrnx_path_var.set(path)
            self.enqueue_ui("log", f"GFZRNX setat: {path}")

    def on_close(self):
        try:
            self.stop_worker = True
            self.stop_watchdog()
        finally:
            self.root.destroy()


def main():
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass

    RinexHotFolderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()