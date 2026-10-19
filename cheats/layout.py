"""
The layouts: the Cheats tab in the pause menu, and columns for Purple and White in the Onion menu.

Three of the game's files are made again from your own copies of them:

* `lyt/common.szs` holds the layouts of the game's windows. The pause menu's Other Settings page
  (`PauseWindow_00`) gets a fourth tab, Cheats: a bubble beside the game's three, and under it rows
  of buttons and the game's own scroll bar (`pause_window`). The Onion menu (`OnyonWindow_00`) gets
  columns 6 and 7, for the sixth and seventh types listed: Purple and White (`onion_layout`).
* `lyt/parts.szs` holds the parts the layouts are built of. The Onion menu's "all types" overlay
  gets a Purple and a White icon and number (`onion_parts`).
* `command/lyt_command_table.szs` gives the buttons their sounds. The new buttons get copies of the
  records of the buttons they are copies of (`command_table`).

The new panes do nothing of themselves: the menu's code finds them by name and runs them, as the
game's code runs its own. A layout archive is 60 to 70 MB once decompressed, so it is not compressed
again: the stock stream is kept but around the files that change (`yaz0.splice`), and every file in
the archive keeps the boundary it starts on (`sarc.rebuild_aligned`).
"""

from __future__ import annotations

import contextlib
import functools
import logging
import struct

from typing import TYPE_CHECKING

from cheats.errors import BuildError
from cheats.formats import bflyt, sarc, yaz0
from cheats.rows import ROWS, VISIBLE, Action, Row, columns

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from cheats.romfs import Mod, RomFs

logger = logging.getLogger(__name__)

LAYOUT_ARCHIVE, LAYOUT_INNER = "lyt/common.szs", "common.arc"
PARTS_ARCHIVE, PARTS_INNER = "lyt/parts.szs", "parts.arc"
COMMAND_ARCHIVE, COMMAND_FILE = "command/lyt_command_table.szs", "sound_table.txt"

# -- the Cheats tab -------------------------------------------------------------------------------

PAUSE_LAYOUT = "blyt/PauseWindow_00.bflyt"
SETTING_CHANGE = "anim/PauseWindow_00_SettingChange.bflan"  # shows the rows of the tab whose number is its frame
TAB_ROWS = "N_SelectionD_00"  # the tab's rows, beside the game's three tabs' (N_SelectionA_00 to C)
# Four bubbles where there were three, smaller: the game's are 0.8 at 370 apart, a gap of 72 of
# their own units with one grown to 1.1 as the cursor is on it, and 0.6 at 300 apart keeps that gap.
# The tab's bubble, Pa_MenuBtn_03, is a copy of More's (Pa_MenuBtn_02), and stands before it.
BUBBLES = (("Pa_MenuBtn_00", -450.0), ("Pa_MenuBtn_01", -150.0), ("Pa_MenuBtn_03", 150.0), ("Pa_MenuBtn_02", 450.0))
BUBBLE_SCALE = 0.6
ROW_Y = (154.0, 54.0, -46.0, -146.0)  # where the rows stand, as the game's
CHEATS_FRAME = 3.0  # SettingChange's frame for the tab: its number
# A row of the tab is a copy of Gyro Function's row (N_CRow_00): its Off button (Pa_CBtn_01) and
# its On button (Pa_CBtn_00) become columns 0 and 1, and the other columns are copies of column 1.
# The two differ only in their names, places and messages, and the menu's code writes every
# button's text, so the messages never show. A row's buttons fill the room from just past where the
# labels end (every row's name at its longest ends before x -135, in the game's font at its size)
# to where the game's right button ends, each column a button scaled to leave GAP between
# neighbours, and no larger than the game's own.
BUTTONS_FROM, BUTTONS_TO = -135.0, 497.0
BUTTON_WIDTH = 390.0  # a button part's widest pane (its shadow), unscaled
BUTTON_SCALE = 0.55  # the game's own buttons'
GAP = 18.0
ROW_BUTTONS_AT = -20.0  # where a row's pane of buttons stands in the row, as the game's
# The faint dark band behind a row's label (W_ShadowR, a window pane standing from its left edge at
# x -520, 300 wide at scale 1.5): the game's reaches x -70, past where these rows' buttons begin.
# These rows' end SHADOW_GAP short of their first button, still past where the labels end.
SHADOW_GAP = 10.0
FIRST_SHADOW = 9  # the game's bands are W_ShadowR_00 to _08: the rows' are numbered on from there
# The scroll bar is the game's own part (PaScrollBar_00, the badges menu's), its track from the
# first row's middle to the last's, at the right of the rows: between the last column, which ends at
# x 488, and the window's frame at x 560. Its control is a "Locator", of which the game makes
# nothing, so it is no button and the cursor never reaches it. Placed at magnify 1, its panes are as
# its file has them; the menu's code sizes the track and the thumb and places the arrows, as the
# game's own lists move their thumbs.
SCROLL_PART, SCROLL_PANE = "PaScrollBar_00", "Pa_ScrollBar_00"
SCROLL_X = 530.0
SCROLL_Y = (ROW_Y[0] + ROW_Y[-1]) / 2
TRACK = ROW_Y[0] - ROW_Y[-1]
ARROW_GAP = 4.0  # between the track's end and an arrow
THUMB_LEAST = 36.0  # the thumb's window frame is 14 each end

