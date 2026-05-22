from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


DEFAULT_PORT = 4499
DEFAULT_PLAYER_ADDRESS = ""
LEGACY_DEFAULT_PLAYER_ADDRESSES = {"10.8.1.14:4499"}
DEFAULT_VPN_ADAPTER_KEYWORDS = [
    "wireguard",
    "amnezia",
    "tailscale",
    "zerotier",
    "nebula",
    "openvpn",
    "softether",
    "wintun",
    "tap-windows",
    "radmin",
    "hamachi",
]
SCRIPT_HOOK_V_REQUIRED_FILES = ("ScriptHookV.dll", "dinput8.dll", "xinput1_4.dll", "args.txt")
SCRIPT_HOOK_V_DOTNET_REQUIRED_FILES = (
    "ScriptHookVDotNet.asi",
    "ScriptHookVDotNet2.dll",
    "ScriptHookVDotNet3.dll",
    "MinHook.x64.dll",
)
RAGECOOP_CLIENT_DLL_CANDIDATES = (
    "scripts/RageCoop.Client.dll",
    "scripts/RageCoop/RageCoop.Client.dll",
)
RAGECOOP_CLIENT_SETTINGS_CANDIDATES = (
    "scripts/Data/RageCoop.Client.Settings.xml",
    "scripts/RageCoop/Data/RageCoop.Client.Settings.xml",
)


class LauncherError(Exception):
    """User-facing launcher error."""


