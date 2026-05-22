from __future__ import annotations

import ctypes
import shutil
import sys
import threading
import time
from pathlib import Path
from tkinter import BooleanVar, filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError as exc:  # pragma: no cover - only used on machines without GUI dependency.
    raise SystemExit("CustomTkinter is not installed. Run: python -m pip install customtkinter") from exc


COLORS = {
    "window": "#07111F",
    "surface": "#0D1829",
    "surface_2": "#111F33",
    "stroke": "#24364F",
    "muted": "#9AA8BA",
    "text": "#EEF4FF",
    "accent": "#38BDF8",
    "accent_hover": "#0EA5E9",
    "success": "#22C55E",
    "danger": "#EF4444",
}

PACKAGE_FILES = [
    "GTA5CoopLauncher.exe",
    "launcher_config.json",
    "README.md",
    "RageCoop.Client.zip",
    "RageCoop.Server-win-x64.zip",
    "ScriptHookV.zip",
    "ScriptHookVDotNetEnhanced-v1.1.0.5.zip",
    "PLAYER_INSTRUCTIONS_RU.txt",
    "ЧТО_ВВОДИТЬ_ИГРОКУ.txt",
]
OPTIONAL_FILES = ["playit.exe", "playit-agent.exe", "playit-cli.exe"]
OPTIONAL_PACKAGE_PATTERNS = ["RageCoopPlus.zip", "RageCoop+.zip", "*RageCoop+*.zip", "*RageCoopPlus*.zip"]
VPN_INSTALLER_PATTERNS = [
    "wireguard-amd64*.msi",
    "WireGuard*.msi",
    "wireguard-installer.exe",
    "AmneziaVPN*.exe",
    "amnezia*.exe",
]


def source_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        bundled = Path(bundle_root)
        if (bundled / "GTA5CoopLauncher.exe").exists():
            return bundled
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent / "dist"


def external_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent / "dist"


def is_gta_folder(path: Path) -> bool:
    return (path / "GTA5.exe").exists() or (path / "PlayGTAV.exe").exists()


def available_package_files(src: Path, optional_src: Path | None = None) -> list[Path]:
    files = [src / name for name in PACKAGE_FILES if (src / name).exists()]
    seen = {path.name for path in files}
    for root in [src, optional_src]:
        if root is None:
            continue
        for name in OPTIONAL_FILES:
            path = root / name
            if path.exists() and path.name not in seen:
                files.append(path)
                seen.add(path.name)
        for pattern in OPTIONAL_PACKAGE_PATTERNS:
            for path in sorted(root.glob(pattern)):
                if path.exists() and path.name not in seen:
                    files.append(path)
                    seen.add(path.name)
    return files


def find_vpn_installer(*roots: Path | None) -> Path | None:
    seen: set[Path] = set()
    for root in roots:
        if root is None or not root.exists():
            continue
        for pattern in VPN_INSTALLER_PATTERNS:
            for path in sorted(root.glob(pattern)):
                resolved = path.resolve()
                if resolved in seen or not path.is_file():
                    continue
                seen.add(resolved)
                return resolved
    return None


def launch_elevated(file_path: str, parameters: str = "") -> None:
    if sys.platform != "win32":
        raise RuntimeError("Автоустановка VPN поддерживается только на Windows.")
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", file_path, parameters, None, 1)
    if result <= 32:
        raise RuntimeError(f"Windows не запустил установку с правами администратора. Код ShellExecute: {result}")


def start_vpn_install(vpn_installer: Path | None) -> str:
    if vpn_installer:
        if vpn_installer.suffix.lower() == ".msi":
            launch_elevated(
                "msiexec.exe",
                f'/i "{vpn_installer}" /quiet /norestart DO_NOT_LAUNCH=1',
            )
            return f"Запущена установка VPN через MSI: {vpn_installer.name}"
        launch_elevated(str(vpn_installer))
        return f"Запущен VPN installer: {vpn_installer.name}"

    launch_elevated(
        "winget.exe",
        "install --id WireGuard.WireGuard --exact --accept-package-agreements --accept-source-agreements",
    )
    return "Встроенный VPN installer не найден. Запущена установка WireGuard через winget."