# -- columns 6 and 7 of the Onion menu ------------------------------------------------------------
#
# The Onion window has five type columns and "all", and its code has room for no more. Columns 6
# and 7 are copies of column 4 (N_PikBtn_04 and all under it) that the menu's code runs itself, as
# the game runs its own. Each copy's arrows get materials of their own, since their colour is
# animated by type, and the copy gets the groups the game binds a column's animations through
# (G_ArrowColor_0n, G_ArrowLoopT_0n, G_ArrowLoopD_0n). A number on screen is a counter, which hides
# its text box and draws in digits of its own the value its text's tag names, or an int it is
# pointed at: the copies' numbers keep column 5's messages, and the menu's code points their
# counters at ints of its own. The Number animation, which places the columns by how many types are
# listed (its frame is the count less one), gets frames 5 and 6 for six and seven types. The "all"
# overlay's two parts get numbers 5 and 6 (`onion_parts`), and the window's properties for those
# parts give them messages, copies of number 4's.

ONION_LAYOUT = "blyt/OnyonWindow_00.bflyt"
ONION_ANIMATIONS = ("Number", "Color", "ArrowLoop", "ArrowIn", "ArrowOut", "AllBtnInOut")  # those that reach a column
GAME_COLUMNS = 5  # the game's type columns; its sixth record is "all"
NEW_COLUMNS = (5, 6)  # the mod's, counted from 0: columns 6 and 7 on screen
ALL_PARTS = ("Pa_AllBtnTop_00", "Pa_AllBtnDown_00")  # the "all" overlay's parts, in the window
# Where things stand for six and seven types (Number's frames 5 and 6; frames 0 to 4 are the
# game's): the columns' x; the buttons' scale, the game's being 0.8 from two types on, its round
# buttons 196 across at scale 1, so that its five just touch at 155 apart, and six and seven touch
# as closely; OK's and Back's x (the game's at five: 495.8 and -470); the "all" box's width (763).
COLUMN_X = {6: (-335.0, -201.0, -67.0, 67.0, 201.0, 335.0), 7: (-348.0, -232.0, -116.0, 0.0, 116.0, 232.0, 348.0)}
COLUMN_SCALE = {6: 0.69, 7: 0.6}
OK_X = {6: 530.0, 7: 530.0}
BACK_X = {6: -490.0, 7: -490.0}
ALL_BOX_W = {6: 820.0, 7: 830.0}
GAME_SPAN = 620.0  # the game's five columns, from the first's middle to the last's
# Each column has a second pair of glowing arrows whose colour is fixed by its place, not animated
# (P_ArrowOnOffT_06 to _10: Red's, Rock's, Yellow's, Winged's, Blue's). The new columns' are white,
# as Rock's are: the type a column holds varies with how many are listed.
GLOW = (0xFF, 0xFF, 0xFF, 0xFF)

# The parts of the "all" overlay: PaOnyonPikAllBtn_00 above, of Onion tops, and _01 below, of
# Pikmin. Each has an icon (N_Pik<colour>_00, fixed to a type) and a number (Pa_OniyonNumber_0p,
# the p-th column's) for each of five types, placed by its own Number animation (its frame is the
# count less two, for two to five types). They get a Purple and a White icon, numbers 5 and 6, and
# frames 4 and 5 for six and seven types. There is no Onion top for Purple or White, so theirs above
# are Blue's, as on the buttons (whose parts are the game's: the upper button shows the Onion top of
# its column's type, and has textures for the five Onions only); the Pikmin below are their own.
# With Story Purple And White on, the menu's code moves each listed type's icon over its column's
# number: the icons stand in the order the game lists types when Purple and White are not about.
OVERLAY_TOP, OVERLAY_BOTTOM = "PaOnyonPikAllBtn_00", "PaOnyonPikAllBtn_01"
TYPE_ICONS = (
    "N_PikRed_00",
    "N_PikRock_00",
    "N_PikYellow_00",
    "N_PikPink_00",
    "N_PikBlue_00",
    "N_PikPurple_00",
    "N_PikWhite_00",
)
NEW_ICONS = TYPE_ICONS[5:]
PORTRAITS = ("nh_PikPurple_00^q", "nh_PikWhite_00^q")  # Purple and White Pikmin, among the parts' textures
OVERLAY_SHRINK = 290.0 / 310.0  # the icons stand closer than the columns: at five, 290 from the middle to the last
OVERLAY_STEP = 145.0  # the icons apart at five types

# -- the buttons' sounds --------------------------------------------------------------------------
#
# The sounds of a layout's buttons are records of the command table, by the layout's and the
# button's names: "PauseWindow_00/down/Pa_CBtn_00" plays a sound as that button's "down" animation
# starts, which is a press. Buttons of new names have none, so the new buttons get copies of the
# records of the buttons they are copies of.

