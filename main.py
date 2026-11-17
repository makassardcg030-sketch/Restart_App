import json
import os
import socket
import threading
from datetime import datetime
# ini kita coba branch
# test branch kedua
# test gis
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.animation import Animation
from kivy.graphics import Color, Ellipse, RoundedRectangle
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.textinput import TextInput


# ============================================================
# KONFIGURASI
# ============================================================

DB_DEFAULTS = {
    "host": "",
    "port": 3306,
    "user": "",
    "password": "",
    "database": "",
}

# Mapping Dropdown Label -> Value Database/Sistem
TIPE_OPTIONS = {
    "DPD": "STANDARD",
    "DCP": "P_MAP",
    "REOPEN DPD": "REOPEN",
}
TIPE_LABELS = {v: k for k, v in TIPE_OPTIONS.items()}

DB_TIMEOUT = 5

CLIENT_PORT = 5005
SOCKET_TIMEOUT = 2
CONFIRM_BEFORE_SEND = False

COLUMNS = 2

# Tema warna
BG = (0.055, 0.085, 0.13, 1)
PANEL = (0.09, 0.14, 0.21, 1)
CARD_BG = (0.12, 0.19, 0.28, 1)
WHITE = (0.94, 0.96, 0.99, 1)
MUTED = (0.62, 0.70, 0.79, 1)
BLUE = (0.13, 0.48, 0.78, 1)
GREEN = (0.12, 0.60, 0.40, 1)
ORANGE = (0.85, 0.43, 0.12, 1)
RED = (0.80, 0.22, 0.22, 1)

SECTIONS = [
    ("RESTART", "STANDARD", lambda z: "RUN_MACRO",
     lambda z: "Zona " + z, BLUE),

    ("DCP", "P_MAP", lambda z: "RESTART_DCP_" + z,
     lambda z: "DCP " + z, GREEN),

    ("REOPEN DPD", "REOPEN", lambda z: "RESTART_PROGRAM",
     lambda z: "Zona " + z, ORANGE),
]


# ============================================================
# FUNGSI DATABASE & FORMAT DATA
# ============================================================

def zona_sort_key(z):
    return (0, int(z)) if str(z).isdigit() else (1, str(z))


def group_and_sort_rows(rows):
    """Mengelompokkan list tuple (zona, tipe, ip) menjadi dict terurut."""
    data = {}
    for zona, tipe, ip in rows:
        if ip and zona and tipe:
            data.setdefault(tipe, []).append((str(zona).strip(), str(ip).strip()))

    for tipe in data:
        data[tipe].sort(key=lambda r: zona_sort_key(r[0]))

    return data


def fetch_zones_from_db(cfg):
    import pymysql

    conn = pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        connect_timeout=DB_TIMEOUT,
    )

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT zona, tipe, ip_target FROM tbl_restart"
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return group_and_sort_rows(rows)


# ============================================================
# SOCKET CLIENT
# ============================================================

def send_command(ip, command):
    try:
        with socket.create_connection(
            (ip, CLIENT_PORT),
            timeout=SOCKET_TIMEOUT
        ) as s:
            s.sendall(command.encode("utf-8"))
            s.settimeout(SOCKET_TIMEOUT)

            try:
                resp = s.recv(1024).decode(errors="ignore").strip()
            except socket.timeout:
                resp = ""

        if "OK" in resp:
            return True, "Perintah berhasil dijalankan."

        if "BUSY" in resp:
            return False, "BENTROK: Target sedang menjalankan perintah user lain. Tunggu beberapa detik lalu coba lagi."

        return False, "Respons client: " + (resp or "Tidak ada respons")

    except Exception as e:
        return False, "Gagal koneksi ke {}: {}".format(ip, e)


# ============================================================
# KOMPONEN UI
# ============================================================

class RoundedPanel(BoxLayout):

    def __init__(self, bg_color=PANEL, radius=16, **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color

        with self.canvas.before:
            self.bg_instruction = Color(*bg_color)
            self.rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[dp(radius)]
            )

        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *_):
        self.rect.pos = self.pos
        self.rect.size = self.size


