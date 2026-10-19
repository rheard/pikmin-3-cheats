"""
Yaz0, the compression around the game's files (the `.szs` extension).

A Yaz0 file is a 16-byte big-endian header (the letters `Yaz0`, the size of the data once
decompressed, an alignment, four zero bytes) and then a run of groups. A group is a flag byte and up
to eight pieces, one for each bit from the top down: a set bit is one plain byte, a clear bit is a
copy of 3 to 0x111 bytes from 1 to 0x1000 bytes back in what has been written so far. A copy is two
bytes, `NR RR`: N + 2 bytes from RRR + 1 back. When N is 0 a third byte follows, and the length is
that byte + 0x12. A copy may run into the bytes it is itself writing, which is how a long run of one
value is stored.

The alignment matters. The game allocates the buffer it decompresses into with it, and when it is
zero asks the resource being loaded for a default, through a virtual call that not every resource
implements: "Pure virtual function called!", and the game stops. So a file made here must carry the
stock file's value, which `alignment` reads: 0x2000 for the layout archives, 0x20 for the table of
the buttons' sounds.

`decompress` and `compress` handle whole files. `splice` is for changing a few places in a large
one: it keeps the stock file's stream and rewrites only the groups near a change.
"""

from __future__ import annotations

import bisect
import itertools
import struct

MAGIC = b"Yaz0"
HEADER = 16
FURTHEST = 0x1000  # how far back a copy may reach
LONGEST = 0x111  # how many bytes a copy may write

Piece = tuple[bool, bytes]  # (is a plain byte, its bytes in the stream)
Edit = tuple[int, int, bytes]  # (start, end, new bytes): data[start:end] replaced by the new bytes


def decompress(data: bytes) -> bytes:
    """Decompress a Yaz0 stream; anything that is not one comes back unchanged."""
    if data[:4] != MAGIC:
        return data
    size = struct.unpack_from(">I", data, 4)[0]
    out = bytearray()
    src = HEADER
    n_data = len(data)
    while len(out) < size and src < n_data:
        code = data[src]
        src += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if code >> bit & 1:
                out.append(data[src])
                src += 1
            else:
                b1, b2 = data[src], data[src + 1]
                src += 2
                dist = ((b1 & 0x0F) << 8 | b2) + 1
                n = b1 >> 4
                if n == 0:
                    n = data[src] + 0x12
                    src += 1
                else:
                    n += 2
                start = len(out) - dist
                if dist >= n:
                    out += out[start : start + n]
                else:
                    # Overlapping copy: the source repeats with period `dist`.
                    chunk = out[start:]
                    reps, rest = divmod(n, dist)
                    out += chunk * reps + chunk[:rest]
    return bytes(out)


def alignment(raw: bytes) -> int:
    """The alignment a Yaz0 file asks for its decompressed data (0 when it is not a Yaz0 file)."""
    return struct.unpack_from(">I", raw, 8)[0] if raw[:4] == MAGIC else 0


def compress(data: bytes, alignment: int, tries: int = 4) -> bytes:
    """
    Compress bytes into a Yaz0 stream the game will read.

    `alignment` goes in the header and must be the stock file's: see the top of this module.

    Matching is greedy against the last 4 KB: the `tries` nearest earlier copies of the next three
    bytes are tried and the longest kept. That is slower and a little looser than Nintendo's packer,
    which is fine for a file built once.

    Returns:
        The whole file, header included.
    """
    data = bytes(data)
    n = len(data)
    out = bytearray(MAGIC + struct.pack(">II", n, alignment) + bytes(4))
    pos = 0
    rfind = data.rfind
    while pos < n:
        code_at = len(out)
        out.append(0)
        code = 0
        for bit in range(7, -1, -1):
            if pos >= n:
                break
            best, best_at = 0, 0
            limit = min(LONGEST, n - pos)
            if limit >= 3:
                key = data[pos : pos + 3]
                lo = pos - FURTHEST if pos > FURTHEST else 0
                at = rfind(key, lo, pos + 2)  # a copy may overlap the bytes it produces
                left = tries
                while at >= 0:
                    # Longest common run of data[at:] and data[pos:], by bisection on slice equality.
                    a, b = 3, limit
                    while a < b:
                        mid = (a + b + 1) >> 1
                        if data[at : at + mid] == data[pos : pos + mid]:
                            a = mid
                        else:
                            b = mid - 1
                    if a > best:
                        best, best_at = a, at
                        if a == limit:
                            break
                    left -= 1
                    if not left:
                        break
                    at = rfind(key, lo, at + 2)
            if best >= 3:
                out += _copy(pos - best_at, best)
                pos += best
            else:
                code |= 1 << bit
                out.append(data[pos])
                pos += 1
        out[code_at] = code
    return bytes(out)