ONION_RECORDS = ("Pa_PikBtnT_04", "Pa_PikBtnD_04", "Pa_NunStick_04")  # column 4's, copied for columns 6 and 7


def build(romfs: RomFs, mod: Mod, rows: tuple[Row | Action, ...] = ROWS) -> None:
    """
    Write the three files into the mod folder.

    Args:
        romfs: The game's files.
        mod: The mod folder.
        rows: The rows of the Cheats tab.
    """
    with _reading(PARTS_ARCHIVE):
        scroll = bflyt.part_size(_scroll_part(romfs))

    def common(files: dict[str, bytes]) -> dict[str, bytes]:
        pause, change = pause_window(files[PAUSE_LAYOUT], files[SETTING_CHANGE], scroll, rows)
        return {PAUSE_LAYOUT: pause, SETTING_CHANGE: change, **onion_layout(files)}

    with _reading(LAYOUT_ARCHIVE):
        raw = romfs.read(LAYOUT_ARCHIVE)
        data = _rebuilt(LAYOUT_ARCHIVE, raw, yaz0.decompress(raw), LAYOUT_INNER, common)
    mod.write(LAYOUT_ARCHIVE, data)
    logger.info("  %s: the Cheats tab, and the Onion menu's columns 6 and 7", LAYOUT_ARCHIVE)
    with _reading(PARTS_ARCHIVE):
        raw, plain = _parts(romfs)
        data = _rebuilt(PARTS_ARCHIVE, raw, plain, PARTS_INNER, onion_parts)
    mod.write(PARTS_ARCHIVE, data)
    logger.info("  %s: Purple and White in the Onion menu's overlay", PARTS_ARCHIVE)
    with _reading(COMMAND_ARCHIVE):
        data, added = command_table(romfs.read(COMMAND_ARCHIVE), rows)
    mod.write(COMMAND_ARCHIVE, data)
    logger.info("  %s: %d records for the new buttons' sounds", COMMAND_ARCHIVE, added)


def scroll_bar(romfs: RomFs, rows: tuple[Row | Action, ...] = ROWS) -> dict[str, float]:
    """
    Work out the scroll bar's sizes and places, for the menu's code, from the part's own file.

    The menu's code sizes the track and the thumb and moves the thumb and the arrows. An arrow's y
    counts from its parent's top or bottom edge, as its origin says, and the part's root stands
    from its middle.

    Returns:
        `track`: the track's height. `shown`: whether there are more rows than the page shows.
        `thumb`: the thumb's height. `step`: how far it moves for a row. `top`: its y with the list
        at its top. `up` and `down`: the arrows' y.

    Raises:
        BuildError: If the part's root or arrows do not stand as this takes them to.
    """
    with _reading(PARTS_ARCHIVE):
        part = _scroll_part(romfs)
        _, root_origin, _, (_, root_h) = bflyt.pane_info(part, "RootPane")
        arrows = {arrow: bflyt.pane_info(part, arrow) for arrow in ("Pa_Arrow_00", "Pa_Arrow_01")}
    if root_origin & 0x0F:
        raise BuildError("the scroll bar's root does not stand from its middle")
    out = {"track": TRACK, "shown": len(rows) > VISIBLE}
    out["thumb"] = max(THUMB_LEAST, TRACK * min(VISIBLE, len(rows)) / len(rows))
    out["step"] = (TRACK - out["thumb"]) / (len(rows) - VISIBLE) if len(rows) > VISIBLE else 0.0
    out["top"] = TRACK / 2 - out["thumb"] / 2
    for arrow, sign, key in (("Pa_Arrow_00", 1, "up"), ("Pa_Arrow_01", -1, "down")):
        _, origin, _, (_, height) = arrows[arrow]
        edge = {1: 0.5, 2: -0.5}.get(origin >> 6)  # its parent's top or bottom edge
        if edge is None or origin & 0x0F or (edge > 0) != (sign > 0):
            raise BuildError(f"the scroll bar's {arrow} does not stand from its {'top' if sign > 0 else 'bottom'} edge")
        out[key] = sign * (TRACK / 2 + ARROW_GAP + height / 2) - edge * root_h
    return out


# -- the stock files ------------------------------------------------------------------------------


@contextlib.contextmanager
def _reading(name: str) -> Iterator[None]:
    """Turn an error of the formats, as one of the game's files is read and changed, into one that names it."""
    try:
        yield
    except BuildError:
        raise
    except (KeyError, ValueError, IndexError, struct.error) as error:  # it lacks a pane, a file or a record
        what = error.args[0] if isinstance(error, KeyError) and error.args else error
        raise BuildError(f"{name} is not the game's file the mod is made from: {what}") from error


