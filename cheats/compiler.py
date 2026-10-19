"""
Compile and link code for the game: 32-bit ARM code that runs beside the game's own and calls into it.

The compiler is LLVM's: `clang` and `ld.lld`, found through the environment variable `LLVM_BIN`,
then the `PATH`, then where LLVM's Windows installer puts them.

**Nothing may hold an absolute address.** The game is not loaded at the addresses its code is
numbered by; what does not change is the distance from the mod's program file to the game's code
(the loader lays it out straight after the game's own files). So every reference, to the game or to
the code's own constants and variables, has to count from the pc, and the build refuses anything
else:

* `-fPIC`, with every name hidden (`-fvisibility=hidden`, and `#pragma GCC visibility push(hidden)`
  around the game's names): the compiler then reaches a variable by its distance from the
  instruction, never through a table of addresses.
* `--pic-veneer`: a call farther than a `bl` reaches goes through a few words the linker adds,
  which count the distance from the pc too.
* `--emit-relocs`: the linker keeps a record of every place it filled in, and the build stops on
  any of a kind that writes an address: a pointer to a function or a string kept in a variable, or a
  table of them. Code works out such an address when it runs instead.

**The game's conventions**, which the flags follow: ARM instructions, not Thumb; floats passed in
the float registers; division by instruction; enums the size of an int. No library comes with it:
code that wants `memcpy` writes its own.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess as sp
import tempfile

from dataclasses import dataclass
from pathlib import Path

from cheats.errors import BuildError

FLAGS = (
    "--target=armv7a-none-eabihf",
    "-march=armv7ve",
    "-marm",
    "-mfloat-abi=hard",
    "-mfpu=vfpv4",
    "-fPIC",
    "-fvisibility=hidden",
    "-ffreestanding",
    "-fno-builtin",
    "-fno-short-enums",
    "-fno-unwind-tables",
    "-fno-asynchronous-unwind-tables",
    "-fno-exceptions",
    "-fno-stack-protector",
    "-ffp-contract=off",
    "-fno-common",
    "-ffunction-sections",
    "-O2",
    "-Wall",
    "-Werror=implicit-function-declaration",
)
INSTALLED = Path("C:/Program Files/LLVM/bin")  # where LLVM's Windows installer puts it
GAME_LABEL = re.compile(r"LAB_([0-9a-f]{8})")  # a place in the game's code, named by its address
# The kinds of the linker's records that count from the pc, or write nothing (ELF for the ARM architecture):
# none, rel32, plt32, call, jump24, v4bx, movw_prel_nc, movt_prel
RELATIVE = frozenset((0, 3, 27, 28, 29, 40, 45, 46))
SHT_SYMTAB, SHT_REL = 2, 9
SHF_ALLOC = 2


def llvm() -> Path:
    """
    Find LLVM.

    Returns:
        The folder that holds `clang` and `ld.lld`.

    Raises:
        BuildError: If they are not found.
    """
    tried = []
    if os.environ.get("LLVM_BIN"):
        tried.append(Path(os.environ["LLVM_BIN"]))
    on_path = shutil.which("clang")
    if on_path:
        tried.append(Path(on_path).parent)
    tried.append(INSTALLED)
    suffix = ".exe" if os.name == "nt" else ""
    for folder in tried:
        if all((folder / f"{tool}{suffix}").is_file() for tool in ("clang", "ld.lld")):
            return folder
    looked = "; ".join(str(folder) for folder in tried)
    raise BuildError(
        f"LLVM's clang and ld.lld were not found (looked in: {looked}). Set LLVM_BIN to the folder they are in",
    )


def _tool(name: str) -> str:
    return str(llvm() / f"{name}{'.exe' if os.name == 'nt' else ''}")


def _run(args: list[str]) -> str:
    """
    Run one of LLVM's tools.

    Returns:
        What it printed.

    Raises:
        BuildError: If it fails.
    """
    done = sp.run(args, capture_output=True, text=True, check=False)
    if done.returncode:
        raise BuildError(f"{Path(args[0]).name} failed:\n{done.stdout}{done.stderr}")
    return done.stdout


def version() -> str:
    """The version of the `clang` found, as it gives it on its first line."""
    return _run([_tool("clang"), "--version"]).splitlines()[0]


class Elf:
    """The little of a 32-bit little-endian ELF file the build reads: sections, symbols, the linker's records."""

    def __init__(self, data: bytes):
        """
        Read the table of sections.

        Raises:
            BuildError: If it is not a 32-bit little-endian ELF file.
        """
        if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
            raise BuildError("the linker did not write a 32-bit little-endian ELF file")
        self.data = data
        start = struct.unpack_from("<I", data, 0x20)[0]
        size, count, names = struct.unpack_from("<HHH", data, 0x2E)
        raw = [struct.unpack_from("<10I", data, start + k * size) for k in range(count)]
        self.sections = [
            {
                "name": self._string(raw[names][4], name),
                "kind": kind,
                "flags": flags,
                "addr": addr,
                "offset": offset,
                "size": size_,
                "link": link,
                "info": info,
            }
            for name, kind, flags, addr, offset, size_, link, info, _, _ in raw
        ]

    def _string(self, table: int, at: int) -> str:
        return self.data[table + at : self.data.index(b"\0", table + at)].decode("latin-1")

    def symbols(self) -> list[tuple[str, int, int, int]]:
        """Every symbol: its name, value, section and the byte of its kind and binding."""
        out = []
        for s in self.sections:
            if s["kind"] != SHT_SYMTAB:
                continue
            strings = self.sections[s["link"]]["offset"]
            for k in range(s["size"] // 16):
                name, value, _, info, _, section = struct.unpack_from("<IIIBBH", self.data, s["offset"] + 16 * k)
                out.append((self._string(strings, name), value, section, info))
        return out

    def records(self) -> list[tuple[int, int, str]]:
        """Every record the linker kept (`--emit-relocs`) for a loaded section: its place, its kind and its symbol."""
        names = self.symbols()
        out = []
        for s in self.sections:
            if s["kind"] != SHT_REL or not self.sections[s["info"]]["flags"] & SHF_ALLOC:
                continue
            for k in range(s["size"] // 8):
                place, info = struct.unpack_from("<II", self.data, s["offset"] + 8 * k)
                out.append((place, info & 0xFF, names[info >> 8][0] if info >> 8 < len(names) else "?"))
        return out


@dataclass(frozen=True)
class Built:
    """
    Code built to run at `at`.

    Attributes:
        code: The bytes of the code and its constants, from `at`.
        data: The bytes of its variables, from `data_at`.
        zeroed: How many zero bytes its variables go on into.
        symbols: The address of everything it defines, by name.
        at: Where the code is.
        data_at: Where the variables are.
    """

    code: bytes
    data: bytes
    zeroed: int
    symbols: dict[str, int]
    at: int
    data_at: int


def build(
    sources: list[Path],
    at: int,
    data_at: int,
    *,
    include: list[Path],
    script: str = "",
    names: dict[str, int] | None = None,
) -> Built:
    """
    Compile and link `sources` (C files, or assembly ending in .s or .S).

    Args:
        sources: The files, in the order their code is laid out.
        at: Where the code runs, a multiple of 4.
        data_at: Where its variables are.
        include: The folders `#include` looks in.
        script: Linker script text that names things of the game's (`name = 0x60000000;`).
        names: More names of the game's, by address. Besides these, a name `LAB_<address>` is the
            game's code at that address.

    Returns:
        The code built.

    Raises:
        BuildError: If it does not compile or link, or would hold an absolute address.
    """
    names = dict(names or {})
    with tempfile.TemporaryDirectory() as work:
        objects = []
        for n, source in enumerate(sources):
            obj = Path(work) / f"{n}.o"
            _run([_tool("clang"), *FLAGS, "-c", str(source), "-o", str(obj), *(f"-I{folder}" for folder in include)])
            objects.append(obj)
        for obj in objects:
            for name, _value, section, _info in Elf(obj.read_bytes()).symbols():
                found = GAME_LABEL.fullmatch(name)
                if found and not section:
                    names[name] = int(found.group(1), 16)
        lines = [
            "SECTIONS {",
            f"  . = {at:#x};",
            "  .text : { *(.text.first) *(.text .text.*) }",
            "  .rodata : { *(.rodata .rodata.*) }",
            f"  . = {data_at:#x};",
            "  .data : { *(.data .data.*) }",
            "  .bss : { *(.bss .bss.*) }",
            "  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) }",
            "}",
            script,
            *(f"{name} = {address:#x};" for name, address in sorted(names.items())),
        ]
        (Path(work) / "link.ld").write_text("\n".join(lines) + "\n", encoding="utf-8")
        out = Path(work) / "out.elf"
        args = [_tool("ld.lld"), "-m", "armelf", "--pic-veneer", "--emit-relocs", "--no-undefined", "-static"]
        _run([*args, "-T", str(Path(work) / "link.ld"), "-o", str(out), *(str(obj) for obj in objects)])
        elf = Elf(out.read_bytes())
    absolute = [(place, kind, name) for place, kind, name in elf.records() if kind not in RELATIVE]
    if absolute:
        where = "\n".join(f"  {place:#x}: kind {kind}, against {name}" for place, kind, name in absolute)
        raise BuildError(
            f"the code would hold an address that moves with the game (count it from the pc instead):\n{where}",
        )
    loaded = [s for s in elf.sections if s["flags"] & SHF_ALLOC and s["size"]]
    others = [s["name"] for s in loaded if s["name"] not in (".text", ".rodata", ".data", ".bss")]
    if others:
        raise BuildError(f"the code has sections the build does not place: {', '.join(others)}")
    parts = {s["name"]: s for s in loaded}
    end = max((s["addr"] + s["size"] for s in loaded if s["name"] in (".text", ".rodata")), default=at)
    code = bytearray(end - at)
    for s in loaded:
        if s["name"] in (".text", ".rodata"):
            code[s["addr"] - at : s["addr"] - at + s["size"]] = elf.data[s["offset"] : s["offset"] + s["size"]]
    code += bytes(-len(code) % 4)
    data_part, zeroed_part = parts.get(".data"), parts.get(".bss")
    place = data_part["addr"] if data_part else zeroed_part["addr"] if zeroed_part else data_at
    data = elf.data[data_part["offset"] : data_part["offset"] + data_part["size"]] if data_part else b""
    if data_part and zeroed_part and zeroed_part["addr"] < data_part["addr"] + data_part["size"]:
        raise BuildError("the code's zeroed variables overlap its others")
    zeroed = zeroed_part["addr"] + zeroed_part["size"] - place - len(data) if zeroed_part else 0
    symbols = {
        name: value
        for name, value, section, info in elf.symbols()
        if name and section and section < 0xFF00 and info & 0xF in (1, 2)
    }
    return Built(bytes(code), bytes(data), zeroed, symbols, at, place)
