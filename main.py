import json
import os
import socket
import threading
from datetime import datetime

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
# FUNGSI DATABASE
# ============================================================

def zona_sort_key(z):
    return (0, int(z)) if str(z).isdigit() else (1, str(z))


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

    data = {}

    for zona, tipe, ip in rows:
        if ip:
            data.setdefault(tipe, []).append(
                (str(zona), ip)
            )

    for tipe in data:
        data[tipe].sort(
            key=lambda r: zona_sort_key(r[0])
        )

    return data


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
                resp = s.recv(1024).decode(
                    errors="ignore"
                ).strip()

            except socket.timeout:
                resp = ""

        if "OK" in resp:
            return True, "Perintah berhasil dijalankan."

        return False, "Respons client: " + (
            resp or "Tidak ada respons"
        )

    except Exception as e:
        return False, "Gagal koneksi ke {}: {}".format(ip, e)


# ============================================================
# KOMPONEN UI
# ============================================================

class RoundedPanel(BoxLayout):

    def __init__(
        self,
        bg_color=PANEL,
        radius=16,
        **kwargs
    ):
        super().__init__(**kwargs)

        self.bg_color = bg_color

        with self.canvas.before:
            self.bg_instruction = Color(*bg_color)
            self.rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[dp(radius)]
            )

        self.bind(
            pos=self.update_rect,
            size=self.update_rect
        )

    def update_rect(self, *_):
        self.rect.pos = self.pos
        self.rect.size = self.size


class ActionCard(ButtonBehavior, BoxLayout):

    def __init__(
        self,
        title,
        subtitle,
        color,
        **kwargs
    ):
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

        self.bind(
            pos=self.update_rect,
            size=self.update_rect
        )

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
        self.bg_color_instruction.rgba = (
            0.17, 0.25, 0.35, 1
        )

    def on_release(self):
        self.bg_color_instruction.rgba = CARD_BG