@functools.lru_cache(maxsize=1)
def _parts(romfs: RomFs) -> tuple[bytes, bytes]:
    """The game's `lyt/parts.szs` and the archive in it, decompressed once for the scroll bar and the overlay."""
    raw = romfs.read(PARTS_ARCHIVE)
    return raw, yaz0.decompress(raw)


def _scroll_part(romfs: RomFs) -> bytes:
    """The scroll bar part's layout, from the game's `lyt/parts.szs`."""
    _, plain = _parts(romfs)
    start, end = sarc.Sarc(plain).span(PARTS_INNER)
    inner = sarc.Sarc(plain[start:end])
    start, end = inner.span(f"blyt/{SCROLL_PART}.bflyt")
    return inner.data[start:end]


def _rebuilt(
    name: str,
    raw: bytes,
    plain: bytes,
    inner_name: str,
    change: Callable[[dict[str, bytes]], dict[str, bytes]],
) -> bytes:
    """
    Make one of the game's `.szs` archives again, some of the files of the archive inside it changed.

    The archive holds one file, `inner_name`, itself an archive. Each of its files keeps the
    boundary it starts on, and the stock stream is spliced, not compressed again.

    Args:
        name: The archive's name, for an error.
        raw: The stock `.szs` file.
        plain: What it decompresses to.
        inner_name: The archive inside it.
        change: Given the inner archive's files by name, the new bytes of those to change.

    Returns:
        The new `.szs` file.

    Raises:
        BuildError: If it does not decompress to the archive meant.
    """
    start, end = sarc.Sarc(plain).span(inner_name)
    inner = plain[start:end]
    new_inner, inner_edits = sarc.rebuild_aligned(inner, change(sarc.Sarc(inner).files()))
    new = sarc.replace(plain, inner_name, new_inner)
    edits = yaz0.same_length_edits(plain[:start], new[:start])
    edits += [(start + lo, start + hi, body) for lo, hi, body in inner_edits]
    szs = yaz0.splice(raw, plain, edits)
    if yaz0.decompress(szs) != new:
        raise BuildError(f"the new {name} does not decompress to what was meant")
    return szs


# -- the Cheats tab -------------------------------------------------------------------------------


def column_place(c: int, rows: tuple[Row | Action, ...]) -> tuple[float, float]:
    """Where column `c`'s button stands in its row's pane of buttons (x), and its scale."""
    step = (BUTTONS_TO - BUTTONS_FROM) / columns(rows)
    scale = min(BUTTON_SCALE, (step - GAP) / BUTTON_WIDTH)
    return BUTTONS_FROM + step * (c + 0.5) - ROW_BUTTONS_AT, scale


def shadow_width(lyt: bflyt.Layout, rows: tuple[Row | Action, ...]) -> float:
    """The width, unscaled, of a row's label band that ends `SHADOW_GAP` before its first button."""
    x, scale = lyt.position("W_ShadowR_04")[0], lyt.scale("W_ShadowR_04")[0]
    first_x, first_scale = column_place(0, rows)
    first = first_x + ROW_BUTTONS_AT - BUTTON_WIDTH * first_scale / 2
    return (first - SHADOW_GAP - x) / scale


def pause_window(
    layout: bytes,
    change: bytes,
    scroll: tuple[float, float],
    rows: tuple[Row | Action, ...],
) -> tuple[bytes, bytes]:
    """
    Add the Cheats tab to the pause window's layout and to its SettingChange animation.

    Args:
        layout: The stock layout.
        change: The stock animation.
        scroll: The scroll bar part's own size (`bflyt.part_size`).
        rows: The rows of the tab.

    Returns:
        The new layout and the new animation.
    """
    lyt = bflyt.Layout(layout)
    lyt.copy("Pa_MenuBtn_02", {"Pa_MenuBtn_02": "Pa_MenuBtn_03"}, after="Pa_MenuBtn_02")
    for name, x in BUBBLES:
        lyt.move(name, x=x)
        lyt.scale(name, BUBBLE_SCALE)
    lyt.copy("N_SelectionC_00", {"N_SelectionC_00": TAB_ROWS}, after="N_SelectionC_00", alone=True)
    count = columns(rows)
    for r in range(min(VISIBLE, len(rows))):
        shadow = f"W_ShadowR_{FIRST_SHADOW + r:02d}"
        renames = {
            "N_CRow_00": f"N_DRow_{r:02d}",
            "N_CBtn_00": f"N_DBtn_{r:02d}",
            "Pa_CBtn_01": f"Pa_DBtn_{r}0",
            "Pa_CBtn_00": f"Pa_DBtn_{r}1",
            "W_ShadowR_04": shadow,
            "T_CItem_00": f"T_DItem_{r:02d}",
        }
        lyt.copy("N_CRow_00", renames, into=TAB_ROWS)
        lyt.move(f"N_DRow_{r:02d}", y=ROW_Y[r])
        lyt.size(shadow, w=shadow_width(lyt, rows))
        for c in range(2, count):
            lyt.copy(f"Pa_DBtn_{r}1", {f"Pa_DBtn_{r}1": f"Pa_DBtn_{r}{c}"}, after=f"Pa_DBtn_{r}{c - 1}")
        for c in range(count):
            x, scale = column_place(c, rows)
            lyt.move(f"Pa_DBtn_{r}{c}", x=x)
            lyt.scale(f"Pa_DBtn_{r}{c}", scale)
    lyt.add_part(SCROLL_PANE, SCROLL_PART, scroll, into=TAB_ROWS, like="Pa_CBtn_00", x=SCROLL_X, y=SCROLL_Y)
    lyt.add_to_group("G_SettingChange_00", TAB_ROWS)
    anim = bflyt.Animation(change)
    # More's rows are shown from frame 2 on: hidden again at the tab's frame, where the tab's are shown
    anim.keys("N_SelectionA_00", "FLVC", bflyt.OPACITY).extend(((CHEATS_FRAME, 255.0, 0.0), (CHEATS_FRAME, 0.0, 0.0)))
    shown, opacity = [(0.0, 1)], [(0.0, 0.0, 0.0), (CHEATS_FRAME, 0.0, 0.0), (CHEATS_FRAME, 255.0, 0.0)]
    anim.add_pane(TAB_ROWS, [("FLVI", bflyt.SHOWN, bflyt.STEP, shown), ("FLVC", bflyt.OPACITY, bflyt.HERMITE, opacity)])
    return lyt.data(), anim.data()