def differences(old: bytes | bytearray, new: bytes | bytearray, step: int = 0x10000) -> list[tuple[int, int]]:
    """
    Find where two equally long buffers differ.

    Returns:
        (start, end) of each run of differing bytes, in order.

    Raises:
        ValueError: If the buffers are not the same length.
    """
    if len(old) != len(new):
        raise ValueError(f"the buffers differ in length ({len(old)} and {len(new)})")
    spans = []
    for base in range(0, len(old), step):
        a, b = old[base : base + step], new[base : base + step]
        if a == b:
            continue
        i = 0
        while i < len(a):
            if a[i] == b[i]:
                i += 1
                continue
            j = i
            while j < len(a) and a[j] != b[j]:
                j += 1
            if spans and spans[-1][1] == base + i:
                spans[-1] = (spans[-1][0], base + j)
            else:
                spans.append((base + i, base + j))
            i = j
    return spans


def same_length_edits(old: bytes | bytearray, new: bytes | bytearray) -> list[Edit]:
    """The edits that turn `old` into `new`, two buffers of the same length: one for each run of changed bytes."""
    return [(start, end, bytes(new[start:end])) for start, end in differences(old, new)]


def apply_edits(plain: bytes, edits: list[Edit]) -> bytes:
    """
    Make the edits to `plain`: each puts its new bytes in place of plain[start:end].

    Returns:
        The new data.

    Raises:
        ValueError: If the edits are not in order and apart.
    """
    out, at = bytearray(), 0
    for start, end, new in edits:
        if start < at or end < start:
            raise ValueError(f"edits overlap or run backwards at {start:#x}")
        out += plain[at:start]
        out += new
        at = end
    out += plain[at:]
    return bytes(out)


def splice(stock: bytes, plain: bytes, edits: list[Edit]) -> bytes:
    """
    Make a Yaz0 stream for the stock file's data with some stretches of it replaced.

    This is for changing a few places in a large file, even by bytes of another length: compressing
    70 MB with `compress` takes minutes, and all but a sliver of the result would say what the stock
    stream already says. A copy says "the n bytes from d back", never where it is, so the stock
    stream after a change still writes the same bytes, only further along, once its copies no longer
    reach back into the change (0x1000 bytes past it). So the groups near a change are taken apart:
    the new bytes go in as plain bytes, and a piece of the stock stream is kept only where it writes
    what the new data has there. That leaves the count of pieces out of step with the stock groups
    that follow, so a few of their copies are cut in two (the same distance, the same bytes written)
    until the pieces fill whole groups again, and from there the stock stream is taken over again.

    The header keeps the stock file's alignment and gives the new size. Check the result as for any
    packing: `decompress(result) == apply_edits(plain, edits)`.

    Args:
        stock: The stock file.
        plain: What it decompresses to.
        edits: (start, end, new bytes) for each stretch of `plain` to replace, in order and apart;
            the new bytes may be of any length, and an edit with no stretch puts bytes in.

    Returns:
        The whole file, header included.

    Raises:
        ValueError: If `stock` is not a Yaz0 file.
    """
    if stock[:4] != MAGIC:
        raise ValueError("not a Yaz0 file")
    size = struct.unpack_from(">I", stock, 4)[0]
    if not edits:
        return bytes(stock)
    new = apply_edits(plain, edits)
    zones = _zones([(start, end) for start, end, _ in edits])
    out = bytearray(stock[:4] + struct.pack(">I", len(new)) + stock[8:HEADER])
    pieces = _Pieces(new, edits, size)
    src, pos, zone = HEADER, 0, 0
    while pos < size:
        end, at = _group_end(stock, src, pos, size)
        while zone < len(zones) and zones[zone][1] <= pos:
            zone += 1
        hot = zone < len(zones) and zones[zone][0] < at
        if not hot and not pieces.queue:
            out += stock[src:end]
        else:
            # Outside the changed places every copy is still true, and there the pieces short of a
            # whole group are made up by cutting copies in two.
            pieces.take_group(stock, src, pos, 0 if hot else (8 - len(pieces.queue)) % 8)
            _flush(pieces.queue, out)
        src, pos = end, at
    pieces.take(size, size, None)  # what an edit puts in at the very end
    _flush(pieces.queue, out, everything=True)
    return bytes(out)