def copy_with_backup(source: Path, destination: Path) -> tuple[str, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup_note = ""
    if destination.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = destination.with_name(destination.name + f".installer-bak-{stamp}")
        shutil.copy2(destination, backup)
        backup_note = f"backup: {backup.name}"
    shutil.copy2(source, destination)
    return destination.name, backup_note


class InstallerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.src = source_root()
        self.optional_src = external_root()
        self.target: Path | None = None
        self.install_vpn_var = BooleanVar(value=True)
        self.pending_install_vpn = True
        self.busy = False
        self.tick = 0

        self.title("GTA V RAGECOOP Installer")
        self.geometry("790x610")
        self.minsize(720, 580)
        self.configure(fg_color=COLORS["window"])

        self._build_ui()
        self.after(200, self._animate)
        self._append_log(f"Пакет установки: {self.src}")
        vpn_installer = find_vpn_installer(self.src, self.optional_src)
        if vpn_installer:
            self._append_log(f"VPN installer найден в пакете: {vpn_installer.name}")
        else:
            self._append_log("VPN installer в пакете не найден. Будет доступен fallback через winget.")

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            self,
            text="GTA V RAGECOOP Installer",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(22, 4))

        ctk.CTkLabel(
            self,
            text="Установит лаунчер, конфиг, архивы RAGECOOP и поможет поставить VPN-клиент.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=14),
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 16))

        panel = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            border_width=1,
            border_color=COLORS["stroke"],
            corner_radius=12,
        )
        panel.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 14))
        panel.grid_columnconfigure(0, weight=1)

        self.path_entry = ctk.CTkEntry(
            panel,
            height=44,
            placeholder_text="Выбери корневую папку GTA V",
            fg_color=COLORS["window"],
            border_color=COLORS["stroke"],
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["muted"],
        )
        self.path_entry.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))

        button_row = ctk.CTkFrame(panel, fg_color="transparent")
        button_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        button_row.grid_columnconfigure((0, 1), weight=1)

        self.browse_button = ctk.CTkButton(
            button_row,
            text="Выбрать папку GTA V",
            height=42,
            fg_color=COLORS["surface_2"],
            hover_color=COLORS["stroke"],
            command=self.choose_folder,
        )
        self.browse_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.install_button = ctk.CTkButton(
            button_row,
            text="Установить",
            height=42,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#04111F",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.install,
        )
        self.install_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self.status = ctk.CTkLabel(
            panel,
            text="Ожидание выбора папки",
            text_color=COLORS["muted"],
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.status.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        self.vpn_checkbox = ctk.CTkCheckBox(
            panel,
            text="Установить/открыть VPN-клиент: встроенный WireGuard/Amnezia или WireGuard через winget",
            variable=self.install_vpn_var,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            checkbox_width=20,
            checkbox_height=20,
        )
        self.vpn_checkbox.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 12))

        self.progress = ctk.CTkProgressBar(
            panel,
            mode="indeterminate",
            progress_color=COLORS["accent"],
            fg_color=COLORS["surface_2"],
        )
        self.progress.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 16))
        self.progress.set(0)

        self.log_box = ctk.CTkTextbox(
            self,
            fg_color=COLORS["surface"],
            text_color=COLORS["text"],
            border_width=1,
            border_color=COLORS["stroke"],
            corner_radius=12,
        )
        self.log_box.grid(row=3, column=0, sticky="nsew", padx=22, pady=(0, 22))
        self.log_box.configure(state="disabled")

    def _append_log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message.rstrip() + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _animate(self) -> None:
        self.tick += 1
        if self.busy:
            color = [COLORS["accent"], "#7DD3FC", COLORS["success"], "#7DD3FC"][self.tick % 4]
            self.status.configure(text_color=color)
        self.after(220, self._animate)

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Выбери корневую папку GTA V")
        if not selected:
            return
        self.target = Path(selected)
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, str(self.target))
        if is_gta_folder(self.target):
            self.status.configure(text="Папка GTA V найдена", text_color=COLORS["success"])
        else:
            self.status.configure(text="В этой папке не найден GTA5.exe или PlayGTAV.exe", text_color=COLORS["danger"])

    def install(self) -> None:
        raw_path = self.path_entry.get().strip()
        if raw_path:
            self.target = Path(raw_path)
        if not self.target:
            messagebox.showinfo("Папка GTA V", "Сначала выбери корневую папку GTA V.")
            return
        if not self.target.exists():
            messagebox.showerror("Папка GTA V", "Выбранная папка не существует.")
            return
        if not is_gta_folder(self.target):
            proceed = messagebox.askyesno(
                "Папка не похожа на GTA V",
                "В папке не найден GTA5.exe или PlayGTAV.exe. Всё равно установить сюда?",
            )
            if not proceed:
                return

        self.install_button.configure(state="disabled")
        self.browse_button.configure(state="disabled")
        self.vpn_checkbox.configure(state="disabled")
        self.pending_install_vpn = bool(self.install_vpn_var.get())
        self.busy = True
        self.progress.start()
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self) -> None:
        try:
            files = available_package_files(self.src, self.optional_src)
            required_missing = [name for name in PACKAGE_FILES if not (self.src / name).exists()]
            if required_missing:
                raise RuntimeError("Не хватает файлов рядом с установщиком: " + ", ".join(required_missing))

            assert self.target is not None
            for source in files:
                installed, backup = copy_with_backup(source, self.target / source.name)
                suffix = f" ({backup})" if backup else ""
                self.after(0, lambda item=installed, note=suffix: self._append_log(f"Установлено: {item}{note}"))

            if self.pending_install_vpn:
                vpn_installer = find_vpn_installer(self.src, self.optional_src)
                try:
                    vpn_message = start_vpn_install(vpn_installer)
                except Exception as exc:
                    self.after(0, lambda err=str(exc): self._append_log(f"VPN не установлен автоматически: {err}"))
                    self.after(
                        0,
                        lambda: self._append_log(
                            "Поставь WireGuard/Amnezia вручную, затем запускай GTA5CoopLauncher."
                        ),
                    )
                else:
                    self.after(0, lambda msg=vpn_message: self._append_log(msg))
                    self.after(
                        0,
                        lambda: self._append_log(
                            "Если появилось окно UAC/установщика VPN, нажми Да и дождись завершения установки."
                        ),
                    )
            else:
                self.after(0, lambda: self._append_log("Установка VPN пропущена по выбору пользователя."))

            self.after(0, lambda: self.status.configure(text="Установка завершена", text_color=COLORS["success"]))
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "Готово",
                    "GTA5CoopLauncher установлен. Если открылась установка VPN, заверши её в отдельном окне.",
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive installer guard.
            self.after(0, lambda: self.status.configure(text="Ошибка установки", text_color=COLORS["danger"]))
            self.after(0, lambda: self._append_log(f"Ошибка: {exc}"))
            self.after(0, lambda: messagebox.showerror("Ошибка установки", str(exc)))
        finally:
            self.busy = False
            self.after(0, self.progress.stop)
            self.after(0, lambda: self.progress.set(0))
            self.after(0, lambda: self.install_button.configure(state="normal"))
            self.after(0, lambda: self.browse_button.configure(state="normal"))
            self.after(0, lambda: self.vpn_checkbox.configure(state="normal"))


def main() -> None:
    app = InstallerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