# -- columns 6 and 7 of the Onion menu ------------------------------------------------------------


def _onion_animation(name: str) -> str:
    """The path of one of the Onion window's animations."""
    return f"anim/OnyonWindow_00_{name}.bflan"


def column_renames(c: int) -> dict[str, str]:
    """Column 4's panes (N_PikBtn_04 and all under it), and their names in column `c` (5 or 6)."""
    return {
        "N_PikBtn_04": f"N_PikBtn_{c:02d}",
        "Pa_PikBtnT_04": f"Pa_PikBtnT_{c:02d}",
        "N_AllBtnInOut_00": f"N_AllBtnInOut_{c + 1:02d}",
        "N_ArrowInOut_04": f"N_ArrowInOut_{c + 1:02d}",
        "P_ArrowT_04": f"P_ArrowT_{c + 1:02d}",
        "P_ArrowOnOffT_04": f"P_ArrowOnOffT_{2 * c + 1:02d}",
        "P_ArrowOnOffT_10": f"P_ArrowOnOffT_{2 * c + 2:02d}",
        "P_ArrowD_04": f"P_ArrowD_{c + 1:02d}",
        "P_ArrowOnOffD_04": f"P_ArrowOnOffD_{2 * c + 1:02d}",
        "P_ArrowOnOffD_10": f"P_ArrowOnOffD_{2 * c + 2:02d}",
        "Pa_NunStick_04": f"Pa_NunStick_{c:02d}",
        "Pa_PikBtnD_04": f"Pa_PikBtnD_{c:02d}",
        "B_PikBtn_04": f"B_PikBtn_{c:02d}",
    }


def extend_steps(keys: list[bflyt.Key], values: dict[int, float]) -> None:
    """
    Carry a curve of steps on to later frames, a value for each ({frame: value}), in place.

    A Hermite curve gets two keys at each frame it changes, the later holding from there, as the
    game's Number animations are made; a step curve gets one key a change.
    """
    if len(keys[0]) == 3:
        frame, value, _ = keys[-1]
        keys[-1] = (frame, value, 0.0)
        for at in sorted(values):
            keys.extend(((float(at), keys[-1][1], 0.0), (float(at), float(values[at]), 0.0)))
    else:
        keys.extend((float(at), int(values[at])) for at in sorted(values))


def onion_number(anim: bflyt.Animation) -> None:
    """Give the window's Number animation frames 5 and 6, for six and seven types, in place."""
    for k in range(GAME_COLUMNS):
        extend_steps(anim.keys(f"N_PikBtn_{k:02d}", "FLPA", bflyt.PLACE_X), {5: COLUMN_X[6][k], 6: COLUMN_X[7][k]})
        for button in (f"Pa_PikBtnT_{k:02d}", f"Pa_PikBtnD_{k:02d}"):
            for target in (bflyt.SCALE_X, bflyt.SCALE_Y):
                extend_steps(anim.keys(button, "FLPA", target), {5: COLUMN_SCALE[6], 6: COLUMN_SCALE[7]})
        extend_steps(anim.keys(f"B_PikBtn_{k:02d}", "FLPA", bflyt.SCALE_X), {5: COLUMN_SCALE[6], 6: COLUMN_SCALE[7]})
    extend_steps(anim.keys("Pa_OkBtn_00", "FLPA", bflyt.PLACE_X), {5: OK_X[6], 6: OK_X[7]})
    extend_steps(anim.keys("Pa_BackBtn_00", "FLPA", bflyt.PLACE_X), {5: BACK_X[6], 6: BACK_X[7]})
    extend_steps(anim.keys("B_PikBtnAll_00", "FLPA", bflyt.WIDTH), {5: ALL_BOX_W[6], 6: ALL_BOX_W[7]})
    for c in NEW_COLUMNS:
        renames = column_renames(c)
        for old in ("Pa_PikBtnT_04", "Pa_PikBtnD_04", "B_PikBtn_04"):
            anim.copy_content(old, renames[old])
        # placed at the frames for as many types as reach it, shown from the first of them
        x = [COLUMN_X[n][c] for n in (6, 7) if c < n]
        place = [(float(c), x[0], 0.0), *([(6.0, x[0], 0.0), (6.0, x[1], 0.0)] if len(x) > 1 else [])]
        shown = [(0.0, 0), (float(c), 1)]
        anim.add_pane(
            renames["N_PikBtn_04"],
            [("FLPA", bflyt.PLACE_X, bflyt.HERMITE, place), ("FLVI", bflyt.SHOWN, bflyt.STEP, shown)],
        )
    anim.frame_count(6)


