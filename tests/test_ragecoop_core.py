import tempfile
import unittest
import zipfile
from pathlib import Path

from ragecoop_core import (
    LauncherConfig,
    LauncherError,
    _safe_extract_zip,
    extract_claim_url,
    extract_public_address,
    find_client_settings,
    find_game_executable,
    ensure_ragecoop_client_installed,
    ensure_mod_loaders_installed,
    install_mod_loaders_from_adjacent_zips,
    install_ragecoop_from_adjacent_zips,
    missing_mod_loader_files,
    normalize_address,
    parse_radmin_ipv4_from_ipconfig,
    parse_vpn_ipv4_from_ipconfig,
    read_server_port,
    setup_ragecoop_plus_package,
    update_client_settings,
)


class RageCoopCoreTests(unittest.TestCase):
    def test_normalize_address_accepts_common_forms(self) -> None:
        self.assertEqual(normalize_address("tcp://0.tcp.ngrok.io:12345"), "0.tcp.ngrok.io:12345")
        self.assertEqual(normalize_address(" udp://name.playit.gg:4499 "), "name.playit.gg:4499")
        self.assertEqual(normalize_address("friend-host.example:62000"), "friend-host.example:62000")
        self.assertEqual(normalize_address("able-straw.auto.playit.gg:51795"), "able-straw.auto.playit.gg:51795")

    def test_normalize_address_rejects_bad_port(self) -> None:
        with self.assertRaises(LauncherError):
            normalize_address("name.playit.gg:notaport")
        with self.assertRaises(LauncherError):
            normalize_address("name.playit.gg:70000")

    def test_read_server_port_uses_xml_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Settings.xml"
            path.write_text("<Settings><Port>4501</Port></Settings>", encoding="utf-8")
            self.assertEqual(read_server_port(path, 4499), 4501)

    def test_read_server_port_falls_back_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_server_port(Path(tmp) / "Settings.xml", 4499), 4499)

    def test_update_client_settings_creates_and_updates_last_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scripts" / "RageCoop" / "Data" / "RageCoop.Client.Settings.xml"
            backup = update_client_settings(path, "name.playit.gg:12345")
            self.assertIsNone(backup)
            text = path.read_text(encoding="utf-8")
            self.assertIn("<LastServerAddress>name.playit.gg:12345</LastServerAddress>", text)

            backup = update_client_settings(path, "other.playit.gg:23456")
            self.assertIsNotNone(backup)
            self.assertTrue(backup.exists())
            text = path.read_text(encoding="utf-8")
            self.assertIn("<LastServerAddress>other.playit.gg:23456</LastServerAddress>", text)

    def test_update_client_settings_preserves_other_elements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "RageCoop.Client.Settings.xml"
            path.write_text(
                "<Settings><Username>Misha</Username><LastServerAddress>old:1</LastServerAddress></Settings>",
                encoding="utf-8",
            )
            update_client_settings(path, "new.playit.gg:4499")
            text = path.read_text(encoding="utf-8")
            self.assertIn("<Username>Misha</Username>", text)
            self.assertIn("<LastServerAddress>new.playit.gg:4499</LastServerAddress>", text)

    def test_find_game_executable_prefers_playgtav(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "GTA5.exe").write_text("", encoding="utf-8")
            (root / "PlayGTAV.exe").write_text("", encoding="utf-8")
            found = find_game_executable(root, LauncherConfig().game_exe_candidates)
            self.assertEqual(found.name, "PlayGTAV.exe")

    def test_find_client_settings_prefers_ragecoop_plus_direct_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plus_path = root / "scripts" / "Data" / "RageCoop.Client.Settings.xml"
            old_path = root / "scripts" / "RageCoop" / "Data" / "RageCoop.Client.Settings.xml"
            plus_path.parent.mkdir(parents=True)
            old_path.parent.mkdir(parents=True)
            plus_path.write_text("<Settings />", encoding="utf-8")
            old_path.write_text("<Settings />", encoding="utf-8")

            self.assertEqual(find_client_settings(root, LauncherConfig()), plus_path.resolve())

    def test_extract_public_address_ignores_localhost(self) -> None:
        line = "local 127.0.0.1:4499 public able-straw.auto.playit.gg:51795"
        self.assertEqual(extract_public_address(line), "able-straw.auto.playit.gg:51795")

    def test_extract_public_address_from_split_playit_style_text(self) -> None:
        text = "tunnel ready\naddress able-straw.auto.playit.gg\nport: 51795"
        self.assertEqual(extract_public_address(text), "able-straw.auto.playit.gg:51795")

    def test_extract_public_address_accepts_public_ipv4(self) -> None:
        self.assertEqual(extract_public_address("public 147.185.221.16:51795"), "147.185.221.16:51795")

    def test_extract_claim_url(self) -> None:
        line = "open https://playit.gg/claim/abc123 to claim this agent"
        self.assertEqual(extract_claim_url(line), "https://playit.gg/claim/abc123")

    def test_parse_radmin_ipv4_from_english_ipconfig(self) -> None:
        text = """
Ethernet adapter Ethernet:
   IPv4 Address. . . . . . . . . . . : 192.168.1.10

Ethernet adapter Radmin VPN:
   IPv4 Address. . . . . . . . . . . : 26.45.67.89
"""
        self.assertEqual(parse_radmin_ipv4_from_ipconfig(text), "26.45.67.89")

    def test_parse_radmin_ipv4_from_russian_ipconfig(self) -> None:
        text = """
Адаптер Ethernet Radmin VPN:
   IPv4-адрес. . . . . . . . . . . . : 26.10.20.30
"""
        self.assertEqual(parse_radmin_ipv4_from_ipconfig(text), "26.10.20.30")

    def test_parse_vpn_ipv4_prefers_wireguard(self) -> None:
        text = """
Ethernet adapter Radmin VPN:
   IPv4 Address. . . . . . . . . . . : 26.45.67.89

Unknown adapter WireGuard Tunnel:
   IPv4 Address. . . . . . . . . . . : 10.44.1.14
"""
        self.assertEqual(
            parse_vpn_ipv4_from_ipconfig(text, ["wireguard", "radmin"]),
            ("Unknown adapter WireGuard Tunnel", "10.44.1.14"),
        )

    def test_parse_vpn_ipv4_accepts_openvpn_adapter(self) -> None:
        text = """
Ethernet adapter OpenVPN TAP-Windows6:
   IPv4 Address. . . . . . . . . . . : 10.9.0.2
"""
        self.assertEqual(
            parse_vpn_ipv4_from_ipconfig(text, ["openvpn", "tap-windows"]),
            ("Ethernet adapter OpenVPN TAP-Windows6", "10.9.0.2"),
        )

    def test_parse_vpn_ipv4_accepts_amnezia_adapter(self) -> None:
        text = """
Неизвестный адаптер AmneziaVPN:
   IPv4-адрес. . . . . . . . . . . . : 10.44.1.14
"""
        self.assertEqual(
            parse_vpn_ipv4_from_ipconfig(text, ["amnezia", "wireguard"]),
            ("Неизвестный адаптер AmneziaVPN", "10.44.1.14"),
        )

    def test_safe_extract_zip_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../bad.txt", "bad")
            with self.assertRaises(LauncherError):
                _safe_extract_zip(archive, root / "out")

    def test_install_client_zip_from_external_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game_root = Path(tmp) / "game"
            source_root = Path(tmp) / "source"
            source_root.mkdir()
            with zipfile.ZipFile(source_root / "RageCoop.Client.zip", "w") as zf:
                zf.writestr("RageCoop/RageCoop.Client.dll", "dll")

            messages = install_ragecoop_from_adjacent_zips(
                game_root,
                LauncherConfig(),
                source_roots=[source_root],
                install_server=False,
                install_client=True,
            )

            self.assertTrue((game_root / "scripts" / "RageCoop" / "RageCoop.Client.dll").exists())
            self.assertEqual(messages, ["Клиент распакован из RageCoop.Client.zip в scripts."])


    def test_install_client_zip_skips_when_ragecoop_plus_client_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game_root = Path(tmp) / "game"
            source_root = Path(tmp) / "source"
            plus_client = game_root / "scripts" / "RageCoop.Client.dll"
            plus_client.parent.mkdir(parents=True)
            plus_client.write_text("plus", encoding="utf-8")
            source_root.mkdir()
            with zipfile.ZipFile(source_root / "RageCoop.Client.zip", "w") as zf:
                zf.writestr("RageCoop/RageCoop.Client.dll", "old")

            messages = install_ragecoop_from_adjacent_zips(
                game_root,
                LauncherConfig(),
                source_roots=[source_root],
                install_server=False,
                install_client=True,
            )

            self.assertEqual(messages, [])
            self.assertFalse((game_root / "scripts" / "RageCoop" / "RageCoop.Client.dll").exists())
            ensure_ragecoop_client_installed(game_root)

    def test_install_mod_loaders_from_local_zips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game_root = Path(tmp) / "game"
            source_root = Path(tmp) / "source"
            game_root.mkdir()
            source_root.mkdir()

            with zipfile.ZipFile(source_root / "ScriptHookV.zip", "w") as zf:
                zf.writestr("bin/ScriptHookV.dll", "hook")
                zf.writestr("bin/dinput8.dll", "asi loader")
                zf.writestr("bin/xinput1_4.dll", "enhanced loader")
                zf.writestr("bin/args.txt", "-nobattleye -noBE")
                zf.writestr("bin/NativeTrainer.asi", "not copied")
            with zipfile.ZipFile(source_root / "ScriptHookVDotNet.zip", "w") as zf:
                zf.writestr("ScriptHookVDotNet.asi", "asi")
                zf.writestr("ScriptHookVDotNet2.dll", "v2")
                zf.writestr("ScriptHookVDotNet3.dll", "v3")
                zf.writestr("MinHook.x64.dll", "minhook")

            config = LauncherConfig(script_hook_v_dotnet_zip_candidates=["ScriptHookVDotNet.zip"])
            messages = install_mod_loaders_from_adjacent_zips(game_root, config, source_roots=[source_root])

            self.assertIn("Script Hook V установлен из ScriptHookV.zip.", messages)
            self.assertIn("ScriptHookVDotNet Enhanced установлен из ScriptHookVDotNet.zip.", messages)
            self.assertTrue((game_root / "ScriptHookV.dll").exists())
            self.assertTrue((game_root / "dinput8.dll").exists())
            self.assertTrue((game_root / "xinput1_4.dll").exists())
            self.assertTrue((game_root / "args.txt").exists())
            self.assertFalse((game_root / "NativeTrainer.asi").exists())
            self.assertEqual(missing_mod_loader_files(game_root), [])
            ensure_mod_loaders_installed(game_root)

    def test_setup_ragecoop_plus_extracts_client_and_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "source"
            client_dir = root / "RageCoopPlus"
            server_dir = root / "RageCoopPlusServer"
            source_root.mkdir()

            with zipfile.ZipFile(source_root / "RageCoopPlus.zip", "w") as zf:
                zf.writestr("Client/RageCoop.Client.Installer.exe", "installer")
                zf.writestr("Server/RageCoop.Server.exe", "server")
                zf.writestr("Server/Settings.xml", "<Settings><Port>4499</Port></Settings>")

            config = LauncherConfig(
                ragecoop_plus_client_dir=str(client_dir),
                ragecoop_plus_server_dir=str(server_dir),
            )
            messages = setup_ragecoop_plus_package(root, config, source_roots=[source_root])

            self.assertTrue((client_dir / "Client" / "RageCoop.Client.Installer.exe").exists())
            self.assertTrue((server_dir / "RageCoop.Server.exe").exists())
            self.assertTrue((server_dir / "Settings.xml").exists())
            self.assertIn(f"RageCoop+ server copied to {server_dir}.", messages)


if __name__ == "__main__":
    unittest.main()