class ActionCard(ButtonBehavior, BoxLayout):

    def __init__(self, title, subtitle, color, **kwargs):
        super().__init__(
            orientation="vertical",
            padding=[dp(14), dp(12)],
            spacing=dp(5),
            **kwargs
        )

        self.base_color = color

        with self.canvas.before:
            self.bg_color_instruction = Color(*CARD_BG)
            self.rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[dp(15)]
            )

        with self.canvas.after:
            self.accent_color = Color(*color)
            self.accent = RoundedRectangle(
                pos=self.pos,
                size=(dp(5), self.height),
                radius=[dp(3)]
            )

        self.bind(pos=self.update_rect, size=self.update_rect)

        self.add_widget(
            Label(
                text=title,
                font_size="19sp",
                bold=True,
                color=WHITE,
                halign="left",
                valign="middle",
                size_hint_y=0.65
            )
        )

        self.add_widget(
            Label(
                text=subtitle,
                font_size="12sp",
                color=MUTED,
                halign="left",
                valign="middle",
                size_hint_y=0.35
            )
        )

    def update_rect(self, *_):
        self.rect.pos = self.pos
        self.rect.size = self.size
        self.accent.pos = self.pos
        self.accent.size = (dp(5), self.height)

    def on_press(self):
        self.bg_color_instruction.rgba = (0.17, 0.25, 0.35, 1)

    def on_release(self):
        self.bg_color_instruction.rgba = CARD_BG