@dataclass
class LauncherConfig:
    tunnel_backend: str = "vpn_lan"
    default_port: int = DEFAULT_PORT
    default_player_address: str = DEFAULT_PLAYER_ADDRESS
    game_exe_candidates: list[str] = field(default_factory=lambda: ["PlayGTAV.exe", "GTA5.exe"])
    server_exe: str = "server/RageCoop.Server.exe"
    client_settings: str = "scripts/RageCoop/Data/RageCoop.Client.Settings.xml"
    client_settings_candidates: list[str] = field(default_factory=lambda: list(RAGECOOP_CLIENT_SETTINGS_CANDIDATES))
    log_file: str = "logs/launcher.log"
    playit_exe_candidates: list[str] = field(
        default_factory=lambda: ["playit.exe", "playit-agent.exe", "playit-cli.exe"]
    )
    ngrok_exe: str = "ngrok.exe"
    radmin_vpn_exe_candidates: list[str] = field(
        default_factory=lambda: [
            r"C:\Program Files (x86)\Radmin VPN\RvRvpnGui.exe",
            r"C:\Program Files\Radmin VPN\RvRvpnGui.exe",
            r"Radmin VPN\RvRvpnGui.exe",
            "RvRvpnGui.exe",
        ]
    )
    vpn_exe_candidates: list[str] = field(
        default_factory=lambda: [
            r"C:\Program Files\WireGuard\wireguard.exe",
            r"C:\Program Files\Tailscale\tailscale-ipn.exe",
            r"C:\Program Files (x86)\ZeroTier\One\zerotier_desktop_ui.exe",
            r"C:\Program Files (x86)\Radmin VPN\RvRvpnGui.exe",
            r"C:\Program Files\Radmin VPN\RvRvpnGui.exe",
            "wireguard.exe",
            "tailscale-ipn.exe",
            "zerotier_desktop_ui.exe",
            "RvRvpnGui.exe",
        ]
    )
    vpn_adapter_keywords: list[str] = field(default_factory=lambda: DEFAULT_VPN_ADAPTER_KEYWORDS.copy())
    server_zip_candidates: list[str] = field(
        default_factory=lambda: ["RageCoop.Server-win-x64.zip", "RageCoop.Server.zip"]
    )
    client_zip_candidates: list[str] = field(default_factory=lambda: ["RageCoop.Client.zip"])
    script_hook_v_zip_candidates: list[str] = field(
        default_factory=lambda: [
            "ScriptHookV.zip",
            "ScriptHookV_3788.0_1013.34.zip",
            "script-hook-v-1-0-3788-0.zip",
        ]
    )
    script_hook_v_dotnet_zip_candidates: list[str] = field(
        default_factory=lambda: [
            "ScriptHookVDotNetEnhanced-v1.1.0.5.zip",
            "ScriptHookVDotNetEnhanced.zip",
            "ScriptHookVDotNet.zip",
        ]
    )
    ragecoop_plus_zip_candidates: list[str] = field(
        default_factory=lambda: [
            "RageCoopPlus.zip",
            "RageCoop+.zip",
            "RageCoopPlus_1.1.zip",
            "RageCoop+ Multiplayer Client Installer + Server (FIXED) 1.1.zip",
            "*RageCoop+*.zip",
            "*RageCoopPlus*.zip",
        ]
    )
    ragecoop_plus_client_dir: str = r"D:\Games\RageCoopPlus"
    ragecoop_plus_server_dir: str = r"D:\Games\RageCoopPlusServer"
    ragecoop_plus_installer_candidates: list[str] = field(
        default_factory=lambda: [
            "RageCoop.Client.Installer.exe",
            "RageCoop.Installer.exe",
            "RageCoopPlus.Installer.exe",
            "Installer.exe",
        ]
    )
    ragecoop_plus_server_exe_candidates: list[str] = field(
        default_factory=lambda: [
            "RageCoop.Server.exe",
            "Server/RageCoop.Server.exe",
            "server/RageCoop.Server.exe",
        ]
    )

    @classmethod
    def load(cls, app_root: Path, filename: str = "launcher_config.json") -> "LauncherConfig":
        path = app_root / filename
        config = cls()
        if not path.exists():
            return config

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LauncherError(f"Некорректный JSON в {path.name}: {exc}") from exc

        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        if config.default_player_address in LEGACY_DEFAULT_PLAYER_ADDRESSES:
            config.default_player_address = ""
        return config

    def as_json_dict(self) -> dict[str, Any]:
        return {
            "tunnel_backend": self.tunnel_backend,
            "default_port": self.default_port,
            "default_player_address": self.default_player_address,
            "game_exe_candidates": self.game_exe_candidates,
            "server_exe": self.server_exe,
            "client_settings": self.client_settings,
            "client_settings_candidates": self.client_settings_candidates,
            "vpn_exe_candidates": self.vpn_exe_candidates,
            "vpn_adapter_keywords": self.vpn_adapter_keywords,
            "script_hook_v_zip_candidates": self.script_hook_v_zip_candidates,
            "script_hook_v_dotnet_zip_candidates": self.script_hook_v_dotnet_zip_candidates,
            "ragecoop_plus_zip_candidates": self.ragecoop_plus_zip_candidates,
            "ragecoop_plus_client_dir": self.ragecoop_plus_client_dir,
            "ragecoop_plus_server_dir": self.ragecoop_plus_server_dir,
        }


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_bundle_root() -> Path | None:
    bundle_root = getattr(sys, "_MEIPASS", None)
    return Path(bundle_root).resolve() if bundle_root else None


def get_resource_roots(app_root: Path, extra_roots: Iterable[Path] | None = None) -> list[Path]:
    roots: list[Path] = []
    for root in [app_root, get_bundle_root(), *(extra_roots or [])]:
        if root is None:
            continue
        resolved = Path(root).resolve()
        if resolved not in roots:
            roots.append(resolved)
    return roots


def resolve_app_path(app_root: Path, relative_or_absolute: str | Path) -> Path:
    path = Path(relative_or_absolute)
    if path.is_absolute():
        return path
    return (app_root / path).resolve()


def setup_logging(app_root: Path, config: LauncherConfig) -> Path:
    log_path = resolve_app_path(app_root, config.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        encoding="utf-8",
    )
    return log_path


