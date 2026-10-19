"""
Read and write the game's layouts (`.bflyt`) and their animations (`.bflan`), to add panes to a page::

    lyt = Layout(data)  # a .bflyt's bytes
    lyt.copy("N_CRow_00", {"N_CRow_00": "N_DRow_00", ...}, into="N_SelectionD_00")  # a pane and all under it
    lyt.move("N_DRow_00", y=154.0)  # where it stands in its parent
    lyt.add_to_group("G_SettingChange_00", "N_SelectionD_00")
    data = lyt.data()
    anim = Animation(data)  # a .bflan's bytes
    anim.keys("N_SelectionA_00", "FLVC", OPACITY)  # [(frame, value, slope)] of one curve, to change in place
    anim.add_pane("N_SelectionD_00", [("FLVI", SHOWN, STEP, [(0.0, 1)]), ("FLVC", OPACITY, HERMITE, [...])])
    data = anim.data()

**The layout file** (version 8.3, the game's): a header ("FLYT", the byte-order mark, the header's
size 0x14, the version, the file's size, how many sections follow) and sections, each a four-letter
kind and its size. The panes are sections of their own (`pan1` a plain pane, `pic1` a picture,
`txt1` text, `wnd1` a window, `prt1` a part: a layout of `lyt/parts.szs` placed here, which is how
the game's buttons are made), each followed by its user data (`usd1`) if it has any, and by `pas1`
... `pae1` around its children. Every pane begins alike: flags (+0x08, bit 0 shown), its origin
(+0x09), its opacity (+0x0a), more flags, its name (24 bytes, at +0x0c), user data (8 bytes), then
where it stands (+0x2c, three floats), its turn (+0x38), its scale (+0x44, two floats) and its size
(+0x4c). The origin's low four bits say which point of the pane stands there (0 its middle), and its
top two bits which of its parent's edges its y counts from (0 the middle, 1 the top, 2 the bottom).
Nothing in a pane refers to another pane by place, so a copy of one with its children, under new
names, is a layout the library builds like any other.

A part pane's own fields follow the common ones: how many properties (+0x54), its magnify (+0x58,
two floats: its size over the part layout's own size as a part, the `lyt1` section's last two
floats), the properties (40 bytes each), then the part layout's name, padded to 4. With no
properties it is 0x60 bytes and the name. A property is the part's pane it is for (24 bytes), four
flag bytes, and the offsets of a pane that overrides it, of user data and of basic information
(+28, +32, +36; 0 for none), which count from the start of the part's section. The overriding pane
is a whole pane section (a part's again, for a part within the part), after the part layout's
name; the Onion window's give the "all" overlay's numbers their messages.

Groups (`grp1`, between `grs1` and `gre1`) list their panes by name: a name of 34 bytes at +0x08,
how many at +0x2a, then 24 bytes for each.

**Materials** (`mat1`): how many (+0x08), then an offset for each, counting from the section's
start. A material is its name (28 bytes), flags (+0x1c: bits 0-1 how many texture maps, 2-3 how
many texture transforms), its black and white colours (+0x24, +0x28), its texture maps (+0x2c, 4
bytes each: the texture's place in `txl1` and two of wrapping) and then its texture transforms. A
picture pane names its material by place (+0x64), and an animation's material curves find it by
name, so a copied picture whose colour is animated apart from its original needs a material of its
own. `txl1` lists the textures by name (how many at +0x08, an offset each from +0x0c). Materials and
textures are only ever added at the end, so no place already given changes.

**The animation file** ("FLAN", the same header): `pat1` names the animation and the groups it is
bound through; `pai1` holds its frame count and its contents. A content is one pane or material by
name, 28 bytes, then how many tags it has, its kind and the tags' offsets. A tag is four letters
(`FLVI` shown or not, `FLVC` colour and opacity, `FLPA` place, turn, scale and size, `FLTP` a
texture by its place in the animation's own list, ...) and its curves' offsets. A curve names what
it changes (+1), its kind (1 steps, 2 Hermite) and its keys: a step key is a frame and a 16-bit
value, a Hermite key a frame, a value and a slope, all floats. Offsets count from the start of what
holds them. An animation that changes textures lists their names first (how many at +0x0c, an
offset each from +0x14), and its contents' table follows. Every content is read into a `Content`
and written again in the same order, so a file read and written unchanged comes back byte for byte.
"""

from __future__ import annotations

import itertools
import struct

from dataclasses import dataclass

