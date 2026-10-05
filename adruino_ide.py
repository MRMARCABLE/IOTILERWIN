"""
arduino_cli_ide.py  —  Layout "Mission Control"
Code editor Python (Tkinter) untuk sketch Arduino/ESP32 dengan arduino-cli.

Konsep layout (beda dari IDE biasa):
  - Kiri  : editor lega (tanpa toolbar/menubar/panel bawah)
  - Kanan : panel kontrol berisi kartu
        PERANGKAT : status board live (auto-deteksi port) + board/port/baud
        BUILD     : pipeline Simpan > Compile > Upload + meter Flash/RAM
        KONSOL    : tab Output & Serial Monitor terpisah
  - Atas  : header ramping dengan "Shelf" (chip sketch terbaru) + menu ☰
  - Drag & drop: lepaskan file .ino / folder sketch ke jendela mana saja

Drag & drop butuh paket opsional:  pip install tkinterdnd2
(tanpa paket itu, semua fitur lain tetap jalan)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
import subprocess
import os
import re
import sys
import shlex
import shutil
import json
import glob
import queue
import threading
from urllib.parse import unquote

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_TERSEDIA = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    DND_TERSEDIA = False

# ============================================================
# KONFIGURASI DEFAULT
# ============================================================
DEFAULT_FQBN = "esp32:esp32:esp32"
DEFAULT_PORT = "/dev/ttyUSB0"

BOARD_PRESET = [
    ("ESP32 Dev Module", "esp32:esp32:esp32"),
    ("ESP32-S3 Dev Module", "esp32:esp32:esp32s3"),
    ("ESP32-C3 Dev Module", "esp32:esp32:esp32c3"),
    ("Arduino Uno", "arduino:avr:uno"),
    ("Arduino Nano", "arduino:avr:nano"),
    ("Arduino Mega 2560", "arduino:avr:mega"),
    ("ESP8266 NodeMCU", "esp8266:esp8266:nodemcuv2"),
    ("Raspberry Pi Pico", "rp2040:rp2040:rpipico"),
]
BAUD_LIST = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]

# ============================================================
# PALET "MIDNIGHT + AMBER"
# ============================================================
BG_APP = "#12141c"        # header
BG_EDITOR = "#0f111a"     # editor & konsol
BG_PANEL = "#181b26"      # panel kanan
BG_CARD = "#1f2333"
BG_CARD_ALT = "#2a3047"
BG_BORDER = "#2e3450"
BG_INPUT = "#2a2f45"
BG_HOVER = "#343b5a"
BG_CURLINE = "#151827"
BG_SELECT = "#33406b"
BG_STATUSBAR = "#0c0e15"
FG_TEXT = "#e4e7f2"
FG_DIM = "#7d84a3"

AMBER = "#f5a524"
AMBER_H = "#ffbb4d"
ON_AMBER = "#1a1204"
SECOND = "#2f3d6e"
SECOND_H = "#3a4a85"
TEAL = "#2dd4bf"
RED = "#f87171"
RED_BTN = "#b93a3a"
RED_BTN_H = "#d04a4a"
YELLOW = "#fbbf24"
BLUE = "#60a5fa"

STATUS_WARNA = {"idle": FG_DIM, "busy": AMBER, "ok": TEAL, "err": RED, "warn": YELLOW}
STEP_STYLE = {
    "idle": (BG_CARD_ALT, FG_DIM),
    "aktif": (AMBER, ON_AMBER),
    "ok": ("#123b36", TEAL),
    "gagal": ("#4a1b1b", RED),
}

# Syntax highlighting
WARNA_KEYWORD = "#c792ea"
WARNA_TIPE = "#2dd4bf"
WARNA_STRING = "#a5e075"
WARNA_COMMENT = "#5c6485"
WARNA_FUNGSI = "#60a5fa"
WARNA_ANGKA = "#f78c6c"
WARNA_PREPROC = "#ff6ac1"

CPP_KEYWORDS = [
    "return", "if", "else", "for", "while", "do", "switch", "case", "default",
    "break", "continue", "struct", "class", "public", "private", "protected",
    "true", "false", "const", "static", "volatile", "typedef", "enum", "new",
    "delete", "namespace", "using", "nullptr", "NULL", "HIGH", "LOW", "INPUT",
    "OUTPUT", "INPUT_PULLUP", "LED_BUILTIN",
]
CPP_TIPE = [
    "void", "int", "float", "double", "char", "bool", "boolean", "byte", "long",
    "short", "unsigned", "signed", "String", "size_t", "uint8_t", "uint16_t",
    "uint32_t", "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t", "word",
]
ARDUINO_FUNGSI_BAWAAN = [
    "setup", "loop", "digitalWrite", "digitalRead", "analogWrite", "analogRead",
    "pinMode", "delay", "delayMicroseconds", "millis", "micros", "Serial", "Wire",
    "SPI", "map", "constrain", "min", "max", "abs", "random", "randomSeed",
]

RE_KEYWORD = re.compile(r"\b(?:" + "|".join(CPP_KEYWORDS) + r")\b")
RE_TIPE = re.compile(r"\b(?:" + "|".join(CPP_TIPE) + r")\b")
RE_BUILTIN = re.compile(r"\b(?:" + "|".join(ARDUINO_FUNGSI_BAWAAN) + r")\b")
RE_FUNGSI = re.compile(r"\b([A-Za-z_]\w*)\s*(?=\()")
RE_ANGKA = re.compile(r"\b(?:0[xX][0-9A-Fa-f]+|0[bB][01]+|\d+\.?\d*(?:[eE][+-]?\d+)?[fFuUlL]*)\b")
RE_PREPROC = re.compile(r"^[ \t]*#[ \t]*\w+", re.M)
RE_INCLUDE = re.compile(r"^[ \t]*#[ \t]*include[ \t]*(<[^>\n]*>)", re.M)
RE_TOKEN = re.compile(
    r"(?P<komentar>//[^\n]*|/\*.*?\*/)"
    r"|(?P<string>\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')",
    re.S,
)
TAG_SYNTAX = ("fungsi", "tipe", "keyword", "angka", "preproc", "string", "komentar")

RE_FLASH = re.compile(r"Sketch uses (\d+) bytes \((\d+)%\) of program storage space\. Maximum is (\d+) bytes")
RE_RAM = re.compile(r"Global variables use (\d+) bytes \((\d+)%\) of dynamic memory.*?Maximum is (\d+) bytes")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

MAX_TAMPIL_BYTE = 64 * 1024
CONFIG_PATH = os.path.expanduser("~/.config/arduino_cli_ide.json")
EKSTENSI_SKETCH = (".ino", ".pde")

TEMPLATE_SKETCH = {
    "Kosong": "void setup() {\n  \n}\n\nvoid loop() {\n  \n}\n",
    "Blink LED": (
        "// Blink LED bawaan board\n"
        "void setup() {\n"
        "  pinMode(LED_BUILTIN, OUTPUT);\n"
        "}\n\n"
        "void loop() {\n"
        "  digitalWrite(LED_BUILTIN, HIGH);\n"
        "  delay(500);\n"
        "  digitalWrite(LED_BUILTIN, LOW);\n"
        "  delay(500);\n"
        "}\n"
    ),
    "Serial Hello": (
        "// Kirim teks lewat Serial Monitor\n"
        "int hitung = 0;\n\n"
        "void setup() {\n"
        "  Serial.begin(115200);\n"
        "}\n\n"
        "void loop() {\n"
        "  Serial.print(\"Hello, hitungan ke-\");\n"
        "  Serial.println(hitung++);\n"
        "  delay(1000);\n"
        "}\n"
    ),
    "OLED SSD1306 (ESP32)": (
        "#include <Wire.h>\n"
        "#include <Adafruit_GFX.h>\n"
        "#include <Adafruit_SSD1306.h>\n\n"
        "#define SCREEN_WIDTH 128\n"
        "#define SCREEN_HEIGHT 64\n"
        "#define OLED_ADDR 0x3C\n\n"
        "Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);\n\n"
        "void setup() {\n"
        "  Serial.begin(115200);\n"
        "  Wire.begin(21, 22);  // SDA, SCL ESP32\n"
        "  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {\n"
        "    Serial.println(\"OLED tidak ditemukan\");\n"
        "    while (true) delay(100);\n"
        "  }\n"
        "  display.clearDisplay();\n"
        "  display.setTextSize(2);\n"
        "  display.setTextColor(SSD1306_WHITE);\n"
        "  display.setCursor(0, 20);\n"
        "  display.println(\"Halo ESP32\");\n"
        "  display.display();\n"
        "}\n\n"
        "void loop() {\n"
        "}\n"
    ),
}

SHORTCUT_BANTUAN = """\
DRAG & DROP
  Lepaskan file .ino / folder sketch ke jendela mana saja
  (banyak file sekaligus -> masuk Shelf, yang pertama dibuka)
  File lain (.bin/.hex/dll) -> ditampilkan sebagai hex dump

FILE
  Ctrl+N          Sketch baru
  Ctrl+O          Buka sketch
  Ctrl+S          Simpan
  Ctrl+Shift+S    Simpan sebagai

BUILD
  Ctrl+R          Verify (compile)
  Ctrl+U          Upload
  F6              Serial Monitor start/stop
  Ctrl+H          Lihat hex file

EDITOR
  Ctrl+F          Cari / Ganti
  Ctrl+/          Toggle komentar
  Tab / Shift+Tab Indent / unindent
  Ctrl + / -      Zoom font (atau Ctrl+scroll)
  Ctrl+0          Reset zoom
