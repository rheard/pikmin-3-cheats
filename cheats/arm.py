"""
What the build needs to know of 32-bit ARM instructions (A32), the only kind in the game's code.

Every switch runs one of the game's words, or one of an entry's, somewhere other than where it
stands. Most words do the same anywhere. Those that count from the pc do not: a branch, and a load
of a constant kept beside the code. The build rewrites those to reach the same place from where they
now run (`branch_target`, `literal`), and refuses any other word that reads the pc (`reads_pc`).
"""

from __future__ import annotations

from cheats.errors import BuildError

COND = ("eq", "ne", "cs", "cc", "mi", "pl", "vs", "vc", "hi", "ls", "ge", "lt", "gt", "le", "", "")
PC = 15


def branch_target(address: int, word: int) -> int | None:
    """
    Where a `b` or `bl` at `address` goes, whatever its condition.

    Returns:
        The address it goes to, or None if the word is no such branch.

    Raises:
        BuildError: For a `blx` to an address, which changes to the other instruction set.
    """
    if word >> 25 & 7 != 0b101:
        return None
    if word >> 28 == 0xF:
        raise BuildError(f"{address:#x}: a blx to an address, which changes to Thumb code")
    offset = word & 0xFFFFFF
    if offset & 0x800000:
        offset -= 1 << 24
    return address + 8 + offset * 4


def branch(at: int, to: int) -> int:
    """
    A branch from `at` to `to`.

    Returns:
        The word of the `b`.

    Raises:
        BuildError: If `to` is out of a branch's reach (32 MB either way).
    """
    offset = to - (at + 8)
    if offset % 4 or not -(1 << 25) <= offset < 1 << 25:
        raise BuildError(f"{at:#x} cannot reach {to:#x} with a branch")
    return 0xEA000000 | (offset >> 2) & 0xFFFFFF


def literal(address: int, word: int) -> tuple[int, int, str] | None:
    """
    A load of a constant kept beside the code: an `ldr` of a word, or a `vldr`, counted from the pc.

    Returns:
        Where it reads, how many words, and the assembly for it with `{}` in place of the place; or
        None for any other word.

    Raises:
        BuildError: For a load of the pc itself, which no switch could run.
    """
    cond = COND[word >> 28]
    if (word & 0x0F7F0000) == 0x051F0000:  # ldr rt, [pc, #+-imm12]
        rt = word >> 12 & 15
        if rt == PC:
            raise BuildError(f"{address:#x}: a load of the pc from beside the code")
        imm = word & 0xFFF
        return address + 8 + (imm if word >> 23 & 1 else -imm), 1, f"ldr{cond} r{rt}, {{}}"
    if (word & 0x0F3F0E00) == 0x0D1F0A00:  # vldr s/d, [pc, #+-imm8*4]
        imm = (word & 0xFF) * 4
        double = word >> 8 & 1
        d, vd = word >> 22 & 1, word >> 12 & 15
        register = f"d{d << 4 | vd}" if double else f"s{vd << 1 | d}"
        return ((address + 8) & ~3) + (imm if word >> 23 & 1 else -imm), 1 + double, f"vldr{cond} {register}, {{}}"
    return None


def pc_user(word: int) -> int | None:
    """
    The second half of an address made the position-independent way, whose first is an `ldr` of a
    constant that counts from it.

    Returns:
        The register an unconditional `ldr rd, [pc, rm]` or `add rd, pc, rm` adds to the pc, or None
        for any other word.
    """
    if (word & 0xFFFF0FF0) in (0xE79F0000, 0xE08F0000):
        return word & 15
    return None


def pair_first(word: int) -> int | None:
    """The register an unconditional `ldr rt, [pc, #+-imm12]` loads, else None."""
    if (word & 0xFF7F0000) == 0xE51F0000:
        return word >> 12 & 15
    return None


