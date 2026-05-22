from __future__ import annotations

import logging
import queue
import subprocess
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError as exc:  # pragma: no cover - only used on machines without GUI dependency.
    raise SystemExit("CustomTkinter is not installed. Run: python -m pip install customtkinter") from exc

from ragecoop_core import (
    LauncherConfig,
    LauncherError,
    extract_claim_url,
    extract_public_address,
    find_client_settings,
    find_game_executable,
    find_ragecoop_plus_installer,
    find_ragecoop_plus_server_exe,
    find_vpn_executable,
    get_app_root,
    get_vpn_ipv4,
    install_mod_loaders_from_adjacent_zips,
    install_ragecoop_from_adjacent_zips,
    ensure_mod_loaders_installed,
    ensure_ragecoop_client_installed,
    launch_vpn_client,
    normalize_address,
    read_server_port,
    resolve_app_path,
    setup_logging,
    setup_ragecoop_plus_package,
    start_server_process,
    start_ragecoop_plus_installer,
    start_ragecoop_plus_server_process,
    start_tunnel_process,
    terminate_process,
    update_client_settings,
    write_default_config,
)


COLORS = {
    "window": "#07111F",
    "surface": "#0D1829",
    "surface_2": "#111F33",
    "surface_3": "#16263C",
    "stroke": "#24364F",
    "muted": "#9AA8BA",
    "text": "#EEF4FF",
    "accent": "#38BDF8",
    "accent_hover": "#0EA5E9",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
}


class RageCoopLauncherApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.app_root = get_app_root()
        self.config = LauncherConfig.load(self.app_root)
        write_default_config(self.app_root, self.config)
        self.log_path = setup_logging(self.app_root, self.config)

        self.server_process: subprocess.Popen[str] | None = None
        self.tunnel_process: subprocess.Popen[str] | None = None
        self.public_address: str | None = None
        self.selected_game_root: Path | None = self._default_game_root()
        self.selected_host_root: Path = self.selected_game_root or self.app_root
        self.selected_host_game_root: Path | None = self.selected_game_root
        self.ui_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running_threads: list[threading.Thread] = []
        self.busy_targets: set[str] = set()
        self.animation_tick = 0
        self.tunnel_output_buffer: list[str] = []
        self.pending_host_root: Path | None = None
        self.pending_host_game_root: Path | None = None
        self.pending_player_game_root: Path | None = None
        self.pending_player_address: str | None = None

        self.title("GTA V RAGECOOP Launcher")
        self.geometry("1040x720")
        self.minsize(900, 640)
        self.configure(fg_color=COLORS["window"])
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_ui()
        self.after(100, self._drain_ui_queue)
        self.after(160, self._animate_status)
        self.log(f"Рабочая папка: {self.app_root}")
        self.log(f"Лог: {self.log_path}")

    def _default_game_root(self) -> Path | None:
        return self.app_root if find_game_executable(self.app_root, self.config.game_exe_candidates) else None

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        self.tabs = ctk.CTkTabview(
            self,
            fg_color=COLORS["surface"],
            segmented_button_fg_color=COLORS["surface_2"],
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_selected_hover_color=COLORS["accent_hover"],
            segmented_button_unselected_color=COLORS["surface_2"],
            segmented_button_unselected_hover_color=COLORS["surface_3"],
            text_color=COLORS["text"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["stroke"],
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.tabs.add("Я Хост")
        self.tabs.add("Я Игрок")

        self._build_host_tab(self.tabs.tab("Я Хост"))
        self._build_player_tab(self.tabs.tab("Я Игрок"))

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=COLORS["window"], corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 14))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="GTA V RAGECOOP",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle_text = "One-click кооператив: сервер, VPN/UDP-адрес и запуск игры из одного окна"
        subtitle = ctk.CTkLabel(
            header,
            text=subtitle_text,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=14),
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(2, 0))

        backend_text = f"{self.config.tunnel_backend}"
        if self.config.tunnel_backend.lower() == "ngrok_tcp":
            backend_text += " / experimental TCP"
        if self.uses_local_vpn_backend():
            backend_text += " / LAN VPN"
        backend = ctk.CTkLabel(
            header,
            text=f"Backend: {backend_text}",
            text_color=COLORS["accent"],
            fg_color=COLORS["surface_2"],
            corner_radius=8,
            padx=14,
            pady=7,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        backend.grid(row=0, column=1, rowspan=2, sticky="e", padx=(16, 0))

    def _panel(self, parent: ctk.CTkBaseClass) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=COLORS["surface_2"],
            border_width=1,
            border_color=COLORS["stroke"],
            corner_radius=12,
        )

    def _build_host_tab(self, tab: ctk.CTkFrame) -> None:
        tab.configure(fg_color=COLORS["surface"])
        tab.grid_columnconfigure(0, weight=1, uniform="host")
        tab.grid_columnconfigure(1, weight=2, uniform="host")
        tab.grid_rowconfigure(0, weight=1)

        steps_panel = self._panel(tab)
        steps_panel.grid(row=0, column=0, sticky="nsew", padx=(12, 8), pady=12)
        steps_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            steps_panel,
            text="Сценарий хоста",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))

        if self.uses_local_vpn_backend():
            host_steps = [
                "1. Включи VPN-сеть: WireGuard / OpenVPN / Nebula",
                "2. Выбери папку GTA V хоста",
                "3. Лаунчер поставит мод и запустит сервер",
                "4. Отправь другу VPN IP с портом 4499",
            ]
        else:
            host_steps = [
                "1. Выбери папку GTA V хоста",
                "2. Лаунчер поставит мод и запустит сервер",
                "3. Отправь адрес другу",
                "4. Не закрывай окно во время игры",
            ]

        for row, text in enumerate(host_steps, start=1):
            ctk.CTkLabel(
                steps_panel,
                text=text,
                anchor="w",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=14),
            ).grid(row=row, column=0, sticky="ew", padx=18, pady=5)

        self.host_progress = ctk.CTkProgressBar(
            steps_panel,
            mode="indeterminate",
            progress_color=COLORS["accent"],
            fg_color=COLORS["surface_3"],
        )
        self.host_progress.grid(row=5, column=0, sticky="ew", padx=18, pady=(18, 8))
        self.host_progress.set(0)

        self.host_dot = ctk.CTkLabel(
            steps_panel,
            text="●",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.host_dot.grid(row=6, column=0, sticky="w", padx=18, pady=(4, 0))

        self.host_status = ctk.CTkLabel(
            steps_panel,
            text="Сервер остановлен",
            anchor="w",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.host_status.grid(row=6, column=0, sticky="ew", padx=(42, 18), pady=(4, 0))

        main_panel = self._panel(tab)
        main_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 12), pady=12)
        main_panel.grid_columnconfigure(0, weight=1)
        main_panel.grid_rowconfigure(12, weight=1)

        ctk.CTkLabel(
            main_panel,
            text="Папка хоста",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 6))

        host_folder_row = ctk.CTkFrame(main_panel, fg_color="transparent")
        host_folder_row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        host_folder_row.grid_columnconfigure(0, weight=1)

        self.host_folder_entry = ctk.CTkEntry(
            host_folder_row,
            height=40,
            fg_color=COLORS["window"],
            border_color=COLORS["stroke"],
            text_color=COLORS["text"],
            placeholder_text="Папка, где лежит/будет server",
            placeholder_text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13),
        )
        self.host_folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.host_folder_entry.insert(0, str(self.selected_host_root))

        self.host_browse_button = ctk.CTkButton(
            host_folder_row,
            text="Выбрать",
            width=118,
            height=40,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            command=self.choose_host_folder,
        )
        self.host_browse_button.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            main_panel,
            text="Папка GTA V хоста",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=2, column=0, sticky="w", padx=18, pady=(0, 6))

        host_game_row = ctk.CTkFrame(main_panel, fg_color="transparent")
        host_game_row.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 12))
        host_game_row.grid_columnconfigure(0, weight=1)

        self.host_game_folder_entry = ctk.CTkEntry(
            host_game_row,
            height=40,
            fg_color=COLORS["window"],
            border_color=COLORS["stroke"],
            text_color=COLORS["text"],
            placeholder_text="Корневая папка GTA V, куда ставить RAGECOOP клиент",
            placeholder_text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13),
        )
        self.host_game_folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        if self.selected_host_game_root:
            self.host_game_folder_entry.insert(0, str(self.selected_host_game_root))

        self.host_game_browse_button = ctk.CTkButton(
            host_game_row,
            text="Выбрать",
            width=118,
            height=40,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            command=self.choose_host_game_folder,
        )
        self.host_game_browse_button.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            main_panel,
            text="Адрес для друга",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=4, column=0, sticky="w", padx=18, pady=(0, 6))

        address_box = ctk.CTkFrame(main_panel, fg_color=COLORS["window"], corner_radius=10)
        address_box.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 12))
        address_box.grid_columnconfigure(0, weight=1)

        self.address_label = ctk.CTkLabel(
            address_box,
            text="Нажми «Запустить сервер»",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=26, weight="bold"),
            wraplength=560,
        )
        self.address_label.grid(row=0, column=0, sticky="ew", padx=18, pady=20)

        manual_row = ctk.CTkFrame(main_panel, fg_color="transparent")
        manual_row.grid(row=6, column=0, sticky="ew", padx=18, pady=(0, 12))
        manual_row.grid_columnconfigure(0, weight=1)

        self.host_manual_address = ctk.CTkEntry(
            manual_row,
            height=40,
            fg_color=COLORS["window"],
            border_color=COLORS["stroke"],
            text_color=COLORS["text"],
            placeholder_text="Если адрес известен вручную, вставь сюда host:port",
            placeholder_text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13),
        )
        self.host_manual_address.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.host_apply_address_button = ctk.CTkButton(
            manual_row,
            text="Применить",
            width=118,
            height=40,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            command=self.apply_manual_host_address,
        )
        self.host_apply_address_button.grid(row=0, column=1, sticky="e")

        vpn_row = ctk.CTkFrame(main_panel, fg_color="transparent")
        vpn_row.grid(row=7, column=0, sticky="ew", padx=18, pady=(0, 12))
        vpn_row.grid_columnconfigure((0, 1), weight=1)

        self.vpn_open_button = ctk.CTkButton(
            vpn_row,
            text="Открыть VPN",
            height=40,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.open_vpn_client,
        )
        self.vpn_open_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.vpn_ip_button = ctk.CTkButton(
            vpn_row,
            text="Обновить VPN IP",
            height=40,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.refresh_vpn_address,
        )
        self.vpn_ip_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        buttons = ctk.CTkFrame(main_panel, fg_color="transparent")
        buttons.grid(row=8, column=0, sticky="ew", padx=18, pady=(0, 12))
        buttons.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.start_button = ctk.CTkButton(
            buttons,
            text="Запустить сервер",
            height=44,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#04111F",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.start_host,
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.stop_button = ctk.CTkButton(
            buttons,
            text="Остановить",
            height=44,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.stop_host,
        )
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=8)

        self.copy_button = ctk.CTkButton(
            buttons,
            text="Скопировать",
            height=44,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.copy_address,
        )
        self.copy_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self.copy_log_button = ctk.CTkButton(
            buttons,
            text="Копировать журнал",
            height=44,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.copy_host_log,
        )
        self.copy_log_button.grid(row=0, column=3, sticky="ew", padx=(8, 0))

        plus_buttons = ctk.CTkFrame(main_panel, fg_color="transparent")
        plus_buttons.grid(row=9, column=0, sticky="ew", padx=18, pady=(0, 12))
        plus_buttons.grid_columnconfigure((0, 1, 2), weight=1)

        self.ragecoop_plus_prepare_button = ctk.CTkButton(
            plus_buttons,
            text="Подготовить RageCoop+",
            height=40,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.prepare_ragecoop_plus,
        )
        self.ragecoop_plus_prepare_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.ragecoop_plus_installer_button = ctk.CTkButton(
            plus_buttons,
            text="Открыть RageCoop+ installer",
            height=40,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.open_ragecoop_plus_installer,
        )
        self.ragecoop_plus_installer_button.grid(row=0, column=1, sticky="ew", padx=8)

        self.ragecoop_plus_server_button = ctk.CTkButton(
            plus_buttons,
            text="RageCoop+ server",
            height=40,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.start_ragecoop_plus_server,
        )
        self.ragecoop_plus_server_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self.host_hint = ctk.CTkLabel(
            main_panel,
            text=self._host_hint_text(),
            text_color=COLORS["muted"],
            wraplength=620,
            justify="left",
        )
        self.host_hint.grid(row=10, column=0, sticky="ew", padx=18, pady=(0, 12))

        ctk.CTkLabel(
            main_panel,
            text="Журнал",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=11, column=0, sticky="w", padx=18, pady=(0, 6))

        self.host_log = ctk.CTkTextbox(
            main_panel,
            height=260,
            fg_color=COLORS["window"],
            text_color=COLORS["text"],
            border_width=1,
            border_color=COLORS["stroke"],
            corner_radius=10,
        )
        self.host_log.grid(row=12, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.host_log.configure(state="disabled")

    def _build_player_tab(self, tab: ctk.CTkFrame) -> None:
        tab.configure(fg_color=COLORS["surface"])
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        top_panel = self._panel(tab)
        top_panel.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        top_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top_panel,
            text="Подключение игрока",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 4))

        ctk.CTkLabel(
            top_panel,
            text="Выбери папку GTA V, введи адрес хоста и нажми запуск. Лаунчер сам поставит RAGECOOP-клиент, пропишет адрес и запустит GTA V.",
            text_color=COLORS["muted"],
            wraplength=860,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))

        ctk.CTkLabel(
            top_panel,
            text="Папка GTA V",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=2, column=0, sticky="w", padx=18, pady=(0, 6))

        folder_row = ctk.CTkFrame(top_panel, fg_color="transparent")
        folder_row.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 12))
        folder_row.grid_columnconfigure(0, weight=1)

        self.player_game_folder = ctk.CTkEntry(
            folder_row,
            height=42,
            placeholder_text="Например: D:\\Games\\Grand Theft Auto V",
            fg_color=COLORS["window"],
            border_color=COLORS["stroke"],
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["muted"],
            font=ctk.CTkFont(size=14),
        )
        self.player_game_folder.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        if self.selected_game_root:
            self.player_game_folder.insert(0, str(self.selected_game_root))

        self.player_browse_button = ctk.CTkButton(
            folder_row,
            text="Выбрать",
            width=120,
            height=42,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            command=self.choose_player_game_folder,
        )
        self.player_browse_button.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            top_panel,
            text="Адрес хоста",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=4, column=0, sticky="w", padx=18, pady=(0, 6))

        address_row = ctk.CTkFrame(top_panel, fg_color="transparent")
        address_row.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 12))
        address_row.grid_columnconfigure(0, weight=1)

        self.player_address = ctk.CTkEntry(
            address_row,
            height=44,
            placeholder_text=self.config.default_player_address or "Вставь адрес хоста, например 10.x.x.x:4499",
            fg_color=COLORS["window"],
            border_color=COLORS["stroke"],
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["muted"],
            font=ctk.CTkFont(size=15),
        )
        self.player_address.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        if self.config.default_player_address:
            self.player_address.insert(0, self.config.default_player_address)

        self.player_paste_button = ctk.CTkButton(
            address_row,
            text="Вставить",
            width=120,
            height=44,
            fg_color=COLORS["surface_3"],
            hover_color=COLORS["stroke"],
            command=self.paste_player_address,
        )
        self.player_paste_button.grid(row=0, column=1, sticky="e")

        self.launch_game_button = ctk.CTkButton(
            top_panel,
            text="Добавить кооператив и запустить GTA 5",
            height=48,
            fg_color=COLORS["success"],
            hover_color="#16A34A",
            text_color="#04110B",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.start_player_flow,
        )
        self.launch_game_button.grid(row=6, column=0, sticky="ew", padx=18, pady=(0, 12))

        ctk.CTkLabel(
            top_panel,
            text=self._player_instruction_text(),
            text_color=COLORS["warning"],
            wraplength=860,
            justify="left",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=7, column=0, sticky="ew", padx=18, pady=(0, 14))

        status_row = ctk.CTkFrame(top_panel, fg_color="transparent")
        status_row.grid(row=8, column=0, sticky="ew", padx=18, pady=(0, 16))
        status_row.grid_columnconfigure(1, weight=1)

        self.player_dot = ctk.CTkLabel(
            status_row,
            text="●",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.player_dot.grid(row=0, column=0, sticky="w")

        self.player_status = ctk.CTkLabel(
            status_row,
            text="Ожидание адреса",
            anchor="w",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.player_status.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        self.player_progress = ctk.CTkProgressBar(
            status_row,
            mode="indeterminate",
            progress_color=COLORS["success"],
            fg_color=COLORS["surface_3"],
        )
        self.player_progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.player_progress.set(0)

        log_panel = self._panel(tab)
        log_panel.grid(row=1, column=0, sticky="nsew", padx=12, pady=(8, 12))
        log_panel.grid_columnconfigure(0, weight=1)
        log_panel.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            log_panel,
            text="Журнал",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 6))

        self.player_log = ctk.CTkTextbox(
            log_panel,
            height=260,
            fg_color=COLORS["window"],
            text_color=COLORS["text"],
            border_width=1,
            border_color=COLORS["stroke"],
            corner_radius=10,
        )
        self.player_log.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.player_log.configure(state="disabled")

    def log(self, message: str, target: str = "both") -> None:
        logging.info(message)
        self.ui_queue.put((target, message))

    def _append_log(self, textbox: ctk.CTkTextbox, message: str) -> None:
        textbox.configure(state="normal")
        textbox.insert("end", message.rstrip() + "\n")
        textbox.see("end")
        textbox.configure(state="disabled")

    def _drain_ui_queue(self) -> None:
        while True:
            try:
                target, message = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if target in {"both", "host"}:
                self._append_log(self.host_log, message)
            if target in {"both", "player"}:
                self._append_log(self.player_log, message)

        self.after(100, self._drain_ui_queue)

    def _animate_status(self) -> None:
        self.animation_tick += 1
        pulse = [COLORS["accent"], "#7DD3FC", COLORS["success"], "#7DD3FC"]
        color = pulse[self.animation_tick % len(pulse)]

        self.host_dot.configure(text_color=color if "host" in self.busy_targets else COLORS["muted"])
        self.player_dot.configure(text_color=color if "player" in self.busy_targets else COLORS["muted"])
        self.after(260, self._animate_status)

    def set_busy(self, target: str, is_busy: bool) -> None:
        def update() -> None:
            progress = self.host_progress if target == "host" else self.player_progress
            if is_busy:
                self.busy_targets.add(target)
                progress.start()
            else:
                self.busy_targets.discard(target)
                progress.stop()
                progress.set(0)

        self.after(0, update)

    def uses_local_vpn_backend(self) -> bool:
        return self.config.tunnel_backend.lower().strip() in {"vpn_lan", "radmin_vpn"}

    def _host_hint_text(self) -> str:
        if self.uses_local_vpn_backend():
            return (
                "Лаунчер автоматически ставит RAGECOOP-клиент в папку GTA V хоста и использует уже включённую "
                "VPN-сеть: WireGuard, OpenVPN, Nebula, ZeroTier "
                "или похожий адаптер. Друг должен быть в этой же сети. Адрес обычно выглядит как 10.x.x.x:4499 "
                "или 26.x.x.x:4499."
            )
        return (
            "Положи playit.exe в выбранную папку хоста или рядом с лаунчером. "
            "Если туннель показал адрес в консоли, вставь его в поле выше и нажми «Применить»."
        )

    def _player_instruction_text(self) -> str:
        if self.uses_local_vpn_backend():
            return (
                "Перед запуском GTA убедись, что ты в той же VPN-сети, что и хост. Затем запусти GTA, дождись "
                "одиночной игры, нажми F9 и в меню RAGECOOP выбери Connect/Подключиться."
            )
        return (
            "После запуска GTA: дождись загрузки в одиночную игру, нажми F9, "
            "в меню RAGECOOP выбери Connect/Подключиться. Адрес уже будет подставлен как последний сервер."
        )

    def run_threaded(self, action) -> None:
        thread = threading.Thread(target=action, daemon=True)
        self.running_threads.append(thread)
        thread.start()

    def _ragecoop_plus_source_roots(self) -> list[Path]:
        roots = [self.app_root]
        downloads = Path.home() / "Downloads"
        if downloads.exists():
            roots.append(downloads)
        return roots

    def prepare_ragecoop_plus(self) -> None:
        self.set_busy("host", True)
        self.set_host_status("Preparing RageCoop+...")

        def worker() -> None:
            try:
                for message in setup_ragecoop_plus_package(
                    self.app_root,
                    self.config,
                    source_roots=self._ragecoop_plus_source_roots(),
                ):
                    self.log(message, "host")
                self.log(
                    "Next: open RageCoop+ installer, choose Enhanced, and select the folder with GTA5_Enhanced.exe.",
                    "host",
                )
                self.set_host_status("RageCoop+ package is ready")
            except LauncherError as exc:
                self.set_host_status("RageCoop+ error")
                self.log(f"RageCoop+ error: {exc}", "host")
                self.after(0, lambda: messagebox.showerror("RageCoop+", str(exc)))
            except Exception as exc:  # pragma: no cover - defensive GUI guard.
                logging.exception("Unexpected RageCoop+ setup error")
                self.set_host_status("RageCoop+ error")
                self.log(f"Unexpected RageCoop+ error: {exc}", "host")
            finally:
                self.set_busy("host", False)

        self.run_threaded(worker)

    def open_ragecoop_plus_installer(self) -> None:
        self.set_busy("host", True)
        self.set_host_status("Opening RageCoop+ installer...")

        def worker() -> None:
            try:
                process = start_ragecoop_plus_installer(self.config)
                self.log(f"RageCoop+ installer opened: {find_ragecoop_plus_installer(self.config)}", "host")
                self.log(
                    "In installer: select Enhanced, choose the GTA folder with GTA5_Enhanced.exe, then click Install.",
                    "host",
                )
                self.log(f"Installer process id: {process.pid}", "host")
                self.set_host_status("RageCoop+ installer opened")
            except LauncherError as exc:
                self.set_host_status("RageCoop+ installer not found")
                self.log(f"RageCoop+ installer error: {exc}", "host")
                self.after(0, lambda: messagebox.showerror("RageCoop+", str(exc)))
            except Exception as exc:  # pragma: no cover - defensive GUI guard.
                logging.exception("Unexpected RageCoop+ installer error")
                self.set_host_status("RageCoop+ error")
                self.log(f"Unexpected RageCoop+ installer error: {exc}", "host")
            finally:
                self.set_busy("host", False)

        self.run_threaded(worker)

    def start_ragecoop_plus_server(self) -> None:
        if self.server_process and self.server_process.poll() is None:
            self.log("Server is already running. Stop it before starting RageCoop+ server.", "host")
            return

        self.set_busy("host", True)
        self.set_host_status("Starting RageCoop+ server...")

        def worker() -> None:
            try:
                server_exe = find_ragecoop_plus_server_exe(self.config)
                self.server_process = start_ragecoop_plus_server_process(self.config)
                self.log(f"RageCoop+ server started: {server_exe}", "host")
                self._start_reader(self.server_process, "ragecoop+", "host")

                server_dir = Path(self.config.ragecoop_plus_server_dir)
                port = read_server_port(server_dir / "Settings.xml", self.config.default_port)
                vpn_info = get_vpn_ipv4(self.config.vpn_adapter_keywords)
                if vpn_info:
                    adapter_name, ip_address = vpn_info
                    address = normalize_address(f"{ip_address}:{port}")
                    self.set_public_address(address)
                    self.log(f"VPN address for RageCoop+ ({adapter_name}): {address}", "host")
                else:
                    self.log("VPN IP was not detected. Use ZeroTier IP or forwarded public IP manually.", "host")
                self.set_host_status("RageCoop+ server running")
            except LauncherError as exc:
                self.set_host_status("RageCoop+ server error")
                self.log(f"RageCoop+ server error: {exc}", "host")
                self.after(0, lambda: messagebox.showerror("RageCoop+", str(exc)))
            except Exception as exc:  # pragma: no cover - defensive GUI guard.
                logging.exception("Unexpected RageCoop+ server error")
                self.set_host_status("RageCoop+ server error")
                self.log(f"Unexpected RageCoop+ server error: {exc}", "host")
            finally:
                self.set_busy("host", False)

        self.run_threaded(worker)

    def set_host_status(self, text: str) -> None:
        self.after(0, lambda: self.host_status.configure(text=text))

    def set_player_status(self, text: str) -> None:
        self.after(0, lambda: self.player_status.configure(text=text))

    def choose_host_folder(self) -> None:
        selected = filedialog.askdirectory(title="Выбери папку хоста: GTA V или папку с сервером")
        if not selected:
            return
        self.selected_host_root = Path(selected).resolve()
        self.host_folder_entry.delete(0, "end")
        self.host_folder_entry.insert(0, str(self.selected_host_root))
        if find_game_executable(self.selected_host_root, self.config.game_exe_candidates):
            self.selected_host_game_root = self.selected_host_root
            self.host_game_folder_entry.delete(0, "end")
            self.host_game_folder_entry.insert(0, str(self.selected_host_game_root))
        self.set_host_status("Папка хоста выбрана")
        self.log(f"Папка хоста: {self.selected_host_root}", "host")

    def get_host_root(self) -> Path:
        raw_path = self.host_folder_entry.get().strip()
        host_root = Path(raw_path).resolve() if raw_path else self.selected_host_root
        if not host_root.exists():
            host_root.mkdir(parents=True, exist_ok=True)
        self.selected_host_root = host_root
        return host_root

    def choose_host_game_folder(self) -> None:
        selected = filedialog.askdirectory(title="Выбери корневую папку GTA V хоста")
        if not selected:
            return

        game_root = Path(selected).resolve()
        self.selected_host_game_root = game_root
        self.host_game_folder_entry.delete(0, "end")
        self.host_game_folder_entry.insert(0, str(game_root))

        if find_game_executable(game_root, self.config.game_exe_candidates):
            self.set_host_status("Папка GTA V хоста выбрана")
            self.log(f"Папка GTA V хоста: {game_root}", "host")
        else:
            self.set_host_status("В папке хоста не найден GTA5.exe")
            self.log(f"Предупреждение: в папке не найден GTA5.exe или PlayGTAV.exe: {game_root}", "host")

    def get_host_game_root(self, host_root: Path | None = None) -> Path:
        raw_path = self.host_game_folder_entry.get().strip()
        if raw_path:
            game_root = Path(raw_path).resolve()
        elif host_root and find_game_executable(host_root, self.config.game_exe_candidates):
            game_root = host_root.resolve()
        elif self.selected_host_game_root:
            game_root = self.selected_host_game_root.resolve()
        elif self.selected_game_root:
            game_root = self.selected_game_root.resolve()
        else:
            raise LauncherError("Выбери корневую папку GTA V хоста, чтобы лаунчер поставил RAGECOOP-мод.")

        if not game_root.exists():
            raise LauncherError(f"Папка GTA V хоста не существует: {game_root}")
        if not find_game_executable(game_root, self.config.game_exe_candidates):
            raise LauncherError("В папке GTA V хоста не найден PlayGTAV.exe или GTA5.exe.")

        self.selected_host_game_root = game_root
        return game_root

    def choose_player_game_folder(self) -> None:
        selected = filedialog.askdirectory(title="Выбери корневую папку GTA V")
        if not selected:
            return

        game_root = Path(selected).resolve()
        self.selected_game_root = game_root
        self.player_game_folder.delete(0, "end")
        self.player_game_folder.insert(0, str(game_root))

        if find_game_executable(game_root, self.config.game_exe_candidates):
            self.set_player_status("Папка GTA V выбрана")
            self.log(f"Папка GTA V: {game_root}", "player")
        else:
            self.set_player_status("В папке не найден GTA5.exe или PlayGTAV.exe")
            self.log(f"Предупреждение: в папке не найден GTA5.exe или PlayGTAV.exe: {game_root}", "player")

    def paste_player_address(self) -> None:
        try:
            value = self.clipboard_get().strip()
        except Exception:
            messagebox.showinfo("Буфер обмена", "В буфере обмена нет адреса.")
            return

        self.player_address.delete(0, "end")
        self.player_address.insert(0, value)
        try:
            normalized = normalize_address(value)
        except LauncherError as exc:
            self.set_player_status("Вставлен адрес, но формат неверный")
            self.log(f"Адрес из буфера не принят: {exc}", "player")
            return

        self.set_player_status("Адрес вставлен")
        self.log(f"Адрес вставлен: {normalized}", "player")

    def get_player_game_root(self) -> Path:
        raw_path = self.player_game_folder.get().strip()
        game_root = Path(raw_path).resolve() if raw_path else self.selected_game_root
        if not game_root:
            raise LauncherError("Выбери корневую папку GTA V.")
        if not game_root.exists():
            raise LauncherError(f"Папка GTA V не существует: {game_root}")
        if not find_game_executable(game_root, self.config.game_exe_candidates):
            raise LauncherError("В выбранной папке не найден PlayGTAV.exe или GTA5.exe.")
        self.selected_game_root = game_root
        return game_root

    def set_public_address(self, address: str) -> None:
        def update() -> None:
            self.public_address = address
            self.address_label.configure(text=address, text_color=COLORS["success"])
            self.host_manual_address.delete(0, "end")
            self.host_manual_address.insert(0, address)
            self.host_status.configure(text="Адрес готов и скопирован")
            self.host_dot.configure(text_color=COLORS["success"])
            self.clipboard_clear()
            self.clipboard_append(address)
            self.update()

        self.after(0, update)

    def apply_manual_host_address(self) -> None:
        try:
            address = normalize_address(self.host_manual_address.get())
        except LauncherError as exc:
            messagebox.showerror("Адрес", str(exc))
            self.log(f"Ручной адрес не принят: {exc}", "host")
            return
        self.set_public_address(address)
        self.log(f"Ручной адрес применён и скопирован: {address}", "host")

    def open_vpn_client(self) -> None:
        try:
            host_root = self.get_host_root()
            exe = launch_vpn_client(host_root, self.config, source_roots=[self.app_root])
        except LauncherError as exc:
            messagebox.showerror("VPN", str(exc))
            self.log(f"VPN-клиент не запущен: {exc}", "host")
            return

        self.set_host_status("VPN открыт")
        self.log(f"VPN-клиент запущен: {exe}", "host")

    def refresh_vpn_address(self) -> None:
        try:
            self.pending_host_root = self.get_host_root()
        except Exception as exc:
            messagebox.showerror("VPN", str(exc))
            return

        def worker() -> None:
            self.set_busy("host", True)
            try:
                host_root = self.pending_host_root or self.selected_host_root
                server_settings = resolve_app_path(host_root, "server/Settings.xml")
                port = read_server_port(server_settings, self.config.default_port)
                vpn_info = get_vpn_ipv4(self.config.vpn_adapter_keywords)
                if not vpn_info:
                    raise LauncherError(
                        "Не вижу IPv4-адрес VPN. Включи WireGuard/OpenVPN/Nebula или другой VPN, "
                        "где вы с другом в одной сети."
                    )
                adapter_name, ip_address = vpn_info
                address = normalize_address(f"{ip_address}:{port}")
                self.set_public_address(address)
                self.log(f"VPN адрес найден ({adapter_name}) и скопирован: {address}", "host")
            except LauncherError as exc:
                self.set_host_status("VPN IP не найден")
                self.log(f"Ошибка VPN IP: {exc}", "host")
                self.after(0, lambda: messagebox.showerror("VPN", str(exc)))
            finally:
                self.set_busy("host", False)

        self.run_threaded(worker)

    def start_host(self) -> None:
        try:
            self.pending_host_root = self.get_host_root()
            self.pending_host_game_root = self.get_host_game_root(self.pending_host_root)
        except LauncherError as exc:
            self.set_host_status("Ошибка")
            self.log(f"Ошибка: {exc}", "host")
            messagebox.showerror("Папка GTA V хоста", str(exc))
            return

        self.start_button.configure(state="disabled")
        self.host_browse_button.configure(state="disabled")
        self.host_game_browse_button.configure(state="disabled")
        self.vpn_open_button.configure(state="disabled")
        self.vpn_ip_button.configure(state="disabled")
        self.set_busy("host", True)
        self.run_threaded(self._start_host_worker)

    def _start_host_worker(self) -> None:
        try:
            host_root = self.pending_host_root or self.selected_host_root
            host_game_root = self.pending_host_game_root
            if not host_game_root:
                raise LauncherError("Не выбрана папка GTA V хоста.")
            if self.server_process and self.server_process.poll() is None:
                self.log("Сервер уже запущен.", "host")
                return

            self.log(f"Папка хоста: {host_root}", "host")
            for message in install_ragecoop_from_adjacent_zips(
                host_root,
                self.config,
                source_roots=[self.app_root],
                install_server=True,
                install_client=False,
            ):
                self.log(message, "host")

            server_settings = resolve_app_path(host_root, "server/Settings.xml")
            port = read_server_port(server_settings, self.config.default_port)
            self.log(f"Локальный порт RAGECOOP: {port}", "host")

            self.set_host_status("Ставлю RAGECOOP мод хосту...")
            self.log(f"Папка GTA V хоста: {host_game_root}", "host")
            for message in install_ragecoop_from_adjacent_zips(
                host_game_root,
                self.config,
                source_roots=[self.app_root],
                install_server=False,
                install_client=True,
            ):
                self.log(message, "host")
            ensure_ragecoop_client_installed(host_game_root)
            for message in install_mod_loaders_from_adjacent_zips(
                host_game_root,
                self.config,
                source_roots=[self.app_root],
            ):
                self.log(message, "host")
            ensure_mod_loaders_installed(host_game_root)

            host_self_address = f"127.0.0.1:{port}"
            settings_path = find_client_settings(host_game_root, self.config)
            backup = update_client_settings(settings_path, host_self_address)
            if backup:
                self.log(f"Backup конфига хоста: {backup.name}", "host")
            self.log(f"RAGECOOP мод хоста готов. Адрес для себя: {host_self_address}", "host")

            self.server_process = start_server_process(host_root, self.config)
            self.log("RageCoop.Server.exe запущен.", "host")
            self._start_reader(self.server_process, "server", "host")

            if self.uses_local_vpn_backend():
                vpn_exe = find_vpn_executable(host_root, self.config, source_roots=[self.app_root])
                if vpn_exe:
                    launch_vpn_client(host_root, self.config, source_roots=[self.app_root])
                    self.log(f"VPN-клиент открыт: {vpn_exe}", "host")
                else:
                    self.log(
                        "VPN-клиент не найден, но это не блокирует сервер. "
                        "Если WireGuard/OpenVPN/Nebula уже включён, адрес всё равно будет найден.",
                        "host",
                    )

                self.set_host_status("Ищу VPN IP...")
                time.sleep(1)
                vpn_info = get_vpn_ipv4(self.config.vpn_adapter_keywords)
                if vpn_info:
                    adapter_name, ip_address = vpn_info
                    address = normalize_address(f"{ip_address}:{port}")
                    self.set_public_address(address)
                    self.log(f"VPN адрес для друга ({adapter_name}): {address}", "host")
                else:
                    self.set_host_status("VPN IP не найден")
                    self.log(
                        "Не вижу VPN IPv4. Включи WireGuard/OpenVPN/Nebula или другой VPN, "
                        "затем нажми «Обновить VPN IP».",
                        "host",
                    )
                self.set_busy("host", False)
                return

            self.tunnel_output_buffer = []
            self.tunnel_process, command_text = start_tunnel_process(
                host_root,
                self.config,
                port,
                source_roots=[self.app_root],
            )
            self.log(f"Туннель запущен: {command_text}", "host")
            self.set_host_status("Ожидание публичного адреса...")
            self._start_reader(self.tunnel_process, "tunnel", "host", parse_tunnel=True)
        except LauncherError as exc:
            self.log(f"Ошибка: {exc}", "host")
            self.set_host_status("Ошибка запуска")
            self.stop_host()
        except Exception as exc:  # pragma: no cover - defensive GUI guard.
            logging.exception("Unexpected host start error")
            self.log(f"Неожиданная ошибка: {exc}", "host")
            self.set_host_status("Ошибка запуска")
            self.stop_host()
        finally:
            self.after(0, lambda: self.start_button.configure(state="normal"))
            self.after(0, lambda: self.host_browse_button.configure(state="normal"))
            self.after(0, lambda: self.host_game_browse_button.configure(state="normal"))
            self.after(0, lambda: self.vpn_open_button.configure(state="normal"))
            self.after(0, lambda: self.vpn_ip_button.configure(state="normal"))

    def _start_reader(
        self,
        process: subprocess.Popen[str],
        prefix: str,
        target: str,
        *,
        parse_tunnel: bool = False,
    ) -> None:
        def reader() -> None:
            if not process.stdout:
                return
            for line in process.stdout:
                text = line.rstrip()
                if text:
                    self.log(f"[{prefix}] {text}", target)
                if parse_tunnel:
                    if text:
                        self.tunnel_output_buffer.append(text)
                        self.tunnel_output_buffer = self.tunnel_output_buffer[-12:]
                    address = extract_public_address("\n".join(self.tunnel_output_buffer))
                    if address:
                        self.log(f"Публичный адрес: {address}", "host")
                        self.set_public_address(address)
                        self.set_busy("host", False)
                    claim_url = extract_claim_url(text)
                    if claim_url:
                        self.log(f"Открой для привязки playit: {claim_url}", "host")
                        self.set_host_status("Нужна привязка playit agent")

        self.run_threaded(reader)

    def copy_address(self) -> None:
        address = self.public_address
        if not address:
            manual = self.host_manual_address.get().strip()
            if manual:
                try:
                    address = normalize_address(manual)
                except LauncherError:
                    address = None
        if not address:
            messagebox.showinfo("Адрес", "Адрес ещё не получен от туннеля.")
            return
        self.clipboard_clear()
        self.clipboard_append(address)
        self.log(f"Адрес скопирован: {address}", "host")

    def copy_host_log(self) -> None:
        text = self.host_log.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Журнал", "Журнал пуст.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.log("Журнал хоста скопирован в буфер обмена.", "host")

    def stop_host(self) -> None:
        def worker() -> None:
            self.set_busy("host", False)
            terminate_process(self.tunnel_process, "tunnel")
            terminate_process(self.server_process, "server")
            self.tunnel_process = None
            self.server_process = None
            self.set_host_status("Сервер остановлен")
            self.log("Сервер и туннель остановлены.", "host")

        self.run_threaded(worker)

    def start_player_flow(self) -> None:
        try:
            self.pending_player_game_root = self.get_player_game_root()
            raw_address = self.player_address.get().strip()
            if not raw_address and self.config.default_player_address:
                raw_address = self.config.default_player_address
            self.pending_player_address = normalize_address(raw_address)
        except LauncherError as exc:
            self.set_player_status("Ошибка")
            self.log(f"Ошибка: {exc}", "player")
            messagebox.showerror("Запуск GTA V", str(exc))
            return

        self.launch_game_button.configure(state="disabled")
        self.player_browse_button.configure(state="disabled")
        self.player_paste_button.configure(state="disabled")
        self.set_busy("player", True)
        self.run_threaded(self._player_worker)

    def _player_worker(self) -> None:
        try:
            if not self.pending_player_game_root or not self.pending_player_address:
                raise LauncherError("Не выбрана папка GTA V или адрес сервера.")
            game_root = self.pending_player_game_root
            address = self.pending_player_address
            self.set_player_status("Ставлю RAGECOOP клиент...")
            self.log(f"Папка GTA V: {game_root}", "player")
            self.log(f"Адрес нормализован: {address}", "player")

            for message in install_ragecoop_from_adjacent_zips(
                game_root,
                self.config,
                source_roots=[self.app_root],
                install_server=False,
                install_client=True,
            ):
                self.log(message, "player")
            ensure_ragecoop_client_installed(game_root)
            for message in install_mod_loaders_from_adjacent_zips(
                game_root,
                self.config,
                source_roots=[self.app_root],
            ):
                self.log(message, "player")
            ensure_mod_loaders_installed(game_root)

            self.set_player_status("Обновляю RAGECOOP config...")
            settings_path = find_client_settings(game_root, self.config)
            backup = update_client_settings(settings_path, address)
            if backup:
                self.log(f"Backup конфига: {backup.name}", "player")
            self.log(f"RAGECOOP config обновлён: {settings_path}", "player")

            game_exe = find_game_executable(game_root, self.config.game_exe_candidates)
            if not game_exe:
                raise LauncherError("Не найден PlayGTAV.exe или GTA5.exe в корне игры.")

            subprocess.Popen([str(game_exe)], cwd=str(game_root), shell=False)
            self.set_player_status("GTA 5 запущена")
            self.log(f"Запущено: {game_exe.name}", "player")
            self.log("В игре: дождись загрузки, нажми F9, выбери Connect/Подключиться в меню RAGECOOP.", "player")
        except LauncherError as exc:
            self.set_player_status("Ошибка")
            self.log(f"Ошибка: {exc}", "player")
        except Exception as exc:  # pragma: no cover - defensive GUI guard.
            logging.exception("Unexpected player flow error")
            self.set_player_status("Ошибка")
            self.log(f"Неожиданная ошибка: {exc}", "player")
        finally:
            self.set_busy("player", False)
            self.after(0, lambda: self.launch_game_button.configure(state="normal"))
            self.after(0, lambda: self.player_browse_button.configure(state="normal"))
            self.after(0, lambda: self.player_paste_button.configure(state="normal"))

    def on_close(self) -> None:
        if (self.server_process and self.server_process.poll() is None) or (
            self.tunnel_process and self.tunnel_process.poll() is None
        ):
            if messagebox.askyesno("Выход", "Остановить сервер и туннель перед выходом?"):
                terminate_process(self.tunnel_process, "tunnel")
                terminate_process(self.server_process, "server")
        self.destroy()


def main() -> None:
    app = RageCoopLauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
