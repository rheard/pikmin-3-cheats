"""
Where the files are: the game's own, read from an extracted RomFS, and the mod folders being written.

A mod folder mirrors the game's layout. A loader that finds `romfs/CMCmn/lyt/common.szs` in it
hands the game that file in place of its own, applies `exefs/<build id>.ips` to the program whose
build ID that is, lays out `exefs/subsdk1` after the game's own program files, and lists the
entries of `cheats/<build id>.txt` for the player to tick.
"""

from __future__ import annotations

from pathlib import Path

from cheats.errors import BuildError

COMMON = "CMCmn"  # the folder of the RomFS that every file this mod touches is in
LANDMARK = "lyt/common.szs"


class RomFs:
    """The game's files, extracted from your own copy. Nothing is ever written here."""

    def __init__(self, path: str | Path):
        """
        Find the game's files at `path`: the RomFS folder itself, or a folder holding it as `romfs`.

        Raises:
            BuildError: If the game's files are not there.
        """
        path = Path(path)
        for root in (path / COMMON, path / "romfs" / COMMON, path):
            if (root / LANDMARK).is_file():
                self.root = root
                return
        raise BuildError(f"{path} does not look like Pikmin 3 Deluxe's RomFS: there is no {COMMON}/{LANDMARK} in it")

    def read(self, name: str) -> bytes:
        """The bytes of one file, named from inside `CMCmn/` with forward slashes."""
        file = self.root / name
        if not file.is_file():
            raise BuildError(f"the RomFS has no {COMMON}/{name}")
        return file.read_bytes()


class Mod:
    """A mod folder being written."""

    def __init__(self, path: str | Path):
        self.root = Path(path)

    def write(self, name: str, data: bytes) -> Path:
        """Write a file the game will load in place of its own `CMCmn/<name>`."""
        return self._write(self.root / "romfs" / COMMON / name, data)

    def write_patch(self, build_id: str, data: bytes) -> Path:
        """Write an IPS patch of the program with this build ID."""
        return self._write(self.root / "exefs" / f"{build_id}.ips", data)

    def write_program(self, name: str, data: bytes) -> Path:
        """Write a program file of the mod's own, which the loader lays out after the game's."""
        return self._write(self.root / "exefs" / name, data)

    def write_cheats(self, build_id: str, text: str) -> Path:
        """Write the cheat file of the program with this build ID (its first 16 digits name it)."""
        return self._write(self.root / "cheats" / f"{build_id[:16]}.txt", text.encode("utf-8"))

    @staticmethod
    def _write(file: Path, data: bytes) -> Path:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        return file