def reads_pc(word: int) -> bool:
    """
    Whether an instruction reads the pc as one of its operands.

    Branches are not asked about: `branch_target` deals with them. A `blx` to a register reads the pc
    only for the return address, which from a switch is the switch's, and it goes on from there, so
    it does not count. An instruction outside the kinds this knows raises `BuildError`.

    Returns:
        True if it reads the pc.
    """
    rn, rt, rm = word >> 16 & 15, word >> 12 & 15, word & 15
    load = word >> 20 & 1
    if word >> 28 == 0xF:
        return _unconditional(word)
    kind = word >> 25 & 7
    if kind <= 1:
        return _data_processing(word)
    if kind == 2:  # a load or store, immediate offset: a store reads what it stores
        return PC in (rn, *(() if load else (rt,)))
    if kind == 3 and not word >> 4 & 1:  # the same, register offset
        return PC in (rn, rm, *(() if load else (rt,)))
    if kind == 3:
        return _media(word)
    if kind == 4:  # ldm/stm: a store reads every register in its list
        return rn == PC or (not load and bool(word >> 15 & 1))
    if kind == 5:
        return False
    if kind == 6:
        if word >> 21 & 15 == 0b0010:  # two registers to or from the coprocessor (vmov d, r, r)
            return not load and PC in (rt, rn)
        return rn == PC  # vldr, vstr, vldm, vstm, vpush, vpop, ldc, stc
    if word >> 24 & 1 or not word >> 4 & 1:  # svc; the float unit's arithmetic, on its own registers
        return False
    return not load and rt == PC  # a core register to the float unit or a coprocessor (vmov s, r; vmsr; mcr)


def _data_processing(word: int) -> bool:
    """`reads_pc` for the kinds whose bits 27-26 are 00."""
    rn, rt, rs, rm = word >> 16 & 15, word >> 12 & 15, word >> 8 & 15, word & 15
    immediate = word >> 25 & 1
    opcode, setting = word >> 21 & 15, word >> 20 & 1
    if immediate:
        if word >> 20 & 0x1F == 0b10000:  # movw
            return False
        if word >> 20 & 0x1F == 0b10100:  # movt keeps the register's low half
            return rt == PC
        if word >> 23 & 3 == 0b10 and word >> 20 & 3 == 0b10:  # msr of a constant, and the hints (nop)
            return False
        return opcode not in (0b1101, 0b1111) and rn == PC  # every operation but mov and mvn reads rn
    low = word >> 4 & 15
    if low == 0b1001:
        if not word >> 24 & 1:  # multiplies
            accumulates = word >> 21 & 7 in (0b001, 0b010, 0b011, 0b101, 0b111)
            high = word >> 21 & 7 in (0b010, 0b101, 0b111)  # the long ones that add to both halves
            return PC in (rm, rs, *((rt,) if accumulates else ()), *((rn,) if high else ()))
        if word >> 23 & 1:  # ldrex and strex, and the like: a store reads what it stores
            return rn == PC or (not setting and rm == PC)
        return PC in (rn, rm)  # swp
    if low & 0b1001 == 0b1001:  # halfword, signed byte and doubleword loads and stores
        stores = not setting and (word >> 5 & 3 == 0b01 or word >> 5 & 3 == 0b11)
        stored = (rt, rt + 1) if word >> 5 & 3 == 0b11 else (rt,)
        return PC in (rn, *(() if word >> 22 & 1 else (rm,)), *(stored if stores else ()))
    if word >> 23 & 3 == 0b10 and not setting:  # the miscellaneous ones
        if word >> 7 & 1:  # halfword multiplies
            op = word >> 21 & 3
            reads = [rm, rs]
            if op == 0b00 or op == 0b10 or (op == 0b01 and not word >> 5 & 1):
                reads.append(rt)
            if op == 0b10:
                reads.append(rn)
            return PC in reads
        op2, op = word >> 4 & 7, word >> 21 & 3
        if op2 == 0b000:  # mrs reads none; msr reads rm
            return bool(op & 1) and rm == PC
        if op2 == 0b001 or op2 == 0b010:  # bx, clz, bxj
            return rm == PC
        if op2 == 0b011:  # blx to a register
            return False
        if op2 == 0b101:  # saturating add and subtract
            return PC in (rn, rm)
        if op2 == 0b111:  # bkpt, hvc, smc
            return False
        raise BuildError(f"{word:08x} is not an instruction this build knows")
    reads = [rm]
    if opcode not in (0b1101, 0b1111):
        reads.append(rn)
    if low & 1:  # shifted by a register
        reads.append(rs)
    return PC in reads


