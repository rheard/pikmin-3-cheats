"""
The rows of the Cheats tab: their names, their buttons, and what each button does.

A row is one of three kinds:

* A `Row` switches cheats. Each of its buttons is a value, and each value is an entry of
  `entries/rows.txt`: pressing a button turns the row to that value, and pressing the lit one again
  turns the row off. The row's value is kept in a byte of `cheats.sav`, its slot, which is given out
  once and never changes, so that a saved choice still means the same thing after rows are added or
  moved about. A row taken out leaves its slot empty; a new row takes the next one.
* A `Toggle` is a row of one value, with buttons after it that each do something once.
* An `Action` row's buttons each add Pikmin to the Onion, as flowers. It keeps nothing.

`ROWS` is in the order the rows stand on the page, which shows `VISIBLE` of them at a time and
scrolls. The menu's C code (`menu/menu.c`) reads them from `rows.h`, which `header` writes.
"""

from __future__ import annotations

import struct

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cheats.errors import BuildError

if TYPE_CHECKING:
    from cheats.game import Game


@dataclass(frozen=True)
class Row:
    """
    A row that switches cheats.

    Attributes:
        slot: Its byte in `cheats.sav` and in the menu's own table of values.
        label: Its name on the page.
        values: For each of its values, the name of its button and the entry of `entries/rows.txt`
            it turns on (None for a row the menu's own code does, which `code` names).
        code: For a row with no entries, the name the menu's C code knows it by (`<code>_SLOT`).
        keep: Words of the game's its entry writes that the row leaves as the game has them.
    """

    slot: int
    label: str
    values: tuple[tuple[str, str | None], ...]
    code: str | None = None
    keep: frozenset[int] = frozenset()

    def names(self) -> tuple[str, ...]:
        """Its buttons' names, in order."""
        return tuple(name for name, _ in self.values)


@dataclass(frozen=True)
class Toggle(Row):
    """
    A row of one value, with buttons after it that each do something once.

    Attributes:
        actions: For each button after the value, its name and what it does: `ACTION_<what>` in the
            menu's C code.
    """

    actions: tuple[tuple[str, str], ...] = ()

    def names(self) -> tuple[str, ...]:
        """Its buttons' names, in order: its value's, then its actions'."""
        return super().names() + tuple(name for name, _ in self.actions)


@dataclass(frozen=True)
class Action:
    """
    A row whose buttons each add Pikmin of one type to the Onion, as flowers, by the game's own count.

    Its name shows how many of the type the Onion holds, or "not found" while it holds none (the
    game could not give them out, so a press adds none).

    Attributes:
        label: Its name on the page.
        pikmin: The game's number for the type.
        amounts: How many each button adds.
    """

    label: str
    pikmin: int
    amounts: tuple[int, ...]

    def names(self) -> tuple[str, ...]:
        """Its buttons' names, in order."""
        return tuple(f"+{amount}" for amount in self.amounts)


def on(slot: int, label: str, entry: str) -> Row:
    """A row with one value, its button "On"."""
    return Row(slot, label, (("On", entry),))


def times(slot: int, label: str, entry: str, *factors: int) -> Row:
    """A row of multiples, its buttons "x2", "x5" and so on, each the entry named so: "<entry> x2"."""
    return Row(slot, label, tuple((f"x{factor}", f"{entry} x{factor}") for factor in factors))


PIKMIN_ADD = (10, 50, 100, 1000)  # what an Onion row's buttons add
FLOWER = 2  # the stage they go into the Onion as: 0 leaf, 1 bud, 2 flower
ONION_MOST = 9999  # never more than this of a type: the game's own setter turns more into 9,999 flowers
STORY_PURPLE_WHITE = "Story Onion Holds Purple And White Pikmin"
NO_CARRY_PENALTY = "Pikmin No Carry Penalty"