def normalize_address(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise LauncherError("Вставь адрес сервера в формате host:port.")

    value = re.sub(r"\s+", "", value)
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0]
    value = value.split("?", 1)[0]
    value = value.split("#", 1)[0]

    if value.startswith("["):
        end = value.find("]")
        if end == -1 or end + 1 >= len(value) or value[end + 1] != ":":
            raise LauncherError("Неверный адрес. Для IPv6 нужен формат [host]:port.")
        host = value[1:end]
        port_text = value[end + 2 :]
    else:
        if ":" not in value:
            raise LauncherError("Неверный адрес. Нужен формат host:port.")
        host, port_text = value.rsplit(":", 1)

    host = host.strip()
    if not host:
        raise LauncherError("В адресе отсутствует host.")
    if not port_text.isdigit():
        raise LauncherError("Порт должен быть числом.")

    port = int(port_text)
    if port < 1 or port > 65535:
        raise LauncherError("Порт должен быть от 1 до 65535.")

    return f"{host}:{port}"


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def read_server_port(settings_path: Path, default_port: int = DEFAULT_PORT) -> int:
    if not settings_path.exists():
        return default_port

    try:
        root = ET.parse(settings_path).getroot()
    except ET.ParseError as exc:
        raise LauncherError(f"Не удалось прочитать {settings_path.name}: {exc}") from exc

    for element in root.iter():
        if _xml_local_name(element.tag) == "Port" and element.text:
            try:
                port = int(element.text.strip())
            except ValueError as exc:
                raise LauncherError(f"В {settings_path.name} указан некорректный Port.") from exc
            if port < 1 or port > 65535:
                raise LauncherError(f"В {settings_path.name} Port должен быть от 1 до 65535.")
            return port

    return default_port


def find_client_settings(app_root: Path, config: LauncherConfig) -> Path:
    for candidate in config.client_settings_candidates:
        path = resolve_app_path(app_root, candidate)
        if path.exists():
            return path

    configured = resolve_app_path(app_root, config.client_settings)
    if configured.exists():
        return configured

    scripts_root = app_root / "scripts"
    if scripts_root.exists():
        matches = sorted(
            (
                path
                for path in scripts_root.rglob("RageCoop.Client.Settings.xml")
                if ".disabled-" not in str(path)
            ),
            key=lambda path: (len(path.parts), str(path).lower()),
        )
        if matches:
            return matches[0].resolve()

    return configured


def _indent_xml(element: ET.Element, level: int = 0) -> None:
    indent = "\n" + level * "  "
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "
        for child in element:
            _indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indent


def backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(path.suffix + f".{stamp}.bak")
    shutil.copy2(path, backup)
    return backup


def create_default_client_settings(address: str) -> ET.ElementTree:
    root = ET.Element("Settings")
    defaults = {
        "DataDirectory": "scripts\\RageCoop\\Data",
        "DisableAlternatePause": "true",
        "DisableTraffic": "false",
        "FlipMenu": "false",
        "LastServerAddress": address,
        "LogLevel": "2",
        "MenuKey": "F9",
        "PassengerKey": "G",
        "Password": "",
        "Username": "",
        "Voice": "false",
        "WorldPedSoftLimit": "80",
        "WorldVehicleSoftLimit": "60",
    }
    for key, value in defaults.items():
        child = ET.SubElement(root, key)
        child.text = value
    _indent_xml(root)
    return ET.ElementTree(root)


def update_client_settings(settings_path: Path, address: str) -> Path | None:
    address = normalize_address(address)
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    backup = backup_file(settings_path)
    if settings_path.exists():
        try:
            tree = ET.parse(settings_path)
            root = tree.getroot()
        except ET.ParseError:
            tree = create_default_client_settings(address)
        else:
            target = None
            for element in root.iter():
                if _xml_local_name(element.tag) == "LastServerAddress":
                    target = element
                    break
            if target is None:
                target = ET.SubElement(root, "LastServerAddress")
            target.text = address
            _indent_xml(root)
    else:
        tree = create_default_client_settings(address)

    tree.write(settings_path, encoding="utf-8", xml_declaration=True)
    return backup