class DcpGroupCard(RoundedPanel):

    ZONE_COLS = 3
    BTN_H = dp(43)
    GAP = dp(7)

    def __init__(self, ip, zones, color, on_zone, **kwargs):
        super().__init__(
            bg_color=CARD_BG,
            orientation="vertical",
            padding=dp(12),
            spacing=dp(10),
            size_hint_y=None,
            **kwargs
        )

        self.color = color

        header = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(8))
        header.add_widget(
            Label(
                text="[b]IP TARGET[/b]",
                markup=True,
                color=WHITE,
                font_size="15sp",
                halign="left"
            )
        )
        header.add_widget(
            Label(
                text=ip,
                color=MUTED,
                font_size="13sp",
                halign="right"
            )
        )
        self.add_widget(header)

        line = BoxLayout(size_hint_y=None, height=dp(1))
        with line.canvas:
            Color(0.27, 0.35, 0.44, 1)
            Rectangle = RoundedRectangle(pos=line.pos, size=line.size)

        line.bind(
            pos=lambda w, p: setattr(Rectangle, "pos", p),
            size=lambda w, s: setattr(Rectangle, "size", s)
        )
        self.add_widget(line)

        rows = -(-len(zones) // self.ZONE_COLS)
        grid = GridLayout(
            cols=self.ZONE_COLS,
            spacing=self.GAP,
            size_hint_y=None
        )
        grid.height = rows * self.BTN_H + max(0, rows - 1) * self.GAP

        for z in zones:
            b = Button(
                text="ZONA " + z,
                bold=True,
                font_size="12sp",
                color=WHITE,
                background_normal="",
                background_down="",
                background_color=color
            )
            b.bind(on_release=lambda btn, zz=z: on_zone(zz))
            grid.add_widget(b)

        self.add_widget(grid)

        self.height = dp(24) + dp(35) + dp(1) + dp(10) + grid.height


# ============================================================
# APLIKASI UTAMA
# ============================================================

class RestartApp(App):

    title = "Restart DPD Control Center"

    def build(self):
        self.data = {}
        self.current = 0
        self.busy = False

        self.cache_file = os.path.join(self.user_data_dir, "zones_cache.json")
        self.config_file = os.path.join(self.user_data_dir, "db_config.json")
        self.manual_file = os.path.join(self.user_data_dir, "manual_zones.json")
        self.mode_file = os.path.join(self.user_data_dir, "source_mode.json")

        self.source_mode = self.read_source_mode()  # "db" atau "manual"
        self.db_config = self.read_db_config()
        self.manual_zones = self.read_manual_zones()  # list of [zona, tipe, ip]

        # Root
        root = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(10)
        )

        with root.canvas.before:
            Color(*BG)
            self.root_bg = RoundedRectangle(pos=root.pos, size=root.size)

        root.bind(pos=self.update_root, size=self.update_root)

        # HEADER
        header = RoundedPanel(
            bg_color=PANEL,
            orientation="horizontal",
            padding=dp(14),
            spacing=dp(10),
            size_hint_y=None,
            height=dp(78)
        )

        title_box = BoxLayout(orientation="vertical", spacing=dp(2))
        title_box.add_widget(
            Label(
                text="[b]RESTART DPD[/b]",
                markup=True,
                font_size="22sp",
                color=WHITE,
                halign="left",
                valign="middle"
            )
        )
        title_box.add_widget(
            Label(
                text="CONTROL CENTER  |  SYSTEM MANAGEMENT",
                font_size="10sp",
                color=MUTED,
                halign="left"
            )
        )
        header.add_widget(title_box)

        refresh = Button(
            text="REFRESH",
            size_hint_x=None,
            width=dp(90),
            bold=True,
            font_size="12sp",
            background_normal="",
            background_color=BLUE
        )
        refresh.bind(on_release=lambda *_: self.load_zones())

        setting = Button(
            text="SETTING",
            size_hint_x=None,
            width=dp(90),
            bold=True,
            font_size="12sp",
            background_normal="",
            background_color=CARD_BG
        )
        setting.bind(on_release=lambda *_: self.open_settings())

        header.add_widget(setting)
        header.add_widget(refresh)
        root.add_widget(header)

        # NAVIGASI TAB
        self.tabs = []
        tab_header = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(5))

        for i, sec in enumerate(SECTIONS):
            b = ToggleButton(
                text=sec[0],
                group="restart_tabs",
                state="down" if i == 0 else "normal",
                allow_no_selection=False,
                bold=True,
                font_size="12sp",
                background_normal="",
                background_down="",
                background_color=PANEL,
                color=MUTED
            )
            b.bind(on_release=lambda btn, idx=i: self.select_tab(idx))
            self.tabs.append(b)
            tab_header.add_widget(b)

        root.add_widget(tab_header)

        # AREA KONTEN
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.grid = GridLayout(
            cols=COLUMNS,
            spacing=dp(10),
            padding=dp(2),
            size_hint_y=None,
            row_force_default=True,
            row_default_height=dp(112)
        )
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.scroll.add_widget(self.grid)
        root.add_widget(self.scroll)

        # PANEL AKTIVITAS
        activity = RoundedPanel(
            bg_color=PANEL,
            orientation="vertical",
            padding=[dp(12), dp(7)],
            spacing=dp(3),
            size_hint_y=None,
            height=dp(72)
        )

        activity_header = BoxLayout(size_hint_y=None, height=dp(20))
        activity_header.add_widget(
            Label(
                text="[b]SYSTEM ACTIVITY[/b]",
                markup=True,
                color=WHITE,
                font_size="11sp",
                halign="left"
            )
        )

        self.connection_label = Label(
            text="READY",
            color=GREEN,
            font_size="10sp",
            bold=True
        )
        activity_header.add_widget(self.connection_label)
        activity.add_widget(activity_header)

        self.status = Label(
            text="Menunggu data zona...",
            font_size="11sp",
            color=MUTED,
            halign="left",
            valign="middle",
            text_size=(None, None)
        )
        activity.add_widget(self.status)
        root.add_widget(activity)

        Clock.schedule_once(lambda *_: self.load_zones(), 0.5)
        return root

    def update_root(self, instance, *_):
        self.root_bg.pos = instance.pos
        self.root_bg.size = instance.size

    # ========================================================
    # PENYIMPANAN KONFIGURASI (DB & MANUAL)
    # ========================================================

    def read_source_mode(self):
        try:
            with open(self.mode_file, "r") as f:
                data = json.load(f)
            if data.get("mode") in ("db", "manual"):
                return data["mode"]
        except Exception:
            pass
        return "db"

    def save_source_mode(self, mode):
        with open(self.mode_file, "w") as f:
            json.dump({"mode": mode}, f)
        self.source_mode = mode

    def read_db_config(self):
        try:
            with open(self.config_file, "r") as f:
                cfg = json.load(f)
            if cfg.get("host") and cfg.get("user") and cfg.get("database"):
                return cfg
        except Exception:
            pass
        return None

    def save_db_config(self, cfg):
        with open(self.config_file, "w") as f:
            json.dump(cfg, f)
        self.db_config = cfg

    def read_manual_zones(self):
        try:
            with open(self.manual_file, "r") as f:
                rows = json.load(f)
            if isinstance(rows, list):
                return rows
        except Exception:
            pass
        return []

    def save_manual_zones(self, rows):
        with open(self.manual_file, "w") as f:
            json.dump(rows, f)
        self.manual_zones = rows

    # ========================================================
    # POPUP PENGATURAN (DATABASE & MANUAL)
    # ========================================================

    def open_settings(self, first_time=False):
        root_box = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10)
        )

        # Pemilih Mode Sumber Data
        mode_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        btn_mode_db = ToggleButton(
            text="MODE DATABASE",
            group="cfg_mode",
            state="down" if self.source_mode == "db" else "normal",
            allow_no_selection=False,
            bold=True,
            font_size="12sp",
            background_normal="",
            background_down="",
        )
        btn_mode_manual = ToggleButton(
            text="MODE MANUAL",
            group="cfg_mode",
            state="down" if self.source_mode == "manual" else "normal",
            allow_no_selection=False,
            bold=True,
            font_size="12sp",
            background_normal="",
            background_down="",
        )
        mode_row.add_widget(btn_mode_db)
        mode_row.add_widget(btn_mode_manual)
        root_box.add_widget(mode_row)

        # Container dinamis untuk konten form
        form_container = BoxLayout(orientation="vertical")
        root_box.add_widget(form_container)

        err = Label(
            text="",
            color=RED,
            font_size="11sp",
            size_hint_y=None,
            height=dp(20)
        )
        root_box.add_widget(err)

        # Tombol Aksi Bawah
        action_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        save_btn = Button(
            text="SIMPAN & TERAPKAN",
            background_normal="",
            background_color=GREEN,
            bold=True
        )
        action_row.add_widget(save_btn)

        pop = Popup(
            title="Pengaturan Sumber Zona",
            content=root_box,
            size_hint=(0.94, None),
            height=dp(540),
            auto_dismiss=not first_time
        )

        if not first_time:
            cancel_btn = Button(
                text="BATAL",
                background_normal="",
                background_color=RED,
                bold=True
            )
            cancel_btn.bind(on_release=pop.dismiss)
            action_row.add_widget(cancel_btn)

        root_box.add_widget(action_row)

        # --- STATE & WIDGET FORM DATABASE ---
        cfg = self.db_config or DB_DEFAULTS
        db_box = BoxLayout(orientation="vertical", spacing=dp(6))
        db_fields = {}
        for key, label, secret in [
            ("host", "Host / IP", False),
            ("port", "Port", False),
            ("user", "User", False),
            ("password", "Password", True),
            ("database", "Nama Database", False),
        ]:
            db_box.add_widget(Label(
                text=label,
                font_size="12sp",
                color=MUTED,
                halign="left",
                size_hint_y=None,
                height=dp(18)
            ))
            ti = TextInput(
                text=str(cfg.get(key, "")),
                multiline=False,
                password=secret,
                write_tab=False,
                size_hint_y=None,
                height=dp(38)
            )
            db_fields[key] = ti
            db_box.add_widget(ti)
        db_box.add_widget(Label())  # spacer

        # --- STATE & WIDGET FORM MANUAL ---
        temp_manual = [list(r) for r in self.manual_zones]
        manual_box = BoxLayout(orientation="vertical", spacing=dp(8))

        # Baris input tambah zona
        input_grid = GridLayout(cols=3, spacing=dp(6), size_hint_y=None, height=dp(62))
        input_grid.add_widget(Label(text="Zona", font_size="11sp", color=MUTED, size_hint_y=None, height=dp(18)))
        input_grid.add_widget(Label(text="Tipe", font_size="11sp", color=MUTED, size_hint_y=None, height=dp(18)))
        input_grid.add_widget(Label(text="IP Target", font_size="11sp", color=MUTED, size_hint_y=None, height=dp(18)))

        in_zona = TextInput(
            hint_text="cth: 1",
            multiline=False,
            write_tab=False,
            size_hint_y=None,
            height=dp(38)
        )
        in_tipe = Spinner(
            text="DPD",
            values=list(TIPE_OPTIONS.keys()),  # ["DPD", "DCP", "REOPEN DPD"]
            size_hint_y=None,
            height=dp(38),
            background_normal="",
            background_color=BLUE,
            bold=True,
            font_size="12sp"
        )
        in_ip = TextInput(
            hint_text="192.168.1.10",
            multiline=False,
            write_tab=False,
            size_hint_y=None,
            height=dp(38)
        )
        input_grid.add_widget(in_zona)
        input_grid.add_widget(in_tipe)
        input_grid.add_widget(in_ip)
        manual_box.add_widget(input_grid)

        add_zone_btn = Button(
            text="+ TAMBAH ZONA KE DAFTAR",
            size_hint_y=None,
            height=dp(36),
            background_normal="",
            background_color=BLUE,
            bold=True,
            font_size="12sp"
        )
        manual_box.add_widget(add_zone_btn)

        # Scroll daftar zona manual yang sudah ditambahkan
        list_scroll = ScrollView(do_scroll_x=False)
        list_container = BoxLayout(
            orientation="vertical",
            spacing=dp(4),
            size_hint_y=None
        )
        list_container.bind(minimum_height=list_container.setter("height"))
        list_scroll.add_widget(list_container)
        manual_box.add_widget(list_scroll)

        def refresh_manual_list():
            list_container.clear_widgets()
            if not temp_manual:
                list_container.add_widget(Label(
                    text="Belum ada zona manual.",
                    color=MUTED,
                    font_size="12sp",
                    size_hint_y=None,
                    height=dp(40)
                ))
                return

            for idx, (z, t_val, ip_addr) in enumerate(temp_manual):
                row_item = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
                t_label = TIPE_LABELS.get(t_val, t_val)
                lbl = Label(
                    text="Zona {}  |  {} ({})  |  {}".format(z, t_label, t_val, ip_addr),
                    font_size="11sp",
                    color=WHITE,
                    halign="left",
                    valign="middle"
                )
                lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))

                del_btn = Button(
                    text="Hapus",
                    size_hint_x=None,
                    width=dp(58),
                    font_size="11sp",
                    background_normal="",
                    background_color=RED
                )
                del_btn.bind(on_release=lambda *_, i=idx: remove_item(i))

                row_item.add_widget(lbl)
                row_item.add_widget(del_btn)
                list_container.add_widget(row_item)

        def remove_item(idx):
            if 0 <= idx < len(temp_manual):
                temp_manual.pop(idx)
                refresh_manual_list()

        def on_add_zone(*_):
            err.text = ""
            z = in_zona.text.strip()
            ip_addr = in_ip.text.strip()
            t_val = TIPE_OPTIONS[in_tipe.text]  # Konversi DPD -> STANDARD, dst.

            if not z or not ip_addr:
                err.text = "Zona dan IP Target wajib diisi."
                return

            temp_manual.append([z, t_val, ip_addr])
            in_zona.text = ""
            refresh_manual_list()

        add_zone_btn.bind(on_release=on_add_zone)
        refresh_manual_list()

        # --- LOGIKA PERPINDAHAN TAMPILAN MODE ---
        def update_mode_view(*_):
            err.text = ""
            form_container.clear_widgets()
            if btn_mode_db.state == "down":
                btn_mode_db.background_color = BLUE
                btn_mode_manual.background_color = CARD_BG
                form_container.add_widget(db_box)
            else:
                btn_mode_manual.background_color = BLUE
                btn_mode_db.background_color = CARD_BG
                form_container.add_widget(manual_box)

        btn_mode_db.bind(on_release=update_mode_view)
        btn_mode_manual.bind(on_release=update_mode_view)
        update_mode_view()

        # --- SIMPAN PENGATURAN ---
        def do_save(*_):
            err.text = ""
            if btn_mode_db.state == "down":
                new_db = {k: v.text.strip() for k, v in db_fields.items()}
                if not (new_db["host"] and new_db["user"] and new_db["database"]):
                    err.text = "Host, User, dan Database wajib diisi."
                    return
                try:
                    new_db["port"] = int(new_db["port"] or 3306)
                except ValueError:
                    err.text = "Port harus berupa angka."
                    return

                self.save_db_config(new_db)
                self.save_source_mode("db")
            else:
                if not temp_manual:
                    err.text = "Tambahkan minimal 1 zona untuk mode manual."
                    return
                self.save_manual_zones(temp_manual)
                self.save_source_mode("manual")

            pop.dismiss()
            self.load_zones()

        save_btn.bind(on_release=do_save)
        pop.open()

    # ========================================================
    # LOAD DATA ZONA (DB ATAU MANUAL)
    # ========================================================

    def load_zones(self):
        if self.busy:
            return

        # 1. Jika menggunakan Mode Manual
        if self.source_mode == "manual":
            if not self.manual_zones:
                self.connection_label.text = "MANUAL KOSONG"
                self.connection_label.color = ORANGE
                self.set_status("Daftar zona manual kosong. Silakan isi di Setting.")
                self.open_settings(first_time=True)
                return

            data = group_and_sort_rows(self.manual_zones)
            self.data = data
            self.connection_label.text = "MANUAL MODE"
            self.connection_label.color = BLUE
            self.set_status("Konfigurasi manual dimuat ({} item).".format(len(self.manual_zones)))
            self.render()
            return

        # 2. Jika menggunakan Mode Database
        if not self.db_config:
            self.connection_label.text = "BELUM DISETTING"
            self.connection_label.color = ORANGE
            self.set_status("Pilih konfigurasi Database atau Manual.")
            self.open_settings(first_time=True)
            return

        self.set_status("Mengambil data dari database...")
        self.connection_label.text = "LOADING"
        self.connection_label.color = ORANGE

        threading.Thread(target=self._load_thread, daemon=True).start()

    def _load_thread(self):
        try:
            data = fetch_zones_from_db(self.db_config)
            with open(self.cache_file, "w") as f:
                json.dump(data, f)
            msg = "Database berhasil dimuat."
            connected = True
        except Exception as e:
            try:
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                msg = "Database gagal. Menggunakan cache terakhir."
                connected = False
            except Exception:
                data = {}
                msg = "Database gagal: {}".format(e)
                connected = False

        Clock.schedule_once(
            lambda *_: self._apply_data(data, msg, connected)
        )

    def _apply_data(self, data, msg, connected):
        self.data = data
        if connected:
            self.connection_label.text = "DB CONNECTED"
            self.connection_label.color = GREEN
        else:
            self.connection_label.text = "CACHE MODE"
            self.connection_label.color = ORANGE

        self.set_status(msg)
        self.render()

    # ========================================================
    # NAVIGASI
    # ========================================================

    def select_tab(self, idx):
        self.current = idx
        for i, tab in enumerate(self.tabs):
            if i == idx:
                tab.background_color = SECTIONS[i][4]
                tab.color = WHITE
            else:
                tab.background_color = PANEL
                tab.color = MUTED
        self.render()

    # ========================================================
    # RENDER KONTEN
    # ========================================================

    def render(self):
        self.grid.clear_widgets()

        _, tipe, cmd_fn, label_fn, color = SECTIONS[self.current]
        items = self.data.get(tipe, [])

        if not items:
            self.grid.cols = 1
            self.grid.row_force_default = False

            empty = Label(
                text=(
                    "\n\n"
                    "[b]DATA TIDAK DITEMUKAN[/b]\n"
                    "[color=9EADBD]"
                    "Tidak ada zona untuk kategori ini."
                    "[/color]"
                ),
                markup=True,
                color=WHITE,
                font_size="15sp",
                halign="center"
            )
            self.grid.add_widget(empty)
            return

        if tipe == "P_MAP":
            self.grid.cols = 1
            self.grid.row_force_default = False

            groups = {}
            for zona, ip in items:
                groups.setdefault(ip, []).append(zona)

            for ip, zonas in sorted(groups.items()):
                card = DcpGroupCard(
                    ip,
                    zonas,
                    color,
                    on_zone=lambda z, i=ip, f=cmd_fn, l=label_fn:
                    self.on_card(l(z), i, f(z))
                )
                self.grid.add_widget(card)
            return

        self.grid.cols = COLUMNS
        self.grid.row_force_default = True
        self.grid.row_default_height = dp(112)

        for zona, ip in items:
            card = ActionCard(
                title=label_fn(zona),
                subtitle="TARGET : " + ip,
                color=color
            )
            card.bind(
                on_release=lambda c, z=zona, i=ip,
                f=cmd_fn, l=label_fn:
                self.on_card(l(z), i, f(z))
            )
            self.grid.add_widget(card)

    # ========================================================
    # EKSEKUSI PERINTAH
    # ========================================================

    def on_card(self, name, ip, command):
        if self.busy:
            self.set_status("Sedang memproses perintah sebelumnya...")
            return

        if CONFIRM_BEFORE_SEND:
            box = BoxLayout(
                orientation="vertical",
                padding=dp(15),
                spacing=dp(10)
            )
            box.add_widget(
                Label(
                    text=(
                        "Kirim perintah berikut?\n\n"
                        "[b]{}[/b]\n"
                        "Target: {}\n"
                        "IP: {}"
                    ).format(command, name, ip),
                    markup=True,
                    color=WHITE
                )
            )

            row = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(10))
            pop = Popup(
                title="Konfirmasi Perintah",
                content=box,
                size_hint=(0.85, 0.4),
                separator_color=BLUE,
                background_color=PANEL
            )

            yes = Button(
                text="KIRIM",
                background_normal="",
                background_color=GREEN,
                bold=True
            )
            no = Button(
                text="BATAL",
                background_normal="",
                background_color=RED,
                bold=True
            )

            yes.bind(
                on_release=lambda *_: (
                    pop.dismiss(),
                    self.execute(name, ip, command)
                )
            )
            no.bind(on_release=pop.dismiss)

            row.add_widget(yes)
            row.add_widget(no)
            box.add_widget(row)
            pop.open()
        else:
            self.execute(name, ip, command)

    def execute(self, name, ip, command):
        if self.busy:
            return

        self.busy = True
        self.set_status(
            "Mengirim {} ke {} ({})...".format(command, name, ip)
        )
        self.connection_label.text = "PROCESSING"
        self.connection_label.color = ORANGE

        def work():
            ok, msg = send_command(ip, command)
            if ok:
                result = "[SUKSES] {} - Perintah {} berhasil.".format(name, command)
                status_color = GREEN
            else:
                result = "[GAGAL] {} - {}".format(name, msg)
                status_color = RED

            Clock.schedule_once(
                lambda *_: self.finish_execute(result, status_color, ok)
            )

        threading.Thread(target=work, daemon=True).start()

    def finish_execute(self, result, color, ok):
        self.busy = False
        self.set_status(result)
        self.connection_label.text = "COMMAND OK" if ok else "COMMAND FAILED"
        self.connection_label.color = color
        self.show_result_popup(ok, result)

    def show_result_popup(self, ok, detail):
        old = getattr(self, "_result_pop", None)
        if old:
            try:
                old.dismiss()
            except Exception:
                pass

        accent = GREEN if ok else RED
        title = "BERHASIL" if ok else "GAGAL"
        icon = "OK" if ok else "X"

        if detail.startswith("["):
            detail = detail.split("]", 1)[-1].strip()

        card = RoundedPanel(
            bg_color=PANEL,
            orientation="vertical",
            padding=dp(16),
            spacing=dp(8)
        )

        badge = BoxLayout(
            size_hint=(None, None),
            size=(dp(64), dp(64)),
            pos_hint={"center_x": 0.5}
        )
        with badge.canvas.before:
            Color(*accent)
            circle = Ellipse(pos=badge.pos, size=badge.size)

        badge.bind(
            pos=lambda w, p: setattr(circle, "pos", p),
            size=lambda w, sz: setattr(circle, "size", sz)
        )
        badge.add_widget(
            Label(
                text="[b]{}[/b]".format(icon),
                markup=True,
                font_size="24sp",
                color=WHITE
            )
        )

        wrap = BoxLayout(size_hint_y=None, height=dp(64))
        wrap.add_widget(Label())
        wrap.add_widget(badge)
        wrap.add_widget(Label())
        card.add_widget(wrap)

        card.add_widget(
            Label(
                text="[b]{}[/b]".format(title),
                markup=True,
                font_size="20sp",
                color=accent,
                size_hint_y=None,
                height=dp(30)
            )
        )

        msg = Label(
            text=detail,
            font_size="12sp",
            color=MUTED,
            halign="center",
            valign="top"
        )
        msg.bind(
            size=lambda w, sz: setattr(w, "text_size", (sz[0], None))
        )
        card.add_widget(msg)

        pop = Popup(
            title="",
            separator_height=0,
            content=card,
            size_hint=(0.8, None),
            height=dp(240),
            background="",
            background_color=(0, 0, 0, 0),
            overlay_color=(0, 0, 0, 0.45),
            auto_dismiss=True,
            opacity=0
        )

        self._result_pop = pop
        pop.open()
        Animation(opacity=1, d=0.15).start(pop)

        def close(*_):
            if self._result_pop is pop:
                a = Animation(opacity=0, d=0.2)
                a.bind(on_complete=lambda *__: pop.dismiss())
                a.start(pop)

        Clock.schedule_once(close, 1.3 if ok else 3.5)

    # ========================================================
    # STATUS
    # ========================================================

    def set_status(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status.text = "[{}] {}".format(timestamp, text)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    RestartApp().run()