def onion_layout(files: dict[str, bytes]) -> dict[str, bytes]:
    """
    Give the Onion window columns 6 and 7.

    Returns:
        {path in the archive: new bytes} of its layout and the animations that reach a column's panes.
    """
    lyt = bflyt.Layout(files[ONION_LAYOUT])
    anims = {name: bflyt.Animation(files[_onion_animation(name)]) for name in ONION_ANIMATIONS}
    after = "N_PikBtn_04"
    groups = lyt.groups()
    for c in NEW_COLUMNS:
        renames = column_renames(c)
        lyt.copy("N_PikBtn_04", renames, after=after, materials=True)
        after = renames["N_PikBtn_04"]
        for old in ("P_ArrowOnOffT_10", "P_ArrowOnOffD_10"):
            lyt.material_colours(lyt.material_index(renames[old]), white=GLOW)
        for stem in ("G_ArrowColor", "G_ArrowLoopT", "G_ArrowLoopD"):
            panes = [renames[pane] for pane in groups[f"{stem}_04"]]
            lyt.add_group(f"{stem}_{c:02d}", panes, like=f"{stem}_{c - 1:02d}")
        for group, panes in (
            ("G_Number_00", ("N_PikBtn_04", "Pa_PikBtnD_04", "Pa_PikBtnT_04", "B_PikBtn_04")),
            ("G_ArrowInOut_00", ("N_ArrowInOut_04",)),
            ("G_AllBtnInOut_00", ("N_AllBtnInOut_00",)),
        ):
            for pane in panes:
                lyt.add_to_group(group, renames[pane])
        for old in ("P_ArrowT_04", "P_ArrowOnOffT_04", "P_ArrowD_04", "P_ArrowOnOffD_04"):  # their colour by type
            anims["Color"].copy_content(old, renames[old])
        for old in (
            "P_ArrowT_04",
            "P_ArrowD_04",
            "P_ArrowOnOffT_04",
            "P_ArrowOnOffD_04",
            "P_ArrowOnOffT_10",
            "P_ArrowOnOffD_10",
        ):
            anims["ArrowLoop"].copy_content(old, renames[old])
        for name in ("ArrowIn", "ArrowOut"):
            anims[name].copy_content("N_ArrowInOut_04", renames["N_ArrowInOut_04"])
        anims["AllBtnInOut"].copy_content("N_AllBtnInOut_00", renames["N_AllBtnInOut_00"])
    for part in ALL_PARTS:  # the overlay's numbers 5 and 6 given messages, as 0 to 4 are: number 4's
        for p in NEW_COLUMNS:
            lyt.add_property(part, "Pa_OniyonNumber_04", f"Pa_OniyonNumber_{p:02d}")
    onion_number(anims["Number"])
    return {ONION_LAYOUT: lyt.data(), **{_onion_animation(name): anim.data() for name, anim in anims.items()}}


def overlay_x(n: int) -> tuple[float, ...]:
    """Where the overlay's icons and numbers stand for `n` types (six or seven), in order."""
    return tuple(round(x * OVERLAY_SHRINK, 1) for x in COLUMN_X[n])


def overlay_scale(n: int) -> float:
    """The overlay's icons' and numbers' scale for `n` types: their spacing over the game's at five."""
    return round((COLUMN_X[n][1] - COLUMN_X[n][0]) * OVERLAY_SHRINK / OVERLAY_STEP, 3)