def find_game_executable(app_root: Path, candidates: Iterable[str]) -> Path | None:
    for candidate in candidates:
        path = resolve_app_path(app_root, candidate)
        if path.exists():
            return path
    return None


def find_first_existing(app_root: Path, candidates: Iterable[str]) -> Path | None:
    for candidate in candidates:
        path = resolve_app_path(app_root, candidate)
        if path.exists():
            return path
    return None


def find_first_existing_in_roots(roots: Iterable[Path], candidates: Iterable[str]) -> Path | None:
    for root in roots:
        found = find_first_existing(Path(root), candidates)
        if found:
            return found
    return None


def find_first_matching_in_roots(roots: Iterable[Path], candidates: Iterable[str]) -> Path | None:
    for root in roots:
        root = Path(root)
        for candidate in candidates:
            if any(marker in candidate for marker in "*?[]"):
                matches = sorted(root.glob(candidate))
                for match in matches:
                    if match.exists():
                        return match.resolve()
            else:
                path = resolve_app_path(root, candidate)
                if path.exists():
                    return path
    return None


def find_radmin_vpn_executable(
    app_root: Path,
    config: LauncherConfig,
    *,
    source_roots: Iterable[Path] | None = None,
) -> Path | None:
    roots = get_resource_roots(app_root, source_roots)
    return find_first_existing_in_roots(roots, config.radmin_vpn_exe_candidates)


def find_vpn_executable(
    app_root: Path,
    config: LauncherConfig,
    *,
    source_roots: Iterable[Path] | None = None,
) -> Path | None:
    roots = get_resource_roots(app_root, source_roots)
    return find_first_existing_in_roots(roots, config.vpn_exe_candidates)


