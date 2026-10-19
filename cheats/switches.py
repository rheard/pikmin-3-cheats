"""
Switches: how a cheat entry becomes a row of the menu.

An entry of a cheat file writes words into the game's program, and a loader writes them again and
again while the entry is ticked. A menu cannot do that while the game runs: the code the game has
already run is not read again from memory. So the mod changes nothing while the game runs. Instead,
every word an entry would write is, from the start, a branch to a few words of the mod's own
program file (its switch), which read the row's value and run the word that value asks for: the
game's own while the row is off, the entry's for each of its values. Then they go on with the
game's next word.

* The pick is a jump counted from the value, `add pc, pc, r12, lsl #4`, so the condition flags reach
  the word as the game left them, and r12 is put back before it runs.
* A word that counts from where it stands (a branch, a load of a constant kept beside the code) is
  rewritten to reach the same place from the switch. One that reads the pc any other way is refused.
* Code an entry adds in words of the game's that never run (its cave) is copied into the program
  file and reached from there. Where an entry changes the game's own code where it stands and runs
  on into the game's words, each word it changes is switched as any other.
* A constant an entry changes is a word the game reads, not runs: its switch goes on each load of
  it, which loads that value's constant from beside the switch instead. A table outside the code,
  whose address the game makes first and then indexes, is switched on its load likewise, each
  value loading from a copy of the table as its entry writes it.
* A word two rows' entries both write, alike, is one switch, which runs the entries' word while
  either row is on.

A branch reaches 32 MB, and the program file lies 38 MB past the start of the game's code. Words of
the game's below `FAR` are reached through a veneer: a word of the game's that never runs, made a
plain branch on (`VENEER_ROOMS`).
"""

from __future__ import annotations

from operator import itemgetter
from typing import TYPE_CHECKING

from cheats import arm
from cheats.errors import BuildError
from cheats.game import BASE, TEXT_END
from cheats.rows import Row, switch_rows

if TYPE_CHECKING:
    from cheats.game import Game
    from cheats.rows import Action

PROGRAM = BASE + 0x1EB8000 + 0x60F000  # where the loader lays out the mod's program file: after main and subsdk0
PROGRAM_CODE = PROGRAM + 0x100  # its code, past the module's header
CODE_MOST = 0x20000  # its code ends before PROGRAM + this (the build checks)
FAR = PROGRAM + CODE_MOST - 0x2000000 + 8  # below this, the game's code is out of a branch's reach from all of it
# The veneers' rooms, filled in this order: words of the game's that never run, and that no entry of the
# mod's own cheat files writes. The first is code for two kinds of mission rule that no mission uses;
# the others are runs of a block that served the Wii U GamePad, behind a check that is now always false.
VENEER_ROOMS = ((0x60E42198, 66), (0x60D63020, 15), (0x60D63080, 32), (0x60D63190, 40))
COPY_AFTER = 20  # in a load from a copy of a table: from the add that counts from the pc to the copy

Words = dict[int, int]  # an entry's words, by address


def runs(addresses: set[int]) -> list[tuple[int, int]]:
    """The runs of consecutive words among `addresses`: (first, how many)."""
    out: list[list[int]] = []
    for a in sorted(addresses):
        if out and a == out[-1][0] + 4 * out[-1][1]:
            out[-1][1] += 1
        else:
            out.append([a, 1])
    return [(first, count) for first, count in out]


def veneer_words() -> list[int]:
    """
    The places a veneer may go.

    Returns:
        Every word of the veneers' rooms, in the order they are filled.

    Raises:
        BuildError: If two rooms share a word.
    """
    out = [start + 4 * k for start, count in VENEER_ROOMS for k in range(count)]
    if len(set(out)) != len(out):
        raise BuildError("the veneers' rooms share words")
    return out


def pool_word(value: int | str) -> str:
    """A word of a switch's constants: a number, or an expression the linker works out."""
    return f"    .word   {value}" if isinstance(value, str) else f"    .word   0x{value:08X}"