def _media(word: int) -> bool:
    """`reads_pc` for the media instructions (bits 27-25 011, bit 4 set)."""
    rn, rt, rs, rm = word >> 16 & 15, word >> 12 & 15, word >> 8 & 15, word & 15
    group, op1, op2 = word >> 23 & 3, word >> 20 & 7, word >> 5 & 7
    if group == 0b00:  # parallel add and subtract
        return PC in (rn, rm)
    if group == 0b01:
        if op1 == 0b000 and (not op2 & 1 or op2 == 0b101):  # pkh, sel
            return PC in (rn, rm)
        # sxtab, uxtah and the like (rn 1111 for the forms that add nothing: sxtb, uxth); ssat, usat and
        # their 16-bit forms; rev, rev16, rbit, revsh: the one register they read is the low one
        return rm == PC
    if (
        group == 0b10
    ):  # signed multiplies and divides (ra 1111 for the forms that add nothing); the long ones add to both
        return PC in (rm, rs) or (op1 == 0b100 and PC in (rt, rn))
    if op1 == 0b000 and op2 == 0b000:  # usad8, usada8 (ra 1111 for the first)
        return PC in (rm, rs)
    if op1 & 0b010 and op2 & 0b011 == 0b010:  # sbfx, ubfx
        return rm == PC
    if op1 & 0b110 == 0b100 and not op2 & 0b011:  # bfi, which keeps the rest of rd (and with rm 1111, bfc)
        return rt == PC
    if op1 == 0b111 and op2 == 0b111:  # udf, the instruction that is always undefined
        return False
    raise BuildError(f"{word:08x} is not an instruction this build knows")


def _unconditional(word: int) -> bool:
    """`reads_pc` for the instructions with no condition (bits 31-28 1111)."""
    rn, rt, rm = word >> 16 & 15, word >> 12 & 15, word & 15
    load = word >> 20 & 1
    if word >> 25 & 0x7F == 0b1111001:  # the vector unit's arithmetic, on its own registers
        return False
    if word >> 25 & 7 == 0b110:  # a coprocessor's loads and stores, and its two-register transfers
        return not load and PC in (rt, rn) if word >> 21 & 15 == 0b0010 else rn == PC
    if word >> 24 & 15 == 0b1110:  # the float unit's newer arithmetic (vsel, vmaxnm, vrint); a coprocessor's transfers
        return bool(word >> 4 & 1) and not load and rt == PC
    if word >> 24 & 0xFF == 0xF4 and not word >> 20 & 1:  # its loads and stores (rm 1101 or 1111: no register)
        return rn == PC
    if word & 0xFFFFFF00 == 0xF57FF000 and word >> 4 & 15 in (1, 4, 5, 6):  # clrex, dsb, dmb, isb
        return False
    if word >> 20 & 0xFFF == 0xF10:  # cps, setend
        return False
    if word >> 24 & 0xFE == 0xF4 and word >> 20 & 3 == 0b01:  # pld, pldw, pli, a constant offset
        return rn == PC
    if word >> 24 & 0xFE == 0xF6 and word >> 20 & 3 == 0b01 and not word >> 4 & 1:  # the same, a register offset
        return PC in (rn, rm)
    raise BuildError(f"{word:08x} is not an instruction this build knows")
