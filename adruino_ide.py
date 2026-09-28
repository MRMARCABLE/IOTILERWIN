"""
arduino_cli_ide.py
Code Editor Python (Tkinter) untuk menulis sketch Arduino (C++)
dan compile/upload BENERAN lewat arduino-cli.

Syarat:
- arduino-cli sudah terinstall (sudo pacman -S arduino-cli)
- Core board sudah terinstall (arduino-cli core install arduino:avr)

Aturan folder sketch Arduino:
- File .ino HARUS berada di dalam folder dengan nama yang SAMA PERSIS
  Contoh: folder "hi-there/" berisi file "hi-there.ino"
- Kalau kalian bikin sketch baru lewat editor ini, folder itu otomatis dibuatkan.

Jalankan dengan:
    python arduino_cli_ide.py
"""

import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, font
import subprocess
import os
import re
import sys
import shutil

# ============================================================
# KONFIGURASI DEFAULT (bisa diubah lewat menu Tools)
# ============================================================
DEFAULT_FQBN = "arduino:avr:uno"   # Fully Qualified Board Name
DEFAULT_PORT = "/dev/ttyACM0"      # ganti sesuai hasil `arduino-cli board list`

# ============================================================
# WARNA TEMA
# ============================================================
WARNA_BG_EDITOR = "#1e1e1e"
WARNA_BG_TOOLBAR = "#2d2d2d"
WARNA_BG_OUTPUT = "#000000"
WARNA_TEKS = "#d4d4d4"
WARNA_ACCENT = "#00a5a5"
WARNA_KEYWORD = "#569cd6"
WARNA_TIPE = "#4ec9b0"
WARNA_STRING = "#ce9178"
WARNA_COMMENT = "#6a9955"
WARNA_FUNGSI = "#dcdcaa"

CPP_KEYWORDS = [
    "void", "int", "float", "double", "char", "bool", "byte", "long",
    "unsigned", "const", "static", "return", "if", "else", "for",
    "while", "do", "switch", "case", "break", "continue", "struct",
    "class", "public", "private", "true", "false", "define", "include"
]
ARDUINO_FUNGSI_BAWAAN = [
    "setup", "loop", "digitalWrite", "digitalRead", "analogWrite",
    "analogRead", "pinMode", "delay", "Serial"
]


# ============================================================
# HEX DUMP (bisa dipakai dari editor maupun dari terminal)
# ============================================================
MAX_TAMPIL_BYTE = 64 * 1024   # batas tampil di panel Output (file txt tetap penuh)


def hex_dump(data, lebar=16):
    """Ubah bytes jadi teks: offset | hex | ASCII, mirip perintah `xxd`/`hexdump -C`."""
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