def launch_vpn_client(
    app_root: Path,
    config: LauncherConfig,
    *,
    source_roots: Iterable[Path] | None = None,
) -> Path:
    vpn_exe = find_vpn_executable(app_root, config, source_roots=source_roots)
    if not vpn_exe:
        raise LauncherError(
            "VPN-клиент не найден. Установи WireGuard, ZeroTier или другой VPN, "
            "затем снова нажми «Открыть VPN»."
        )

    subprocess.Popen(
        [str(vpn_exe)],
        cwd=str(vpn_exe.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        shell=False,
    )
    return vpn_exe


def launch_radmin_vpn(
    app_root: Path,
    config: LauncherConfig,
    *,
    source_roots: Iterable[Path] | None = None,
) -> Path:
    radmin_exe = find_radmin_vpn_executable(app_root, config, source_roots=source_roots)
    if not radmin_exe:
        raise LauncherError(
            "Radmin VPN не найден. Установи Radmin VPN с официального сайта, "
            "затем снова нажми «Открыть Radmin VPN»."
        )

    subprocess.Popen(
        [str(radmin_exe)],
        cwd=str(radmin_exe.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        shell=False,
    )
    return radmin_exe


def _keyword_rank(adapter_name: str, keywords: Iterable[str]) -> int | None:
    lowered = adapter_name.lower()
    for index, keyword in enumerate(keywords):
        if keyword.lower() in lowered:
            return index
    return None


def parse_vpn_ipv4_from_ipconfig(
    text: str,
    keywords: Iterable[str] | None = None,
) -> tuple[str, str] | None:
    keywords = list(keywords or DEFAULT_VPN_ADAPTER_KEYWORDS)
    current_adapter_name: str | None = None
    current_adapter_rank: int | None = None
    matches: list[tuple[int, int, str, str]] = []
    order = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # ipconfig adapter headers are not indented and end with a colon.
        if raw_line[:1] not in {" ", "\t"} and line.endswith(":"):
            current_adapter_name = line[:-1]
            current_adapter_rank = _keyword_rank(current_adapter_name, keywords)
            continue

        if current_adapter_name is None or current_adapter_rank is None:
            continue

        if "ipv4" not in line.lower():
            continue

        match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
        if not match:
            continue

        address = match.group(1)
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.version == 4 and not ip.is_loopback and not ip.is_unspecified:
            matches.append((current_adapter_rank, order, current_adapter_name, address))
            order += 1

    if not matches:
        return None
    _, _, adapter_name, address = min(matches, key=lambda item: (item[0], item[1]))
    return adapter_name, address


def parse_radmin_ipv4_from_ipconfig(text: str) -> str | None:
    result = parse_vpn_ipv4_from_ipconfig(text, ["radmin"])
    return result[1] if result else None


def _read_ipconfig() -> str | None:
    if os.name != "nt":
        return None

    try:
        result = subprocess.run(
            ["ipconfig"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="oem",
            errors="replace",
            creationflags=_creation_flags(),
            check=False,
            shell=False,
        )
    except OSError:
        return None

    return result.stdout


def get_vpn_ipv4(keywords: Iterable[str] | None = None) -> tuple[str, str] | None:
    output = _read_ipconfig()
    if output is None:
        return None
    return parse_vpn_ipv4_from_ipconfig(output, keywords)


def get_radmin_ipv4() -> str | None:
    output = _read_ipconfig()
    if output is None:
        return None
    return parse_radmin_ipv4_from_ipconfig(output)


def _safe_extract_zip(zip_path: Path, destination: Path) -> list[Path]:
    extracted: list[Path] = []
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if destination != target and destination not in target.parents:
                raise LauncherError(f"Архив {zip_path.name} содержит небезопасный путь: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(target)
    return extracted


def install_ragecoop_from_adjacent_zips(
    app_root: Path,
    config: LauncherConfig,
    *,
    source_roots: Iterable[Path] | None = None,
    install_server: bool = True,
    install_client: bool = True,
) -> list[str]:
    messages: list[str] = []
    roots = get_resource_roots(app_root, source_roots)

    server_exe = resolve_app_path(app_root, config.server_exe)
    if install_server and not server_exe.exists():
        server_zip = find_first_existing_in_roots(roots, config.server_zip_candidates)
        if server_zip:
            _safe_extract_zip(server_zip, server_exe.parent)
            messages.append(f"Сервер распакован из {server_zip.name} в {server_exe.parent.name}.")

    client_exists = any(resolve_app_path(app_root, candidate).exists() for candidate in RAGECOOP_CLIENT_DLL_CANDIDATES)
    if install_client and not client_exists:
        client_zip = find_first_existing_in_roots(roots, config.client_zip_candidates)
        if client_zip:
            _safe_extract_zip(client_zip, app_root / "scripts")
            messages.append(f"Клиент распакован из {client_zip.name} в scripts.")

    return messages


def missing_mod_loader_files(app_root: Path) -> list[str]:
    required = [*SCRIPT_HOOK_V_REQUIRED_FILES, *SCRIPT_HOOK_V_DOTNET_REQUIRED_FILES]
    return [name for name in required if not (app_root / name).exists()]


def _extract_named_files_from_zip(zip_path: Path, app_root: Path, file_names: Iterable[str]) -> list[Path]:
    if not zipfile.is_zipfile(zip_path):
        raise LauncherError(
            f"{zip_path.name} не похож на ZIP-архив. Скачай настоящий архив Script Hook V через браузер "
            "с dev-c.com/gtav/scripthookv или gta5-mods.com/tools/script-hook-v."
        )

    wanted = list(file_names)
    members_by_name: dict[str, zipfile.ZipInfo] = {}
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            member_name = Path(member.filename.replace("\\", "/")).name
            if member_name in wanted and member_name not in members_by_name:
                members_by_name[member_name] = member

        missing = [name for name in wanted if name not in members_by_name]
        if missing:
            raise LauncherError(f"В {zip_path.name} нет нужных файлов: {', '.join(missing)}.")

        installed: list[Path] = []
        app_root.mkdir(parents=True, exist_ok=True)
        for name in wanted:
            member = members_by_name[name]
            destination = app_root / name
            backup_file(destination)
            with archive.open(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
            installed.append(destination)

    return installed


def install_mod_loaders_from_adjacent_zips(
    app_root: Path,
    config: LauncherConfig,
    *,
    source_roots: Iterable[Path] | None = None,
) -> list[str]:
    messages: list[str] = []
    roots = get_resource_roots(app_root, source_roots)

    script_hook_missing = [name for name in SCRIPT_HOOK_V_REQUIRED_FILES if not (app_root / name).exists()]
    if script_hook_missing:
        script_hook_zip = find_first_existing_in_roots(roots, config.script_hook_v_zip_candidates)
        if script_hook_zip:
            _extract_named_files_from_zip(script_hook_zip, app_root, SCRIPT_HOOK_V_REQUIRED_FILES)
            messages.append(f"Script Hook V установлен из {script_hook_zip.name}.")

    dotnet_missing = [name for name in SCRIPT_HOOK_V_DOTNET_REQUIRED_FILES if not (app_root / name).exists()]
    if dotnet_missing:
        dotnet_zip = find_first_existing_in_roots(roots, config.script_hook_v_dotnet_zip_candidates)
        if dotnet_zip:
            _extract_named_files_from_zip(dotnet_zip, app_root, SCRIPT_HOOK_V_DOTNET_REQUIRED_FILES)
            messages.append(f"ScriptHookVDotNet Enhanced установлен из {dotnet_zip.name}.")

    return messages


def ensure_ragecoop_client_installed(app_root: Path) -> None:
    if not any(resolve_app_path(app_root, candidate).exists() for candidate in RAGECOOP_CLIENT_DLL_CANDIDATES):
        raise LauncherError(
            "RAGECOOP клиент не найден и не был установлен. "
            "Положи RageCoop.Client.zip рядом с лаунчером или используй установщик."
        )


def ensure_mod_loaders_installed(app_root: Path) -> None:
    missing = missing_mod_loader_files(app_root)
    if not missing:
        return

    raise LauncherError(
        "Не хватает загрузчиков модов в корне GTA V: "
        f"{', '.join(missing)}. "
        "Скачай официальный Script Hook V, положи его ZIP рядом с launcher/installer как ScriptHookV.zip "
        "и нажми кнопку ещё раз. Launcher ставит нужные файлы из папки bin; NativeTrainer.asi не ставится."
    )


def _copy_dir_contents_with_backup(source_dir: Path, destination_dir: Path) -> list[Path]:
    copied: list[Path] = []
    destination_dir.mkdir(parents=True, exist_ok=True)
    for source in source_dir.rglob("*"):
        relative = source.relative_to(source_dir)
        destination = destination_dir / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup_file(destination)
        shutil.copy2(source, destination)
        copied.append(destination)
    return copied


def _find_executable_by_candidates(root: Path, candidates: Iterable[str]) -> Path | None:
    for candidate in candidates:
        direct = resolve_app_path(root, candidate)
        if direct.exists():
            return direct

    candidate_names = {Path(candidate).name.lower() for candidate in candidates}
    for path in sorted(root.rglob("*.exe")):
        if path.name.lower() in candidate_names:
            return path.resolve()
    return None


def setup_ragecoop_plus_package(
    app_root: Path,
    config: LauncherConfig,
    *,
    source_roots: Iterable[Path] | None = None,
) -> list[str]:
    roots = get_resource_roots(app_root, source_roots)
    package_zip = find_first_matching_in_roots(roots, config.ragecoop_plus_zip_candidates)
    if not package_zip:
        raise LauncherError(
            "RageCoop+ archive not found. Download 'RageCoop+ Multiplayer Client Installer + Server (FIXED) 1.1' "
            "from GTA5-Mods and put the ZIP next to GTA5CoopLauncher.exe as RageCoopPlus.zip."
        )
    if not zipfile.is_zipfile(package_zip):
        raise LauncherError(f"{package_zip.name} is not a valid ZIP archive.")

    client_dir = Path(config.ragecoop_plus_client_dir).resolve()
    server_dir = Path(config.ragecoop_plus_server_dir).resolve()
    _safe_extract_zip(package_zip, client_dir)

    messages = [f"RageCoop+ archive extracted to {client_dir}."]
    server_source = _find_executable_by_candidates(client_dir, config.ragecoop_plus_server_exe_candidates)
    if server_source:
        _copy_dir_contents_with_backup(server_source.parent, server_dir)
        messages.append(f"RageCoop+ server copied to {server_dir}.")
    else:
        messages.append("RageCoop+ server folder was not detected automatically; use the Server folder from the archive.")

    installer = _find_executable_by_candidates(client_dir, config.ragecoop_plus_installer_candidates)
    if installer:
        messages.append(f"RageCoop+ installer found: {installer}.")
    else:
        messages.append("RageCoop+ installer was not detected automatically; open the extracted folder manually.")
    return messages


def find_ragecoop_plus_installer(config: LauncherConfig) -> Path | None:
    return _find_executable_by_candidates(Path(config.ragecoop_plus_client_dir), config.ragecoop_plus_installer_candidates)


def find_ragecoop_plus_server_exe(config: LauncherConfig) -> Path | None:
    return _find_executable_by_candidates(Path(config.ragecoop_plus_server_dir), config.ragecoop_plus_server_exe_candidates)


def start_ragecoop_plus_installer(config: LauncherConfig) -> subprocess.Popen[str]:
    installer = find_ragecoop_plus_installer(config)
    if not installer:
        raise LauncherError(
            f"RageCoop+ installer not found in {config.ragecoop_plus_client_dir}. "
            "First run 'Prepare RageCoop+' with the downloaded ZIP next to the launcher."
        )
    return start_process([str(installer)], cwd=installer.parent, pipe_output=False)


def start_ragecoop_plus_server_process(config: LauncherConfig) -> subprocess.Popen[str]:
    server_exe = find_ragecoop_plus_server_exe(config)
    if not server_exe:
        raise LauncherError(
            f"RageCoop+ server not found in {config.ragecoop_plus_server_dir}. "
            "First run 'Prepare RageCoop+' with the downloaded ZIP next to the launcher."
        )
    return start_process([str(server_exe)], cwd=server_exe.parent)


def write_default_config(app_root: Path, config: LauncherConfig | None = None) -> Path:
    config = config or LauncherConfig()
    path = app_root / "launcher_config.json"
    if not path.exists():
        path.write_text(
            json.dumps(config.as_json_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return path


def write_playit_launch_config(app_root: Path, local_port: int) -> Path:
    path = app_root / "playit_ragecoop.toml"
    content = (
        'agent_name = "GTA5 RAGECOOP Launcher"\n'
        'secret_path = "./playit.secret"\n\n'
        "[[tunnels]]\n"
        'name = "ragecoop"\n'
        'proto = "udp"\n'
        "port_count = 1\n"
        f"local = {local_port}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def load_local_secrets(app_root: Path) -> dict[str, Any]:
    path = app_root / "host.local.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LauncherError(f"Некорректный JSON в host.local.json: {exc}") from exc


def _creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def start_process(
    args: list[str],
    cwd: Path,
    *,
    pipe_output: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    stdout = subprocess.PIPE if pipe_output else subprocess.DEVNULL
    return subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=stdout,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_creation_flags(),
        shell=False,
        env=env,
    )


def start_server_process(app_root: Path, config: LauncherConfig) -> subprocess.Popen[str]:
    server_exe = resolve_app_path(app_root, config.server_exe)
    if not server_exe.exists():
        raise LauncherError(
            f"Не найден сервер: {server_exe}. Положи RageCoop.Server.exe в папку server."
        )
    return start_process([str(server_exe)], server_exe.parent)


def start_tunnel_process(
    app_root: Path,
    config: LauncherConfig,
    local_port: int,
    *,
    source_roots: Iterable[Path] | None = None,
) -> tuple[subprocess.Popen[str], str]:
    backend = config.tunnel_backend.lower().strip()
    roots = get_resource_roots(app_root, source_roots)
    if backend == "playit_udp":
        tunnel_exe = find_first_existing_in_roots(roots, config.playit_exe_candidates)
        if not tunnel_exe:
            raise LauncherError(
                "Не найден playit.exe. Скачай playit для Windows и положи exe рядом с лаунчером."
            )

        launch_config = write_playit_launch_config(app_root, local_port)
        first_args = [str(tunnel_exe), "launch", str(launch_config)]
        process = start_process(first_args, app_root)
        try:
            exit_code = process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return process, " ".join(first_args)

        output = ""
        if process.stdout:
            output = process.stdout.read()
        logging.info("playit launch config exited with %s: %s", exit_code, output.strip())

        fallback_args = [str(tunnel_exe)]
        process = start_process(fallback_args, app_root)
        return process, " ".join(fallback_args)

    if backend == "ngrok_tcp":
        tunnel_exe = find_first_existing_in_roots(roots, [config.ngrok_exe])
        if not tunnel_exe:
            raise LauncherError("Не найден ngrok.exe рядом с лаунчером.")

        secrets = load_local_secrets(app_root)
        token = os.environ.get("NGROK_AUTHTOKEN") or secrets.get("ngrok_authtoken")
        args = [str(tunnel_exe), "tcp", str(local_port)]
        if token:
            args.extend(["--authtoken", str(token)])
        return start_process(args, app_root), " ".join(args[:3] + (["--authtoken", "***"] if token else []))

    raise LauncherError(f"Неизвестный tunnel_backend: {config.tunnel_backend}")


_PUBLIC_HOST = r"(?P<host>(?:[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}|(?:\d{1,3}\.){3}\d{1,3}))"
_ADDRESS_PATTERNS = [
    re.compile(rf"(?:(?:tcp|udp)://)?{_PUBLIC_HOST}(?::|%3A)(?P<port>\d{{1,5}})"),
    re.compile(rf"{_PUBLIC_HOST}[\s\S]{{0,100}}?\bport\b\s*[:=]?\s*(?P<port>\d{{1,5}})", re.IGNORECASE),
    re.compile(rf"{_PUBLIC_HOST}\s+(?P<port>\d{{1,5}})"),
]
_CLAIM_URL_PATTERN = re.compile(r"https?://[^\s\"']*playit\.gg/[^\s\"']+")


def _is_private_or_local_host(host: str) -> bool:
    lowered = host.lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return True
    try:
        ip = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified


def extract_public_address(text: str) -> str | None:
    for pattern in _ADDRESS_PATTERNS:
        for match in pattern.finditer(text):
            host = match.group("host")
            if _is_private_or_local_host(host):
                continue
            try:
                return normalize_address(f"{host}:{match.group('port')}")
            except LauncherError:
                continue
    return None


def extract_claim_url(text: str) -> str | None:
    match = _CLAIM_URL_PATTERN.search(text)
    return match.group(0) if match else None


def terminate_process(process: subprocess.Popen[Any] | None, name: str, timeout: float = 8.0) -> None:
    if process is None or process.poll() is not None:
        return

    logging.info("Stopping %s pid=%s", name, process.pid)
    process.terminate()
    try:
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            shell=False,
        )
    else:
        process.kill()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logging.warning("%s pid=%s did not stop after kill request", name, process.pid)