PANES = (b"pan1", b"pic1", b"txt1", b"wnd1", b"bnd1", b"prt1", b"scr1", b"ali1")
NAME = 0x0C  # a pane's name: 24 bytes
USER_DATA = 0x24  # a pane's user data: 8 bytes
TRANSLATE, SCALE, SIZE = 0x2C, 0x44, 0x4C  # where a pane stands, its scale and its size
PART_FIELDS = 0x54  # a part pane's own fields, after the common ones: first its count of properties
PROPERTIES, PROPERTY = 0x60, 40  # where a part's properties start, and the size of one
PIC_MATERIAL = 0x64  # a picture's material, by its place in mat1
MATERIAL_NAME = 28  # a material's name: 28 bytes
MATERIAL_FLAGS, MATERIAL_COLOURS, MATERIAL_MAPS = 0x1C, 0x24, 0x2C
GROUP_NAME, GROUP_COUNT, GROUP_PANES = 0x08, 0x2A, 0x2C  # a group's name (34 bytes), how many panes, their names

# What a curve changes: `FLVI` has one curve, whether the pane is shown; `FLVC` 0 to 15 are its
# corners' colours, 16 its opacity; `FLPA` 0 to 2 are where it stands, 3 to 5 its turn, 6 and 7 its
# scale and 8 and 9 its size.
SHOWN = 0
OPACITY = 16
PLACE_X, SCALE_X, SCALE_Y, WIDTH = 0, 6, 7, 8
STEP, HERMITE = 1, 2  # a curve's kind: it holds each key's value until the next, or runs smoothly between them
PANE, MATERIAL = 0, 1  # a content's kind

Section = tuple[bytes, bytearray]  # a section's kind (four letters) and its bytes, kind and size included
Key = tuple[float, ...]  # a step key (frame, value) or a Hermite key (frame, value, slope)


def _name(raw: bytes | bytearray, at: int, size: int) -> str:
    """The name in a field of `size` bytes at `at`, up to its first zero byte."""
    return raw[at : at + size].split(b"\0")[0].decode("latin-1")


def _padded(name: str, size: int) -> bytes:
    """
    Write a name into a field of `size` bytes.

    Returns:
        The field: the name, then zeros.

    Raises:
        ValueError: If it does not fit with a zero byte after it.
    """
    raw = name.encode("latin-1")
    if len(raw) >= size:
        raise ValueError(f"{name} is longer than a name may be ({size - 1} letters)")
    return raw + bytes(size - len(raw))


def _name_table(names: list[str]) -> bytes:
    """An offset for each name, counted from the first offset, then the names, padded to a word."""
    offsets, blob = [], bytearray()
    for name in names:
        offsets.append(4 * len(names) + len(blob))
        blob += name.encode("latin-1") + b"\0"
    out = b"".join(struct.pack("<I", offset) for offset in offsets) + bytes(blob)
    return out + bytes(-len(out) % 4)


def _sections(data: bytes, magic: bytes) -> tuple[bytes, list[Section]]:
    """
    Split a layout or an animation into its header and its sections.

    Returns:
        The header's bytes, and the sections in order.

    Raises:
        ValueError: If it is not a little-endian file of this kind, or its sections do not add up to it.
    """
    if data[:4] != magic or data[4:6] != b"\xff\xfe":
        raise ValueError(f"not a little-endian {magic.decode()} file")
    header = struct.unpack_from("<H", data, 6)[0]
    count = struct.unpack_from("<H", data, 0x10)[0]
    at, out = header, []
    for _ in range(count):
        size = struct.unpack_from("<I", data, at + 4)[0]
        out.append((bytes(data[at : at + 4]), bytearray(data[at : at + size])))
        at += size
    if at != len(data) or struct.unpack_from("<I", data, 0x0C)[0] != len(data):
        raise ValueError("the sections do not add up to the file")
    return bytes(data[:header]), out


def _join(head: bytes, sections: list[Section]) -> bytes:
    """A file of this header and these sections, its size and its count of sections set."""
    body = b"".join(bytes(data) for _, data in sections)
    out = bytearray(head)
    struct.pack_into("<I", out, 0x0C, len(out) + len(body))
    struct.pack_into("<H", out, 0x10, len(sections))
    return bytes(out) + body


def _marker(kind: bytes) -> Section:
    """A section of no more than its kind and size: `pas1` or `pae1`, around a pane's children."""
    return kind, bytearray(kind + struct.pack("<I", 8))