ROWS = (
    Toggle(
        10,
        "Day Timer",
        (("Pause", "Stop timer operation"),),
        actions=(("Set start", "DAY_START"), ("Set noon", "DAY_NOON")),
    ),
    on(31, "No Map Fog", "No Map Fog"),
    times(0, "Leader Movement Speed", "Leader Movement Speed", 2, 3),
    times(4, "Pikmin Movement Speed", "Pikmin Movement Speed", 2, 3),
    on(11, "Leader God Mode", "Player God Mode (All Koppai)"),
    on(12, "Pikmin God Mode", "Pikmin God Mode"),
    on(13, "Hazard Immunity", "Hazard Immunity (Fire, Water, Electric, Poison, Rock Crush)"),
    times(16, "Pikmin Attack Damage", "Pikmin Attack Damage", 2, 5),
    times(28, "Pikmin Push Strength", "Pikmin Push Strength", 2, 5, 10, 100),
    times(27, "Pikmin Carry Strength", "Pikmin Carry Strength", 2, 5, 10, 100),
    # with No Carry Penalty on as well, Pikmin carry at their walking speed times this row's value
    times(25, "Pikmin Carry Speed", "Pikmin Carry Speed", 2, 3, 5),
    on(26, "Pikmin No Carry Penalty", NO_CARRY_PENALTY),
    times(29, "Pikmin Weight", "Pikmin Weight", 2, 5, 10, 100),
    on(30, "Pikmin Lift Like Winged", "Any Pikmin Can Lift Like Winged Pikmin"),
    times(1, "Throw Distance", "Throw Distance", 2, 3, 5),
    Row(2, "Throw Speed", (("x2", "Throw Speed x2"), ("Max", "Throw Speed Max"))),
    times(20, "Throw Height", "Throw Height", 2, 5),
    on(21, "Yellow Throw For All", "Yellow Throw Height for All Pikmin"),
    on(3, "Full-Auto Throw", "Full-Auto Throw (Hold A)"),
    on(6, "Onion Pikmin Are Flowers", "All Pikmin From Onion Are Flower"),
    on(7, "Instant Flower Sprouts", "Grown Pikmin Have Instant Flower"),
    # the Onion's Pikmin, in the order the Onion menu lists them
    Action("Red Onion", 3, PIKMIN_ADD),
    Action("Rock Onion", 7, PIKMIN_ADD),
    Action("Yellow Onion", 5, PIKMIN_ADD),
    Action("Winged Onion", 6, PIKMIN_ADD),
    Action("Blue Onion", 2, PIKMIN_ADD),
    Action("Purple Onion", 1, PIKMIN_ADD),
    Action("White Onion", 4, PIKMIN_ADD),
    # with Purple and White in columns of their own in the Onion menu (the menu's code), the entry's two
    # calls that would send them to a page of their own stay the game's
    Row(5, "Story Purple And White", (("On", STORY_PURPLE_WHITE),), keep=frozenset((0x60BC2FA4, 0x60BC3024))),
    on(23, "Instant Pikmin Pluck", "Instant Pikmin Pluck"),
    on(24, "Whistle Plucks Sprouts", "Whistle Plucks Sprouts"),
    Row(
        22,
        "Whistle Radius",
        (("x2", "Whistle Radius x2"), ("x5", "Whistle Radius x5"), ("Wii U Size", "Whistle Radius Wii U Size")),
    ),
    on(14, "Invisible To Enemies", "Invisible To Enemies (Pikmin and Koppai)"),
    on(15, "Freeze Healthy Enemies", "Freeze Healthy Enemies In Transform Phase"),
    on(34, "One-Hit Walls And Gates", "Walls And Gates Break In One Hit"),
    on(35, "Pikmin Break Bomb Gates", "Pikmin Can Break Bomb Gates"),
    on(36, "All Pikmin Break Crystal", "Any Pikmin Can Break Crystal"),
    on(37, "All Pikmin Connect Wires", "Any Pikmin Can Connect Electric Wires"),
    # a used spray takes none from the count, and a count of none becomes one: the menu's own code
    Row(8, "Infinite Spicy Spray", (("On", None),), code="INFINITE_SPRAY"),
    on(9, "Ultra-Spicy Spray Lasts", "Ultra-Spicy Spray effect time does not decrease"),
    Row(32, "Depth Of Field Blur", (("Half", "Half Depth Of Field Blur"), ("None", "No Depth Of Field Blur"))),
    on(33, "No Corner Darkening", "No Corner Darkening"),
)