class _Pieces:
    """
    The pieces of a new stream, made from the stock stream's pieces and the edits.

    `take` is handed the stock pieces in order. Where an edit starts it puts in the edit's bytes as
    plain bytes, and it leaves out the stock bytes the edit replaces; a stock piece it keeps if it
    still writes what the new data has there, and the rest become plain bytes of the new data.
    """

    def __init__(self, new: bytes, edits: list[Edit], size: int) -> None:
        self.new, self.edits, self.size = new, edits, size
        self.queue: list[Piece] = []  # pieces waiting for a group
        self.edit = 0  # the first edit not yet put in
        self.skip = 0  # stock bytes before this are replaced by an edit already put in
        # Where a stock position lands in the new data: moved by every edit that ends at or before it.
        self.ends = [end for _, end, _ in edits]
        self.shifts = list(itertools.accumulate(len(body) - (end - start) for start, end, body in edits))

    def moved(self, p: int) -> int:
        """Where stock position `p`, outside the stretches the edits replace, is in the new data."""
        k = bisect.bisect_right(self.ends, p)
        return p + (self.shifts[k - 1] if k else 0)

    def take(self, a: int, b: int, piece: bytes | None) -> None:
        """Add the stock piece that writes stock[a:b]: its two or three bytes, or None for a plain byte."""
        edits = self.edits
        p = a
        while p < b or (self.edit < len(edits) and edits[self.edit][0] == p == b == self.size):
            while self.edit < len(edits) and edits[self.edit][0] <= p:
                _, end, body = edits[self.edit]
                self.queue.extend((True, body[k : k + 1]) for k in range(len(body)))
                self.skip = max(self.skip, end)
                self.edit += 1
            if p >= b:
                break
            if p < self.skip:
                p = min(b, self.skip)
                continue
            q = min(b, edits[self.edit][0]) if self.edit < len(edits) else b
            if piece is not None and (p, q) == (a, b) and self._still_true(a, b, piece):
                self.queue.append((False, piece))
            else:
                at = self.moved(p)
                self.queue.extend((True, self.new[k : k + 1]) for k in range(at, at + q - p))
            p = q

    def _still_true(self, a: int, b: int, piece: bytes) -> bool:
        """Whether the stock copy that writes stock[a:b] writes the same bytes where they now are."""
        distance = ((piece[0] & 0x0F) << 8 | piece[1]) + 1
        at, n = self.moved(a), b - a
        return at - distance >= 0 and self.new[at : at + n] == self.new[at - distance : at - distance + n]

    def take_group(self, stock: bytes, src: int, pos: int, short: int) -> None:
        """Add the pieces of the stock group at `src`, which writes from `pos`, cutting up to `short` copies in two."""
        code = stock[src]
        p, at = src + 1, pos
        for bit in range(7, -1, -1):
            if at >= self.size:
                break
            if code >> bit & 1:
                self.take(at, at + 1, None)
                p += 1
                at += 1
                continue
            if stock[p] >> 4:
                n, length = (stock[p] >> 4) + 2, 2
            else:
                n, length = stock[p + 2] + 0x12, 3
            if short and n >= 6:
                distance = ((stock[p] & 0x0F) << 8 | stock[p + 1]) + 1
                self.queue += [(False, _copy(distance, 3)), (False, _copy(distance, n - 3))]
                short -= 1
            else:
                self.take(at, at + n, stock[p : p + length])
            p += length
            at += n


def _copy(distance: int, n: int) -> bytes:
    """One Yaz0 copy: `n` bytes (3 to 0x111) from `distance` bytes back (1 to 0x1000)."""
    d = distance - 1
    if n >= 0x12:
        return bytes((d >> 8, d & 0xFF, n - 0x12))
    return bytes(((n - 2) << 4 | d >> 8, d & 0xFF))


def _zones(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The stretches of output whose pieces a change can touch, merged where they meet."""
    # A piece at output position p writes [p, p + n) and reads no further back than p - 0x1000.
    zones = []
    for start, end in spans:
        lo, hi = start - LONGEST, end + FURTHEST
        if zones and lo <= zones[-1][1]:
            zones[-1] = (zones[-1][0], hi)
        else:
            zones.append((lo, hi))
    return zones


def _group_end(stock: bytes, src: int, pos: int, size: int) -> tuple[int, int]:
    """Where the group at `src`, which writes from `pos`, ends: in the stream and in the output."""
    code = stock[src]
    if code == 0xFF and pos + 8 <= size:
        return src + 9, pos + 8
    p, at = src + 1, pos
    for bit in range(7, -1, -1):
        if at >= size:
            break
        if code >> bit & 1:
            p += 1
            at += 1
        elif stock[p] >> 4:
            at += (stock[p] >> 4) + 2
            p += 2
        else:
            at += stock[p + 2] + 0x12
            p += 3
    return p, at


def _flush(queue: list[Piece], out: bytearray, *, everything: bool = False) -> None:
    """Move whole groups of eight pieces from the queue to the stream; with `everything`, the rest too."""
    while len(queue) >= 8 or (everything and queue):
        group, code = queue[:8], 0
        del queue[:8]
        for k, (literal, _) in enumerate(group):
            if literal:
                code |= 0x80 >> k
        out.append(code)
        for _, body in group:
            out.extend(body)