def overlay_part(layout: bytes, number: bytes, *, portraits: bool) -> tuple[bytes, bytes]:
    """
    Give one of the "all" overlay's parts a Purple and a White icon and number.

    Args:
        layout: The part's stock layout.
        number: Its stock Number animation.
        portraits: Whether its icons are Pikmin, so that Purple's and White's show their own
            pictures; else they are Onion tops, and Blue's.

    Returns:
        The new layout and the new animation.
    """
    lyt, anim = bflyt.Layout(layout), bflyt.Animation(number)
    x6, x7 = overlay_x(6), overlay_x(7)
    s6, s7 = overlay_scale(6), overlay_scale(7)
    after, after_number = "N_PikBlue_00", "Pa_OniyonNumber_04"
    textures = [lyt.add_texture(name) for name in PORTRAITS] if portraits else [None, None]
    for k, colour in enumerate(("Purple", "White")):
        icon = f"N_Pik{colour}_00"
        renames = {"N_PikBlue_00": icon} | {pane: pane.replace("Blue", colour) for pane in lyt.children("N_PikBlue_00")}
        lyt.copy("N_PikBlue_00", renames, after=after)
        after = icon
        for old, new in renames.items():  # each picture a material of its own
            if old != "N_PikBlue_00":
                lyt.set_material(new, lyt.copy_material(lyt.material_of(new), new, texture=textures[k]))
        name = f"Pa_OniyonNumber_{5 + k:02d}"  # its message, as 0 to 4's, is the window's property
        lyt.copy("Pa_OniyonNumber_04", {"Pa_OniyonNumber_04": name}, after=after_number)
        after_number = name
        for pane in (icon, name):
            lyt.add_to_group("G_Number_00", pane)
    # The Number animation's frames 4 and 5 (six and seven types). The widths grow by as much as the
    # columns' span grows over five's.
    widen = {4: COLUMN_X[6][-1] - COLUMN_X[6][0] - GAME_SPAN, 5: COLUMN_X[7][-1] - COLUMN_X[7][0] - GAME_SPAN}
    for content in anim.contents:
        for tag in content.tags:
            for curve in tag.curves:
                if tag.magic == "FLPA" and curve.target == bflyt.WIDTH:
                    at5 = anim.value(content.name, tag.magic, curve.target, 3.0)
                    extend_steps(curve.keys, {4: at5 + widen[4], 5: at5 + widen[5]})
    order = list(TYPE_ICONS[:5])  # the animation alone: the game's order, then Purple and White
    places = {6: [*order[:4], *NEW_ICONS], 7: [*order, *NEW_ICONS]}
    for p in range(5):
        extend_steps(anim.keys(f"Pa_OniyonNumber_{p:02d}", "FLPA", bflyt.PLACE_X), {4: x6[p], 5: x7[p]})
    for icon in order:
        x = {n: (x6 if n == 6 else x7)[places[n].index(icon)] for n in (6, 7) if icon in places[n]}
        extend_steps(anim.keys(icon, "FLPA", bflyt.PLACE_X), {4: x.get(6, x[7]), 5: x[7]})
    extend_steps(anim.keys("N_PikBlue_00", "FLVI", bflyt.SHOWN), {4: 0, 5: 1})
    for k, icon in enumerate(NEW_ICONS):
        p6, p7 = places[6].index(icon), places[7].index(icon)
        place = [(4.0, x6[p6], 0.0), (5.0, x6[p6], 0.0), (5.0, x7[p7], 0.0)]
        anim.add_pane(
            icon,
            [("FLPA", bflyt.PLACE_X, bflyt.HERMITE, place), ("FLVI", bflyt.SHOWN, bflyt.STEP, [(0.0, 0), (4.0, 1)])],
        )
        if k == 0:
            place, shown = [(4.0, x6[5], 0.0), (5.0, x6[5], 0.0), (5.0, x7[5], 0.0)], [(0.0, 0), (4.0, 1)]
        else:
            place, shown = [(5.0, x7[6], 0.0)], [(0.0, 0), (5.0, 1)]
        anim.add_pane(
            f"Pa_OniyonNumber_{5 + k:02d}",
            [("FLPA", bflyt.PLACE_X, bflyt.HERMITE, place), ("FLVI", bflyt.SHOWN, bflyt.STEP, shown)],
        )
    for name in [*TYPE_ICONS, *(f"Pa_OniyonNumber_{p:02d}" for p in range(7))]:
        flpa = next(tag for tag in anim.content(name).tags if tag.magic == "FLPA")
        for target in (bflyt.SCALE_X, bflyt.SCALE_Y):  # 1 up to five types, then shrunk
            scale = [(0.0, 1.0, 0.0), (4.0, 1.0, 0.0), (4.0, s6, 0.0), (5.0, s6, 0.0), (5.0, s7, 0.0)]
            flpa.curves.append(bflyt.Curve(0, target, bflyt.HERMITE, scale))
    anim.frame_count(5)
    return lyt.data(), anim.data()


def onion_parts(files: dict[str, bytes]) -> dict[str, bytes]:
    """
    Give the "all" overlay's two parts Purple and White.

    Returns:
        {path in the archive: new bytes} of the parts' layouts and their Number animations.
    """
    out = {}
    for part in (OVERLAY_TOP, OVERLAY_BOTTOM):
        layout, number = f"blyt/{part}.bflyt", f"anim/{part}_Number.bflan"
        out[layout], out[number] = overlay_part(files[layout], files[number], portraits=part == OVERLAY_BOTTOM)
    return out


# -- the buttons' sounds --------------------------------------------------------------------------