"""


# ============================================================
# HEX DUMP
# ============================================================
def hex_dump(data, lebar=16):
    baris = []
    for i in range(0, len(data), lebar):
        potongan = data[i:i + lebar]
        hex_bagian = " ".join(f"{b:02X}" for b in potongan)
        ascii_bagian = "".join(chr(b) if 32 <= b < 127 else "." for b in potongan)
        baris.append(f"{i:08X}  {hex_bagian:<{lebar * 3 - 1}}  |{ascii_bagian}|")
    return "\n".join(baris) + ("\n" if baris else "")


def hex_dump_file(path, batas=None):
    with open(path, "rb") as f:
        data = f.read() if batas is None else f.read(batas)
    return hex_dump(data)


def muat_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def fmt_byte(n):
    if n >= 1048576:
        return f"{n / 1048576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def singkat(teks, n=64):
    return teks if len(teks) <= n else "…" + teks[-(n - 1):]


# ============================================================
# WIDGET HELPER
# ============================================================
class FlatButton(tk.Label):
    """Tombol flat modern dengan efek hover."""

    def __init__(self, parent, text, command, bg=BG_CARD, hover=BG_HOVER,
                 fg=FG_TEXT, font=None, padx=12, pady=5):
        super().__init__(parent, text=text, bg=bg, fg=fg, font=font,
                         padx=padx, pady=pady, cursor="hand2")
        self._bg, self._hover, self._fg, self._cmd = bg, hover, fg, command
        self._enabled = True
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonRelease-1>", self._klik)

    def _enter(self, _e):
        if self._enabled:
            self.config(bg=self._hover)

    def _leave(self, _e):
        self.config(bg=self._bg)

    def _klik(self, e):
        if (self._enabled and self._cmd
                and 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height()):
            self._cmd()

    def set_colors(self, bg, hover):
        self._bg, self._hover = bg, hover
        self.config(bg=bg)

    def set_enabled(self, aktif):
        self._enabled = aktif
        self.config(fg=self._fg if aktif else FG_DIM,
                    cursor="hand2" if aktif else "arrow", bg=self._bg)


class Tooltip:
    def __init__(self, widget, teks):
        self.widget, self.teks, self.tip, self.job = widget, teks, None, None
        widget.bind("<Enter>", self._jadwal, add="+")
        widget.bind("<Leave>", self._sembunyi, add="+")
        widget.bind("<ButtonPress>", self._sembunyi, add="+")

    def _jadwal(self, _e=None):
        self._batal()
        self.job = self.widget.after(600, self._tampil)

    def _batal(self):
        if self.job:
            try:
                self.widget.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None

    def _tampil(self):
        if self.tip:
            return
        try:
            x = self.widget.winfo_rootx() + 8
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            tk.Label(self.tip, text=self.teks, bg=BG_CARD_ALT, fg=FG_TEXT, bd=1,
                     relief="solid", padx=8, pady=3).pack()
        except tk.TclError:
            self.tip = None

    def _sembunyi(self, _e=None):
        self._batal()
        if self.tip:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


class Meter(tk.Frame):
    """Bar penggunaan memori (Flash / RAM)."""

    def __init__(self, parent, judul, bg, fnt):
        super().__init__(parent, bg=bg)
        self._persen = None
        tk.Label(self, text=judul, bg=bg, fg=FG_DIM, font=fnt, width=6, anchor="w").pack(side=tk.LEFT)
        self.canvas = tk.Canvas(self, height=8, bg=BG_BORDER, highlightthickness=0, bd=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.lbl = tk.Label(self, text="—", bg=bg, fg=FG_TEXT, font=fnt, anchor="e", width=24)
        self.lbl.pack(side=tk.RIGHT)
        self.canvas.bind("<Configure>", lambda e: self._gambar())

    def set(self, pakai, maks, persen):
        self._persen = persen
        self.lbl.config(text=f"{fmt_byte(pakai)} / {fmt_byte(maks)}  ({persen}%)")
        self._gambar()

    def reset(self):
        self._persen = None
        self.lbl.config(text="—")
        self._gambar()

    def _gambar(self):
        c = self.canvas
        c.delete("all")
        if self._persen is None:
            return
        w, h = c.winfo_width(), c.winfo_height()
        p = self._persen
        warna = TEAL if p < 70 else (AMBER if p < 90 else RED)
        c.create_rectangle(0, 0, max(3, int(w * min(p, 100) / 100)), h, fill=warna, outline="")


# ============================================================
# APLIKASI UTAMA
# ============================================================
class ArduinoCliIDE:
    def __init__(self, root, dnd=False):
        self.root = root
        self.dnd_aktif = dnd
        self.root.title("untitled.ino — Mission Control")
        self.root.geometry("1280x800")
        self.root.minsize(1000, 640)
        self.root.configure(bg=BG_APP)

        cfg = muat_config()
        self.fqbn = cfg.get("fqbn", DEFAULT_FQBN)
        self.port = cfg.get("port", DEFAULT_PORT)
        self.baud = cfg.get("baud", 115200)
        self.recent = [p for p in cfg.get("recent", []) if isinstance(p, str)]
        self.last_dir = cfg.get("last_dir", os.path.expanduser("~"))
        ukuran_font = cfg.get("font_size", 12)

        self.sketch_folder = None
        self.ino_path = None
        self.dirty = False
        self.monitor_proc = None
        self.monitor_queue = queue.Queue()
        self.hex_terakhir = None
        self.sibuk = False
        self.task_proc = None
        self.task_queue = queue.Queue()
        self._dibatalkan = False
        self._cb_ok = self._cb_gagal = self._cb_selesai = None
        self._mode = "lain"
        self._ps = {"simpan": "idle", "compile": "idle", "upload": "idle"}
        self._hl_job = None
        self._dnd_job = None
        self._jumlah_baris = 0
        self._folder_build = None
        self._tab = "out"

        fam = set(font.families(self.root))

        def pilih(kandidat, default):
            for k in kandidat:
                if k in fam:
                    return k
            return default

        fam_editor = pilih(["JetBrains Mono", "Fira Code", "Cascadia Code", "Source Code Pro",
                            "Hack", "DejaVu Sans Mono", "Noto Sans Mono"], "monospace")
        self.fam_ui = pilih(["Inter", "Noto Sans", "Cantarell", "DejaVu Sans", "Segoe UI"], "sans-serif")
        self.font_editor = font.Font(family=fam_editor, size=ukuran_font)
        self.font_console = font.Font(family=fam_editor, size=10)
        self.font_ui = font.Font(family=self.fam_ui, size=10)
        self.font_ui_bold = font.Font(family=self.fam_ui, size=10, weight="bold")
        self.font_small = font.Font(family=self.fam_ui, size=9)
        self.font_cap = font.Font(family=self.fam_ui, size=8, weight="bold")
        self.font_title = font.Font(family=self.fam_ui, size=13, weight="bold")

        self._setup_style()
        self._buat_menu()
        self._buat_header()
        self._buat_status_bar()

        self.body = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG_BORDER,
                                   sashwidth=4, bd=0, sashrelief="flat")
        self.body.pack(fill=tk.BOTH, expand=True)
        self._buat_editor()
        self._buat_find_bar()
        self._buat_overlay()
        self._buat_panel()
        self._buat_shortcut()
        self._setup_clipboard()
        self._setup_dnd()
        self.root.protocol("WM_DELETE_WINDOW", self._tutup)

        self._set_isi(TEMPLATE_SKETCH["Kosong"])
        self._update_title()
        self._tampil_tab("out")
        self._tulis_output("Mission Control siap.\n", tag="info")
        self._tulis_output("Ctrl+N sketch baru  •  Ctrl+R verify  •  Ctrl+U upload  •  F6 serial monitor\n",
                           tag="dim")
        if self.dnd_aktif:
            self._tulis_output("Seret file .ino ke jendela ini untuk membukanya.\n", tag="dim")
        else:
            self._tulis_output("Drag & drop nonaktif. Aktifkan dengan: pip install tkinterdnd2\n", tag="warn")
        self._watch_port()

    # --------------------------------------------------------
    # STYLE
    # --------------------------------------------------------
    def _setup_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TScrollbar", troughcolor=BG_EDITOR, background="#363c5a",
                    bordercolor=BG_EDITOR, lightcolor="#363c5a", darkcolor="#363c5a",
                    arrowcolor=FG_DIM, relief="flat", arrowsize=12)
        s.map("TScrollbar", background=[("active", "#4c5480"), ("pressed", "#5b6494")])
        s.configure("TCombobox", fieldbackground=BG_INPUT, background=BG_INPUT,
                    foreground=FG_TEXT, arrowcolor=FG_TEXT, bordercolor=BG_BORDER,
                    lightcolor=BG_INPUT, darkcolor=BG_INPUT,
                    selectbackground=BG_INPUT, selectforeground=FG_TEXT)
        s.map("TCombobox", fieldbackground=[("readonly", BG_INPUT)],
              foreground=[("readonly", FG_TEXT)], background=[("active", BG_HOVER)])
        s.configure("Amber.Horizontal.TProgressbar", troughcolor=BG_BORDER, background=AMBER,
                    bordercolor=BG_BORDER, lightcolor=AMBER, darkcolor=AMBER, thickness=4)
        self.root.option_add("*TCombobox*Listbox.background", BG_INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", FG_TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", AMBER)
        self.root.option_add("*TCombobox*Listbox.selectForeground", ON_AMBER)
        self.root.option_add("*TCombobox*Listbox.font", self.font_ui)

    # --------------------------------------------------------
    # MENU (popup dari tombol ☰, bukan menubar)
    # --------------------------------------------------------
    def _menu(self, parent):
        return tk.Menu(parent, tearoff=0, bg=BG_CARD, fg=FG_TEXT, bd=0, relief="flat",
                       activebackground=AMBER, activeforeground=ON_AMBER, font=self.font_ui)

    def _buat_menu(self):
        utama = self._menu(self.root)
        self.menu_utama = utama

        m = self._menu(utama)
        m.add_command(label="New Sketch...", command=self.sketch_baru, accelerator="Ctrl+N")
        m.add_command(label="Open Sketch...", command=self.sketch_buka, accelerator="Ctrl+O")
        self.menu_recent = self._menu(m)
        m.add_cascade(label="Open Recent", menu=self.menu_recent)
        m.add_separator()
        m.add_command(label="Save", command=self.sketch_simpan, accelerator="Ctrl+S")
        m.add_command(label="Save As...", command=self.sketch_simpan_sebagai, accelerator="Ctrl+Shift+S")
        m.add_separator()
        m.add_command(label="Exit", command=self._tutup)
        utama.add_cascade(label="File", menu=m)
        self._refresh_recent_menu()

        m = self._menu(utama)
        m.add_command(label="Undo", command=lambda: self.text_area_undo(), accelerator="Ctrl+Z")
        m.add_command(label="Redo", command=lambda: self.text_area_redo(), accelerator="Ctrl+Y")
        m.add_separator()
        m.add_command(label="Cut", command=lambda: self._potong(self.text_area), accelerator="Ctrl+X")
        m.add_command(label="Copy", command=lambda: self._salin(self.text_area), accelerator="Ctrl+C")
        m.add_command(label="Paste", command=lambda: self._tempel(self.text_area), accelerator="Ctrl+V")
        m.add_command(label="Select All", command=lambda: self._pilih_semua(self.text_area), accelerator="Ctrl+A")
        m.add_separator()
        m.add_command(label="Find / Replace", command=self.tampil_cari, accelerator="Ctrl+F")
        m.add_command(label="Toggle Comment", command=self.toggle_komentar, accelerator="Ctrl+/")
        utama.add_cascade(label="Edit", menu=m)

        m = self._menu(utama)
        m.add_command(label="Verify", command=self.verify_kode, accelerator="Ctrl+R")
        m.add_command(label="Upload", command=self.upload_kode, accelerator="Ctrl+U")
        m.add_separator()
        m.add_command(label="Serial Monitor (Start/Stop)", command=self.monitor_toggle, accelerator="F6")
        m.add_command(label="List Connected Boards", command=self.list_boards)
        m.add_command(label="Refresh Port", command=self._refresh_ports_manual)
        utama.add_cascade(label="Build", menu=m)

        m = self._menu(utama)
        m.add_command(label="Zoom In", command=lambda: self.zoom(1), accelerator="Ctrl++")
        m.add_command(label="Zoom Out", command=lambda: self.zoom(-1), accelerator="Ctrl+-")
        m.add_command(label="Reset Zoom", command=self.zoom_reset, accelerator="Ctrl+0")
        utama.add_cascade(label="View", menu=m)

        m = self._menu(utama)
        m.add_command(label="Lihat Hex File...", command=self.hex_buka_file, accelerator="Ctrl+H")
        m.add_command(label="Hex Hasil Compile", command=self.hex_hasil_compile)
        m.add_command(label="Simpan Hex ke .txt...", command=self.hex_simpan_txt)
        utama.add_cascade(label="Hex", menu=m)

        utama.add_separator()
        utama.add_command(label="Keyboard Shortcuts & Drag-Drop", command=self.tampil_bantuan)

    def _tampil_menu(self):
        x = self.btn_menu.winfo_rootx()
        y = self.btn_menu.winfo_rooty() + self.btn_menu.winfo_height()
        try:
            self.menu_utama.tk_popup(x, y)
        finally:
            self.menu_utama.grab_release()

    def _refresh_recent_menu(self):
        self.menu_recent.delete(0, "end")
        if not self.recent:
            self.menu_recent.add_command(label="(kosong)", state="disabled")
            return
        for p in self.recent:
            self.menu_recent.add_command(label=p, command=lambda x=p: self.sketch_buka(x))

    def _tambah_recent(self, path):
        if path in self.recent:
            self.recent.remove(path)
        self.recent.insert(0, path)
        self.recent = self.recent[:10]
        self._refresh_recent_menu()
        self._refresh_shelf()
        self._simpan_config()

    def tampil_bantuan(self):
        messagebox.showinfo("Keyboard Shortcuts & Drag-Drop", SHORTCUT_BANTUAN, parent=self.root)

    # --------------------------------------------------------
    # HEADER + SHELF
    # --------------------------------------------------------
    def _buat_header(self):
        h = tk.Frame(self.root, bg=BG_APP)
        h.pack(fill=tk.X, side=tk.TOP)

        self.btn_menu = FlatButton(h, "☰", self._tampil_menu, bg=BG_APP, hover=BG_HOVER,
                                   font=self.font_title, padx=16, pady=8)
        self.btn_menu.pack(side=tk.LEFT)
        Tooltip(self.btn_menu, "Menu")

        blok = tk.Frame(h, bg=BG_APP)
        blok.pack(side=tk.LEFT, padx=(6, 20), pady=6)
        self.label_tab = tk.Label(blok, text="untitled.ino", fg=FG_TEXT, bg=BG_APP,
                                  font=self.font_title, anchor="w")
        self.label_tab.pack(anchor="w")
        self.label_path = tk.Label(blok, text="Belum disimpan", fg=FG_DIM, bg=BG_APP,
                                   font=self.font_small, anchor="w")
        self.label_path.pack(anchor="w")

        kanan = tk.Frame(h, bg=BG_APP)
        kanan.pack(side=tk.RIGHT, padx=10)
        for teks, cmd, tip in (("New", self.sketch_baru, "Sketch baru (Ctrl+N)"),
                               ("Open", self.sketch_buka, "Buka sketch (Ctrl+O)"),
                               ("Save", self.sketch_simpan, "Simpan (Ctrl+S)")):
            b = FlatButton(kanan, teks, cmd, bg=BG_APP, hover=BG_HOVER, font=self.font_ui)
            b.pack(side=tk.LEFT, padx=1)
            Tooltip(b, tip)

        self.shelf = tk.Frame(h, bg=BG_APP)
        self.shelf.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._refresh_shelf()

        tk.Frame(self.root, bg=BG_BORDER, height=1).pack(fill=tk.X, side=tk.TOP)

    def _refresh_shelf(self):
        for w in self.shelf.winfo_children():
            w.destroy()
        tk.Label(self.shelf, text="SHELF", bg=BG_APP, fg=FG_DIM, font=self.font_cap).pack(
            side=tk.LEFT, padx=(0, 8))
        if not self.recent:
            tk.Label(self.shelf, text="belum ada — seret file .ino ke sini", bg=BG_APP, fg=FG_DIM,
                     font=self.font_small).pack(side=tk.LEFT)
            return
        for p in self.recent[:6]:
            aktif = (p == self.ino_path)
            nama = os.path.splitext(os.path.basename(p))[0]
            nama = nama if len(nama) <= 16 else nama[:15] + "…"
            chip = FlatButton(self.shelf, nama, lambda x=p: self.sketch_buka(x),
                              bg=BG_CARD_ALT if aktif else BG_CARD, hover=BG_HOVER,
                              fg=AMBER if aktif else FG_TEXT, font=self.font_small, padx=10, pady=4)
            chip.pack(side=tk.LEFT, padx=3)
            Tooltip(chip, p)

    # --------------------------------------------------------
    # STATUS BAR
    # --------------------------------------------------------
    def _buat_status_bar(self):
        sb = tk.Frame(self.root, bg=BG_STATUSBAR)
        sb.pack(fill=tk.X, side=tk.BOTTOM)
        self.dot_status = tk.Canvas(sb, width=8, height=8, bg=BG_STATUSBAR, highlightthickness=0)
        self.dot_status.pack(side=tk.LEFT, padx=(12, 4))
        self._dot_status_id = self.dot_status.create_oval(0, 0, 8, 8, fill=FG_DIM, outline="")
        self.lbl_status = tk.Label(sb, text="Siap", fg=FG_DIM, bg=BG_STATUSBAR, font=self.font_small,
                                   anchor="w", pady=3)
        self.lbl_status.pack(side=tk.LEFT)
        self.lbl_pos = tk.Label(sb, text="Ln 1, Col 1", fg=FG_DIM, bg=BG_STATUSBAR,
                                font=self.font_small, padx=12)
        self.lbl_pos.pack(side=tk.RIGHT)
        hint = ("⇩ Seret file .ino ke jendela ini" if self.dnd_aktif
                else "Drag & drop: pip install tkinterdnd2")
        tk.Label(sb, text=hint, fg=FG_DIM, bg=BG_STATUSBAR, font=self.font_small,
                 padx=12).pack(side=tk.RIGHT)

    def _status(self, teks, jenis="idle"):
        warna = STATUS_WARNA.get(jenis, FG_DIM)
        self.lbl_status.config(text=teks, fg=warna)
        self.dot_status.itemconfig(self._dot_status_id, fill=warna)

    def _reset_status_idle(self):
        if not self.sibuk:
            self._status("Siap")

    # --------------------------------------------------------
    # EDITOR
    # --------------------------------------------------------
    def _buat_editor(self):
        self.editor_wrap = tk.Frame(self.body, bg=BG_EDITOR)
        self.body.add(self.editor_wrap, stretch="always", minsize=420)

        ef = tk.Frame(self.editor_wrap, bg=BG_EDITOR)
        self.editor_frame = ef
        ef.pack(fill=tk.BOTH, expand=True)
        ef.grid_rowconfigure(0, weight=1)
        ef.grid_columnconfigure(2, weight=1)

        self.line_numbers = tk.Text(
            ef, width=5, padx=6, pady=8, takefocus=0, bd=0, highlightthickness=0,
            background=BG_EDITOR, foreground="#4a516f", state="disabled", cursor="arrow",
            wrap="none", font=self.font_editor)
        self.line_numbers.tag_configure("r", justify="right")
        self.line_numbers.grid(row=0, column=0, sticky="ns")
        tk.Frame(ef, bg=BG_BORDER, width=1).grid(row=0, column=1, sticky="ns")

        self.text_area = tk.Text(
            ef, wrap="none", undo=True, maxundo=-1, padx=10, pady=8,
            background=BG_EDITOR, foreground=FG_TEXT, insertbackground=AMBER, insertwidth=2,
            selectbackground=BG_SELECT, inactiveselectbackground="#2a3354",
            font=self.font_editor, bd=0, highlightthickness=0)
        self.text_area.grid(row=0, column=2, sticky="nsew")

        self.vsb = ttk.Scrollbar(ef, orient=tk.VERTICAL, command=self.text_area.yview)
        self.vsb.grid(row=0, column=3, sticky="ns")
        hsb = ttk.Scrollbar(ef, orient=tk.HORIZONTAL, command=self.text_area.xview)
        hsb.grid(row=1, column=2, sticky="ew")
        self.text_area.config(yscrollcommand=self._on_yscroll, xscrollcommand=hsb.set)

        ta = self.text_area
        ta.tag_configure("curline", background=BG_CURLINE)
        ta.tag_configure("fungsi", foreground=WARNA_FUNGSI)
        ta.tag_configure("tipe", foreground=WARNA_TIPE)
        ta.tag_configure("keyword", foreground=WARNA_KEYWORD)
        ta.tag_configure("angka", foreground=WARNA_ANGKA)
        ta.tag_configure("preproc", foreground=WARNA_PREPROC)
        ta.tag_configure("string", foreground=WARNA_STRING)
        ta.tag_configure("komentar", foreground=WARNA_COMMENT)
        ta.tag_configure("cari", background="#44507a")
        ta.tag_configure("cari_aktif", background="#9e6a03")
        ta.tag_lower("curline")
        ta.tag_raise("sel")

        ta.bind("<KeyRelease>", self._on_key_release)
        ta.bind("<ButtonRelease-1>", self._update_cursor)
        ta.bind("<<Modified>>", self._on_modified)
        ta.bind("<KeyPress>", self._on_keypress)
        ta.bind("<Return>", self._on_return)
        ta.bind("<KP_Enter>", self._on_return)
        ta.bind("<Tab>", self._on_tab)
        ta.bind("<ISO_Left_Tab>", self._on_shift_tab)
        ta.bind("<Shift-Tab>", self._on_shift_tab)
        for seq in ("<Control-Button-4>", "<Control-Button-5>", "<Control-MouseWheel>"):
            ta.bind(seq, self._on_ctrl_wheel)
        for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self.line_numbers.bind(seq, self._wheel_ln)

    def _on_yscroll(self, first, last):
        self.vsb.set(first, last)
        self.line_numbers.yview_moveto(first)

    def _wheel_ln(self, e):
        unit = -3 if (e.num == 4 or e.delta > 0) else 3
        self.text_area.yview_scroll(unit, "units")
        return "break"

    def _on_ctrl_wheel(self, e):
        self.zoom(1 if (e.num == 4 or e.delta > 0) else -1)
        return "break"

    def _on_modified(self, _e=None):
        self._set_dirty(bool(self.text_area.edit_modified()))

    def _set_dirty(self, nilai):
        if nilai != self.dirty:
            self.dirty = nilai
            self._update_title()

    def _on_key_release(self, _e=None):
        self._update_line_numbers()
        self._update_cursor()
        self._jadwalkan_highlight()

    def _update_line_numbers(self):
        jumlah = int(self.text_area.index("end-1c").split(".")[0])
        if jumlah != self._jumlah_baris:
            self._jumlah_baris = jumlah
            self.line_numbers.config(state="normal", width=max(3, len(str(jumlah))) + 2)
            self.line_numbers.delete("1.0", "end")
            self.line_numbers.insert("1.0", "\n".join(str(i) for i in range(1, jumlah + 1)), "r")
            self.line_numbers.config(state="disabled")
        self.line_numbers.yview_moveto(self.text_area.yview()[0])

    def _update_cursor(self, _e=None):
        ta = self.text_area
        ta.tag_remove("curline", "1.0", "end")
        ta.tag_add("curline", "insert linestart", "insert lineend+1c")
        baris, kolom = ta.index("insert").split(".")
        self.lbl_pos.config(text=f"Ln {baris}, Col {int(kolom) + 1}")

    def _jadwalkan_highlight(self):
        if self._hl_job:
            self.root.after_cancel(self._hl_job)
        self._hl_job = self.root.after(120, self._highlight_syntax)

    def _highlight_syntax(self):
        self._hl_job = None
        ta = self.text_area
        for tag in TAG_SYNTAX:
            ta.tag_remove(tag, "1.0", "end")
        isi = ta.get("1.0", "end-1c")

        def tandai(tag, m, grup=0):
            ta.tag_add(tag, f"1.0+{m.start(grup)}c", f"1.0+{m.end(grup)}c")

        for m in RE_FUNGSI.finditer(isi):
            tandai("fungsi", m, 1)
        for m in RE_BUILTIN.finditer(isi):
            tandai("fungsi", m)
        for m in RE_TIPE.finditer(isi):
            tandai("tipe", m)
        for m in RE_KEYWORD.finditer(isi):
            tandai("keyword", m)
        for m in RE_ANGKA.finditer(isi):
            tandai("angka", m)
        for m in RE_PREPROC.finditer(isi):
            tandai("preproc", m)
        for m in RE_INCLUDE.finditer(isi):
            tandai("string", m, 1)
        for m in RE_TOKEN.finditer(isi):
            tandai(m.lastgroup, m)

    # ---- perilaku editing ----
    def _on_keypress(self, e):
        ch = e.char
        if not ch or len(ch) != 1 or ch < " ":
            return None
        ta = self.text_area
        if ta.tag_ranges("sel"):
            return None
        sesudah = ta.get("insert", "insert+1c")
        if ch in ")]}\"" and sesudah == ch:
            ta.mark_set("insert", "insert+1c")
            return "break"
        pasangan = {"(": ")", "[": "]", "{": "}", '"': '"'}
        if ch in pasangan:
            if ch == '"' and ta.get("insert-1c", "insert").isalnum():
                return None
            ta.insert("insert", ch + pasangan[ch])
            ta.mark_set("insert", "insert-1c")
            return "break"
        return None

    def _on_return(self, _e=None):
        ta = self.text_area
        if ta.tag_ranges("sel"):
            ta.delete("sel.first", "sel.last")
        sebelum = ta.get("insert linestart", "insert")
        indent = re.match(r"[ \t]*", sebelum).group(0)
        tambah = "  " if sebelum.rstrip().endswith("{") else ""
        sesudah = ta.get("insert", "insert lineend")
        if tambah and sesudah.lstrip().startswith("}"):
            ta.insert("insert", "\n" + indent + tambah + "\n" + indent)
            ta.mark_set("insert", "insert-1l lineend")
        else:
            ta.insert("insert", "\n" + indent + tambah)
        ta.see("insert")
        self._on_key_release()
        return "break"

    def _baris_terpilih(self):
        ta = self.text_area
        if ta.tag_ranges("sel"):
            a = int(ta.index("sel.first").split(".")[0])
            b = int(ta.index("sel.last").split(".")[0])
            if ta.index("sel.last").endswith(".0") and b > a:
                b -= 1
            return a, b
        n = int(ta.index("insert").split(".")[0])
        return n, n

    def _on_tab(self, _e=None):
        ta = self.text_area
        if ta.tag_ranges("sel"):
            a, b = self._baris_terpilih()
            for i in range(a, b + 1):
                ta.insert(f"{i}.0", "  ")
        else:
            ta.insert("insert", "  ")
        self._on_key_release()
        return "break"

    def _on_shift_tab(self, _e=None):
        ta = self.text_area
        a, b = self._baris_terpilih()
        for i in range(a, b + 1):
            awal = ta.get(f"{i}.0", f"{i}.2")
            n = len(awal) - len(awal.lstrip(" "))
            if n:
                ta.delete(f"{i}.0", f"{i}.{n}")
        self._on_key_release()
        return "break"

    def toggle_komentar(self):
        ta = self.text_area
        a, b = self._baris_terpilih()
        baris = [ta.get(f"{i}.0", f"{i}.end") for i in range(a, b + 1)]
        semua = all((not l.strip()) or l.strip().startswith("//") for l in baris)
        for i, l in zip(range(a, b + 1), baris):
            if not l.strip():
                continue
            if semua:
                baru = re.sub(r"^(\s*)// ?", r"\1", l, count=1)
            else:
                n = len(l) - len(l.lstrip())
                baru = l[:n] + "// " + l[n:]
            ta.delete(f"{i}.0", f"{i}.end")
            ta.insert(f"{i}.0", baru)
        self._on_key_release()

    def zoom(self, delta):
        ukuran = max(7, min(32, int(self.font_editor.cget("size")) + delta))
        self.font_editor.configure(size=ukuran)
        self._simpan_config()

    def zoom_reset(self):
        self.font_editor.configure(size=12)
        self._simpan_config()

    def text_area_undo(self):
        try:
            self.text_area.edit_undo()
            self._on_key_release()
        except tk.TclError:
            pass

    def text_area_redo(self):
        try:
            self.text_area.edit_redo()
            self._on_key_release()
        except tk.TclError:
            pass

    def _set_isi(self, teks):
        ta = self.text_area
        ta.delete("1.0", "end")
        ta.insert("1.0", teks)
        ta.edit_reset()
        ta.edit_modified(False)
        ta.mark_set("insert", "1.0")
        self._jumlah_baris = 0
        self._update_line_numbers()
        self._update_cursor()
        self._highlight_syntax()

    # --------------------------------------------------------
    # FIND / REPLACE
    # --------------------------------------------------------
    def _buat_find_bar(self):
        self.find_bar = tk.Frame(self.editor_wrap, bg=BG_PANEL)
        self.var_cari = tk.StringVar()
        self.var_ganti = tk.StringVar()
        baris = tk.Frame(self.find_bar, bg=BG_PANEL)
        baris.pack(fill=tk.X, padx=10, pady=6)

        def entry(var, width):
            return tk.Entry(baris, textvariable=var, width=width, bg=BG_INPUT, fg=FG_TEXT,
                            insertbackground=AMBER, relief="flat", font=self.font_ui,
                            highlightthickness=1, highlightbackground=BG_BORDER,
                            highlightcolor=AMBER)

        tk.Label(baris, text="Cari", bg=BG_PANEL, fg=FG_DIM, font=self.font_small).pack(side=tk.LEFT)
        self.ent_cari = entry(self.var_cari, 22)
        self.ent_cari.pack(side=tk.LEFT, padx=6, ipady=3)
        FlatButton(baris, "↓", lambda: self._cari_berikut(1), bg=BG_CARD, hover=BG_HOVER,
                   font=self.font_ui, padx=8, pady=3).pack(side=tk.LEFT, padx=1)
        FlatButton(baris, "↑", lambda: self._cari_berikut(-1), bg=BG_CARD, hover=BG_HOVER,
                   font=self.font_ui, padx=8, pady=3).pack(side=tk.LEFT, padx=1)
        self.lbl_hasil = tk.Label(baris, text="", bg=BG_PANEL, fg=FG_DIM, font=self.font_small, width=11)
        self.lbl_hasil.pack(side=tk.LEFT)
        tk.Label(baris, text="Ganti", bg=BG_PANEL, fg=FG_DIM, font=self.font_small).pack(side=tk.LEFT, padx=(6, 0))
        self.ent_ganti = entry(self.var_ganti, 16)
        self.ent_ganti.pack(side=tk.LEFT, padx=6, ipady=3)
        FlatButton(baris, "Replace", self._ganti, bg=BG_CARD, hover=BG_HOVER,
                   font=self.font_small, pady=3).pack(side=tk.LEFT, padx=1)
        FlatButton(baris, "All", self._ganti_semua, bg=BG_CARD, hover=BG_HOVER,
                   font=self.font_small, pady=3).pack(side=tk.LEFT, padx=1)
        FlatButton(baris, "✕", self.tutup_cari, bg=BG_PANEL, hover=BG_HOVER,
                   font=self.font_ui, padx=8, pady=3).pack(side=tk.RIGHT)

        self.ent_cari.bind("<KeyRelease>", lambda e: self._cari_sorot())
        self.ent_cari.bind("<Return>", lambda e: self._cari_berikut(1))
        self.ent_cari.bind("<Shift-Return>", lambda e: self._cari_berikut(-1))
        self.ent_cari.bind("<Escape>", lambda e: self.tutup_cari())
        self.ent_ganti.bind("<Return>", lambda e: self._ganti())
        self.ent_ganti.bind("<Escape>", lambda e: self.tutup_cari())

    def tampil_cari(self):
        if not self.find_bar.winfo_ismapped():
            self.find_bar.pack(fill=tk.X, before=self.editor_frame)
        ta = self.text_area
        if ta.tag_ranges("sel"):
            teks = ta.get("sel.first", "sel.last")
            if "\n" not in teks and teks:
                self.var_cari.set(teks)
        self.ent_cari.focus_set()
        self.ent_cari.select_range(0, "end")
        self._cari_sorot()

    def tutup_cari(self):
        if self.find_bar.winfo_ismapped():
            self.find_bar.pack_forget()
        self.text_area.tag_remove("cari", "1.0", "end")
        self.text_area.focus_set()

    def _cari_sorot(self):
        ta = self.text_area
        ta.tag_remove("cari", "1.0", "end")
        q = self.var_cari.get()
        if not q:
            self.lbl_hasil.config(text="")
            return
        n, idx = 0, "1.0"
        while n < 5000:
            pos = ta.search(q, idx, "end", nocase=True)
            if not pos:
                break
            akhir = f"{pos}+{len(q)}c"
            ta.tag_add("cari", pos, akhir)
            idx = akhir
            n += 1
        self.lbl_hasil.config(text=f"{n} hasil" if n else "Tidak ada")

    def _cari_berikut(self, arah=1):
        ta = self.text_area
        q = self.var_cari.get()
        if not q:
            return
        ada_sel = bool(ta.tag_ranges("sel"))
        if arah > 0:
            mulai = ta.index("sel.last") if ada_sel else ta.index("insert")
            pos = ta.search(q, mulai, "end", nocase=True) or ta.search(q, "1.0", "end", nocase=True)
        else:
            mulai = ta.index("sel.first") if ada_sel else ta.index("insert")
            pos = (ta.search(q, mulai, "1.0", backwards=True, nocase=True)
                   or ta.search(q, "end", "1.0", backwards=True, nocase=True))
        if not pos:
            return
        akhir = f"{pos}+{len(q)}c"
        ta.tag_remove("sel", "1.0", "end")
        ta.tag_add("sel", pos, akhir)
        ta.mark_set("insert", akhir if arah > 0 else pos)
        ta.see(pos)
        self._update_cursor()

    def _ganti(self):
        ta = self.text_area
        q = self.var_cari.get()
        if not q:
            return
        if ta.tag_ranges("sel") and ta.get("sel.first", "sel.last").lower() == q.lower():
            r = self.var_ganti.get()
            pos = ta.index("sel.first")
            ta.delete("sel.first", "sel.last")
            ta.insert(pos, r)
            ta.mark_set("insert", f"{pos}+{len(r)}c")
            self._on_key_release()
            self._cari_sorot()
        self._cari_berikut(1)

    def _ganti_semua(self):
        ta = self.text_area
        q, r = self.var_cari.get(), self.var_ganti.get()
        if not q:
            return
        n, idx = 0, "1.0"
        while True:
            pos = ta.search(q, idx, "end", nocase=True)
            if not pos:
                break
            ta.delete(pos, f"{pos}+{len(q)}c")
            ta.insert(pos, r)
            idx = f"{pos}+{len(r)}c"
            n += 1
        self._on_key_release()
        self._cari_sorot()
        self.lbl_hasil.config(text=f"{n} diganti")

    # --------------------------------------------------------
    # OVERLAY DRAG & DROP
    # --------------------------------------------------------
    def _buat_overlay(self):
        self.overlay = tk.Canvas(self.editor_wrap, bg="#171c30", highlightthickness=0)
        self.overlay.bind("<Configure>", self._gambar_overlay)

    def _gambar_overlay(self, _e=None):
        c = self.overlay
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 60 or h < 60:
            return
        c.create_rectangle(18, 18, w - 18, h - 18, outline=AMBER, width=2, dash=(8, 6))
        c.create_text(w // 2, h // 2 - 30, text="⇩", fill=AMBER, font=(self.fam_ui, 42, "bold"))
        c.create_text(w // 2, h // 2 + 24, text="Lepaskan file sketch di sini",
                      fill=FG_TEXT, font=self.font_title)
        c.create_text(w // 2, h // 2 + 52, text=".ino   •   folder sketch   •   banyak file sekaligus",
                      fill=FG_DIM, font=self.font_small)

    def _tampil_overlay(self):
        self.overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self.overlay.tkraise()

    def _sembunyi_overlay(self):
        self._dnd_job = None
        self.overlay.place_forget()

    # --------------------------------------------------------
    # DRAG & DROP
    # --------------------------------------------------------
    def _setup_dnd(self):
        if not self.dnd_aktif:
            return
        target = (self.root, self.editor_wrap, self.text_area, self.line_numbers, self.overlay,
                  self.panel, self.output_console, self.serial_console)
        for w in target:
            try:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<DropEnter>>", self._dnd_masuk)
                w.dnd_bind("<<DropPosition>>", self._dnd_posisi)
                w.dnd_bind("<<DropLeave>>", self._dnd_keluar)
                w.dnd_bind("<<Drop>>", self._dnd_jatuh)
            except Exception:
                pass

    def _dnd_batal_sembunyi(self):
        if self._dnd_job:
            try:
                self.root.after_cancel(self._dnd_job)
            except tk.TclError:
                pass
            self._dnd_job = None

    def _dnd_masuk(self, e):
        self._dnd_batal_sembunyi()
        self._tampil_overlay()
        return getattr(e, "action", "copy")

    def _dnd_posisi(self, e):
        self._dnd_batal_sembunyi()
        return getattr(e, "action", "copy")

    def _dnd_keluar(self, e):
        self._dnd_batal_sembunyi()
        self._dnd_job = self.root.after(150, self._sembunyi_overlay)
        return getattr(e, "action", "copy")

    def _dnd_jatuh(self, e):
        self._dnd_batal_sembunyi()
        self._sembunyi_overlay()
        paths = self._parse_drop(e.data)
        # tunda agar aplikasi sumber (file manager) tidak ikut terblokir dialog
        self.root.after(80, lambda: self._buka_dari_drop(paths))
        return getattr(e, "action", "copy")

    def _parse_drop(self, data):
        try:
            items = self.root.tk.splitlist(data)
        except tk.TclError:
            items = data.split()
        hasil = []
        for it in items:
            if it.startswith("file://"):
                it = unquote(it[7:])
            hasil.append(it)
        return hasil

    @staticmethod
    def _cari_ino_di_folder(d):
        utama = os.path.join(d, os.path.basename(os.path.normpath(d)) + ".ino")
        if os.path.isfile(utama):
            return utama
        kandidat = sorted(glob.glob(os.path.join(d, "*.ino")))
        return kandidat[0] if kandidat else None

    def _buka_dari_drop(self, paths):
        sketsa, lain = [], []
        for p in paths:
            p = os.path.abspath(os.path.expanduser(p))
            if os.path.isdir(p):
                ino = self._cari_ino_di_folder(p)
                if ino:
                    sketsa.append(ino)
            elif p.lower().endswith(EKSTENSI_SKETCH) and os.path.isfile(p):
                sketsa.append(p)
            elif os.path.isfile(p):
                lain.append(p)
        if sketsa:
            for p in reversed(sketsa[1:]):
                self._tambah_recent(p)
            self.sketch_buka(sketsa[0])
            if len(sketsa) > 1:
                self._tulis_output(f"{len(sketsa) - 1} sketch lain ditambahkan ke Shelf.\n", tag="info")
        elif lain:
            self._tampil_tab("out")
            self._tampilkan_hex(lain[0])
            self._status(f"Bukan sketch — ditampilkan sebagai hex: {os.path.basename(lain[0])}", "warn")
        else:
            self._status("Tidak ada file sketch (.ino) pada yang dilepas", "warn")

    # --------------------------------------------------------
    # PANEL KANAN (kartu)
    # --------------------------------------------------------
    def _kartu(self, parent, judul, expand=False):
        luar = tk.Frame(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BG_BORDER)
        luar.pack(fill=tk.BOTH if expand else tk.X, expand=expand, padx=10, pady=(10, 0))
        kepala = tk.Frame(luar, bg=BG_CARD)
        kepala.pack(fill=tk.X, padx=12, pady=(8, 0))
        if judul:
            tk.Label(kepala, text=judul, bg=BG_CARD, fg=FG_DIM, font=self.font_cap).pack(side=tk.LEFT)
        isi = tk.Frame(luar, bg=BG_CARD)
        isi.pack(fill=tk.BOTH, expand=True, padx=12, pady=(6, 12))
        return luar, kepala, isi

    def _buat_panel(self):
        self.panel = tk.Frame(self.body, bg=BG_PANEL)
        self.body.add(self.panel, stretch="never", minsize=340, width=420)
        self._buat_kartu_device(self.panel)
        self._buat_kartu_build(self.panel)
        self._buat_kartu_konsol(self.panel)

    # ---- kartu PERANGKAT ----
    def _buat_kartu_device(self, parent):
        _, kepala, isi = self._kartu(parent, "PERANGKAT")
        self.dot_dev = tk.Canvas(kepala, width=10, height=10, bg=BG_CARD, highlightthickness=0)
        self.dot_dev.pack(side=tk.RIGHT)
        self._dot_dev_id = self.dot_dev.create_oval(1, 1, 9, 9, fill=FG_DIM, outline="")
        self.lbl_dev = tk.Label(kepala, text="Board tidak terdeteksi", fg=FG_DIM, bg=BG_CARD,
                                font=self.font_small)
        self.lbl_dev.pack(side=tk.RIGHT, padx=(0, 6))

        isi.grid_columnconfigure(1, weight=1)

        def lbl(teks, row):
            tk.Label(isi, text=teks, bg=BG_CARD, fg=FG_DIM, font=self.font_small, anchor="w").grid(
                row=row, column=0, sticky="w", padx=(0, 10), pady=4)

        lbl("Board", 0)
        self.var_board = tk.StringVar(value=self._board_display(self.fqbn))
        self.cb_board = ttk.Combobox(isi, textvariable=self.var_board, font=self.font_ui, width=10,
                                     values=[f"{n}  —  {f}" for n, f in BOARD_PRESET])
        self.cb_board.grid(row=0, column=1, columnspan=2, sticky="ew")
        for seq in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
            self.cb_board.bind(seq, self._on_board)

        lbl("Port", 1)
        self.var_port = tk.StringVar(value=self.port)
        self.cb_port = ttk.Combobox(isi, textvariable=self.var_port, font=self.font_ui, width=10,
                                    postcommand=self._refresh_ports)
        self.cb_port.grid(row=1, column=1, sticky="ew")
        for seq in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
            self.cb_port.bind(seq, self._on_port)
        b = FlatButton(isi, "↻", self._refresh_ports_manual, bg=BG_CARD_ALT, hover=BG_HOVER,
                       font=self.font_ui, padx=9, pady=2)
        b.grid(row=1, column=2, padx=(6, 0))
        Tooltip(b, "Refresh daftar port")

        lbl("Baud", 2)
        self.var_baud = tk.StringVar(value=str(self.baud))
        self.cb_baud = ttk.Combobox(isi, textvariable=self.var_baud, font=self.font_ui, width=10,
                                    values=BAUD_LIST)
        self.cb_baud.grid(row=2, column=1, columnspan=2, sticky="ew")
        self.cb_baud.bind("<<ComboboxSelected>>", self._on_baud)
        self.cb_baud.bind("<Return>", self._on_baud)

    @staticmethod
    def _board_display(fqbn):
        for n, f in BOARD_PRESET:
            if f == fqbn:
                return f"{n}  —  {f}"
        return fqbn

    def _on_board(self, _e=None):
        teks = self.var_board.get().strip()
        fqbn = teks.split("—")[-1].strip() if "—" in teks else teks
        if fqbn and fqbn != self.fqbn:
            self.fqbn = fqbn
            self._simpan_config()
        if fqbn:
            self.var_board.set(self._board_display(fqbn))

    def _on_port(self, _e=None):
        nilai = self.var_port.get().strip()
        if nilai and nilai != self.port:
            self.port = nilai
            self._simpan_config()
            self._perbarui_perangkat()

    def _on_baud(self, _e=None):
        try:
            nilai = int(self.var_baud.get().strip())
        except ValueError:
            self.var_baud.set(str(self.baud))
            return
        if nilai > 0 and nilai != self.baud:
            self.baud = nilai
            self._simpan_config()
            if self.monitor_proc:
                self.monitor_stop()
                self.monitor_start()

    @staticmethod
    def _deteksi_port():
        return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))

    def _refresh_ports(self):
        ports = self._deteksi_port()
        if self.port and self.port not in ports:
            ports.append(self.port)
        self.cb_port["values"] = ports

    def _refresh_ports_manual(self):
        self._refresh_ports()
        ditemukan = self._deteksi_port()
        if ditemukan:
            self._status(f"Port terdeteksi: {', '.join(ditemukan)}", "ok")
        else:
            self._status("Tidak ada port terdeteksi — colok board lalu coba lagi", "warn")
        self._perbarui_perangkat()

    def _perbarui_perangkat(self):
        ada = self.port in self._deteksi_port()
        self.dot_dev.itemconfig(self._dot_dev_id, fill=TEAL if ada else FG_DIM)
        self.lbl_dev.config(text=f"Terhubung · {self.port}" if ada else "Board tidak terdeteksi",
                            fg=TEAL if ada else FG_DIM)

    def _watch_port(self):
        """Polling ringan: deteksi colok/cabut board & auto-pilih port tunggal."""
        ports = self._deteksi_port()
        daftar = list(ports)
        if self.port and self.port not in daftar:
            daftar.append(self.port)
        self.cb_port["values"] = daftar
        try:
            fokus = self.root.focus_get()
        except Exception:
            fokus = None
        if (self.port not in ports and len(ports) == 1 and fokus is not self.cb_port
                and not self.sibuk and not self.monitor_proc):
            self.port = ports[0]
            self.var_port.set(self.port)
            self._simpan_config()
            self._status(f"Port otomatis: {self.port}", "ok")
        self._perbarui_perangkat()
        self.root.after(2000, self._watch_port)

    # ---- kartu BUILD ----
    def _buat_kartu_build(self, parent):
        _, _, isi = self._kartu(parent, "BUILD")

        pipe = tk.Frame(isi, bg=BG_CARD)
        pipe.pack(fill=tk.X)
        self.langkah = {}
        for i, (kunci, teks) in enumerate((("simpan", "1 · Simpan"), ("compile", "2 · Compile"),
                                           ("upload", "3 · Upload"))):
            l = tk.Label(pipe, text=teks, font=self.font_small, padx=10, pady=4,
                         bg=STEP_STYLE["idle"][0], fg=STEP_STYLE["idle"][1])
            l.pack(side=tk.LEFT)
            self.langkah[kunci] = l
            if i < 2:
                tk.Label(pipe, text="›", bg=BG_CARD, fg=FG_DIM, font=self.font_ui).pack(side=tk.LEFT, padx=5)

        tombol = tk.Frame(isi, bg=BG_CARD)
        tombol.pack(fill=tk.X, pady=(12, 0))
        tombol.grid_columnconfigure(0, weight=1, uniform="b")
        tombol.grid_columnconfigure(1, weight=1, uniform="b")
        self.btn_verify = FlatButton(tombol, "✓  Verify", self.verify_kode, bg=SECOND, hover=SECOND_H,
                                     fg="white", font=self.font_ui_bold, pady=10)
        self.btn_verify.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        Tooltip(self.btn_verify, "Compile sketch (Ctrl+R)")
        self.btn_upload = FlatButton(tombol, "➜  Upload", self.upload_kode, bg=AMBER, hover=AMBER_H,
                                     fg=ON_AMBER, font=self.font_ui_bold, pady=10)
        self.btn_upload.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        Tooltip(self.btn_upload, "Compile + upload ke board (Ctrl+U)")
        self.btn_stop = FlatButton(tombol, "■  Stop", self.batalkan_task, bg=RED_BTN, hover=RED_BTN_H,
                                   fg="white", font=self.font_ui_bold, pady=7)
        self.btn_stop.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.btn_stop.grid_remove()

        self.progress = ttk.Progressbar(isi, mode="indeterminate", style="Amber.Horizontal.TProgressbar")

        self.meter_flash = Meter(isi, "FLASH", BG_CARD, self.font_small)
        self.meter_flash.pack(fill=tk.X, pady=(14, 4))
        self.meter_ram = Meter(isi, "RAM", BG_CARD, self.font_small)
        self.meter_ram.pack(fill=tk.X)
        self._meter_isi = isi

    def _pipeline(self, **kw):
        for k, v in kw.items():
            self._ps[k] = v
            bg, fg = STEP_STYLE[v]
            self.langkah[k].config(bg=bg, fg=fg)

    def _pipeline_reset(self):
        self._pipeline(simpan="idle", compile="idle", upload="idle")

    # ---- kartu KONSOL ----
    def _buat_text_console(self, parent):
        kerangka = tk.Frame(parent, bg=BG_EDITOR)
        t = tk.Text(kerangka, bg=BG_EDITOR, fg=FG_TEXT, font=self.font_console, state="disabled",
                    bd=0, highlightthickness=0, padx=10, pady=6, wrap="word",
                    selectbackground=BG_SELECT, inactiveselectbackground=BG_SELECT)
        sb = ttk.Scrollbar(kerangka, orient=tk.VERTICAL, command=t.yview)
        t.config(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        t.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        t.tag_configure("out", foreground=FG_TEXT)
        t.tag_configure("serial", foreground="#9cdcfe")
        t.tag_configure("info", foreground=BLUE)
        t.tag_configure("ok", foreground=TEAL)
        t.tag_configure("err", foreground=RED)
        t.tag_configure("warn", foreground=YELLOW)
        t.tag_configure("dim", foreground=FG_DIM)
        return kerangka, t

    def _buat_kartu_konsol(self, parent):
        luar, kepala, isi = self._kartu(parent, None, expand=True)
        luar.pack_configure(pady=10)

        self.btn_tab_out = FlatButton(kepala, "Output", lambda: self._tampil_tab("out"),
                                      font=self.font_ui_bold, padx=12, pady=3)
        self.btn_tab_out.pack(side=tk.LEFT)
        self.btn_tab_serial = FlatButton(kepala, "Serial", lambda: self._tampil_tab("serial"),
                                         font=self.font_ui_bold, padx=12, pady=3)
        self.btn_tab_serial.pack(side=tk.LEFT, padx=(4, 0))
        FlatButton(kepala, "Copy", self.salin_output, font=self.font_small, pady=3).pack(side=tk.RIGHT)
        FlatButton(kepala, "Clear", self.bersihkan_output, font=self.font_small, pady=3).pack(side=tk.RIGHT)

        # tab OUTPUT
        self.frame_out, self.output_console = self._buat_text_console(isi)

        # tab SERIAL
        self.frame_serial = tk.Frame(isi, bg=BG_CARD)
        atas = tk.Frame(self.frame_serial, bg=BG_CARD)
        atas.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))
        self.btn_monitor = FlatButton(atas, "●  Start Monitor", self.monitor_toggle, bg=SECOND,
                                      hover=SECOND_H, fg="white", font=self.font_small, padx=12, pady=4)
        self.btn_monitor.pack(side=tk.LEFT)
        Tooltip(self.btn_monitor, "Start/Stop Serial Monitor (F6)")
        self.lbl_mon = tk.Label(atas, text="Tidak aktif", bg=BG_CARD, fg=FG_DIM, font=self.font_small)
        self.lbl_mon.pack(side=tk.LEFT, padx=10)

        kirim = tk.Frame(self.frame_serial, bg=BG_CARD)
        kirim.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        self.var_kirim = tk.StringVar()
        self.ent_kirim = tk.Entry(kirim, textvariable=self.var_kirim, bg=BG_INPUT, fg=FG_TEXT,
                                  insertbackground=AMBER, relief="flat", font=self.font_console,
                                  highlightthickness=1, highlightbackground=BG_BORDER, highlightcolor=AMBER)
        self.ent_kirim.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.ent_kirim.bind("<Return>", lambda e: self.monitor_kirim())
        self.var_akhir = tk.StringVar(value="Newline")
        ttk.Combobox(kirim, textvariable=self.var_akhir, width=8, state="readonly", font=self.font_small,
                     values=["Newline", "None", "CR", "CR+LF"]).pack(side=tk.LEFT, padx=6)
        FlatButton(kirim, "Send", self.monitor_kirim, bg=AMBER, hover=AMBER_H, fg=ON_AMBER,
                   font=self.font_ui_bold, padx=12, pady=3).pack(side=tk.LEFT)

        kerangka_s, self.serial_console = self._buat_text_console(self.frame_serial)
        kerangka_s.pack(fill=tk.BOTH, expand=True)
        self._isi_konsol = isi

    def _tampil_tab(self, nama):
        self._tab = nama
        if nama == "out":
            self.frame_serial.pack_forget()
            self.frame_out.pack(fill=tk.BOTH, expand=True)
        else:
            self.frame_out.pack_forget()
            self.frame_serial.pack(fill=tk.BOTH, expand=True)
        for b, k in ((self.btn_tab_out, "out"), (self.btn_tab_serial, "serial")):
            aktif = (k == nama)
            b.set_colors(BG_CARD_ALT if aktif else BG_CARD, BG_HOVER)
            b.config(fg=AMBER if aktif else FG_DIM)

    def _konsol_aktif(self):
        return self.output_console if self._tab == "out" else self.serial_console

    def bersihkan_output(self):
        c = self._konsol_aktif()
        c.config(state="normal")
        c.delete("1.0", tk.END)
        c.config(state="disabled")

    def salin_output(self):
        teks = self._konsol_aktif().get("1.0", "end-1c")
        if teks:
            self._set_clipboard(teks)
            self._status("Isi konsol disalin ke clipboard", "ok")
            self.root.after(2500, self._reset_status_idle)

    def _tulis_ke(self, c, teks, bersihkan=False, tag=None):
        teks = ANSI_RE.sub("", teks)
        c.config(state="normal")
        if bersihkan:
            c.delete("1.0", tk.END)
        if tag:
            c.insert(tk.END, teks, tag)
        else:
            for baris in teks.splitlines(keepends=True):
                low = baris.lower()
                if "error" in low or "fatal" in low or "failed" in low:
                    t = "err"
                elif "warning" in low:
                    t = "warn"
                else:
                    t = "out"
                c.insert(tk.END, baris, t)
        c.see(tk.END)
        c.config(state="disabled")

    def _tulis_output(self, teks, bersihkan=False, tag=None):
        self._tulis_ke(self.output_console, teks, bersihkan, tag)

    def _tulis_serial(self, teks, bersihkan=False, tag="serial"):
        self._tulis_ke(self.serial_console, teks, bersihkan, tag)

    # --------------------------------------------------------
    # SHORTCUT
    # --------------------------------------------------------
    def _bind_all(self, urutan, fn):
        for s in urutan:
            self.root.bind(s, lambda e, f=fn: f())
            self.text_area.bind(s, lambda e, f=fn: (f(), "break")[1])

    def _buat_shortcut(self):
        self._bind_all(["<Control-n>"], self.sketch_baru)
        self._bind_all(["<Control-o>"], self.sketch_buka)
        self._bind_all(["<Control-s>"], self.sketch_simpan)
        self._bind_all(["<Control-S>"], self.sketch_simpan_sebagai)
        self._bind_all(["<Control-r>"], self.verify_kode)
        self._bind_all(["<Control-u>"], self.upload_kode)
        self._bind_all(["<Control-h>"], self.hex_buka_file)
        self._bind_all(["<Control-f>"], self.tampil_cari)
        self._bind_all(["<Control-slash>"], self.toggle_komentar)
        self._bind_all(["<Control-y>"], self.text_area_redo)
        self._bind_all(["<F6>"], self.monitor_toggle)
        self._bind_all(["<Control-plus>", "<Control-equal>", "<Control-KP_Add>"], lambda: self.zoom(1))
        self._bind_all(["<Control-minus>", "<Control-KP_Subtract>"], lambda: self.zoom(-1))
        self._bind_all(["<Control-0>"], self.zoom_reset)
        self.root.bind("<Escape>", lambda e: self.tutup_cari() if self.find_bar.winfo_ismapped() else None)

    # --------------------------------------------------------
    # FILE / SKETCH
    # --------------------------------------------------------
    def _update_title(self):
        nama = os.path.basename(self.ino_path) if self.ino_path else "untitled.ino"
        titik = "● " if self.dirty else ""
        self.root.title(f"{titik}{nama} — Mission Control")
        self.label_tab.config(text=f"{nama}{'  ●' if self.dirty else ''}",
                              fg=AMBER if self.dirty else FG_TEXT)
        self.label_path.config(text=singkat(self.ino_path) if self.ino_path else "Belum disimpan")
        self._refresh_shelf()

    def _konfirmasi_simpan(self):
        if not self.dirty:
            return True
        nama = os.path.basename(self.ino_path) if self.ino_path else "untitled.ino"
        jawab = messagebox.askyesnocancel("Simpan perubahan?",
                                          f"Simpan perubahan pada {nama} sebelum melanjutkan?",
                                          parent=self.root)
        if jawab is None:
            return False
        if jawab:
            self.sketch_simpan()
            return not self.dirty
        return True

    def sketch_baru(self, pertahankan_isi=False):
        if not pertahankan_isi and not self._konfirmasi_simpan():
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Sketch Baru")
        dlg.configure(bg=BG_PANEL)
        dlg.transient(self.root)
        dlg.resizable(False, False)

        var_nama = tk.StringVar(value="sketch_baru")
        var_lokasi = tk.StringVar(value=self.last_dir)
        var_tpl = tk.StringVar(value="Kosong")
        body = tk.Frame(dlg, bg=BG_PANEL, padx=18, pady=16)
        body.pack()

        def label(teks, row):
            tk.Label(body, text=teks, bg=BG_PANEL, fg=FG_TEXT, font=self.font_ui,
                     anchor="w").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))

        def entry(var, row):
            e = tk.Entry(body, textvariable=var, width=36, bg=BG_INPUT, fg=FG_TEXT,
                         insertbackground=AMBER, relief="flat", font=self.font_ui,
                         highlightthickness=1, highlightbackground=BG_BORDER, highlightcolor=AMBER)
            e.grid(row=row, column=1, sticky="ew", ipady=4)
            return e

        label("Nama sketch", 0)
        e_nama = entry(var_nama, 0)
        label("Lokasi", 1)
        entry(var_lokasi, 1)

        def browse():
            d = filedialog.askdirectory(parent=dlg, initialdir=var_lokasi.get() or os.path.expanduser("~"))
            if d:
                var_lokasi.set(d)

        FlatButton(body, "Browse", browse, bg=BG_CARD, hover=BG_HOVER,
                   font=self.font_ui).grid(row=1, column=2, padx=(8, 0))
        label("Template", 2)
        cb = ttk.Combobox(body, textvariable=var_tpl, values=list(TEMPLATE_SKETCH),
                          state="readonly", font=self.font_ui, width=34)
        cb.grid(row=2, column=1, sticky="ew")
        if pertahankan_isi:
            cb.config(state="disabled")

        hasil = {}

        def buat(_e=None):
            nama = var_nama.get().strip()
            lok = os.path.expanduser(var_lokasi.get().strip())
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", nama):
                messagebox.showerror("Nama tidak valid",
                                     "Gunakan huruf, angka, _ atau - (tanpa spasi).", parent=dlg)
                return
            if not os.path.isdir(lok):
                messagebox.showerror("Lokasi tidak valid", "Folder lokasi tidak ditemukan.", parent=dlg)
                return
            if os.path.exists(os.path.join(lok, nama, nama + ".ino")):
                if not messagebox.askyesno("File sudah ada",
                                           f"{nama}.ino sudah ada di lokasi itu. Timpa?", parent=dlg):
                    return
            hasil.update(nama=nama, lokasi=lok, template=var_tpl.get())
            dlg.destroy()

        tombol = tk.Frame(body, bg=BG_PANEL)
        tombol.grid(row=3, column=0, columnspan=3, sticky="e", pady=(14, 0))
        FlatButton(tombol, "Batal", dlg.destroy, bg=BG_CARD, hover=BG_HOVER,
                   font=self.font_ui, padx=16).pack(side=tk.LEFT, padx=4)
        FlatButton(tombol, "Buat", buat, bg=AMBER, hover=AMBER_H, fg=ON_AMBER,
                   font=self.font_ui_bold, padx=20).pack(side=tk.LEFT, padx=4)

        dlg.bind("<Return>", buat)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        e_nama.focus_set()
        e_nama.select_range(0, "end")
        dlg.wait_visibility()
        dlg.grab_set()
        self.root.wait_window(dlg)

        if not hasil:
            return
        folder = os.path.join(hasil["lokasi"], hasil["nama"])
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Gagal", str(e), parent=self.root)
            return
        self.sketch_folder = folder
        self.ino_path = os.path.join(folder, f"{hasil['nama']}.ino")
        self.last_dir = hasil["lokasi"]
        if not pertahankan_isi:
            self._set_isi(TEMPLATE_SKETCH.get(hasil["template"], TEMPLATE_SKETCH["Kosong"]))
        self._simpan_file()
        self._tambah_recent(self.ino_path)
        self._update_title()
        self._tampil_tab("out")
        self._tulis_output(f"Sketch baru dibuat: {self.ino_path}\n", bersihkan=True, tag="info")
        self.text_area.focus_set()

    def sketch_buka(self, path=None):
        if not self._konfirmasi_simpan():
            return
        if not isinstance(path, str):
            path = filedialog.askopenfilename(parent=self.root, initialdir=self.last_dir,
                                              filetypes=[("Arduino Sketch", "*.ino"), ("Semua file", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                isi = f.read()
        except (OSError, UnicodeDecodeError) as e:
            messagebox.showerror("Gagal membuka", str(e), parent=self.root)
            return
        self.ino_path = path
        self.sketch_folder = os.path.dirname(path)
        self.last_dir = self.sketch_folder
        self._set_isi(isi)
        self._tambah_recent(path)
        self._update_title()
        self._status(f"Dibuka: {os.path.basename(path)}", "ok")
        self.root.after(2500, self._reset_status_idle)
        self.text_area.focus_set()

    def sketch_simpan(self):
        if not self.ino_path:
            self.sketch_baru(pertahankan_isi=True)
        else:
            self._simpan_file()
            self._status(f"Tersimpan: {os.path.basename(self.ino_path)}", "ok")
            self.root.after(2500, self._reset_status_idle)

    def sketch_simpan_sebagai(self):
        awal = os.path.basename(self.ino_path) if self.ino_path else "sketch.ino"
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".ino", initialfile=awal,
                                            initialdir=self.sketch_folder or self.last_dir,
                                            filetypes=[("Arduino Sketch", "*.ino")])
        if not path:
            return
        self.ino_path = path
        self.sketch_folder = os.path.dirname(path)
        self.last_dir = self.sketch_folder
        self._simpan_file()
        self._tambah_recent(path)
        self._update_title()

    def _simpan_file(self):
        if not self.ino_path:
            return
        try:
            with open(self.ino_path, "w", encoding="utf-8") as f:
                f.write(self.text_area.get("1.0", "end-1c") + "\n")
            self.text_area.edit_modified(False)
        except OSError as e:
            messagebox.showerror("Gagal menyimpan", str(e), parent=self.root)

    def _simpan_config(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "fqbn": self.fqbn, "port": self.port, "baud": self.baud,
                    "recent": self.recent, "last_dir": self.last_dir,
                    "font_size": int(self.font_editor.cget("size")),
                }, f)
        except OSError:
            pass

    # --------------------------------------------------------
    # MENJALANKAN arduino-cli (background thread)
    # --------------------------------------------------------
    def _set_busy(self, sibuk):
        self.sibuk = sibuk
        for b in (self.btn_verify, self.btn_upload):
            b.set_enabled(not sibuk)
        if sibuk:
            self.btn_stop.grid()
            self.progress.pack(fill=tk.X, pady=(10, 0), before=self.meter_flash)
            self.progress.start(12)
            self._status("Sedang bekerja...", "busy")
        else:
            self.btn_stop.grid_remove()
            self.progress.stop()
            self.progress.pack_forget()

    def _jalankan(self, args, judul, teks_ok, teks_gagal, selesai=None, mode="lain"):
        if self.sibuk:
            return
        self._set_busy(True)
        self._dibatalkan = False
        self._mode = mode
        self._cb_ok, self._cb_gagal, self._cb_selesai = teks_ok, teks_gagal, selesai
        self._tampil_tab("out")
        if mode in ("verify", "upload"):
            self.meter_flash.reset()
            self.meter_ram.reset()
            self._pipeline_reset()
            self._pipeline(simpan="ok", compile="aktif")
        else:
            self._pipeline_reset()
        self._tulis_output(f"» {judul}\n", bersihkan=True, tag="info")
        self._tulis_output("$ " + shlex.join(args) + "\n\n", tag="dim")
        q = queue.Queue()
        self.task_queue = q

        def worker():
            try:
                p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1, errors="replace")
                self.task_proc = p
                for baris in iter(p.stdout.readline, ""):
                    q.put(("line", baris))
                p.wait()
                q.put(("done", p.returncode))
            except FileNotFoundError:
                q.put(("notfound", None))
            except Exception as e:
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_task()

    def _parse_build_line(self, baris):
        m = RE_FLASH.search(baris)
        if m:
            self.meter_flash.set(int(m.group(1)), int(m.group(3)), int(m.group(2)))
            if self._mode in ("verify", "upload"):
                self._pipeline(compile="ok")
                if self._mode == "upload":
                    self._pipeline(upload="aktif")
        m = RE_RAM.search(baris)
        if m:
            self.meter_ram.set(int(m.group(1)), int(m.group(3)), int(m.group(2)))

    def _poll_task(self):
        try:
            while True:
                jenis, data = self.task_queue.get_nowait()
                if jenis == "line":
                    self._tulis_output(data)
                    self._parse_build_line(data)
                elif jenis == "done":
                    self._task_selesai(data)
                    return
                elif jenis == "notfound":
                    self._tulis_output("[ERROR] arduino-cli tidak ditemukan. "
                                       "Pastikan sudah terinstall dan ada di PATH.\n", tag="err")
                    self._task_selesai(None)
                    return
                elif jenis == "error":
                    self._tulis_output(f"[ERROR] {data}\n", tag="err")
                    self._task_selesai(None)
                    return
        except queue.Empty:
            pass
        self.root.after(50, self._poll_task)

    def _task_selesai(self, rc):
        self._set_busy(False)
        self.task_proc = None
        sukses = False
        if self._dibatalkan:
            self._tulis_output("\n■ Dibatalkan.\n", tag="warn")
            self._status("Dibatalkan", "warn")
            for k in ("compile", "upload"):
                if self._ps[k] == "aktif":
                    self._pipeline(**{k: "idle"})
        elif rc == 0:
            sukses = True
            self._tulis_output(f"\n✓ {self._cb_ok}\n", tag="ok")
            self._status(self._cb_ok, "ok")
            if self._mode in ("verify", "upload"):
                self._pipeline(compile="ok")
                if self._mode == "upload":
                    self._pipeline(upload="ok")
        elif rc is None:
            self._status("arduino-cli tidak ditemukan", "err")
        else:
            self._tulis_output(f"\n✗ {self._cb_gagal} (exit code {rc})\n", tag="err")
            self._status(self._cb_gagal, "err")
            for k in ("compile", "upload"):
                if self._ps[k] == "aktif":
                    self._pipeline(**{k: "gagal"})
        self.root.after(5000, self._reset_status_idle)
        if sukses and self._cb_selesai:
            self._cb_selesai(rc)

    def batalkan_task(self):
        if self.task_proc:
            self._dibatalkan = True
            try:
                self.task_proc.terminate()
            except Exception:
                pass

    def list_boards(self):
        self._jalankan(["arduino-cli", "board", "list"], "Mencari board yang terhubung...",
                       "Pencarian selesai", "Pencarian gagal")

    def verify_kode(self):
        if self.sibuk:
            return
        self.monitor_stop()
        if not self._pastikan_sketch_siap():
            return
        self._jalankan(["arduino-cli", "compile", "--fqbn", self.fqbn, self._folder_kompilasi()],
                       "Compiling sketch...", "Compile selesai", "Compile gagal", mode="verify")

    def upload_kode(self):
        if self.sibuk:
            return
        self.monitor_stop()
        if not self._pastikan_sketch_siap():
            return
        self._jalankan(["arduino-cli", "compile", "--upload", "-p", self.port,
                        "--fqbn", self.fqbn, self._folder_kompilasi()],
                       f"Compile & upload ke {self.port} ({self.fqbn})...",
                       "Upload selesai", "Upload gagal", mode="upload")

    def _folder_kompilasi(self):
        stem = os.path.splitext(os.path.basename(self.ino_path))[0]
        if os.path.basename(os.path.normpath(self.sketch_folder)) == stem:
            return self.sketch_folder
        staging = os.path.join(os.path.expanduser("~/.cache/arduino_cli_ide"), stem)
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        for nama in os.listdir(self.sketch_folder):
            sumber = os.path.join(self.sketch_folder, nama)
            if os.path.isfile(sumber) and (nama == os.path.basename(self.ino_path)
                                           or nama.lower().endswith((".h", ".hpp", ".c", ".cpp"))):
                shutil.copy2(sumber, os.path.join(staging, nama))
        return staging

    def _pastikan_sketch_siap(self):
        if not self.ino_path:
            messagebox.showinfo("Info", "Sketch belum disimpan. Tentukan nama & lokasi dulu.",
                                parent=self.root)
            self.sketch_baru(pertahankan_isi=True)
            if not self.ino_path:
                return False
        else:
            self._simpan_file()
        return True

    # --------------------------------------------------------
    # HEX
    # --------------------------------------------------------
    def _tampilkan_hex(self, path):
        try:
            ukuran = os.path.getsize(path)
            self.hex_terakhir = (path, hex_dump_file(path))
            isi = hex_dump_file(path, MAX_TAMPIL_BYTE)
        except OSError as e:
            self._tulis_output(f"[ERROR] {e}\n", bersihkan=True, tag="err")
            return
        header = (f"Hex dump: {path}  ({ukuran} byte)\n"
                  "OFFSET    00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F  ASCII\n")
        self._tulis_output(header, bersihkan=True, tag="info")
        self._tulis_output(isi, tag="out")
        if ukuran > MAX_TAMPIL_BYTE:
            self._tulis_output("\n... dipotong. Pakai Hex > Simpan Hex ke .txt untuk versi lengkap.\n", tag="warn")

    def hex_buka_file(self):
        path = filedialog.askopenfilename(parent=self.root, title="Pilih file untuk dilihat hex-nya")
        if path:
            self._tampil_tab("out")
            self._tampilkan_hex(path)

    def hex_hasil_compile(self):
        if self.sibuk or not self._pastikan_sketch_siap():
            return
        self._folder_build = os.path.join(self.sketch_folder, "build")
        self._jalankan(["arduino-cli", "compile", "--fqbn", self.fqbn,
                        "--output-dir", self._folder_build, self._folder_kompilasi()],
                       "Compiling sketch untuk hex dump...", "Compile selesai", "Compile gagal",
                       selesai=self._setelah_hex_compile, mode="verify")

    def _setelah_hex_compile(self, _rc):
        nama = os.path.basename(self.ino_path)
        kandidat = [os.path.join(self._folder_build, nama + ".bin"),
                    os.path.join(self._folder_build, nama + ".hex")]
        target = next((k for k in kandidat if os.path.exists(k)), None)
        if target:
            self._tampilkan_hex(target)
        else:
            self._tulis_output(f"\n✗ File bin/hex tidak ditemukan di {self._folder_build}\n", tag="err")

    def hex_simpan_txt(self):
        if not self.hex_terakhir:
            path = filedialog.askopenfilename(parent=self.root, title="Pilih file")
            if not path:
                return
            self._tampil_tab("out")
            self._tampilkan_hex(path)
        if not self.hex_terakhir:
            return
        sumber, teks = self.hex_terakhir
        tujuan = filedialog.asksaveasfilename(parent=self.root, defaultextension=".txt",
                                              initialfile=os.path.basename(sumber) + ".hex.txt")
        if tujuan:
            with open(tujuan, "w", encoding="utf-8") as f:
                f.write(teks)
            self._tulis_output(f"\n✓ Hex disimpan: {tujuan}\n", tag="ok")

    # --------------------------------------------------------
    # CLIPBOARD (support Wayland)
    # --------------------------------------------------------
    def _setup_clipboard(self):
        for widget, bisa_edit in ((self.text_area, True), (self.output_console, False),
                                  (self.serial_console, False)):
            widget.bind("<Button-1>", lambda e, w=widget: w.focus_set(), add="+")
            widget.bind("<Button-3>", lambda e, w=widget, ed=bisa_edit: self._menu_klik_kanan(e, w, ed))
            for tombol in ("<Control-c>", "<Control-C>", "<Control-Shift-C>", "<Control-Insert>"):
                widget.bind(tombol, lambda e, w=widget: self._salin(w))
            for tombol in ("<Control-a>", "<Control-A>"):
                widget.bind(tombol, lambda e, w=widget: self._pilih_semua(w))
            if bisa_edit:
                for tombol in ("<Control-x>", "<Control-X>", "<Shift-Delete>"):
                    widget.bind(tombol, lambda e, w=widget: self._potong(w))
                for tombol in ("<Control-v>", "<Control-V>", "<Control-Shift-V>", "<Shift-Insert>"):
                    widget.bind(tombol, lambda e, w=widget: self._tempel(w))

    def _set_clipboard(self, teks):
        self.root.clipboard_clear()
        self.root.clipboard_append(teks)
        self.root.update()
        if shutil.which("wl-copy"):
            try:
                p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                p.stdin.write(teks.encode("utf-8"))
                p.stdin.close()
            except Exception:
                pass

    def _ambil_clipboard(self):
        if shutil.which("wl-paste"):
            try:
                hasil = subprocess.run(["wl-paste", "-n"], capture_output=True, timeout=2)
                if hasil.returncode == 0 and hasil.stdout:
                    return hasil.stdout.decode("utf-8", errors="replace")
            except Exception:
                pass
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return ""

    def _salin(self, widget):
        try:
            teks = widget.get("sel.first", "sel.last")
        except tk.TclError:
            return "break"
        self._set_clipboard(teks)
        return "break"

    def _potong(self, widget):
        try:
            teks = widget.get("sel.first", "sel.last")
        except tk.TclError:
            return "break"
        self._set_clipboard(teks)
        widget.delete("sel.first", "sel.last")
        self._on_key_release()
        return "break"

    def _tempel(self, widget):
        teks = self._ambil_clipboard()
        if not teks:
            return "break"
        try:
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        widget.insert("insert", teks)
        widget.see("insert")
        self._on_key_release()
        return "break"

    def _pilih_semua(self, widget):
        widget.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _menu_klik_kanan(self, event, widget, bisa_edit):
        widget.focus_set()
        menu = self._menu(self.root)
        if bisa_edit:
            menu.add_command(label="Cut", command=lambda: self._potong(widget))
        menu.add_command(label="Copy", command=lambda: self._salin(widget))
        if bisa_edit:
            menu.add_command(label="Paste", command=lambda: self._tempel(widget))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: self._pilih_semua(widget))
        if bisa_edit:
            menu.add_separator()
            menu.add_command(label="Toggle Comment", command=self.toggle_komentar)
            menu.add_command(label="Find / Replace", command=self.tampil_cari)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    # --------------------------------------------------------
    # SERIAL MONITOR
    # --------------------------------------------------------
    def monitor_toggle(self):
        if self.monitor_proc:
            self.monitor_stop()
        else:
            self.monitor_start()

    def _monitor_ui(self, aktif):
        if aktif:
            self.btn_monitor.config(text="■  Stop Monitor")
            self.btn_monitor.set_colors(RED_BTN, RED_BTN_H)
            self.btn_tab_serial.config(text="Serial ●")
            self.lbl_mon.config(text=f"{self.port} @ {self.baud} baud", fg=TEAL)
            self._status(f"Serial Monitor aktif ({self.port} @ {self.baud})", "ok")
            self.ent_kirim.focus_set()
        else:
            self.btn_monitor.config(text="●  Start Monitor")
            self.btn_monitor.set_colors(SECOND, SECOND_H)
            self.btn_tab_serial.config(text="Serial")
            self.lbl_mon.config(text="Tidak aktif", fg=FG_DIM)
            if not self.sibuk:
                self._status("Siap")

    def monitor_start(self):
        if self.monitor_proc or self.sibuk:
            return
        self._tampil_tab("serial")
        self._tulis_serial(f"● Serial Monitor {self.port} @ {self.baud} baud (F6 untuk stop)\n",
                           bersihkan=True, tag="info")
        try:
            proc = subprocess.Popen(
                ["arduino-cli", "monitor", "-p", self.port, "-c", f"baudrate={self.baud}"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, errors="replace")
            self.monitor_proc = proc
            self.monitor_queue = queue.Queue()
            threading.Thread(target=self._monitor_baca, args=(proc, self.monitor_queue), daemon=True).start()
            self._monitor_ui(True)
            self._monitor_poll()
        except FileNotFoundError:
            self._tulis_serial("[ERROR] arduino-cli tidak ditemukan.\n", tag="err")

    def _monitor_baca(self, proc, antrean):
        for baris in iter(proc.stdout.readline, ""):
            antrean.put((proc, baris))
        antrean.put((proc, None))

    def _monitor_poll(self):
        try:
            while True:
                proc, baris = self.monitor_queue.get_nowait()
                if proc is not self.monitor_proc:
                    continue
                if baris is None:
                    self._tulis_serial("\n[Serial Monitor berhenti]\n", tag="warn")
                    self.monitor_proc = None
                    self._monitor_ui(False)
                    return
                self._tulis_serial(baris)
        except queue.Empty:
            pass

        if int(self.serial_console.index("end-1c").split(".")[0]) > 3000:
            self.serial_console.config(state="normal")
            self.serial_console.delete("1.0", "800.0")
            self.serial_console.config(state="disabled")
        if self.monitor_proc:
            self.root.after(100, self._monitor_poll)

    def monitor_kirim(self):
        proc = self.monitor_proc
        if not proc:
            self._status("Monitor belum aktif — tekan Start Monitor (F6)", "warn")
            self.root.after(3000, self._reset_status_idle)
            return
        akhir = {"Newline": "\n", "None": "", "CR": "\r", "CR+LF": "\r\n"}.get(self.var_akhir.get(), "\n")
        teks = self.var_kirim.get()
        try:
            proc.stdin.write(teks + akhir)
            proc.stdin.flush()
            self._tulis_serial(f"> {teks}\n", tag="ok")
            self.var_kirim.set("")
        except (OSError, ValueError):
            self._tulis_serial("[ERROR] Gagal mengirim data ke port.\n", tag="err")

    def monitor_stop(self):
        proc = self.monitor_proc
        self.monitor_proc = None
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            self._tulis_serial("\n[Serial Monitor dihentikan]\n", tag="warn")
            self._monitor_ui(False)

    # --------------------------------------------------------
    # KELUAR
    # --------------------------------------------------------
    def _tutup(self):
        if not self._konfirmasi_simpan():
            return
        self.batalkan_task()
        self.monitor_stop()
        self._simpan_config()
        self.root.destroy()


def mode_terminal(argv):
    if len(argv) < 3:
        return 1
    sumber = argv[2]
    if not os.path.isfile(sumber):
        return 1
    teks = hex_dump_file(sumber)
    if "--out" in argv and argv.index("--out") + 1 < len(argv):
        tujuan = argv[argv.index("--out") + 1]
        with open(tujuan, "w", encoding="utf-8") as f:
            f.write(teks)
    else:
        print(teks, end="")
    return 0


def buat_root():
    """Pakai root TkinterDnD bila tersedia; jatuh ke Tk biasa jika gagal."""
    if DND_TERSEDIA:
        try:
            return TkinterDnD.Tk(), True
        except Exception:
            pass
    return tk.Tk(), False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--hex":
        sys.exit(mode_terminal(sys.argv))
    root, dnd_ok = buat_root()
    app = ArduinoCliIDE(root, dnd=dnd_ok)
    # file/folder sebagai argumen:  python arduino_cli_ide.py Blink.ino
    berkas = [a for a in sys.argv[1:] if not a.startswith("-")]
    if berkas:
        root.after(300, lambda: app._buka_dari_drop(berkas))
    root.mainloop()