class DcpGroupCard(ButtonBehavior, RoundedPanel):

    ZONE_COLS = 3
    BTN_H = dp(43)
    GAP = dp(7)

    def __init__(
        self,
        ip,
        zones,
        color,
        **kwargs
    ):
        super().__init__(
            bg_color=CARD_BG,
            orientation="vertical",
            padding=dp(12),
            spacing=dp(10),
            size_hint_y=None,
            **kwargs
        )

        self.color = color

        # Header IP
        header = BoxLayout(
            size_hint_y=None,
            height=dp(35),
            spacing=dp(8)
        )

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

        # Garis pembatas
        line = BoxLayout(
            size_hint_y=None,
            height=dp(1)
        )

        with line.canvas:
            Color(0.27, 0.35, 0.44, 1)
            Rectangle = RoundedRectangle(
                pos=line.pos,
                size=line.size
            )

        line.bind(
            pos=lambda w, p: setattr(
                Rectangle, "pos", p
            ),
            size=lambda w, s: setattr(
                Rectangle, "size", s
            )
        )

        self.add_widget(line)

        # Zona
        rows = -(-len(zones) // self.ZONE_COLS)

        grid = GridLayout(
            cols=self.ZONE_COLS,
            spacing=self.GAP,
            size_hint_y=None
        )

        grid.height = (
            rows * self.BTN_H
            + max(0, rows - 1) * self.GAP
        )

        for z in zones:

            b = Label(
                text="ZONA " + z,
                bold=True,
                font_size="12sp",
                color=WHITE
            )

            with b.canvas.before:
                Color(*color)
                chip_rect = RoundedRectangle(
                    pos=b.pos,
                    size=b.size,
                    radius=[dp(6)]
                )

            b.bind(
                pos=lambda w, p, r=chip_rect: setattr(r, "pos", p),
                size=lambda w, sz, r=chip_rect: setattr(r, "size", sz)
            )

            grid.add_widget(b)

        self.add_widget(grid)

        self.height = (
            dp(24)
            + dp(35)
            + dp(1)
            + dp(10)
            + grid.height
        )


# ============================================================
# APLIKASI UTAMA
# ============================================================

class RestartApp(App):

    title = "Restart DPD Control Center"

    def build(self):

        self.data = {}
        self.current = 0
        self.busy = False

        self.cache_file = os.path.join(
            self.user_data_dir,
            "zones_cache.json"
        )

        self.config_file = os.path.join(
            self.user_data_dir,
            "db_config.json"
        )

        self.db_config = self.read_db_config()

        # Root
        root = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(10)
        )

        with root.canvas.before:
            Color(*BG)
            self.root_bg = RoundedRectangle(
                pos=root.pos,
                size=root.size
            )

        root.bind(
            pos=self.update_root,
            size=self.update_root
        )

        # ====================================================
        # HEADER
        # ====================================================

        header = RoundedPanel(
            bg_color=PANEL,
            orientation="horizontal",
            padding=dp(14),
            spacing=dp(10),
            size_hint_y=None,
            height=dp(78)
        )

        title_box = BoxLayout(
            orientation="vertical",
            spacing=dp(2)
        )

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

        refresh.bind(
            on_release=lambda *_: self.load_zones()
        )

        setting = Button(
            text="SETTING",
            size_hint_x=None,
            width=dp(90),
            bold=True,
            font_size="12sp",
            background_normal="",
            background_color=CARD_BG
        )

        setting.bind(
            on_release=lambda *_: self.open_settings()
        )

        header.add_widget(setting)
        header.add_widget(refresh)

        root.add_widget(header)

        
        

        # ====================================================
        # NAVIGASI TAB
        # ====================================================

        self.tabs = []

        tab_header = BoxLayout(
            size_hint_y=None,
            height=dp(45),
            spacing=dp(5)
        )

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

            b.bind(
                on_release=lambda btn, idx=i:
                self.select_tab(idx)
            )

            self.tabs.append(b)
            tab_header.add_widget(b)

        root.add_widget(tab_header)

        # ====================================================
        # AREA KONTEN
        # ====================================================

        self.scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4)
        )

        self.grid = GridLayout(
            cols=COLUMNS,
            spacing=dp(10),
            padding=dp(2),
            size_hint_y=None,
            row_force_default=True,
            row_default_height=dp(112)
        )

        self.grid.bind(
            minimum_height=self.grid.setter("height")
        )

        self.scroll.add_widget(self.grid)

        root.add_widget(self.scroll)

        # ====================================================
        # PANEL AKTIVITAS
        # ====================================================

        activity = RoundedPanel(
            bg_color=PANEL,
            orientation="vertical",
            padding=[dp(12), dp(7)],
            spacing=dp(3),
            size_hint_y=None,
            height=dp(72)
        )

        activity_header = BoxLayout(
            size_hint_y=None,
            height=dp(20)
        )

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

        activity_header.add_widget(
            self.connection_label
        )

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

        Clock.schedule_once(
            lambda *_: self.load_zones(),
            0.5
        )

        return root

    def update_root(self, instance, *_):
        self.root_bg.pos = instance.pos
        self.root_bg.size = instance.size

    # ========================================================
    # DATABASE
    # ========================================================

    def read_db_config(self):
        try:
            with open(self.config_file, "r") as f:
                cfg = json.load(f)
            if cfg.get("host") and cfg.get("user") \
                    and cfg.get("database"):
                return cfg
        except Exception:
            pass
        return None

    def save_db_config(self, cfg):
        with open(self.config_file, "w") as f:
            json.dump(cfg, f)
        self.db_config = cfg

    def open_settings(self, first_time=False):

        cfg = self.db_config or DB_DEFAULTS

        box = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(10)
        )

        fields = {}

        for key, label, secret in [
            ("host", "Host / IP", False),
            ("port", "Port", False),
            ("user", "User", False),
            ("password", "Password", True),
            ("database", "Nama Database", False),
        ]:
            box.add_widget(Label(
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
                height=dp(40)
            )
            fields[key] = ti
            box.add_widget(ti)

        err = Label(
            text="",
            color=RED,
            font_size="11sp",
            size_hint_y=None,
            height=dp(20)
        )
        box.add_widget(err)

        row = BoxLayout(
            size_hint_y=None,
            height=dp(44),
            spacing=dp(8)
        )

        save = Button(
            text="SIMPAN",
            background_normal="",
            background_color=GREEN,
            bold=True
        )
        row.add_widget(save)

        pop = Popup(
            title="Pengaturan Database",
            content=box,
            size_hint=(0.92, None),
            height=dp(470),
            auto_dismiss=not first_time
        )

        if not first_time:
            cancel = Button(
                text="BATAL",
                background_normal="",
                background_color=RED,
                bold=True
            )
            cancel.bind(on_release=pop.dismiss)
            row.add_widget(cancel)

        box.add_widget(row)

        def do_save(*_):
            new = {k: v.text.strip() for k, v in fields.items()}
            if not (new["host"] and new["user"]
                    and new["database"]):
                err.text = "Host, User, dan Database wajib diisi"
                return
            try:
                new["port"] = int(new["port"] or 3306)
            except ValueError:
                err.text = "Port harus angka"
                return
            self.save_db_config(new)
            pop.dismiss()
            self.load_zones()

        save.bind(on_release=do_save)

        pop.open()

    def load_zones(self):

        if self.busy:
            return

        if not self.db_config:
            self.connection_label.text = "BELUM DISETTING"
            self.connection_label.color = ORANGE
            self.set_status("Isi pengaturan database dulu.")
            self.open_settings(first_time=True)
            return

        self.set_status(
            "Mengambil data dari database..."
        )

        self.connection_label.text = "LOADING"
        self.connection_label.color = ORANGE

        threading.Thread(
            target=self._load_thread,
            daemon=True
        ).start()

    def _load_thread(self):

        try:

            data = fetch_zones_from_db(self.db_config)

            with open(
                self.cache_file,
                "w"
            ) as f:
                json.dump(data, f)

            msg = "Database berhasil dimuat."

            connected = True

        except Exception as e:

            try:

                with open(
                    self.cache_file,
                    "r"
                ) as f:
                    data = json.load(f)

                msg = "Database gagal. Menggunakan cache terakhir."

                connected = False

            except Exception:

                data = {}

                msg = "Database gagal: {}".format(e)

                connected = False

        Clock.schedule_once(
            lambda *_: self._apply_data(
                data,
                msg,
                connected
            )
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
    # STATISTIK
    # ========================================================

    

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

        _, tipe, cmd_fn, label_fn, color = SECTIONS[
            self.current
        ]

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

        # DCP: Kelompok berdasarkan IP
        if tipe == "P_MAP":

            self.grid.cols = 1
            self.grid.row_force_default = False

            groups = {}

            for zona, ip in items:

                groups.setdefault(
                    ip, []
                ).append(zona)

            for ip, zonas in sorted(groups.items()):

                card = DcpGroupCard(
                    ip,
                    zonas,
                    color
                )

                card.bind(
                    on_release=lambda c, i=ip, zs=list(zonas),
                    f=cmd_fn:
                    self.on_group(i, zs, f)
                )

                self.grid.add_widget(card)

            return

        # RESTART / REOPEN
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
            self.set_status(
                "Sedang memproses perintah sebelumnya..."
            )
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

            row = BoxLayout(
                size_hint_y=None,
                height=dp(45),
                spacing=dp(10)
            )

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

            no.bind(
                on_release=pop.dismiss
            )

            row.add_widget(yes)
            row.add_widget(no)

            box.add_widget(row)

            pop.open()

        else:

            self.execute(name, ip, command)

    def on_group(self, ip, zonas, cmd_fn):

        if self.busy:
            self.set_status(
                "Sedang memproses perintah sebelumnya..."
            )
            return

        if not CONFIRM_BEFORE_SEND:
            self.execute_group(ip, zonas, cmd_fn)
            return

        box = BoxLayout(
            orientation="vertical",
            padding=dp(15),
            spacing=dp(10)
        )

        box.add_widget(
            Label(
                text=(
                    "Restart DCP di IP target ini?\n\n"
                    "[b]{}[/b]\n"
                    "{} zona"
                ).format(ip, len(zonas)),
                markup=True,
                color=WHITE
            )
        )

        row = BoxLayout(
            size_hint_y=None,
            height=dp(45),
            spacing=dp(10)
        )

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
                self.execute_group(ip, zonas, cmd_fn)
            )
        )

        no.bind(on_release=pop.dismiss)

        row.add_widget(yes)
        row.add_widget(no)
        box.add_widget(row)

        pop.open()

    def execute_group(self, ip, zonas, cmd_fn):

        if self.busy:
            return

        self.busy = True

        self.set_status(
            "Mengirim restart DCP ke {} ({} zona)...".format(
                ip, len(zonas)
            )
        )

        self.connection_label.text = "PROCESSING"
        self.connection_label.color = ORANGE

        def work():

            failed = []
            last_msg = ""

            for z in zonas:
                ok, msg = send_command(ip, cmd_fn(z))
                if not ok:
                    failed.append(z)
                    last_msg = msg

            total = len(zonas)

            if not failed:
                result = (
                    "[SUKSES] DCP {} - {} zona berhasil."
                    .format(ip, total)
                )
                status_color = GREEN
                ok_all = True
            else:
                result = (
                    "[GAGAL] DCP {} - {}/{} zona gagal ({}). {}"
                    .format(
                        ip,
                        len(failed),
                        total,
                        ", ".join(failed),
                        last_msg
                    )
                )
                status_color = RED
                ok_all = False

            Clock.schedule_once(
                lambda *_: self.finish_execute(
                    result,
                    status_color,
                    ok_all
                )
            )

        threading.Thread(
            target=work,
            daemon=True
        ).start()

    def execute(self, name, ip, command):

        if self.busy:
            return

        self.busy = True

        self.set_status(
            "Mengirim {} ke {} ({})...".format(
                command, name, ip
            )
        )

        self.connection_label.text = "PROCESSING"
        self.connection_label.color = ORANGE

        def work():

            ok, msg = send_command(
                ip,
                command
            )

            if ok:

                result = (
                    "[SUKSES] {} - Perintah {} berhasil."
                    .format(name, command)
                )

                status_color = GREEN

            else:

                result = (
                    "[GAGAL] {} - {}"
                    .format(name, msg)
                )

                status_color = RED

            Clock.schedule_once(
                lambda *_: self.finish_execute(
                    result,
                    status_color,
                    ok
                )
            )

        threading.Thread(
            target=work,
            daemon=True
        ).start()

    def finish_execute(self, result, color, ok):

        self.busy = False

        self.set_status(result)

        self.connection_label.text = (
            "COMMAND OK" if ok else "COMMAND FAILED"
        )

        self.connection_label.color = color

        self.show_result_popup(ok, result)

    def show_result_popup(self, ok, detail):

        # Tutup popup hasil sebelumnya
        old = getattr(self, "_result_pop", None)
        if old:
            try:
                old.dismiss()
            except Exception:
                pass

        accent = GREEN if ok else RED
        title = "BERHASIL" if ok else "GAGAL"
        icon = "OK" if ok else "X"

        # Buang prefix [SUKSES] / [GAGAL] dari detail
        if detail.startswith("["):
            detail = detail.split("]", 1)[-1].strip()

        card = RoundedPanel(
            bg_color=PANEL,
            orientation="vertical",
            padding=dp(16),
            spacing=dp(8)
        )

        # Lingkaran ikon
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

        # Hilang otomatis tanpa konfirmasi
        Clock.schedule_once(close, 1.3 if ok else 2.2)

    # ========================================================
    # STATUS
    # ========================================================

    def set_status(self, text):

        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )

        self.status.text = "[{}] {}".format(
            timestamp,
            text
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    RestartApp().run()