class TableSite:
    """
    A load of a table outside the code, whose address is made the position-independent way::

        ldr  rb, [pc, #k]          k's word: the table less (the add's place + 8)
        add  rb, pc, rb            rb = the table
        add  rn, rb, ri, lsl #2    (or the load straight from rb)
        vldr s0, [rn, #imm]        (or ldr)

    Its switch goes on the load: off, the game's own load; for a value, the same load at the same
    distance into a copy of the table as that value's entry writes it.

    Attributes:
        start: The table's first word.
        count: How many words it has.
        load: The load, the word the switch stands in for.
        rn: The register the load reads through.
        imm: The load's own offset.
        form: The load's assembly, through r12, with `{}` in place of its offset.
    """

    def __init__(self, game: Game, start: int, count: int, add: int):
        """
        Read the code that makes the table's address at `add`, and the load after it.

        Raises:
            BuildError: For anything but the pattern above, or code a branch reaches in the middle of.
        """
        self.start, self.count = start, count
        rb = game.word(add) & 15
        word = game.word(add + 4)
        if (word & 0xFFF00FF0) == 0xE0800100 and word >> 16 & 15 == rb:  # add rn, rb, ri, lsl #2
            self.rn, index, self.load = word >> 12 & 15, word & 15, add + 8
        else:
            self.rn, index, self.load = rb, None, add + 4
        word = game.word(self.load)
        cond = arm.COND[word >> 28]
        if (word & 0x0F300E00) == 0x0D100A00:  # vldr s/d, [rn, #+-imm8*4]
            imm = (word & 0xFF) * 4
            double, d, vd = word >> 8 & 1, word >> 22 & 1, word >> 12 & 15
            self.form = f"vldr{cond} {f'd{d << 4 | vd}' if double else f's{vd << 1 | d}'}, [r12, #{{}}]"
        elif (word & 0x0F700000) == 0x05100000 and word >> 12 & 15 not in (12, 13, 15):  # ldr rt, [rn, #+-imm12]
            imm = word & 0xFFF
            self.form = f"ldr{cond} r{word >> 12 & 15}, [r12, #{{}}]"
        else:
            raise BuildError(
                f"{self.load:#x}: the table at {start:#x} is read by {word:08x}, not a load the build switches",
            )
        self.imm = imm if word >> 23 & 1 else -imm
        if (word >> 16 & 15) != self.rn or self.rn in (12, 13, 15):
            raise BuildError(f"{self.load:#x}: the load after the table's address at {add:#x} does not read through it")
        if index in (13, 15):
            raise BuildError(f"{add + 4:#x}: the table at {start:#x} is indexed in a way the build does not switch")
        entered = [a for a in range(add, self.load + 4, 4) if a in game.branch_targets()]
        if entered:
            raise BuildError(
                f"{entered[0]:#x} is reached by a branch: the table's address may not be in r{self.rn} there",
            )


