import tempfile
import unittest
from pathlib import Path

from ragecoop_installer import available_package_files, copy_with_backup, find_vpn_installer, is_gta_folder


class RageCoopInstallerTests(unittest.TestCase):
    def test_is_gta_folder_accepts_known_exes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(is_gta_folder(root))
            (root / "GTA5.exe").write_text("", encoding="utf-8")
            self.assertTrue(is_gta_folder(root))

    def test_available_package_files_collects_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "GTA5CoopLauncher.exe").write_text("x", encoding="utf-8")
            (root / "launcher_config.json").write_text("{}", encoding="utf-8")
            files = available_package_files(root)
            self.assertEqual([path.name for path in files], ["GTA5CoopLauncher.exe", "launcher_config.json"])

    def test_available_package_files_collects_external_playit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"
            external = Path(tmp) / "external"
            root.mkdir()
            external.mkdir()
            (root / "GTA5CoopLauncher.exe").write_text("x", encoding="utf-8")
            (external / "playit.exe").write_text("x", encoding="utf-8")

            files = available_package_files(root, external)

            self.assertEqual([path.name for path in files], ["GTA5CoopLauncher.exe", "playit.exe"])

    def test_available_package_files_collects_ragecoop_plus_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "GTA5CoopLauncher.exe").write_text("x", encoding="utf-8")
            (root / "RageCoopPlus.zip").write_text("zip", encoding="utf-8")

            files = available_package_files(root)

            self.assertEqual([path.name for path in files], ["GTA5CoopLauncher.exe", "RageCoopPlus.zip"])

    def test_find_vpn_installer_accepts_wireguard_installer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installer = root / "wireguard-installer.exe"
            installer.write_text("x", encoding="utf-8")

            self.assertEqual(find_vpn_installer(root), installer.resolve())

    def test_copy_with_backup_preserves_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            destination = root / "target.txt"
            source.write_text("new", encoding="utf-8")
            destination.write_text("old", encoding="utf-8")

            name, backup_note = copy_with_backup(source, destination)

            self.assertEqual(name, "target.txt")
            self.assertIn("backup:", backup_note)
            self.assertEqual(destination.read_text(encoding="utf-8"), "new")
            backups = list(root.glob("target.txt.installer-bak-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "old")


if __name__ == "__main__":
    unittest.main()