# Where the cursor was last on the tab (the list's top row on the page, the row, the column), so that the
# tab opens there again: three slots no row has, read whatever they hold.
PLACE_SLOT, PLACE_SLOTS = 17, 3
SLOTS = 38  # slots given out so far: the next row takes slot 38
VISIBLE = 4  # rows of panes on the page: the game's window holds four
LAYOUT_VERSION = 1  # raised only if slots are ever given out again from nothing: every row then starts off
NO_SLOT = 255  # an Action's slot: none
TAB_LABEL = "Cheats"
COUNT_AFTER, NOT_FOUND = ": ", ": not found"  # an Onion row's name: "Red Onion: 120", or "Red Onion: not found"
SHOWN_MOST, SHOWN_LEAST = 99999, -9999  # an Onion row shows a count between these
CARRY_CONSTANT = 0x60C7F7B4  # the 42.0 a carried thing's speed is worked out from, which Carry Speed's entries change


def switch_rows(rows: tuple[Row | Action, ...] = ROWS) -> list[Row]:
    """The rows that switch cheats (and toggles), in order."""
    return [row for row in rows if isinstance(row, Row)]


def columns(rows: tuple[Row | Action, ...] = ROWS) -> int:
    """
    Count the columns of the page: every row of panes has as many buttons as the widest row, since
    any row of the list may scroll into it. The menu's code hides those a row has no button for.

    Returns:
        How many buttons the widest row has.
    """
    return max(len(row.names()) for row in rows)


def longest_labels(rows: tuple[Row | Action, ...] = ROWS) -> list[str]:
    """Every row's name at its longest: an Onion row's with the widest counts it shows, or "not found"."""
    out = []
    for row in rows:
        if isinstance(row, Action):
            out += [
                f"{row.label}{COUNT_AFTER}{SHOWN_MOST}",
                f"{row.label}{COUNT_AFTER}{SHOWN_LEAST}",
                row.label + NOT_FOUND,
            ]
        else:
            out.append(row.label)
    return out


def the_row(rows: tuple[Row | Action, ...], entry: str) -> Row:
    """
    Find the row of an entry.

    Returns:
        The one row that has `entry` among its values.

    Raises:
        BuildError: If there is not exactly one.
    """
    found = [row for row in switch_rows(rows) if any(name == entry for _, name in row.values)]
    if len(found) != 1:
        raise BuildError(f"{len(found)} rows have the entry [{entry}]")
    return found[0]


def carry_speed(
    rows: tuple[Row | Action, ...],
    entries: dict[str, dict[int, int]],
    game: Game,
) -> tuple[Row, list[float]]:
    """
    Carry Speed's row, and what each of its values multiplies a carried thing's speed by (1.0 for off).

    No Carry Penalty's entry makes a carried thing go at its carriers' walking speed, and goes round
    the constant Carry Speed's entries change, so the two entries alone never add up. With both rows
    on, the menu's code multiplies the speed No Carry Penalty makes by these.

    Returns:
        The row, and the factor of each of its values.

    Raises:
        BuildError: If no one row writes that constant alone, or a value is no whole multiple of it.
    """
    found = [
        row
        for row in switch_rows(rows)
        if row.values and all(name in entries and list(entries[name]) == [CARRY_CONSTANT] for _, name in row.values)
    ]
    if len(found) != 1:
        raise BuildError(f"{len(found)} rows write only the carry speed's constant")

    def f32(word: int) -> float:
        return struct.unpack("<f", struct.pack("<I", word))[0]

    stock = f32(game.word(CARRY_CONSTANT))
    factors = [1.0]
    for _, name in found[0].values:
        made = f32(entries[name][CARRY_CONSTANT])
        factors.append(made / stock)
        if f32(struct.unpack("<I", struct.pack("<f", factors[-1] * stock))[0]) != made:
            raise BuildError(f"[{name}]: its constant {made:g} is no whole multiple of the game's {stock:g}")
    return found[0], factors