class Layout:
    """
    A layout, read into its sections to be changed and written again.

    Attributes:
        head: The file's header.
        sections: Its sections in order, each its kind and its bytes.
    """

    def __init__(self, data: bytes) -> None:
        self.head, self.sections = _sections(data, b"FLYT")

    def data(self) -> bytes:
        """The layout as a file again."""
        return _join(self.head, self.sections)

    # -- panes -------------------------------------------------------------------------------------

    def names(self) -> dict[str, int]:
        """{pane name: its section's index}."""
        return {_name(data, NAME, 24): k for k, (kind, data) in enumerate(self.sections) if kind in PANES}

    def index(self, name: str) -> int:
        """
        Find a pane's section.

        Returns:
            Its index in `sections`.

        Raises:
            KeyError: If not exactly one pane has that name.
        """
        found = [k for k, (kind, data) in enumerate(self.sections) if kind in PANES and _name(data, NAME, 24) == name]
        if len(found) != 1:
            raise KeyError(f"{len(found)} panes named {name}")
        return found[0]

    def section(self, name: str) -> bytearray:
        """The bytes of a pane's section, to change in place."""
        return self.sections[self.index(name)][1]

    def _own_end(self, k: int) -> int:
        """The index after the pane at `k` and its user data: where the list of its children starts, if it has one."""
        k += 1
        if k < len(self.sections) and self.sections[k][0] == b"usd1":
            k += 1
        return k

    def span(self, name: str) -> tuple[int, int]:
        """
        Find a pane and everything under it.

        That is the pane, its user data, and its children from `pas1` to the matching `pae1`.

        Returns:
            The index of its first section and of the one after its last.
        """
        first = self.index(name)
        end = self._own_end(first)
        if end < len(self.sections) and self.sections[end][0] == b"pas1":
            depth = 0
            while True:
                kind = self.sections[end][0]
                if kind == b"pas1":
                    depth += 1
                elif kind == b"pae1":
                    depth -= 1
                end += 1
                if not depth:
                    break
        return first, end

    def children(self, name: str) -> list[str]:
        """The panes straight under a pane, in order."""
        first, end = self.span(name)
        out, depth = [], 0
        for kind, data in self.sections[first + 1 : end]:
            if kind == b"pas1":
                depth += 1
            elif kind == b"pae1":
                depth -= 1
            elif kind in PANES and depth == 1:
                out.append(_name(data, NAME, 24))
        return out

    def _add_child(self, into: str, block: list[Section]) -> None:
        """Put sections in as the last child of pane `into`, starting a list of its children if it has none."""
        k, end = self.span(into)
        if self._own_end(k) == end:
            self.sections[end:end] = [_marker(b"pas1"), *block, _marker(b"pae1")]
        else:
            self.sections[end - 1 : end - 1] = block  # before its pae1

    def copy(
        self,
        name: str,
        renames: dict[str, str],
        *,
        after: str | None = None,
        into: str | None = None,
        alone: bool = False,
        materials: bool = False,
    ) -> str:
        """
        Copy a pane and all under it, every pane of the copy under a new name.

        Args:
            name: The pane to copy.
            renames: The new name of every pane copied.
            after: Put the copy straight after this pane and all under it, so beside it, under the
                same parent.
            into: Put the copy in this pane instead, as its last child.
            alone: Copy the pane and its user data only, none of its children.
            materials: Give each picture copied a copy of its material, named as the picture is now,
                so that an animation's material curves reach the copy apart from the original.

        Returns:
            The copy's name.

        Raises:
            KeyError: If a pane copied has no new name.
            ValueError: If a new name is taken, or not one of `after` and `into` is given.
        """
        first, end = self.span(name)
        if alone:
            end = self._own_end(first)
        block = [(kind, bytearray(data)) for kind, data in self.sections[first:end]]
        for kind, data in block:
            if kind not in PANES:
                continue
            old = _name(data, NAME, 24)
            if old not in renames:
                raise KeyError(f"no new name given for {old}")
            data[NAME : NAME + 24] = _padded(renames[old], 24)
            if materials and kind == b"pic1":
                index = self.copy_material(struct.unpack_from("<H", data, PIC_MATERIAL)[0], renames[old])
                struct.pack_into("<H", data, PIC_MATERIAL, index)
        taken = self.names()
        clash = [new for new in renames.values() if new in taken]
        if clash:
            raise ValueError(f"the layout already has panes named {', '.join(clash)}")
        if (after is None) == (into is None):
            raise ValueError("give `after` or `into`")
        if after is not None:
            _, at = self.span(after)
            self.sections[at:at] = block
        else:
            self._add_child(into, block)
        return renames[name]

    def add_part(
        self,
        name: str,
        part: str,
        size: tuple[float, float],
        *,
        into: str,
        like: str,
        x: float = 0.0,
        y: float = 0.0,
    ) -> str:
        """
        Add a part pane, with no properties, as the last child of a pane.

        The part's own panes are as its file has them: the pane has the part's own size and magnify
        1, so the library changes none of their sizes as it builds it.

        Args:
            name: The new pane's name.
            part: The layout of `lyt/parts.szs` it places, by name.
            size: That layout's own size as a part (`part_size`).
            into: The pane to put it in.
            like: The pane whose flags, origin and opacity it takes.
            x: Where it stands in its parent, across.
            y: Where it stands in its parent, up.

        Returns:
            Its name.

        Raises:
            ValueError: If the layout already has a pane of that name.
        """
        if name in self.names():
            raise ValueError(f"the layout already has a pane named {name}")
        data = bytearray(self.section(like)[:PART_FIELDS])
        data[0:4] = b"prt1"
        data[NAME : NAME + 24] = _padded(name, 24)
        data[USER_DATA : USER_DATA + 8] = bytes(8)
        struct.pack_into("<3f3f2f2f", data, TRANSLATE, x, y, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, *size)
        label = part.encode("latin-1") + b"\0"
        data += struct.pack("<I2f", 0, 1.0, 1.0) + label + bytes(-len(label) % 4)
        struct.pack_into("<I", data, 4, len(data))
        self._add_child(into, [(b"prt1", data)])
        return name

    def move(self, name: str, *, x: float | None = None, y: float | None = None) -> None:
        """Change where a pane stands in its parent."""
        data = self.section(name)
        if x is not None:
            struct.pack_into("<f", data, TRANSLATE, x)
        if y is not None:
            struct.pack_into("<f", data, TRANSLATE + 4, y)

    def position(self, name: str) -> tuple[float, float, float]:
        """Where a pane stands in its parent: x, y and z."""
        return struct.unpack_from("<3f", self.section(name), TRANSLATE)

    def scale(self, name: str, value: float | None = None) -> tuple[float, float]:
        """A pane's scale across and up, first made `value` both ways if that is given."""
        data = self.section(name)
        if value is not None:
            struct.pack_into("<2f", data, SCALE, value, value)
        return struct.unpack_from("<2f", data, SCALE)

    def size(self, name: str, *, w: float | None = None, h: float | None = None) -> tuple[float, float]:
        """A pane's width and height, first changed to those given."""
        data = self.section(name)
        if w is not None:
            struct.pack_into("<f", data, SIZE, w)
        if h is not None:
            struct.pack_into("<f", data, SIZE + 4, h)
        return struct.unpack_from("<2f", data, SIZE)

    # -- materials and textures --------------------------------------------------------------------

    def _only(self, kind: bytes) -> int:
        """
        Find the one section of a kind.

        Returns:
            Its index in `sections`.

        Raises:
            ValueError: If the layout has none of that kind, or more than one.
        """
        found = [k for k, (each, _) in enumerate(self.sections) if each == kind]
        if len(found) != 1:
            raise ValueError(f"{len(found)} {kind.decode()} sections")
        return found[0]

    def materials(self) -> list[tuple[str, bytes]]:
        """(name, its bytes) of each material, in mat1's order: a picture's material is its place in this list."""
        mat = self.sections[self._only(b"mat1")][1]
        count = struct.unpack_from("<H", mat, 8)[0]
        offsets = [*(struct.unpack_from("<I", mat, 0x0C + 4 * k)[0] for k in range(count)), len(mat)]
        return [(_name(mat, start, MATERIAL_NAME), bytes(mat[start:end])) for start, end in itertools.pairwise(offsets)]

    def material_index(self, name: str) -> int:
        """
        Find a material by name.

        Returns:
            Its place in mat1.

        Raises:
            KeyError: If not exactly one material has that name.
        """
        found = [k for k, (each, _) in enumerate(self.materials()) if each == name]
        if len(found) != 1:
            raise KeyError(f"{len(found)} materials named {name}")
        return found[0]

    @staticmethod
    def material_maps(material: bytes | bytearray) -> tuple[int, int]:
        """(how many texture maps, how many texture transforms) a material's flags give."""
        flags = struct.unpack_from("<I", material, MATERIAL_FLAGS)[0]
        return flags & 3, flags >> 2 & 3

    def copy_material(self, index: int, name: str, *, texture: int | None = None) -> int:
        """
        Copy a material, the copy named `name` and put last.

        Args:
            index: The material's place in mat1.
            name: The copy's name.
            texture: A texture's place in txl1, for the copy's first texture map to show.

        Returns:
            The copy's place in mat1.

        Raises:
            ValueError: If the name is taken, the material has no texture map for `texture`, or mat1
                holds more than this writes again.
        """
        materials = self.materials()
        if any(each == name for each, _ in materials):
            raise ValueError(f"the layout already has a material named {name}")
        body = bytearray(materials[index][1])
        body[:MATERIAL_NAME] = _padded(name, MATERIAL_NAME)
        if texture is not None:
            if not self.material_maps(body)[0]:
                raise ValueError(f"material {index} has no texture map")
            struct.pack_into("<H", body, MATERIAL_MAPS, texture)
        k = self._only(b"mat1")
        if struct.unpack_from("<H", self.sections[k][1], 0x0A)[0] != 0:
            raise ValueError("mat1 has something after its count this does not keep")
        self.sections[k] = (b"mat1", mat1_bytes([*(each for _, each in materials), bytes(body)]))
        return len(materials)

    def material_colours(
        self,
        index: int,
        *,
        black: tuple[int, int, int, int] | None = None,
        white: tuple[int, int, int, int] | None = None,
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """A material's black and white colours (red, green, blue, opacity), first changed to those given."""
        mat = self.sections[self._only(b"mat1")][1]
        at = struct.unpack_from("<I", mat, 0x0C + 4 * index)[0] + MATERIAL_COLOURS
        if black is not None:
            mat[at : at + 4] = bytes(black)
        if white is not None:
            mat[at + 4 : at + 8] = bytes(white)
        return tuple(mat[at : at + 4]), tuple(mat[at + 4 : at + 8])

    def material_of(self, pane: str) -> int:
        """A picture's material: its place in mat1."""
        return struct.unpack_from("<H", self._picture(pane), PIC_MATERIAL)[0]

    def set_material(self, pane: str, index: int) -> None:
        """Give a picture the material at `index` in mat1."""
        struct.pack_into("<H", self._picture(pane), PIC_MATERIAL, index)

    def _picture(self, pane: str) -> bytearray:
        """
        A picture pane's section.

        Returns:
            Its bytes, to change in place.

        Raises:
            ValueError: If the pane is not a picture.
        """
        data = self.section(pane)
        if bytes(data[:4]) != b"pic1":
            raise ValueError(f"{pane} is not a picture")
        return data

    def textures(self) -> list[str]:
        """The names of the layout's textures, in txl1's order: a material's texture is its place in this list."""
        txl = self.sections[self._only(b"txl1")][1]
        count = struct.unpack_from("<H", txl, 8)[0]
        return [_name(txl, 0x0C + struct.unpack_from("<I", txl, 0x0C + 4 * k)[0], 64) for k in range(count)]

    def add_texture(self, name: str) -> int:
        """
        Find a texture by name, adding it to the end of txl1 if the layout does not have it.

        Returns:
            Its place in txl1.

        Raises:
            ValueError: If txl1 does not read back as written.
        """
        names = self.textures()
        if name in names:
            return names.index(name)
        names.append(name)
        self.sections[self._only(b"txl1")] = (b"txl1", txl1_bytes(names))
        if self.textures() != names:
            raise ValueError("txl1 does not read back")
        return len(names) - 1

    # -- a part's properties -----------------------------------------------------------------------

    def add_property(self, pane: str, source: str, name: str) -> None:
        """
        Give a part pane a property for its part's pane `name`, a copy of its property for `source`.

        The pane that property overrides is copied and renamed `name`, as the Onion window's own
        properties give the "all" overlay's numbers 0 to 4 their messages. The new property goes
        last in the table, so what follows the table (the part's name, then the properties' panes)
        moves 40 bytes on, and each offset with it; the copied pane goes at the end.

        Raises:
            KeyError: If the part has not exactly one property for `source`.
            ValueError: If `pane` is not a part, already has a property for `name`, or its property
                for `source` does more than override a pane of that name.
        """
        k = self.index(pane)
        data = self.sections[k][1]
        if bytes(data[:4]) != b"prt1":
            raise ValueError(f"{pane} is not a part")
        count = struct.unpack_from("<I", data, PART_FIELDS)[0]
        table = [bytearray(data[PROPERTIES + PROPERTY * p : PROPERTIES + PROPERTY * (p + 1)]) for p in range(count)]
        names = [_name(entry, 0, 24) for entry in table]
        if name in names:
            raise ValueError(f"{pane} already has a property {name}")
        if names.count(source) != 1:
            raise KeyError(f"{pane} has {names.count(source)} properties {source}")
        entry = bytearray(table[names.index(source)])
        pane_at, user_at, basic_at = struct.unpack_from("<III", entry, 28)
        if not pane_at or user_at or basic_at:
            raise ValueError(f"{source}: only a property that overrides a pane and nothing else is copied")
        copied = bytearray(data[pane_at : pane_at + struct.unpack_from("<I", data, pane_at + 4)[0]])
        if bytes(copied[:4]) not in PANES or _name(copied, NAME, 24) != source:
            raise ValueError(f"{source}: the pane its property overrides is not one named so")
        copied[NAME : NAME + 24] = _padded(name, 24)
        for each in table:
            for at in (28, 32, 36):
                offset = struct.unpack_from("<I", each, at)[0]
                if offset:
                    struct.pack_into("<I", each, at, offset + PROPERTY)
        end = len(data) + PROPERTY
        pad = -end % 4
        entry[:24] = _padded(name, 24)
        struct.pack_into("<I", entry, 28, end + pad)
        new = bytearray(data[:PROPERTIES]) + b"".join(table) + entry + data[PROPERTIES + PROPERTY * count :]
        new += bytes(pad) + copied
        struct.pack_into("<I", new, PART_FIELDS, count + 1)
        struct.pack_into("<I", new, 4, len(new))
        self.sections[k] = (b"prt1", new)

    # -- groups ------------------------------------------------------------------------------------

    def groups(self) -> dict[str, list[str]]:
        """{group name: its panes}."""
        return {
            _name(data, GROUP_NAME, 34): [
                _name(data, GROUP_PANES + 24 * k, 24) for k in range(struct.unpack_from("<H", data, GROUP_COUNT)[0])
            ]
            for kind, data in self.sections
            if kind == b"grp1"
        }

    def _group(self, name: str) -> int:
        """
        Find a group's section.

        Returns:
            Its index in `sections`.

        Raises:
            KeyError: If not exactly one group has that name.
        """
        found = [
            k for k, (kind, data) in enumerate(self.sections) if kind == b"grp1" and _name(data, GROUP_NAME, 34) == name
        ]
        if len(found) != 1:
            raise KeyError(f"{len(found)} groups named {name}")
        return found[0]

    def add_to_group(self, group: str, pane: str) -> None:
        """
        Add a pane to a group, last.

        Raises:
            ValueError: If the group's section holds more than its names.
        """
        k = self._group(group)
        data = self.sections[k][1]
        count = struct.unpack_from("<H", data, GROUP_COUNT)[0]
        if len(data) != GROUP_PANES + 24 * count:
            raise ValueError(f"group {group} has more after its names than this reads")
        self.index(pane)
        new = bytearray(data) + _padded(pane, 24)
        struct.pack_into("<H", new, GROUP_COUNT, count + 1)
        struct.pack_into("<I", new, 4, len(new))
        self.sections[k] = (b"grp1", new)

    def add_group(self, group: str, panes: list[str], *, like: str) -> None:
        """
        Add a group of these panes, straight after group `like`, a group of the same level.

        Its own fields past the name are `like`'s.

        Raises:
            ValueError: If the layout has a group of that name, or `like` has groups of its own.
        """
        if group in self.groups():
            raise ValueError(f"the layout already has a group named {group}")
        k = self._group(like)
        if k + 1 < len(self.sections) and self.sections[k + 1][0] == b"grs1":
            raise ValueError(f"group {like} has groups of its own: not one to put a group beside")
        for pane in panes:
            self.index(pane)
        data = bytearray(self.sections[k][1][:GROUP_PANES])
        data[GROUP_NAME : GROUP_NAME + 34] = _padded(group, 34)
        struct.pack_into("<H", data, GROUP_COUNT, len(panes))
        for pane in panes:
            data += _padded(pane, 24)
        struct.pack_into("<I", data, 4, len(data))
        self.sections[k + 1 : k + 1] = [(b"grp1", data)]


def mat1_bytes(bodies: list[bytes]) -> bytearray:
    """
    Make a mat1 section of these materials, each straight after the last.

    Returns:
        The section, its kind and size included.

    Raises:
        ValueError: If the materials do not come to whole words.
    """
    out = bytearray(b"mat1" + bytes(4) + struct.pack("<HH", len(bodies), 0) + bytes(4 * len(bodies)))
    for k, body in enumerate(bodies):
        struct.pack_into("<I", out, 0x0C + 4 * k, len(out))
        out += body
    if len(out) % 4:
        raise ValueError("mat1 would not be whole words")
    struct.pack_into("<I", out, 4, len(out))
    return out


def txl1_bytes(names: list[str]) -> bytearray:
    """A txl1 section of these texture names, its kind and size included."""
    out = bytearray(b"txl1" + bytes(4) + struct.pack("<HH", len(names), 0)) + _name_table(names)
    struct.pack_into("<I", out, 4, len(out))
    return out


def part_size(data: bytes) -> tuple[float, float]:
    """
    A layout's own size as a part: the size a part pane of it has at magnify 1.

    That is the last two floats of its `lyt1` section, after whether it is drawn from its middle
    and its screen's width and height.

    Returns:
        The width and height.

    Raises:
        ValueError: If the layout has no `lyt1` section.
    """
    _, sections = _sections(data, b"FLYT")
    for kind, body in sections:
        if kind == b"lyt1":
            return struct.unpack_from("<2f", body, 0x14)
    raise ValueError("no lyt1 section")


def pane_info(data: bytes, name: str) -> tuple[int, int, tuple[float, float], tuple[float, float]]:
    """
    Read one pane of a layout, by name.

    Returns:
        Its flags, its origin, where it stands (x, y) and its size (width, height).
    """
    pane = Layout(data).section(name)
    return pane[8], pane[9], struct.unpack_from("<2f", pane, TRANSLATE), struct.unpack_from("<2f", pane, SIZE)


@dataclass
class Curve:
    """
    One thing an animation changes, key by key.

    Attributes:
        index: Which of several alike it is for, as a material's texture map (0 for a pane's own).
        target: What it changes, by its number in its tag (`SHOWN`, `OPACITY`, `PLACE_X`, ...).
        kind: `STEP` or `HERMITE`.
        keys: Its keys, in order of frame: (frame, value) for steps, (frame, value, slope) for Hermite.
    """

    index: int
    target: int
    kind: int
    keys: list[Key]


@dataclass
class Tag:
    """
    The curves of one kind of change to a pane or material.

    Attributes:
        magic: The kind, four letters (`FLVI`, `FLVC`, `FLPA`, ...).
        curves: Its curves.
    """

    magic: str
    curves: list[Curve]


@dataclass
class Content:
    """
    What an animation does to one pane or material.

    Attributes:
        name: The pane's or material's name.
        kind: `PANE` or `MATERIAL`.
        tags: What it changes, a tag for each kind of change.
    """

    name: str
    kind: int
    tags: list[Tag]


class Animation:
    """
    An animation, its `pai1` read into contents to be changed and written again.

    Attributes:
        head: The file's header.
        pat1: Its `pat1` section, kept as it is.
        frames: How many frames it has.
        loop: Whether it loops.
        textures: The textures its `FLTP` curves pick from, by name.
        contents: What it does to each pane and material, in the file's order.
    """

    def __init__(self, data: bytes) -> None:
        """
        Read the animation's contents.

        Raises:
            ValueError: If it has other sections than `pat1` then `pai1`, a curve of another kind
                than steps or Hermite, or contents that are not laid out the way they are written.
        """
        self.head, sections = _sections(data, b"FLAN")
        kinds = [kind for kind, _ in sections]
        if kinds != [b"pat1", b"pai1"]:
            raise ValueError(f"an animation of sections {kinds}: only pat1 then pai1 is read here")
        self.pat1 = sections[0][1]
        pai = sections[1][1]
        self.frames, self.loop = struct.unpack_from("<HB", pai, 8)
        textures, count, table = struct.unpack_from("<HHI", pai, 0x0C)
        self.textures = [
            _name(pai, 0x14 + struct.unpack_from("<I", pai, 0x14 + 4 * t)[0], 128) for t in range(textures)
        ]
        if table != self._table_at():
            raise ValueError(f"contents table at {table:#x}, not where its textures end ({self._table_at():#x})")
        self.contents: list[Content] = []
        ends = [table + 4 * count]
        for c in range(count):
            at = struct.unpack_from("<I", pai, table + 4 * c)[0]
            tags = []
            for t in range(pai[at + 28]):
                tag_at = at + struct.unpack_from("<I", pai, at + 32 + 4 * t)[0]
                curves = []
                for g in range(pai[tag_at + 4]):
                    curve_at = tag_at + struct.unpack_from("<I", pai, tag_at + 8 + 4 * g)[0]
                    index, target, kind, key_count, keys_at = struct.unpack_from("<BBBxHxxI", pai, curve_at)
                    keys_at += curve_at
                    if kind == HERMITE:
                        keys = [struct.unpack_from("<3f", pai, keys_at + 12 * n) for n in range(key_count)]
                    elif kind == STEP:
                        keys = [struct.unpack_from("<fH", pai, keys_at + 8 * n) for n in range(key_count)]
                    else:
                        raise ValueError(f"curve kind {kind} of {_name(pai, at, 28)}: not read here")
                    curves.append(Curve(index, target, kind, keys))
                    ends.append(keys_at + (12 if kind == HERMITE else 8) * key_count)
                tags.append(Tag(bytes(pai[tag_at : tag_at + 4]).decode(), curves))
            self.contents.append(Content(_name(pai, at, 28), pai[at + 29], tags))
        if max(ends) != len(pai):
            raise ValueError("the contents do not end where the section does")

    def _table_at(self) -> int:
        """Where the contents' table is in `pai1`: after the textures' names."""
        return 0x14 + len(_name_table(self.textures))

    def _pai1(self) -> bytearray:
        """The `pai1` section, from the contents."""
        out = bytearray(b"pai1" + bytes(4))
        out += struct.pack("<HBxHH", self.frames, self.loop, len(self.textures), len(self.contents))
        out += struct.pack("<I", self._table_at())
        out += _name_table(self.textures)
        table = len(out)
        out += bytes(4 * len(self.contents))
        for c, content in enumerate(self.contents):
            at = len(out)
            struct.pack_into("<I", out, table + 4 * c, at)
            out += content.name.encode("latin-1") + bytes(28 - len(content.name))
            out += struct.pack("<BBxx", len(content.tags), content.kind)
            offsets = len(out)
            out += bytes(4 * len(content.tags))
            for t, tag in enumerate(content.tags):
                tag_at = len(out)
                struct.pack_into("<I", out, offsets + 4 * t, tag_at - at)
                out += tag.magic.encode() + struct.pack("<Bxxx", len(tag.curves))
                curve_offsets = len(out)
                out += bytes(4 * len(tag.curves))
                for g, curve in enumerate(tag.curves):
                    curve_at = len(out)
                    struct.pack_into("<I", out, curve_offsets + 4 * g, curve_at - tag_at)
                    out += struct.pack("<BBBxHxxI", curve.index, curve.target, curve.kind, len(curve.keys), 12)
                    for key in curve.keys:
                        out += struct.pack("<3f", *key) if curve.kind == HERMITE else struct.pack("<fHxx", *key)
        struct.pack_into("<I", out, 4, len(out))
        return out

    def data(self) -> bytes:
        """The animation as a file again."""
        return _join(self.head, [(b"pat1", self.pat1), (b"pai1", self._pai1())])

    def frame_count(self, frames: int | None = None) -> int:
        """How many frames the animation has, first changed to `frames` if that is given."""
        if frames is not None:
            self.frames = frames
        return self.frames

    def content(self, name: str) -> Content:
        """
        Find what the animation does to one pane or material.

        Returns:
            Its content.

        Raises:
            KeyError: If not exactly one content has that name.
        """
        found = [content for content in self.contents if content.name == name]
        if len(found) != 1:
            raise KeyError(f"{len(found)} contents named {name}")
        return found[0]

    def _curve(self, name: str, magic: str, target: int) -> Curve:
        """
        Find one curve of a content: the first of its tag `magic` that changes `target`.

        Returns:
            The curve.

        Raises:
            KeyError: If there is none.
        """
        for tag in self.content(name).tags:
            if tag.magic == magic:
                for curve in tag.curves:
                    if curve.target == target:
                        return curve
        raise KeyError(f"{name} has no {magic} target {target}")

    def keys(self, name: str, magic: str, target: int) -> list[Key]:
        """The keys of one curve, to change in place."""
        return self._curve(name, magic, target).keys

    def add_pane(self, name: str, tags: list[tuple[str, int, int, list[Key]]]) -> None:
        """
        Add what the animation does to a pane: [(tag, target, curve kind, keys)], a curve each.

        Raises:
            ValueError: If the animation already does something to that pane.
        """
        if any(content.name == name for content in self.contents):
            raise ValueError(f"the animation already has {name}")
        made = [Tag(magic, [Curve(0, target, kind, list(keys))]) for magic, target, kind, keys in tags]
        self.contents.append(Content(name, PANE, made))

    def copy_content(self, name: str, new: str) -> Content:
        """
        Make the animation do to `new` what it does to `name`, a pane or a material.

        Every curve's keys in the copy are a list of its own.

        Returns:
            The new content.

        Raises:
            ValueError: If the animation already does something to `new`, or its name is too long.
        """
        if any(content.name == new for content in self.contents):
            raise ValueError(f"the animation already has {new}")
        if len(new) > 27:
            raise ValueError(f"{new} is longer than a content name may be")
        old = self.content(name)
        tags = [
            Tag(tag.magic, [Curve(curve.index, curve.target, curve.kind, list(curve.keys)) for curve in tag.curves])
            for tag in old.tags
        ]
        copy = Content(new, old.kind, tags)
        self.contents.append(copy)
        return copy

    def value(self, name: str, magic: str, target: int, frame: float) -> float:
        """
        Work out a curve's value at a frame, as the library does.

        Between two keys a Hermite curve runs smoothly and a step curve holds the earlier key's
        value. At a frame two keys share the later one counts, and before the first key and after
        the last the value is held.

        Returns:
            The value.

        Raises:
            ValueError: If the curve's keys are not in order of frame.
        """
        curve = self._curve(name, magic, target)
        keys = curve.keys
        if frame < keys[0][0]:
            return keys[0][1]
        if frame >= keys[-1][0]:
            return keys[-1][1]
        for a, b in itertools.pairwise(keys):
            if a[0] <= frame < b[0]:
                if curve.kind == STEP:
                    return a[1]
                t = (frame - a[0]) / (b[0] - a[0])
                span = b[0] - a[0]
                h1, h2 = 2 * t**3 - 3 * t**2 + 1, -2 * t**3 + 3 * t**2
                h3, h4 = t**3 - 2 * t**2 + t, t**3 - t**2
                return h1 * a[1] + h2 * b[1] + (h3 * a[2] + h4 * b[2]) * span
        raise ValueError(f"the keys of {name}'s {magic} curve {target} are not in order of frame")