class Switches:
    """
    The switches of the rows: the assembly of their code in the program file, and the game's words the
    patch turns into branches to them. Made from each row's entries' words; anything not understood
    is refused, naming the word.
    """

    def __init__(self, rows: tuple[Row | Action, ...], entries: dict[str, Words], game: Game):
        self.game = game
        self.entries = entries
        # by the game's address: the row, the variants (the game's word, then each value's), each value's
        # words and each value's own code
        self.hooks: dict[int, tuple[Row, list[tuple[str, int | None]], list[Words], list[set[int]]]] = {}
        self.shared: dict[
            int,
            tuple[tuple[Row, Row], int],
        ] = {}  # a word of two rows: the rows, and the word both write
        self.caves: dict[tuple[int, tuple[tuple[int, int], ...]], str] = {}  # an entry's own code copied, by its words
        self.tables: dict[int, TableSite] = {}  # the loads of tables outside the code, by the load's address
        self.far: set[int] = set()  # places below FAR the code branches to, each through a veneer
        for row in switch_rows(rows):
            self._row(row)

    def addresses(self) -> list[int]:
        """Every word of the game's a switch stands in for."""
        return sorted(set(self.hooks) | set(self.shared))

    def reach(self, target: int) -> str:
        """What the program file's code branches to for a place of the game's: the place, or below FAR its veneer."""
        if target < FAR:
            self.far.add(target)
            return f"VEN_{target:08x}"
        return f"LAB_{target:08x}"

    def veneers(self) -> dict[int, str | int]:
        """
        Lay out the veneers: first one for each word of the game's below FAR a switch stands in for,
        then one for each place below FAR the code branches to. Made after `source`, which finds the
        second kind.

        Returns:
            What each veneer branches to, by its address: a switch's label, or a place of the game's.

        Raises:
            BuildError: If the rooms are too small.
        """
        room = veneer_words()
        wanted: list[str | int] = [f"sw_{a:08x}" for a in self.addresses() if a < FAR]
        wanted += sorted(self.far)
        if len(wanted) > len(room):
            raise BuildError(f"{len(wanted)} veneers wanted, and {len(room)} words to put them in")
        return dict(zip(room[: len(wanted)], wanted, strict=True))

    def written(self, name: str) -> Words:
        """
        Look up an entry.

        Returns:
            The words it writes, by address.

        Raises:
            BuildError: If there is no such entry.
        """
        if name not in self.entries:
            raise BuildError(f"the rows' cheat file has no entry [{name}]")
        return self.entries[name]

    def _caves(self, words: Words) -> set[int]:
        """
        Find an entry's own code, in words of the game's that never run: the words its branches reach
        among those it writes, and those it writes after them, in a run that ends in a branch or a
        return (its own constants aside) and so never runs on into the game's words. A run that does
        run on is the game's own code, changed where it stands, which the game also reaches its own
        way: its words are switched one by one, and the entry's branches to them go to the game's
        words, through their switches.

        Returns:
            The addresses of the entry's own code.

        Raises:
            BuildError: For a run that runs on and holds constants of its own.
        """
        reached = set()
        for address, word in words.items():
            target = arm.branch_target(address, word)
            if target is not None and target in words and target != address:
                x = target
                while x in words and x not in reached:
                    reached.add(x)
                    x += 4
        own = set()
        for start, count in runs(reached):
            run = [(start + 4 * k, words[start + 4 * k]) for k in range(count)]
            if self._ends(run):
                own |= {address for address, _ in run}
            elif self._constants(run):
                raise BuildError(
                    f"the entry's words at {start:#x} run on into the game's after them and hold constants of their "
                    "own: neither code of its own nor the game's words to switch one by one",
                )
        return own

    @classmethod
    def _ends(cls, run: list[tuple[int, int]]) -> bool:
        """Whether a run of an entry's code (its constants aside) ends in an unconditional b, bx lr or pop {pc}."""
        data = cls._constants(run)
        code = [word for address, word in run if address not in data]
        last = code[-1] if code else 0
        return (
            ((last & 0x0F000000) == 0x0A000000 and last >> 28 == 0xE)
            or last == 0xE12FFF1E
            or ((last & 0x0FFF8000) == 0x08BD8000 and last >> 28 == 0xE)
        )

    @staticmethod
    def _constants(run: list[tuple[int, int]]) -> set[int]:
        """The words of a run of an entry's own code that its own loads read as constants."""
        inside = {address for address, _ in run}
        out: set[int] = set()
        for address, word in run:
            try:
                found = arm.literal(address, word)
            except BuildError:
                continue
            if found:
                out |= {found[0] + 4 * k for k in range(found[1])} & inside
        return out

    def _row(self, row: Row) -> None:
        """Find the switches a row needs."""
        if row.code:
            return  # done by the menu's own code: no words of an entry to switch
        per_value = [self.written(name) for _, name in row.values if name is not None]
        caves = [self._caves(w) for w in per_value]
        missing = [a for a in row.keep if not any(a in w and a not in c for w, c in zip(per_value, caves, strict=True))]
        if missing:
            raise BuildError(f"[{row.label}] keeps words of the game's its entries do not write: {missing}")
        per_value = [{a: w for a, w in words.items() if a not in row.keep} for words in per_value]
        hooked, constants, data = set(), set(), set()
        for words, cave in zip(per_value, caves, strict=True):
            for address in words:
                if address in cave:
                    continue
                if any(address in c for c in caves):
                    raise BuildError(
                        f"{address:#x} is new code of one of [{row.label}]'s entries, "
                        "and a word of the game's in another",
                    )
                if not BASE <= address < TEXT_END:
                    data.add(address)  # not code: a table read through its address
                    continue
                (constants if self.game.readers(address) else hooked).add(address)
        for address in sorted(constants):
            for reader in self.game.readers(address):
                if any(reader in w for w in per_value):
                    raise BuildError(f"{reader:#x} reads a constant [{row.label}] changes, and is itself changed by it")
                hooked.add(reader)
        made = self.game.addresses_made()
        for start, count in runs(data):
            sites = [site for at in range(start, start + 4 * count, 4) for site in made.get(at, [])]
            if not sites or any(made.get(at) for at in range(start + 4, start + 4 * count, 4)):
                what = "none of them" if not sites else "one inside them, not its first"
                raise BuildError(
                    f"the words at {start:#x} ({count}) are not code, and the code makes the address of {what}",
                )
            for ldr, add in sites:
                site = TableSite(self.game, start, count, add)
                if any(a in w for w in per_value for a in range(ldr, site.load + 4, 4)):
                    raise BuildError(f"{site.load:#x} reads a table [{row.label}] changes, and is itself changed by it")
                hooked.add(site.load)
                self.tables[site.load] = site
        for address in sorted(hooked):
            if address in self.hooks or address in self.shared:
                self._share(address, row, per_value, caves)
                continue
            # value 0 the game's; value k + 1 as entry k has it (its word, or the game's where it writes
            # none, and the constants it loads as that entry has them)
            variants: list[tuple[str, int | None]] = [("game", None)] + [("entry", k) for k in range(len(per_value))]
            self.hooks[address] = (row, variants, per_value, caves)

    def _share(self, address: int, row: Row, per_value: list[Words], caves: list[set[int]]) -> None:
        """
        One switch for a word two rows' entries both write. Made only for a word of the game's that every
        value of both writes alike, that loads no constant, is no table's load and branches to none of the
        entries' own code.

        Raises:
            BuildError: For any other word two rows write, or a word three rows write.
        """
        if address in self.shared:
            first, second = self.shared[address][0]
            raise BuildError(
                f"{address:#x} is a word of three rows' or more ({first.label}, {second.label}, {row.label})",
            )
        other, _variants, other_values, other_caves = self.hooks[address]
        words = [w.get(address) for w in other_values + per_value]
        target = arm.branch_target(address, words[0]) if words[0] is not None else None
        if (
            None in words
            or len(set(words)) != 1
            or address in self.tables
            or arm.literal(address, words[0])
            or any(address in c or target in c for c in other_caves + caves)
        ):
            raise BuildError(
                f"{address:#x} is a word of two rows' ({other.label} and {row.label}), "
                "not written alike as a word of its own by every value of both",
            )
        del self.hooks[address]
        self.shared[address] = ((other, row), words[0])

    def _value(self, address: int, words: Words | None) -> int:
        """The word at `address` as a value has it: its entry's if the entry writes it, else the game's."""
        return words[address] if words is not None and address in words else self.game.word(address)

    def _relocate(
        self,
        address: int,
        word: int,
        words: Words | None,
        cave: set[int] | None,
        label: str,
        pool: list[tuple[str, list[int | str]]],
        start: int | None = None,
    ) -> str:
        """
        The assembly for `word` run in the program file in place of `address`; the constants it loads go
        in `pool`.

        In a copy of an entry's own code (`start` its first word, copied word for word from `label`), an
        address made the position-independent way (`ldr rt, [pc, #k]` then `ldr rd, [pc, rt]` or
        `add rd, pc, rt`) counts from the copy: its constant is the address made less (the copy of its
        second word + 8), and the second word is copied as it is.

        Returns:
            One line of assembly.

        Raises:
            BuildError: For a branch out of the game's code, or a word that reads the pc another way.
        """
        target = arm.branch_target(address, word)
        if target is not None:
            mnemonic = ("bl" if word >> 24 & 1 else "b") + arm.COND[word >> 28]
            if cave and target in cave:
                return f"{mnemonic} {self._cave(words or {}, cave, target)}"
            if not BASE <= target < TEXT_END:
                raise BuildError(f"{address:#x}: a branch out of the game's code, to {target:#x}")
            return f"{mnemonic} {self.reach(target)}"
        found = arm.literal(address, word)
        if found:
            at, count, form = found
            name = f"{label}_k{len(pool)}"
            values: list[int | str] = [self._value(at + 4 * k, words) for k in range(count)]
            user = address + 4
            first = arm.pair_first(word)
            if (
                start is not None
                and cave
                and words
                and user in cave
                and first is not None
                and arm.pc_user(words[user]) == first
            ):
                made = (user + 8 + int(values[0])) & 0xFFFFFFFF
                values = [f"LAB_{made:08x} - ({label} + {user - start + 8})"]
            pool.append((name, values))
            return form.format(name)
        if (
            start is not None
            and cave
            and words
            and address - 4 in cave
            and arm.pc_user(word) is not None
            and arm.pair_first(words[address - 4]) == arm.pc_user(word)
        ):
            return f".word 0x{word:08X}"  # counts from the pc: its constant, the word before, counts from this copy
        if arm.reads_pc(word):
            raise BuildError(f"{address:#x}: {word:08x} reads the pc: no switch is made for it")
        return f".word 0x{word:08X}"

    def _cave(self, words: Words, cave: set[int], target: int) -> str:
        """The label of a copy of the entry's own code that holds `target` (its run of words, copied as it is)."""
        start = target
        while start - 4 in cave:
            start -= 4
        run = []
        x = start
        while x in cave:
            run.append((x, words[x]))
            x += 4
        key = (start, tuple(run))
        if key not in self.caves:
            self.caves[key] = f"cave_{start:08x}_{sum(1 for k in self.caves if k[0] == start)}"
        name = self.caves[key]
        return name if target == start else f"{name} + {target - start}"

    def source(self) -> str:
        """
        Write the switches' code. A word no switch can be made for raises `BuildError`, naming it.

        Returns:
            The assembly of every switch, then of every copy of an entry's own code.
        """
        self.far = set()
        out = ["    .syntax unified", "    .arm", '    .section .text.switches, "ax"', "    .balign 4"]
        for address in sorted(self.hooks):
            out += self._switch(address)
        for address in sorted(self.shared):
            out += self._shared_switch(address)
        for (start, run), name in sorted(self.caves.items(), key=itemgetter(1)):
            out += self._copy(start, run, name)
        return "\n".join(out) + "\n"

    def _switch(self, address: int) -> list[str]:
        """
        Write the switch for one row's word: off, the game's word; each value, its entry's.

        Returns:
            Its lines of assembly.
        """
        row, variants, per_value, caves = self.hooks[address]
        n = 1
        while n < len(variants):
            n *= 2
        label = f"sw_{address:08x}"
        pool: list[tuple[str, list[int | str]]] = []
        out = [
            "",
            f"    .global {label}",
            f"    .type   {label}, %function",
            f"{label}:                    @ [{row.label}] in place of the game's word at {address:#x}",
            "    str     r12, [sp, #-8]!",
            f"    ldr     r12, {label}_slot",
            f"{label}_at:",
            "    add     r12, pc, r12",
            "    ldrb    r12, [r12]",
            f"    and     r12, r12, #{n - 1}",
            "    add     pc, pc, r12, lsl #4",
            "    nop",
        ]
        table = self.tables.get(address)
        copies = []
        for v in range(n):
            kind, k = variants[v] if v < len(variants) else ("game", None)
            words = per_value[k] if kind == "entry" and k is not None else None
            what = "off" if v == 0 else (row.values[v - 1][0] if v < len(variants) else "no value: off")
            if table and words is not None:
                out += [
                    f"{label}_v{v}:                 @ {what}: the load from a copy of the table at {table.start:#x}",
                ]
                out += [f"    b       {label}_v{v}_table", "    nop", "    nop", "    nop"]
                copies.append((v, words))
                continue
            own = words is not None and address in words
            # the entry's own word may branch into its own code; the game's word does not
            cave = caves[k] if own and k is not None else None
            word = self._value(address, words)
            out += [
                f"{label}_v{v}:                 @ {what}: {'the entry' if own else 'the game'}'s word",
                "    ldr     r12, [sp], #8",
                "    " + self._relocate(address, word, words, cave, f"{label}_v{v}", pool),
                f"    b       {self.reach(address + 4)}",
                "    nop",
            ]
        out += [f"{label}_slot:", f"    .word   cheat_values + {row.slot} - ({label}_at + 8)"]
        for name, values in pool:
            out += [f"{name}:", *(pool_word(v) for v in values)]
        for v, words in copies if table else ():
            # r12 is free here (its own value is on the stack): how far into the game's table the load
            # reads, then the same load that far into this value's copy of it
            t = f"{label}_v{v}"
            out += [
                f"{t}_table:",
                f"    ldr     r12, {t}_start",
                f"{t}_a:",
                "    add     r12, pc, r12                   @ the game's table",
                f"    sub     r12, r{table.rn}, r12                  @ how far into it the load reads",
                f"{t}_b:",
                "    add     r12, pc, r12",
                "    " + table.form.format(COPY_AFTER - 8 + table.imm),
                "    ldr     r12, [sp], #8",
                f"    b       {self.reach(address + 4)}",
                f"{t}_start:",
                f"    .word   LAB_{table.start:08x} - ({t}_a + 8)",
                f"{t}_copy:                 @ the table as the value's entry writes it",
                f"    .if {t}_copy - {t}_b - {COPY_AFTER}",
                '    .error "the copy of the table is not where its load reads"',
                "    .endif",
                *(f"    .word   0x{self._value(table.start + 4 * j, words):08X}" for j in range(table.count)),
            ]
        return out

    def _shared_switch(self, address: int) -> list[str]:
        """
        Write the switch for a word of two rows: both rows' bytes read (r11 kept in the word beside
        r12's), 0 while both are off and 1 while either is on, without touching the flags.

        Returns:
            Its lines of assembly.
        """
        (first, second), word = self.shared[address]
        label = f"sw_{address:08x}"
        pool: list[tuple[str, list[int | str]]] = []
        out = [
            "",
            f"    .global {label}",
            f"    .type   {label}, %function",
            f"{label}:                    @ [{first.label}] or [{second.label}], for the game's word at {address:#x}",
            "    str     r12, [sp, #-8]!",
            "    str     r11, [sp, #4]",
            f"    ldr     r12, {label}_slot",
            f"{label}_at:",
            "    add     r12, pc, r12",
            "    ldrb    r11, [r12]",
            f"    ldrb    r12, [r12, #{second.slot - first.slot}]",
            "    orr     r12, r12, r11",
            "    ldr     r11, [sp, #4]",
            "    clz     r12, r12                      @ 32 while both are off, less while either is on",
            "    lsr     r12, r12, #5",
            "    eor     r12, r12, #1",
            "    add     pc, pc, r12, lsl #4",
            "    nop",
        ]
        for v, (what, w) in enumerate(
            (("both off: the game's word", self.game.word(address)), ("either on: the entries' word", word)),
        ):
            out += [
                f"{label}_v{v}:                 @ {what}",
                "    ldr     r12, [sp], #8",
                "    " + self._relocate(address, w, None, None, f"{label}_v{v}", pool),
                f"    b       {self.reach(address + 4)}",
                "    nop",
            ]
        out += [f"{label}_slot:", f"    .word   cheat_values + {first.slot} - ({label}_at + 8)"]
        for name, values in pool:
            out += [f"{name}:", *(pool_word(v) for v in values)]
        return out

    def _copy(self, start: int, run: tuple[tuple[int, int], ...], name: str) -> list[str]:
        """
        Write a copy of an entry's own code.

        Returns:
            Its lines of assembly.

        Raises:
            BuildError: If the code would run on past its last word.
        """
        words = dict(run)
        cave = set(words)
        data = self._constants(list(run))  # read by its own loads, never run: copied as they are
        if not self._ends(list(run)):
            raise BuildError(f"the entry's own code at {start:#x} does not end in a branch or a return")
        pool: list[tuple[str, list[int | str]]] = []
        out = [
            "",
            f"    .global {name}",
            f"    .type   {name}, %function",
            f"{name}:                @ a copy of an entry's own code at {start:#x}",
        ]
        for address, word in run:
            if address in data:
                out.append(
                    f"    .word   0x{word:08X}                 @ a constant of its own (its load reads the copy below)",
                )
            else:
                out.append("    " + self._relocate(address, word, words, cave, name, pool, start=start))
        for pool_name, values in pool:
            out += [f"{pool_name}:", *(pool_word(v) for v in values)]
        return out