def _check(rows: tuple[Row | Action, ...], slot_values: list[int]) -> None:
    """
    Refuse rows the menu's code could not show or keep.

    Raises:
        BuildError: For a slot given out twice or past `SLOTS`, too many rows or columns for a button's
            name, or an Onion row of no type or amount the Onion takes.
    """
    for row in switch_rows(rows):
        if not 0 <= row.slot < SLOTS or slot_values[row.slot]:
            raise BuildError(f"row {row.label}: slot {row.slot} is given out twice, past SLOTS or the place's")
        slot_values[row.slot] = len(row.values)
    if SLOTS >= NO_SLOT:
        raise BuildError("a slot number would be taken for no slot")
    if VISIBLE > 10 or columns(rows) > 10:
        raise BuildError("a button's name holds its row and column as one digit each")
    for row in rows:
        if isinstance(row, Action) and not (1 <= row.pikmin <= 7 and all(0 < a <= ONION_MOST for a in row.amounts)):
            raise BuildError(f"row {row.label}: not a type of Pikmin the Onion holds, or an amount it cannot add")


def header(
    rows: tuple[Row | Action, ...],
    entries: dict[str, dict[int, int]],
    game: Game,
    bar: dict[str, float],
) -> str:
    """
    `rows.h`: the rows as the menu's C code reads them, numbers and text only.

    `bar` gives the scroll bar's sizes and places (`layout.scroll_bar`).

    Returns:
        The header's text.

    Raises:
        BuildError: If a name is not plain ASCII (the game's font has those) or the rows do not fit.
    """
    text: list[int] = []
    at: dict[str, int] = {}

    def put(s: str) -> int:
        if s not in at:
            at[s] = len(text)
            text.extend(ord(c) for c in s)
            text.append(0)
        return at[s]

    for row in rows:
        put(row.label)
        for name in row.names():
            put(name)
    for s in (TAB_LABEL, NOT_FOUND, COUNT_AFTER):
        put(s)
    if any(c > 0x7E or c < 0x20 for c in text if c):
        raise BuildError("a name with letters other than plain ASCII: check the game's font has them first")
    cols = columns(rows)
    slot_values = [0] * SLOTS
    if PLACE_SLOTS != 3 or PLACE_SLOT + PLACE_SLOTS > SLOTS:
        raise BuildError("the menu's code keeps its place in three slots from PLACE_SLOT, inside SLOTS")
    for s in range(PLACE_SLOT, PLACE_SLOT + PLACE_SLOTS):
        slot_values[s] = 255  # the place: any byte
    _check(rows, slot_values)
    actions: list[str] = []  # what a toggle's buttons after its value do, numbered from 1 (0: nothing)
    for row in rows:
        for _, what in getattr(row, "actions", ()):
            if what not in actions:
                actions.append(what)

    def action_of(row: Row | Action) -> tuple[int, ...]:
        if not isinstance(row, Toggle):
            return ()
        return (0,) * len(row.values) + tuple(actions.index(what) + 1 for _, what in row.actions)

    def amounts_of(row: Row | Action) -> tuple[int, ...]:
        return row.amounts if isinstance(row, Action) else ()

    def table(values: list[tuple[int, ...]], fill: int) -> str:
        return ", ".join("{" + ", ".join(str(v) for v in row + (fill,) * (cols - len(row))) + "}" for row in values)

    def numbers(values: list[int] | tuple[int, ...]) -> str:
        return ", ".join(str(v) for v in values)

    def real(value: float) -> str:
        return f"{float(value)!r}f"

    penalty = the_row(rows, NO_CARRY_PENALTY)
    speed, factors = carry_speed(rows, entries, game)
    slot_of = [r.slot if isinstance(r, Row) else NO_SLOT for r in rows]
    pikmin_of = [r.pikmin if isinstance(r, Action) else 0 for r in rows]
    values_of = [len(r.values) if isinstance(r, Row) else 0 for r in rows]  # 0 for an Onion row
    names_of = [tuple(at[n] for n in r.names()) for r in rows]
    lines = [
        "/* The rows of the Cheats tab, written by the build (cheats/rows.py). */",
        f"#define ROWS {len(rows)}",
        f"#define VISIBLE {min(VISIBLE, len(rows))}",
        f"#define COLUMNS {cols}",
        f"#define SLOTS {SLOTS}",
        f"#define NO_SLOT {NO_SLOT}",
        f"#define LAYOUT_VERSION {LAYOUT_VERSION}",
        f"#define PLACE_SLOT {PLACE_SLOT}",
        f"#define TAB_LABEL {at[TAB_LABEL]}",
        f"#define NOT_FOUND {at[NOT_FOUND]}",
        f"#define COUNT_AFTER {at[COUNT_AFTER]}",
        f"#define FLOWER {FLOWER}",
        f"#define ONION_MOST {ONION_MOST}",
        f"#define SHOWN_MOST {SHOWN_MOST}",
        f"#define SHOWN_LEAST {SHOWN_LEAST}",
        f"#define MAX_LABEL {max(len(label) for label in longest_labels(rows))}",
        f"#define MAX_NAME {max(len(n) for r in rows for n in r.names())}",
        f"#define SCROLLS {int(bar['shown'])}",
        f"#define TRACK_H {real(bar['track'])}",
        f"#define THUMB_H {real(bar['thumb'])}",
        f"#define THUMB_TOP {real(bar['top'])}",
        f"#define THUMB_STEP {real(bar['step'])}",
        f"#define ARROW_UP_Y {real(bar['up'])}",
        f"#define ARROW_DOWN_Y {real(bar['down'])}",
        f"static const unsigned char ROW_SLOT[ROWS] = {{{numbers(slot_of)}}};",
        f"static const unsigned char ROW_COLUMNS[ROWS] = {{{numbers([len(r.names()) for r in rows])}}};",
        f"static const unsigned char ROW_PIKMIN[ROWS] = {{{numbers(pikmin_of)}}};",
        f"static const unsigned short ROW_AMOUNT[ROWS][COLUMNS] = {{{table([amounts_of(r) for r in rows], 0)}}};",
        f"static const unsigned char SLOT_VALUES[SLOTS] = {{{numbers(slot_values)}}};",
        f"#define STORY_PURPLE_WHITE_SLOT {the_row(rows, STORY_PURPLE_WHITE).slot}",
        f"#define NO_CARRY_PENALTY_SLOT {penalty.slot}",
        f"#define CARRY_SPEED_SLOT {speed.slot}",
        f"static const float CARRY_SPEED_BY[{len(factors)}] = {{{', '.join(real(f) for f in factors)}}};",
        # how many of a row's buttons are its values: column c the value c + 1
        f"static const unsigned char ROW_VALUES[ROWS] = {{{numbers(values_of)}}};",
        f"static const unsigned char ROW_ACTION[ROWS][COLUMNS] = {{{table([action_of(r) for r in rows], 0)}}};",
        *(f"#define ACTION_{what} {k + 1}" for k, what in enumerate(actions)),
        *(f"#define {r.code}_SLOT {r.slot}" for r in switch_rows(rows) if r.code),
        f"static const unsigned short ROW_LABEL[ROWS] = {{{numbers([at[r.label] for r in rows])}}};",
        f"static const unsigned short ROW_NAME[ROWS][COLUMNS] = {{{table(names_of, at[TAB_LABEL])}}};",
        f"static const unsigned short TEXT[{len(text)}] = {{{numbers(text)}}};",
    ]
    return "\n".join(lines) + "\n"