class ArduinoCliIDE:
    def __init__(self, root):
        self.root = root
        self.root.title("untitled | Arduino CLI Editor")
        self.root.geometry("1000x700")
        self.root.configure(bg=WARNA_BG_TOOLBAR)

        self.sketch_folder = None   # folder tempat file .ino berada
        self.ino_path = None        # path lengkap file .ino
        self.fqbn = DEFAULT_FQBN
        self.port = DEFAULT_PORT
        self.hex_terakhir = None   # (nama_file, teks_hex_penuh)
        self.font_editor = font.Font(family="Consolas", size=12)

        self._buat_menu()
        self._buat_toolbar()
        self._buat_tab_bar()
        self._buat_editor()
        self._buat_output()
        self._buat_status_bar()
        self._buat_shortcut()
        self._setup_clipboard()

    # ========================================================
    # MENU BAR
    # ========================================================
    def _buat_menu(self):
        menubar = tk.Menu(self.root)

        menu_file = tk.Menu(menubar, tearoff=0)
        menu_file.add_command(label="New Sketch...", command=self.sketch_baru, accelerator="Ctrl+N")
        menu_file.add_command(label="Open Sketch...", command=self.sketch_buka, accelerator="Ctrl+O")
        menu_file.add_command(label="Save", command=self.sketch_simpan, accelerator="Ctrl+S")
        menu_file.add_separator()
        menu_file.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=menu_file)

        menu_edit = tk.Menu(menubar, tearoff=0)
        menu_edit.add_command(label="Undo", command=self.text_area_undo, accelerator="Ctrl+Z")
        menu_edit.add_command(label="Cut", command=lambda: self._potong(self.text_area), accelerator="Ctrl+X")
        menu_edit.add_command(label="Copy", command=lambda: self._salin(self.text_area), accelerator="Ctrl+C")
        menu_edit.add_command(label="Paste", command=lambda: self._tempel(self.text_area), accelerator="Ctrl+V")
        menu_edit.add_command(label="Select All", command=lambda: self._pilih_semua(self.text_area), accelerator="Ctrl+A")
        menubar.add_cascade(label="Edit", menu=menu_edit)

        menu_sketch = tk.Menu(menubar, tearoff=0)
        menu_sketch.add_command(label="Verify/Compile", command=self.verify_kode, accelerator="Ctrl+R")
        menu_sketch.add_command(label="Upload", command=self.upload_kode, accelerator="Ctrl+U")
        menubar.add_cascade(label="Sketch", menu=menu_sketch)

        menu_tools = tk.Menu(menubar, tearoff=0)
        menu_tools.add_command(label="Set Board (FQBN)...", command=self.set_fqbn)
        menu_tools.add_command(label="Set Port...", command=self.set_port)
        menu_tools.add_command(label="List Connected Boards", command=self.list_boards)
        menubar.add_cascade(label="Tools", menu=menu_tools)

        menu_hex = tk.Menu(menubar, tearoff=0)
        menu_hex.add_command(label="Lihat Hex File...", command=self.hex_buka_file, accelerator="Ctrl+H")
        menu_hex.add_command(label="Hex Hasil Compile", command=self.hex_hasil_compile)
        menu_hex.add_command(label="Simpan Hex ke .txt...", command=self.hex_simpan_txt)
        menubar.add_cascade(label="Hex", menu=menu_hex)

        self.root.config(menu=menubar)

    # ========================================================
    # TOOLBAR
    # ========================================================
    def _buat_toolbar(self):
        toolbar = tk.Frame(self.root, bg=WARNA_BG_TOOLBAR, height=45)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        tk.Button(
            toolbar, text="✓", font=("Arial", 14, "bold"), fg="white",
            bg="#3c3c3c", activebackground="#505050", border=0, width=3,
            command=self.verify_kode
        ).pack(side=tk.LEFT, padx=(10, 2), pady=5)

        tk.Button(
            toolbar, text="→", font=("Arial", 14, "bold"), fg="white",
            bg="#3c3c3c", activebackground="#505050", border=0, width=3,
            command=self.upload_kode
        ).pack(side=tk.LEFT, padx=2, pady=5)

        self.label_board = tk.Label(
            toolbar, text=self.fqbn, fg="white", bg=WARNA_ACCENT,
            font=("Arial", 10, "bold"), padx=10, pady=3
        )
        self.label_board.pack(side=tk.LEFT, padx=10)

    def _buat_tab_bar(self):
        self.tab_frame = tk.Frame(self.root, bg="#252525", height=28)
        self.tab_frame.pack(fill=tk.X)
        self.label_tab = tk.Label(
            self.tab_frame, text="untitled.ino", fg="white", bg="#252525",
            font=("Arial", 10), anchor="w", padx=10, pady=4
        )
        self.label_tab.pack(side=tk.LEFT)

    # ========================================================
    # EDITOR
    # ========================================================
    def _buat_editor(self):
        container = tk.PanedWindow(self.root, orient=tk.VERTICAL, bg=WARNA_BG_TOOLBAR)
        container.pack(fill=tk.BOTH, expand=True)
        self.editor_container = container

        editor_frame = tk.Frame(container)
        container.add(editor_frame, height=420)

        self.line_numbers = tk.Text(
            editor_frame, width=4, padx=4, takefocus=0, border=0,
            background="#2b2b2b", foreground="#858585",
            state="disabled", font=self.font_editor
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        self.text_area = tk.Text(
            editor_frame, wrap="none", undo=True,
            background=WARNA_BG_EDITOR, foreground=WARNA_TEKS,
            insertbackground="white", font=self.font_editor, border=0
        )
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar_y = tk.Scrollbar(editor_frame, command=self._scroll_sync)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_area.config(yscrollcommand=scrollbar_y.set)

        self.text_area.tag_configure("keyword", foreground=WARNA_KEYWORD)
        self.text_area.tag_configure("string", foreground=WARNA_STRING)
        self.text_area.tag_configure("comment", foreground=WARNA_COMMENT)
        self.text_area.tag_configure("fungsi", foreground=WARNA_FUNGSI)

        self.text_area.bind("<KeyRelease>", self._on_key_release)
        self.text_area.bind("<MouseWheel>", self._update_line_numbers)
        self.text_area.bind("<ButtonRelease-1>", self._update_status_bar)

        # Template kosong awal (setup & loop) biar familiar
        self.text_area.insert("1.0", "void setup() {\n  \n}\n\nvoid loop() {\n  \n}\n")
        self._update_line_numbers()
        self._highlight_syntax()

    def _scroll_sync(self, *args):
        self.text_area.yview(*args)
        self.line_numbers.yview(*args)

    def _on_key_release(self, event=None):
        self._update_line_numbers()
        self._highlight_syntax()
        self._update_status_bar()

    def _update_line_numbers(self, event=None):
        jumlah_baris = int(self.text_area.index("end-1c").split(".")[0])
        teks_nomor = "\n".join(str(i) for i in range(1, jumlah_baris + 1))
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", "end")
        self.line_numbers.insert("1.0", teks_nomor)
        self.line_numbers.config(state="disabled")
        self.line_numbers.yview_moveto(self.text_area.yview()[0])

    def _highlight_syntax(self):
        for tag in ("keyword", "string", "fungsi", "comment"):
            self.text_area.tag_remove(tag, "1.0", tk.END)

        isi = self.text_area.get("1.0", tk.END)

        for kw in CPP_KEYWORDS:
            for match in re.finditer(rf"\b{kw}\b", isi):
                self.text_area.tag_add("keyword", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

        for kw in ARDUINO_FUNGSI_BAWAAN:
            for match in re.finditer(rf"\b{kw}\b", isi):
                self.text_area.tag_add("fungsi", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

        for match in re.finditer(r"(\".*?\")", isi):
            self.text_area.tag_add("string", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

        for match in re.finditer(r"//.*", isi):
            self.text_area.tag_add("comment", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    # ========================================================
    # OUTPUT PANEL
    # ========================================================
    def _buat_output(self):
        output_frame = tk.Frame(self.editor_container)
        self.editor_container.add(output_frame, height=220)

        header = tk.Frame(output_frame, bg="#2d2d2d")
        header.pack(fill=tk.X)
        tk.Label(
            header, text="Output", fg="white", bg="#2d2d2d",
            font=("Arial", 10), anchor="w", padx=8, pady=3
        ).pack(side=tk.LEFT)

        self.output_console = tk.Text(
            output_frame, background=WARNA_BG_OUTPUT, foreground="#00ff90",
            font=("Consolas", 10), state="disabled"
        )
        self.output_console.pack(fill=tk.BOTH, expand=True)

    def _tulis_output(self, teks, bersihkan=False):
        self.output_console.config(state="normal")
        if bersihkan:
            self.output_console.delete("1.0", tk.END)
        self.output_console.insert(tk.END, teks)
        self.output_console.see(tk.END)
        self.output_console.config(state="disabled")

    def _buat_status_bar(self):
        self.status_bar = tk.Label(
            self.root, text="Ln 1, Col 0", fg="white", bg=WARNA_ACCENT,
            font=("Arial", 9), anchor="e", padx=10
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _update_status_bar(self, event=None):
        baris, kolom = self.text_area.index(tk.INSERT).split(".")
        info_port = f" | {self.port}" if self.port else ""
        self.status_bar.config(text=f"Ln {baris}, Col {kolom}{info_port}")

    def _buat_shortcut(self):
        self.root.bind("<Control-n>", lambda e: self.sketch_baru())
        self.root.bind("<Control-o>", lambda e: self.sketch_buka())
        self.root.bind("<Control-s>", lambda e: self.sketch_simpan())
        self.root.bind("<Control-r>", lambda e: self.verify_kode())
        self.root.bind("<Control-u>", lambda e: self.upload_kode())
        self.root.bind("<Control-h>", lambda e: self.hex_buka_file())

    def text_area_undo(self):
        try:
            self.text_area.edit_undo()
        except tk.TclError:
            pass

    # ========================================================
    # MANAJEMEN SKETCH (folder + file .ino harus sama nama)
    # ========================================================
    def sketch_baru(self):
        nama = simpledialog.askstring("Sketch Baru", "Nama sketch (tanpa spasi):")
        if not nama:
            return
        lokasi_induk = filedialog.askdirectory(title="Pilih lokasi untuk folder sketch")
        if not lokasi_induk:
            return

        folder_sketch = os.path.join(lokasi_induk, nama)
        os.makedirs(folder_sketch, exist_ok=True)
        self.sketch_folder = folder_sketch
        self.ino_path = os.path.join(folder_sketch, f"{nama}.ino")

        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", "void setup() {\n  \n}\n\nvoid loop() {\n  \n}\n")
        self._highlight_syntax()
        self._update_line_numbers()
        self._simpan_file()
        self._update_title()
        self._tulis_output(f"[INFO] Sketch baru dibuat: {self.ino_path}\n")

    def sketch_buka(self):
        path = filedialog.askopenfilename(
            filetypes=[("Arduino Sketch", "*.ino")]
        )
        if not path:
            return
        self.ino_path = path
        self.sketch_folder = os.path.dirname(path)
        with open(path, "r", encoding="utf-8") as f:
            isi = f.read()
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", isi)
        self._highlight_syntax()
        self._update_line_numbers()
        self._update_title()

    def sketch_simpan(self):
        if not self.ino_path:
            self.sketch_baru()
        else:
            self._simpan_file()
            self._tulis_output(f"[INFO] Disimpan: {self.ino_path}\n")

    def _simpan_file(self):
        if self.ino_path:
            with open(self.ino_path, "w", encoding="utf-8") as f:
                f.write(self.text_area.get("1.0", tk.END))

    def _update_title(self):
        nama = os.path.basename(self.ino_path) if self.ino_path else "untitled.ino"
        self.root.title(f"{nama} | Arduino CLI Editor")
        self.label_tab.config(text=nama)

    # ========================================================
    # SETTING BOARD / PORT
    # ========================================================
    def set_fqbn(self):
        nilai = simpledialog.askstring("Set Board (FQBN)", "Contoh: arduino:avr:uno", initialvalue=self.fqbn)
        if nilai:
            self.fqbn = nilai
            self.label_board.config(text=self.fqbn)

    def set_port(self):
        nilai = simpledialog.askstring("Set Port", "Contoh: /dev/ttyACM0", initialvalue=self.port)
        if nilai:
            self.port = nilai
            self._update_status_bar()

    def list_boards(self):
        self._tulis_output("Mencari board yang terhubung...\n", bersihkan=True)
        self.root.update()
        try:
            hasil = subprocess.run(
                ["arduino-cli", "board", "list"],
                capture_output=True, text=True, timeout=20
            )
            self._tulis_output(hasil.stdout)
            if hasil.stderr:
                self._tulis_output(hasil.stderr)
        except FileNotFoundError:
            self._tulis_output("[ERROR] arduino-cli tidak ditemukan. Install dulu: sudo pacman -S arduino-cli\n")
        except Exception as e:
            self._tulis_output(f"[ERROR] {e}\n")

    # ========================================================
    # VERIFY / COMPILE (pakai arduino-cli compile)
    # ========================================================
    def verify_kode(self):
        if not self._pastikan_sketch_siap():
            return

        self._tulis_output("Compiling sketch...\n", bersihkan=True)
        self.root.update()

        try:
            hasil = subprocess.run(
                ["arduino-cli", "compile", "--fqbn", self.fqbn, self.sketch_folder],
                capture_output=True, text=True, timeout=120
            )
            self._tulis_output(hasil.stdout)
            if hasil.stderr:
                self._tulis_output(hasil.stderr)

            if hasil.returncode == 0:
                self._tulis_output("Done compiling.\n")
            else:
                self._tulis_output(f"[ERROR] Compile gagal (exit code {hasil.returncode})\n")
        except FileNotFoundError:
            self._tulis_output("[ERROR] arduino-cli tidak ditemukan. Install dulu: sudo pacman -S arduino-cli\n")
        except subprocess.TimeoutExpired:
            self._tulis_output("[ERROR] Compile timeout.\n")

    # ========================================================
    # UPLOAD (pakai arduino-cli upload, otomatis compile dulu)
    # ========================================================
    def upload_kode(self):
        if not self._pastikan_sketch_siap():
            return

        self._tulis_output(f"Uploading ke {self.port} ({self.fqbn})...\n", bersihkan=True)
        self.root.update()

        try:
            hasil = subprocess.run(
                [
                    "arduino-cli", "upload", "-p", self.port,
                    "--fqbn", self.fqbn, self.sketch_folder
                ],
                capture_output=True, text=True, timeout=120
            )
            self._tulis_output(hasil.stdout)
            if hasil.stderr:
                self._tulis_output(hasil.stderr)

            if hasil.returncode == 0:
                self._tulis_output("Done uploading.\n")
            else:
                self._tulis_output(f"[ERROR] Upload gagal (exit code {hasil.returncode})\n")
        except FileNotFoundError:
            self._tulis_output("[ERROR] arduino-cli tidak ditemukan. Install dulu: sudo pacman -S arduino-cli\n")
        except subprocess.TimeoutExpired:
            self._tulis_output("[ERROR] Upload timeout.\n")

    def _pastikan_sketch_siap(self):
        if not self.ino_path:
            messagebox.showinfo("Info", "Buat/simpan sketch dulu (File > New Sketch atau Ctrl+S).")
            self.sketch_baru()
            if not self.ino_path:
                return False
        else:
            self._simpan_file()
        return True

    # ========================================================
    # FITUR HEX VIEWER
    # ========================================================
    def _tampilkan_hex(self, path):
        """Baca file biner, tampilkan hex di panel Output, simpan versi penuh."""
        ukuran = os.path.getsize(path)
        teks_penuh = hex_dump_file(path)
        self.hex_terakhir = (path, teks_penuh)

        header = f"Hex dump: {path}  ({ukuran} byte)\n"
        header += "OFFSET    00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F  ASCII\n"
        self._tulis_output(header, bersihkan=True)
        self._tulis_output(hex_dump_file(path, MAX_TAMPIL_BYTE))
        if ukuran > MAX_TAMPIL_BYTE:
            self._tulis_output(
                f"\n... dipotong, tampil {MAX_TAMPIL_BYTE} dari {ukuran} byte. "
                "Pakai Hex > Simpan Hex ke .txt untuk versi lengkap.\n"
            )

    def hex_buka_file(self):
        path = filedialog.askopenfilename(title="Pilih file untuk dilihat hex-nya")
        if path:
            try:
                self._tampilkan_hex(path)
            except Exception as e:
                self._tulis_output(f"[ERROR] {e}\n", bersihkan=True)

    def hex_hasil_compile(self):
        """Compile sketch, lalu tampilkan hex dari firmware hasil compile (.bin / .hex)."""
        if not self._pastikan_sketch_siap():
            return

        folder_build = os.path.join(self.sketch_folder, "build")
        self._tulis_output("Compiling sketch untuk hex dump...\n", bersihkan=True)
        self.root.update()

        try:
            hasil = subprocess.run(
                ["arduino-cli", "compile", "--fqbn", self.fqbn,
                 "--output-dir", folder_build, self.sketch_folder],
                capture_output=True, text=True, timeout=180
            )
        except FileNotFoundError:
            self._tulis_output("[ERROR] arduino-cli tidak ditemukan.\n")
            return
        except subprocess.TimeoutExpired:
            self._tulis_output("[ERROR] Compile timeout.\n")
            return

        if hasil.returncode != 0:
            self._tulis_output(hasil.stdout + hasil.stderr)
            self._tulis_output("[ERROR] Compile gagal, hex tidak bisa dibuat.\n")
            return

        nama = os.path.basename(self.ino_path)
        kandidat = [
            os.path.join(folder_build, nama + ".bin"),   # ESP32 (firmware aplikasi)
            os.path.join(folder_build, nama + ".hex"),   # AVR (Uno/Nano)
        ]
        target = next((k for k in kandidat if os.path.exists(k)), None)
        if not target:
            self._tulis_output(f"[ERROR] File .bin/.hex tidak ditemukan di {folder_build}\n")
            return
        self._tampilkan_hex(target)

    def hex_simpan_txt(self):
        if not self.hex_terakhir:
            path = filedialog.askopenfilename(title="Pilih file yang mau di-hex-dump ke .txt")
            if not path:
                return
            self._tampilkan_hex(path)

        sumber, teks = self.hex_terakhir
        tujuan = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=os.path.basename(sumber) + ".hex.txt",
            filetypes=[("Text File", "*.txt")]
        )
        if tujuan:
            with open(tujuan, "w", encoding="utf-8") as f:
                f.write(teks)
            self._tulis_output(f"\n[INFO] Hex lengkap disimpan: {tujuan}\n")

    # ========================================================
    # CLIPBOARD (copy/paste yang andal di Linux/Wayland)
    # ========================================================
    def _setup_clipboard(self):
        for widget, bisa_edit in ((self.text_area, True), (self.output_console, False)):
            # Klik = ambil fokus, supaya Ctrl+C bekerja juga di panel Output
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
        # Di Wayland (Hyprland), sinkronkan juga ke clipboard sistem kalau wl-copy ada
        if shutil.which("wl-copy"):
            try:
                p = subprocess.Popen(
                    ["wl-copy"], stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
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
            widget.delete("sel.first", "sel.last")   # ganti teks yang sedang diblok
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
        menu = tk.Menu(self.root, tearoff=0)
        if bisa_edit:
            menu.add_command(label="Cut", command=lambda: self._potong(widget))
        menu.add_command(label="Copy", command=lambda: self._salin(widget))
        if bisa_edit:
            menu.add_command(label="Paste", command=lambda: self._tempel(widget))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: self._pilih_semua(widget))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"


def mode_terminal(argv):
    """python arduino_cli_ide.py --hex <file> [--out hasil.txt]"""
    if len(argv) < 3:
        print("Pemakaian: python arduino_cli_ide.py --hex <file> [--out hasil.txt]")
        return 1
    sumber = argv[2]
    if not os.path.isfile(sumber):
        print(f"File tidak ditemukan: {sumber}")
        return 1
    teks = hex_dump_file(sumber)
    if "--out" in argv and argv.index("--out") + 1 < len(argv):
        tujuan = argv[argv.index("--out") + 1]
        with open(tujuan, "w", encoding="utf-8") as f:
            f.write(teks)
        print(f"Hex disimpan ke {tujuan}")
    else:
        print(teks, end="")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--hex":
        sys.exit(mode_terminal(sys.argv))
    root = tk.Tk()
    app = ArduinoCliIDE(root)
    root.mainloop()