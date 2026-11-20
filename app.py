"""
app.py
------
Simple flat dark sharp-cornered desktop UI for everyday users (Mod Story & Mod Font).
Power users who want advanced flags should use the CLI scripts directly.

Run:
    uv run app.py
"""

import ctypes
import io
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent
FONT_DIR = ROOT_DIR / "font"
STORY_DIR = ROOT_DIR / "story"
sys.path.insert(0, str(STORY_DIR))

import story_mod  # noqa: E402


# =============================================================================
# Flat Dark Theme (0px corners, crisp 1px borders)
# =============================================================================

C_BG = "#0c0c0c"
C_SURFACE = "#141414"
C_INPUT = "#1a1a1a"
C_HOVER = "#232323"
C_BORDER = "#2a2a2a"
C_BORDER_FOCUS = "#38c9b9"
C_ACCENT = "#38c9b9"
C_ACCENT_HOVER = "#4cdbc9"
C_ACCENT_FG = "#090909"
C_FG = "#ebebeb"
C_FG_DIM = "#8a8a8a"
C_LOG_BG = "#070707"
C_OK = "#4ade80"
C_ERR = "#f87171"

FONT_UI = ("Segoe UI", 9)
FONT_UI_BOLD = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 9)


def apply_windows_dark_chrome(root: tk.Tk) -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


def open_in_explorer(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


# =============================================================================
# Flat Sharp Widgets
# =============================================================================

def flat_button(
    parent,
    text: str,
    command: Callable,
    *,
    primary: bool = False,
    padx: int = 12,
    pady: int = 6,
) -> tk.Button:
    bg = C_ACCENT if primary else C_INPUT
    fg = C_ACCENT_FG if primary else C_FG
    hover_bg = C_ACCENT_HOVER if primary else C_HOVER
    font = FONT_UI_BOLD if primary else FONT_UI

    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=hover_bg,
        activeforeground=fg,
        disabledforeground=C_FG_DIM,
        font=font,
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=C_ACCENT if primary else C_BORDER,
        highlightcolor=C_ACCENT,
        padx=padx,
        pady=pady,
        cursor="hand2",
    )
    btn._base_bg = bg
    btn._hover_bg = hover_bg

    def _on_enter(_):
        if btn["state"] != "disabled":
            btn.configure(bg=btn._hover_bg)

    def _on_leave(_):
        if btn["state"] != "disabled":
            btn.configure(bg=btn._base_bg)

    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)
    return btn


def flat_entry(parent, textvariable: tk.StringVar, *, width: Optional[int] = None, mono: bool = False) -> tk.Entry:
    kw = dict(
        textvariable=textvariable,
        bg=C_INPUT,
        fg=C_FG,
        insertbackground=C_ACCENT,
        selectbackground=C_ACCENT,
        selectforeground=C_ACCENT_FG,
        font=FONT_MONO if mono else FONT_UI,
        relief="flat",
        bd=4,
        highlightthickness=1,
        highlightbackground=C_BORDER,
        highlightcolor=C_BORDER_FOCUS,
    )
    if width is not None:
        kw["width"] = width
    return tk.Entry(parent, **kw)


def bordered_panel(parent, *, bg: str = C_SURFACE) -> tk.Frame:
    return tk.Frame(
        parent,
        bg=bg,
        highlightthickness=1,
        highlightbackground=C_BORDER,
        highlightcolor=C_BORDER,
        bd=0,
    )


class QueueWriter(io.TextIOBase):
    def __init__(self, log_fn: Callable[[str], None]):
        self._log = log_fn
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._log(line)
        return len(s)

    def flush(self) -> None:
        if self._buf:
            self._log(self._buf)
            self._buf = ""


# =============================================================================
# Main Application
# =============================================================================

class SekaiModdingApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Sekai-Modding")
        self.root.geometry("980x700")
        self.root.minsize(840, 600)
        self.root.configure(bg=C_BG)

        self._log_queue: "queue.Queue[Tuple[str, Optional[str]]]" = queue.Queue()
        self._busy = False
        self._action_buttons: List[tk.Button] = []

        # Story state
        self.story_region = tk.StringVar(value="jp")
        self.story_kind = tk.StringVar(value="main")
        self.story_search = tk.StringVar(value="")
        self._story_list_items: List[Tuple[str, object]] = []
        self._current_story: Optional[story_mod.StoryEntry] = None

        self._setup_ttk_style()
        self._build_layout()
        apply_windows_dark_chrome(self.root)

        self._select_tab("story")
        self._poll_log_queue()
        self.log("Sẵn sàng.", tag="dim")

    def _setup_ttk_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.Vertical.TScrollbar",
            gripcount=0,
            background=C_HOVER,
            darkcolor=C_HOVER,
            lightcolor=C_HOVER,
            troughcolor=C_SURFACE,
            bordercolor=C_BORDER,
            arrowcolor=C_FG_DIM,
            relief="flat",
        )
        style.map("Dark.Vertical.TScrollbar", background=[("active", C_BORDER_FOCUS)])

    # -------------------------------------------------------------------------
    # Layout: Topbar + Active Tab + Compact Progress Log
    # -------------------------------------------------------------------------

    def _build_layout(self) -> None:
        topbar = tk.Frame(self.root, bg=C_SURFACE, height=44)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        tk.Label(
            topbar,
            text="SEKAI-MODDING",
            bg=C_SURFACE,
            fg=C_FG,
            font=FONT_TITLE,
            padx=16,
        ).pack(side="left")

        tk.Frame(topbar, bg=C_BORDER, width=1).pack(side="left", fill="y", pady=8)

        self._tab_buttons: dict[str, Tuple[tk.Button, tk.Frame]] = {}
        for key, label in (("story", "MOD STORY"), ("font", "MOD FONT")):
            holder = tk.Frame(topbar, bg=C_SURFACE)
            holder.pack(side="left", fill="y")
            btn = tk.Button(
                holder,
                text=label,
                command=lambda k=key: self._select_tab(k),
                bg=C_SURFACE,
                fg=C_FG_DIM,
                activebackground=C_HOVER,
                activeforeground=C_FG,
                font=FONT_UI_BOLD,
                relief="flat",
                bd=0,
                padx=22,
                cursor="hand2",
            )
            btn.pack(side="top", fill="both", expand=True)
            indicator = tk.Frame(holder, bg=C_SURFACE, height=2)
            indicator.pack(side="bottom", fill="x")
            self._tab_buttons[key] = (btn, indicator)

        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.status_lbl = tk.Label(
            topbar,
            textvariable=self.status_var,
            bg=C_SURFACE,
            fg=C_FG_DIM,
            font=FONT_UI,
            padx=16,
        )
        self.status_lbl.pack(side="right")

        tk.Frame(self.root, bg=C_BORDER, height=1).pack(fill="x", side="top")

        # Compact bottom log console
        log_outer = tk.Frame(self.root, bg=C_BG)
        log_outer.pack(fill="x", side="bottom", padx=12, pady=(0, 12))

        log_hdr = tk.Frame(log_outer, bg=C_BG)
        log_hdr.pack(fill="x", pady=(6, 3))
        tk.Label(log_hdr, text="TIẾN TRÌNH", bg=C_BG, fg=C_FG_DIM, font=FONT_UI_BOLD).pack(side="left")
        flat_button(log_hdr, "Xóa log", self._clear_log, padx=8, pady=1).pack(side="right")

        log_box = bordered_panel(log_outer, bg=C_LOG_BG)
        log_box.pack(fill="x")

        self.log_text = tk.Text(
            log_box,
            height=6,
            bg=C_LOG_BG,
            fg=C_FG,
            font=FONT_MONO,
            relief="flat",
            bd=6,
            wrap="word",
            state="disabled",
            insertbackground=C_ACCENT,
            selectbackground=C_ACCENT,
            selectforeground=C_ACCENT_FG,
        )
        log_sb = ttk.Scrollbar(log_box, orient="vertical", command=self.log_text.yview, style="Dark.Vertical.TScrollbar")
        self.log_text.configure(yscrollcommand=log_sb.set)
        log_sb.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

        self.log_text.tag_configure("dim", foreground=C_FG_DIM)
        self.log_text.tag_configure("ok", foreground=C_OK)
        self.log_text.tag_configure("err", foreground=C_ERR)
        self.log_text.tag_configure("accent", foreground=C_ACCENT)

        # Center content
        self.content_area = tk.Frame(self.root, bg=C_BG)
        self.content_area.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        self.pages = {
            "story": self._build_story_tab(self.content_area),
            "font": self._build_font_tab(self.content_area),
        }

    def _select_tab(self, key: str) -> None:
        for k, frame in self.pages.items():
            frame.pack_forget()
            btn, ind = self._tab_buttons[k]
            if k == key:
                btn.configure(fg=C_FG, bg=C_BG)
                ind.configure(bg=C_ACCENT)
            else:
                btn.configure(fg=C_FG_DIM, bg=C_SURFACE)
                ind.configure(bg=C_SURFACE)
        self.pages[key].pack(fill="both", expand=True)
        if key == "story" and not self._story_list_items:
            self._load_story_list()

    # -------------------------------------------------------------------------
    # Logging & Background Runner
    # -------------------------------------------------------------------------

    def log(self, msg: str, tag: Optional[str] = None) -> None:
        self._log_queue.put((msg, tag))

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _poll_log_queue(self) -> None:
        try:
            while True:
                msg, tag = self._log_queue.get_nowait()
                self.log_text.configure(state="normal")
                if tag is None:
                    if "[ERROR]" in msg or "Traceback" in msg:
                        tag = "err"
                    elif "[DONE]" in msg or "[OK]" in msg:
                        tag = "ok"
                    elif msg.startswith("==="):
                        tag = "accent"
                self.log_text.insert("end", msg + "\n", tag or "")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(60, self._poll_log_queue)

    def _set_busy(self, busy: bool, label: str = "Sẵn sàng") -> None:
        self._busy = busy
        self.status_var.set(label if busy else "Sẵn sàng")
        self.status_lbl.configure(fg=C_ACCENT if busy else C_FG_DIM)
        state = "disabled" if busy else "normal"
        for btn in self._action_buttons:
            btn.configure(state=state)

    def _run_bg(self, label: str, fn: Callable, on_done: Optional[Callable] = None) -> None:
        if self._busy:
            self.log("[WARN] Đang chạy tác vụ khác, vui lòng chờ xong...", tag="err")
            return
        self._set_busy(True, label)

        def _worker():
            old_out, old_err = sys.stdout, sys.stderr
            writer = QueueWriter(self.log)
            sys.stdout = writer
            sys.stderr = writer
            result = None
            err = None
            try:
                result = fn()
            except Exception as e:
                err = e
                self.log(f"[ERROR] {e}", tag="err")
            finally:
                writer.flush()
                sys.stdout, sys.stderr = old_out, old_err

                def _finish():
                    self._set_busy(False)
                    if on_done is not None:
                        on_done(result, err)

                self.root.after(0, _finish)

        threading.Thread(target=_worker, daemon=True).start()

    def _run_subprocess(self, cmd: List[str]) -> None:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=creationflags,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            self.log(line.rstrip("\r\n"))
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"Quá trình xử lý báo lỗi (mã {rc}). Xem chi tiết ở khung Tiến trình.")

    def _copy_text(self, text: str, label: str = "đường dẫn") -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log(f"[OK] Đã copy {label}: {text}", tag="ok")

    # =========================================================================
    # TAB 1: MOD STORY (Simple 3-Step Workflow + Built-in Guide)
    # =========================================================================

    def _build_story_tab(self, parent) -> tk.Frame:
        page = tk.Frame(parent, bg=C_BG)

        # Compact 3-step guide banner
        guide = bordered_panel(page)
        guide.pack(fill="x", pady=(0, 8))
        g_in = tk.Frame(guide, bg=C_SURFACE)
        g_in.pack(fill="x", padx=10, pady=7)
        tk.Label(
            g_in,
            text=(
                "CÁCH DÙNG:  "
                "1) Chọn Server, Story & Chapter bên dưới rồi bấm [1. Xuất file dịch (.txt)]   →   "
                "2) Bấm [2. Mở thư mục để dịch], sửa lời thoại trong file .txt (giữ nguyên dòng # và [...])   →   "
                "3) Bấm [3. Đóng gói file mod] rồi chép file vào đúng thư mục Android hiện ở khung bên phải."
            ),
            bg=C_SURFACE,
            fg=C_FG_DIM,
            font=FONT_UI,
            justify="left",
            wraplength=920,
            anchor="w",
        ).pack(fill="x")

        # Filter / selector bar
        ctrl = bordered_panel(page)
        ctrl.pack(fill="x", pady=(0, 8))
        ctrl_in = tk.Frame(ctrl, bg=C_SURFACE)
        ctrl_in.pack(fill="x", padx=10, pady=7)

        tk.Label(ctrl_in, text="Server:", bg=C_SURFACE, fg=C_FG_DIM, font=FONT_UI).pack(side="left", padx=(0, 6))
        self._reg_btns: dict[str, tk.Button] = {}
        for r in ("jp", "en"):
            b = flat_button(ctrl_in, r.upper(), lambda reg=r: self._set_story_region(reg), padx=10, pady=3)
            b.pack(side="left", padx=(0, 4))
            self._reg_btns[r] = b

        tk.Frame(ctrl_in, bg=C_BORDER, width=1).pack(side="left", fill="y", padx=10)

        tk.Label(ctrl_in, text="Loại:", bg=C_SURFACE, fg=C_FG_DIM, font=FONT_UI).pack(side="left", padx=(0, 6))
        self._kind_btns: dict[str, tk.Button] = {}
        for k, lbl in (("main", "Main Story"), ("event", "Event Story")):
            b = flat_button(ctrl_in, lbl, lambda kk=k: self._set_story_kind(kk), padx=10, pady=3)
            b.pack(side="left", padx=(0, 4))
            self._kind_btns[k] = b

        tk.Frame(ctrl_in, bg=C_BORDER, width=1).pack(side="left", fill="y", padx=10)

        tk.Label(ctrl_in, text="Tìm:", bg=C_SURFACE, fg=C_FG_DIM, font=FONT_UI).pack(side="left", padx=(0, 6))
        flat_entry(ctrl_in, self.story_search, width=22).pack(side="left", fill="x", expand=True)
        self.story_search.trace_add("write", lambda *_: self._refresh_story_listbox())

        btn_refresh = flat_button(ctrl_in, "Cập nhật danh sách", self._on_story_refresh, padx=10, pady=3)
        btn_refresh.pack(side="right", padx=(10, 0))
        self._action_buttons.append(btn_refresh)

        # Two-column workspace
        body = tk.Frame(page, bg=C_BG)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=5, uniform="story_cols")
        body.columnconfigure(1, weight=6, uniform="story_cols")
        body.rowconfigure(0, weight=1)

        # Left column: Story list
        left = bordered_panel(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        lhdr = tk.Frame(left, bg=C_SURFACE)
        lhdr.pack(fill="x", padx=10, pady=(8, 4))
        self.story_list_hdr = tk.StringVar(value="CHỌN STORY")
        tk.Label(lhdr, textvariable=self.story_list_hdr, bg=C_SURFACE, fg=C_FG_DIM, font=FONT_UI_BOLD).pack(side="left")

        lwrap = tk.Frame(left, bg=C_SURFACE)
        lwrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.story_listbox = tk.Listbox(
            lwrap,
            bg=C_INPUT,
            fg=C_FG,
            selectbackground=C_ACCENT,
            selectforeground=C_ACCENT_FG,
            font=FONT_UI,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=C_BORDER,
            highlightcolor=C_BORDER_FOCUS,
            activestyle="none",
            exportselection=False,
        )
        lsb = ttk.Scrollbar(lwrap, orient="vertical", command=self.story_listbox.yview, style="Dark.Vertical.TScrollbar")
        self.story_listbox.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.story_listbox.pack(side="left", fill="both", expand=True)
        self.story_listbox.bind("<<ListboxSelect>>", self._on_story_selected)

        # Right column: Chapters + 3 simple buttons + Android destination
        right = bordered_panel(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.sel_title_var = tk.StringVar(value="Chọn một story ở cột bên trái")
        tk.Label(
            right,
            textvariable=self.sel_title_var,
            bg=C_SURFACE,
            fg=C_FG,
            font=FONT_UI_BOLD,
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 4))

        ch_hdr = tk.Frame(right, bg=C_SURFACE)
        ch_hdr.pack(fill="x", padx=10, pady=(2, 4))
        tk.Label(ch_hdr, text="CHỌN CHAPTER (giữ Ctrl để chọn nhiều)", bg=C_SURFACE, fg=C_FG_DIM, font=FONT_UI_BOLD).pack(side="left")
        flat_button(ch_hdr, "Chọn tất cả", self._select_all_chapters, padx=8, pady=2).pack(side="right")

        cwrap = tk.Frame(right, bg=C_SURFACE)
        cwrap.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.chapter_listbox = tk.Listbox(
            cwrap,
            selectmode="extended",
            bg=C_INPUT,
            fg=C_FG,
            selectbackground=C_ACCENT,
            selectforeground=C_ACCENT_FG,
            font=FONT_UI,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=C_BORDER,
            highlightcolor=C_BORDER_FOCUS,
            activestyle="none",
            exportselection=False,
        )
        csb = ttk.Scrollbar(cwrap, orient="vertical", command=self.chapter_listbox.yview, style="Dark.Vertical.TScrollbar")
        self.chapter_listbox.configure(yscrollcommand=csb.set)
        csb.pack(side="right", fill="y")
        self.chapter_listbox.pack(side="left", fill="both", expand=True)

        # Numbered 1 -> 2 -> 3 action buttons
        act_row = tk.Frame(right, bg=C_SURFACE)
        act_row.pack(fill="x", padx=10, pady=(0, 8))

        btn_step1 = flat_button(act_row, "1. Xuất file dịch (.txt)", self._on_story_extract, primary=True)
        btn_step1.pack(side="left", fill="x", expand=True, padx=(0, 6))
        btn_step2 = flat_button(act_row, "2. Mở thư mục để dịch", self._on_open_story_work)
        btn_step2.pack(side="left", padx=(0, 6))
        btn_step3 = flat_button(act_row, "3. Đóng gói file mod", self._on_story_patch, primary=True)
        btn_step3.pack(side="left", fill="x", expand=True)
        self._action_buttons.extend([btn_step1, btn_step3])

        # Android install destination bar
        tk.Frame(right, bg=C_BORDER, height=1).pack(fill="x", padx=10, pady=(0, 6))
        dest_box = tk.Frame(right, bg=C_SURFACE)
        dest_box.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(dest_box, text="Nơi chép file mod trên Android:", bg=C_SURFACE, fg=C_FG_DIM, font=FONT_UI).pack(anchor="w")

        dest_row = tk.Frame(dest_box, bg=C_SURFACE)
        dest_row.pack(fill="x", pady=(2, 0))
        self.sel_path_var = tk.StringVar(value="—")
        tk.Label(dest_row, textvariable=self.sel_path_var, bg=C_SURFACE, fg=C_ACCENT, font=FONT_MONO, anchor="w").pack(side="left", fill="x", expand=True)
        flat_button(dest_row, "Copy", self._on_copy_story_path, padx=8, pady=2).pack(side="right", padx=(6, 0))
        flat_button(dest_row, "Mở file kết quả", self._on_open_story_output, padx=8, pady=2).pack(side="right")

        self._style_story_toggles()
        return page

    def _style_story_toggles(self) -> None:
        cur_reg = self.story_region.get()
        for r, b in self._reg_btns.items():
            active = r == cur_reg
            b._base_bg = C_ACCENT if active else C_INPUT
            b._hover_bg = C_ACCENT_HOVER if active else C_HOVER
            b.configure(
                bg=b._base_bg,
                fg=C_ACCENT_FG if active else C_FG,
                highlightbackground=C_ACCENT if active else C_BORDER,
            )
        cur_kind = self.story_kind.get()
        for k, b in self._kind_btns.items():
            active = k == cur_kind
            b._base_bg = C_ACCENT if active else C_INPUT
            b._hover_bg = C_ACCENT_HOVER if active else C_HOVER
            b.configure(
                bg=b._base_bg,
                fg=C_ACCENT_FG if active else C_FG,
                highlightbackground=C_ACCENT if active else C_BORDER,
            )

    def _set_story_region(self, region: str) -> None:
        if self.story_region.get() == region:
            return
        self.story_region.set(region)
        self._style_story_toggles()
        self._current_story = None
        self._clear_chapter_panel()
        self._load_story_list()

    def _set_story_kind(self, kind: str) -> None:
        if self.story_kind.get() == kind:
            return
        self.story_kind.set(kind)
        self._style_story_toggles()
        self.story_search.set("")
        self._current_story = None
        self._clear_chapter_panel()
        self._load_story_list()

    def _clear_chapter_panel(self) -> None:
        self.sel_title_var.set("Chọn một story ở cột bên trái")
        self.sel_path_var.set("—")
        self.chapter_listbox.delete(0, "end")

    def _load_story_list(self) -> None:
        region = self.story_region.get()
        kind = self.story_kind.get()

        if kind == "main":
            self._all_raw_items = [(g.display_name, g) for g in story_mod.MAIN_STORY_GROUPS]
            self.story_list_hdr.set(f"MAIN STORY ({region.upper()}) — 10 nhóm")
            self._refresh_story_listbox()
            return

        def _task():
            items = story_mod.list_event_stories(region)
            return list(reversed(items))

        def _done(res, err):
            if err or res is None:
                return
            self._all_raw_items = [
                (f"{ev_id}: {ev_name}", (ev_id, ev_name, ab))
                for ev_id, ev_name, ab, _ in res
            ]
            self.story_list_hdr.set(f"EVENT STORY ({region.upper()}) — {len(res)} event")
            self._refresh_story_listbox()

        self._run_bg("Đang tải danh sách...", _task, _done)

    def _refresh_story_listbox(self) -> None:
        raw = getattr(self, "_all_raw_items", [])
        q = self.story_search.get().strip().lower()
        self._story_list_items = []
        self.story_listbox.delete(0, "end")

        for label, payload in raw:
            if q:
                hay = label.lower()
                if isinstance(payload, tuple) and len(payload) >= 3:
                    hay += " " + str(payload[2]).lower()
                elif isinstance(payload, story_mod.MainStoryGroup):
                    hay += " " + " ".join(payload.aliases)
                if q not in hay:
                    continue
            self._story_list_items.append((label, payload))
            self.story_listbox.insert("end", label)

    def _on_story_selected(self, _event=None) -> None:
        sel = self.story_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._story_list_items):
            return
        _, payload = self._story_list_items[idx]
        region = self.story_region.get()

        def _task():
            if isinstance(payload, story_mod.MainStoryGroup):
                return story_mod.get_main_story(region, payload)
            return story_mod.get_event_story(region, payload[0])

        def _done(story: Optional[story_mod.StoryEntry], err):
            if err or story is None:
                return
            self._current_story = story
            cdir, cfile = story_mod.bundle_cache_path(story.bundle_name)
            pkg = story_mod.ANDROID_PACKAGES[story.region]
            self.sel_title_var.set(f"{story.display_title} ({story.region.upper()})")
            self.sel_path_var.set(f"Android/data/{pkg}/files/data/{cdir}/{cfile}")
            self.chapter_listbox.delete(0, "end")
            for ep in story.episodes:
                self.chapter_listbox.insert("end", f"[{ep.display_no:02d}] {ep.label} — {ep.title}")
            if story.episodes:
                self.chapter_listbox.selection_set(0)

        self._run_bg("Đang đọc danh sách chapter...", _task, _done)

    def _select_all_chapters(self) -> None:
        self.chapter_listbox.selection_set(0, "end")

    def _on_copy_story_path(self) -> None:
        if not self._current_story:
            return
        self._copy_text(self.sel_path_var.get(), "đường dẫn Android")

    def _on_story_refresh(self) -> None:
        region = self.story_region.get()
        self._run_bg(
            "Đang cập nhật danh sách...",
            lambda: story_mod.refresh_metadata(region),
            lambda _res, err: None if err else self._load_story_list(),
        )

    def _on_story_extract(self) -> None:
        if not self._current_story:
            messagebox.showwarning("Chưa chọn Story", "Hãy chọn một story ở cột bên trái trước.")
            return
        sel = self.chapter_listbox.curselection()
        if not sel:
            messagebox.showwarning("Chưa chọn Chapter", "Hãy chọn ít nhất 1 chapter để xuất.")
            return

        story = self._current_story
        episodes = [story.episodes[i] for i in sel]

        def _task():
            self.log(f"=== Xuất file dịch: {story.display_title} ({len(episodes)} chapter) ===", tag="accent")
            return story_mod.extract_episodes(story, episodes, overwrite=False)

        def _done(written, err):
            if not err and written:
                messagebox.showinfo(
                    "Đã xuất xong",
                    f"Đã xuất {len(written)} file .txt vào:\n{written[0].parent}\n\n"
                    "Bấm [2. Mở thư mục để dịch] để mở và chỉnh sửa lời thoại.",
                )

        self._run_bg("Đang tải & xuất file .txt...", _task, _done)

    def _on_story_patch(self) -> None:
        if not self._current_story:
            messagebox.showwarning("Chưa chọn Story", "Hãy chọn story bạn đã dịch ở cột bên trái.")
            return
        story = self._current_story
        work_folder = story_mod.WORK_DIR / story.region / story.story_key
        if not work_folder.is_dir():
            messagebox.showerror(
                "Chưa có file dịch",
                "Bạn chưa xuất file .txt cho story này.\nHãy bấm [1. Xuất file dịch (.txt)] trước.",
            )
            return

        def _task():
            self.log(f"=== Đóng gói mod: {story.display_title} ===", tag="accent")
            return story_mod.patch_from_paths(work_folder)

        def _done(out_path, err):
            if not err and out_path:
                cdir, cfile = story_mod.bundle_cache_path(story.bundle_name)
                pkg = story_mod.ANDROID_PACKAGES[story.region]
                messagebox.showinfo(
                    "Đóng gói thành công!",
                    f"File mod đã lưu tại:\n{out_path}\n\n"
                    f"Hãy chép file `{cfile}` vào thư mục trên Android:\n"
                    f"Android/data/{pkg}/files/data/{cdir}/",
                )

        self._run_bg("Đang đóng gói & mã hóa...", _task, _done)

    def _on_open_story_work(self) -> None:
        if self._current_story:
            p = story_mod.WORK_DIR / self._current_story.region / self._current_story.story_key
            open_in_explorer(p if p.exists() else story_mod.WORK_DIR)
        else:
            open_in_explorer(story_mod.WORK_DIR)

    def _on_open_story_output(self) -> None:
        if self._current_story:
            cdir, _ = story_mod.bundle_cache_path(self._current_story.bundle_name)
            p = story_mod.OUTPUT_DIR / self._current_story.region / cdir
            open_in_explorer(p if p.exists() else story_mod.OUTPUT_DIR)
        else:
            open_in_explorer(story_mod.OUTPUT_DIR)

    # =========================================================================
    # TAB 2: MOD FONT (Minimal: Pick DB + EB + 1 Button)
    # =========================================================================

    def _build_font_tab(self, parent) -> tk.Frame:
        page = tk.Frame(parent, bg=C_BG)

        self.font_db_var = tk.StringVar(value="")
        self.font_eb_var = tk.StringVar(value="")

        # Guide banner
        guide = bordered_panel(page)
        guide.pack(fill="x", pady=(0, 10))
        g_in = tk.Frame(guide, bg=C_SURFACE)
        g_in.pack(fill="x", padx=12, pady=8)
        tk.Label(
            g_in,
            text=(
                "CÁCH DÙNG:  "
                "Chọn 2 file font tiếng Việt (hoặc chỉ chọn Font DB nếu dùng chung 1 file)  →  "
                "bấm [GỘP & TẠO FILE MOD FONT]  →  chờ ~20 giây rồi chép file kết quả vào điện thoại."
            ),
            bg=C_SURFACE,
            fg=C_FG_DIM,
            font=FONT_UI,
            justify="left",
            wraplength=920,
            anchor="w",
        ).pack(fill="x")

        # Main Font Card
        card = bordered_panel(page)
        card.pack(fill="x", pady=(0, 10))
        c_in = tk.Frame(card, bg=C_SURFACE)
        c_in.pack(fill="x", padx=14, pady=14)

        tk.Label(c_in, text="Font DB (chữ thường, lời thoại story):", bg=C_SURFACE, fg=C_FG, font=FONT_UI).grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=6
        )
        flat_entry(c_in, self.font_db_var, mono=True).grid(row=0, column=1, sticky="ew", pady=6)
        flat_button(c_in, "Chọn file...", lambda: self._pick_font(self.font_db_var), padx=12, pady=4).grid(
            row=0, column=2, padx=(8, 0), pady=6
        )

        tk.Label(c_in, text="Font EB (chữ đậm, tên nhân vật):", bg=C_SURFACE, fg=C_FG, font=FONT_UI).grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=6
        )
        flat_entry(c_in, self.font_eb_var, mono=True).grid(row=1, column=1, sticky="ew", pady=6)
        flat_button(c_in, "Chọn file...", lambda: self._pick_font(self.font_eb_var), padx=12, pady=4).grid(
            row=1, column=2, padx=(8, 0), pady=6
        )

        tk.Label(
            c_in,
            text="Gợi ý: Nếu chỉ có 1 file font (hoặc Variable Font), để trống dòng Font EB — tool sẽ tự dùng chung file Font DB.",
            bg=C_SURFACE,
            fg=C_FG_DIM,
            font=FONT_UI,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 14))

        btn_row = tk.Frame(c_in, bg=C_SURFACE)
        btn_row.grid(row=3, column=0, columnspan=3, sticky="ew")
        btn_go = flat_button(btn_row, "GỘP & TẠO FILE MOD FONT", self._on_font_run, primary=True, pady=9)
        btn_go.pack(side="left", fill="x", expand=True, padx=(0, 8))
        flat_button(btn_row, "Mở thư mục kết quả", self._on_open_font_output, pady=9).pack(side="right")
        self._action_buttons.append(btn_go)
        c_in.columnconfigure(1, weight=1)

        # Android install instructions
        dest = bordered_panel(page)
        dest.pack(fill="x")
        d_in = tk.Frame(dest, bg=C_SURFACE)
        d_in.pack(fill="x", padx=14, pady=12)

        tk.Label(d_in, text="HƯỚNG DẪN CHÉP VÀO ANDROID", bg=C_SURFACE, fg=C_FG_DIM, font=FONT_UI_BOLD).pack(anchor="w", pady=(0, 6))
        tk.Label(
            d_in,
            text=(
                "Sau khi chạy xong, chép đè file `4ad9182d51b21d790af3f73d72ddc193` trong thư mục font/output/47a2/ vào:\n"
                "  • Bản JP:  Android/data/com.sega.pjsekai/files/data/47a2/\n"
                "  • Bản EN:  Android/data/com.sega.ColorfulStage.en/files/data/47a2/"
            ),
            bg=C_SURFACE,
            fg=C_FG,
            font=FONT_MONO,
            justify="left",
            anchor="w",
        ).pack(fill="x")

        return page

    def _on_open_font_output(self) -> None:
        out_dir = FONT_DIR / "output" / "47a2"
        open_in_explorer(out_dir if out_dir.exists() else (FONT_DIR / "output"))

    def _pick_font(self, target_var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            title="Chọn file font",
            initialdir=str(FONT_DIR),
            filetypes=[("Font files", "*.ttf *.otf *.ttc *.otc"), ("All files", "*.*")],
        )
        if path:
            target_var.set(path)

    def _on_font_run(self) -> None:
        db_src = self.font_db_var.get().strip()
        eb_src = self.font_eb_var.get().strip() or db_src
        if not db_src:
            messagebox.showwarning("Chưa chọn font", "Hãy chọn ít nhất file Font DB trước.")
            return
        if not Path(db_src).is_file():
            messagebox.showerror("Không tìm thấy file", f"Không tìm thấy Font DB:\n{db_src}")
            return
        if not Path(eb_src).is_file():
            messagebox.showerror("Không tìm thấy file", f"Không tìm thấy Font EB:\n{eb_src}")
            return

        font_assets = FONT_DIR / "assets"
        font_output = FONT_DIR / "output"
        font_output.mkdir(parents=True, exist_ok=True)

        cmds = [
            [
                sys.executable,
                str(FONT_DIR / "merge_fonts.py"),
                str(font_assets / "FOT-RodinNTLG Pro DB.otf"),
                db_src,
                str(font_output / "FOT-RodinNTLGPro-DB-OnDemand.otf"),
                "--verify",
            ],
            [
                sys.executable,
                str(FONT_DIR / "merge_fonts.py"),
                str(font_assets / "FOT-RodinNTLG Pro EB.otf"),
                eb_src,
                str(font_output / "FOT-RodinNTLGPro-EB-OnDemand.otf"),
                "--verify",
            ],
            [sys.executable, str(FONT_DIR / "build_font_bundle.py")],
        ]

        def _task():
            self.log("=== [1/3] Đang gộp Font DB ===", tag="accent")
            self._run_subprocess(cmds[0])
            self.log("=== [2/3] Đang gộp Font EB ===", tag="accent")
            self._run_subprocess(cmds[1])
            self.log("=== [3/3] Đang đóng gói & mã hóa bundle ===", tag="accent")
            self._run_subprocess(cmds[2])

            built = font_output / "common"
            hashed = font_output / "47a2" / "4ad9182d51b21d790af3f73d72ddc193"
            if built.is_file():
                hashed.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(built, hashed)
                self.log(f"[DONE] File mod sẵn sàng tại: {hashed}", tag="ok")
                return hashed
            return built

        def _done(out_path, err):
            if not err and out_path:
                messagebox.showinfo(
                    "Hoàn tất Mod Font!",
                    f"File mod font đã sẵn sàng:\n{out_path}\n\n"
                    "Chép đè file này vào thư mục:\n"
                    "• JP: Android/data/com.sega.pjsekai/files/data/47a2/\n"
                    "• EN: Android/data/com.sega.ColorfulStage.en/files/data/47a2/",
                )

        self._run_bg("Đang tạo file mod font...", _task, _done)


def main() -> None:
    root = tk.Tk()
    SekaiModdingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