def command_records(text: str) -> tuple[list[str], list[tuple[str, int, int]]]:
    """
    Read the command table's records.

    A record opens with a line "# (OBJ) ..." and runs to the brace that closes the one after it. Its
    name is the line after "# command name", like "PauseWindow_00/down/Pa_CBtn_00" (the game's own
    table has six names twice).

    Returns:
        The table's lines (split on its own line ending), and (name, first line, end line) of each
        record, in order.

    Raises:
        BuildError: If a record does not open with a brace, does not close, or has not one name.
    """
    lines = text.split("\r\n")
    out, k = [], 0
    while k < len(lines):
        if not lines[k].startswith("\t# (OBJ)"):
            k += 1
            continue
        if lines[k + 1] != "\t{":
            raise BuildError(f"{COMMAND_FILE}: the record at line {k + 1} does not open with a brace")
        depth, end = 0, None
        for j in range(k + 1, len(lines)):
            if lines[j].strip() == "{":
                depth += 1
            elif lines[j].strip() == "}":
                depth -= 1
                if not depth:
                    end = j + 1
                    break
        if end is None:
            raise BuildError(f"{COMMAND_FILE}: the record at line {k + 1} does not close")
        names = [lines[j].strip().strip('"') for j in range(k, end) if lines[j - 1].strip() == "# command name"]
        if len(names) != 1:
            raise BuildError(f"{COMMAND_FILE}: the record at line {k + 1} has {len(names)} command names")
        out.append((names[0], k, end))
        k = end
    return lines, out


def command_copies(listed: list[tuple[str, int, int]], rows: tuple[Row | Action, ...]) -> list[tuple[str, str]]:
    """
    Name the records to copy for the new buttons.

    The tab's bubble gets More's bubble's records. Each of the tab's buttons gets the "down" record
    of the button it is a copy of: column 0's of Gyro Function's Off, the other columns' of its On,
    both the same sound. The Onion menu's columns 6 and 7 get each of column 4's records (its
    buttons' on and off, its stick icon's on).

    Returns:
        (the record copied, the new record's name) for each.
    """
    copies = [("PauseWindow_00/down/Pa_MenuBtn_02", "PauseWindow_00/down/Pa_MenuBtn_03")]
    for r in range(min(VISIBLE, len(rows))):
        copies += [
            (f"PauseWindow_00/down/{'Pa_CBtn_01' if c == 0 else 'Pa_CBtn_00'}", f"PauseWindow_00/down/Pa_DBtn_{r}{c}")
            for c in range(columns(rows))
        ]
    for c in NEW_COLUMNS:
        for name, _, _ in listed:
            if name.count("/") != 2:
                continue
            layout, state, button = name.split("/")
            if layout == "OnyonWindow_00" and button in ONION_RECORDS:
                copies.append((name, f"{layout}/{state}/{button[:-2]}{c:02d}"))
    return copies


def command_table(raw: bytes, rows: tuple[Row | Action, ...]) -> tuple[bytes, int]:
    """
    Add the records `command_copies` names to the command table.

    Each is a copy of its source under its own button's name, and the count of records at the top
    of the table is raised to match.

    Args:
        raw: The stock `command/lyt_command_table.szs`.
        rows: The rows of the Cheats tab.

    Returns:
        The new file, and how many records were added.

    Raises:
        BuildError: If the table is not laid out as this reads it, has no record to copy or already
            has one of a new name, or the new file does not decompress to what was meant.
    """
    plain = yaz0.decompress(raw)
    text = sarc.Sarc(plain).files()[COMMAND_FILE].decode("utf-8")
    lines, listed = command_records(text)
    if lines[2:4] != ["# record num", str(len(listed))]:
        raise BuildError(f"{COMMAND_FILE} does not begin with its count of records")
    records: dict[str, tuple[int, int]] = {}
    for name, start, end in listed:
        records.setdefault(name, (start, end))
    copies = command_copies(listed, rows)
    added = []
    for key, new_key in copies:
        source, name = key.split("/")[2], new_key.split("/")[2]
        if key not in records:
            raise BuildError(f"the command table has no record {key}")
        if new_key in records:
            raise BuildError(f"the command table already has a record {new_key}")
        start, end = records[key]
        block = [line.replace(source, name) for line in lines[start:end]]
        if sum(source in line for line in block) or sum(name in line for line in block) != 3:
            raise BuildError(f"the copy of the record {key} does not name {name} where it named {source}")
        added += block
    if lines[-1] or lines[-2] != "}":  # the last line ends with the line ending
        raise BuildError(f"{COMMAND_FILE} does not end with its closing brace")
    new = [*lines[:3], str(len(listed) + len(copies)), *lines[4:-2], *added, *lines[-2:]]
    packed = sarc.replace(plain, COMMAND_FILE, "\r\n".join(new).encode("utf-8"))
    szs = yaz0.compress(packed, yaz0.alignment(raw))
    if yaz0.decompress(szs) != packed:
        raise BuildError(f"the new {COMMAND_ARCHIVE} does not decompress to what was meant")
    return szs, len(copies)
