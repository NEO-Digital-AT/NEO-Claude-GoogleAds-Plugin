#!/usr/bin/env python3
"""A QR encoder, because two-factor setup without one is a typing exercise.

Every authenticator app scans a code. The alternative — reading a
thirty-two character secret off the screen and typing it into a phone — is
where people give up, and a security feature people give up on is not a
security feature.

The obvious way to get a QR code is a library. This repository does not
take dependencies: a tool has to run in a stranger's CI without an install
step. So the encoder is here, in the standard library only, and it is
narrow on purpose:

    byte mode only          an otpauth:// URI is bytes, nothing else
    error level M           the usual choice, ~15 % recoverable
    versions 1 to 12        up to 290 data codewords, far past our ~120

It implements ISO/IEC 18004: Reed-Solomon over GF(256), the eight data
masks with the four penalty rules, and the BCH-protected format and
version blocks. Verified against an independent encoder — see the self
test, group 'qr code'.

    svg(matrix(b"otpauth://totp/...")) -> an <svg> element, no image file
"""
from __future__ import annotations

# Error correction level M, versions 1..12:
#   (codewords per block for EC, blocks in group 1, data per block in
#    group 1, blocks in group 2, data per block in group 2)
BLOCKS_M: dict[int, tuple[int, int, int, int, int]] = {
    1: (10, 1, 16, 0, 0), 2: (16, 1, 28, 0, 0), 3: (26, 1, 44, 0, 0),
    4: (18, 2, 32, 0, 0), 5: (24, 2, 43, 0, 0), 6: (16, 4, 27, 0, 0),
    7: (18, 4, 31, 0, 0), 8: (22, 2, 38, 2, 39), 9: (22, 3, 36, 2, 37),
    10: (26, 4, 43, 1, 44), 11: (30, 1, 50, 4, 51), 12: (22, 6, 36, 2, 37),
}

# Centres of the alignment patterns, per version.
ALIGNMENT: dict[int, list[int]] = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
    7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
    11: [6, 30, 54], 12: [6, 32, 58],
}

EC_INDICATOR_M = 0b00      # The level, as the format block spells it.
PAD_BYTES = (0xEC, 0x11)   # The alternating filler the standard prescribes.

_EXP = [0] * 512
_LOG = [0] * 256


def _build_tables() -> None:
    """Logarithm tables for GF(256), primitive polynomial 0x11D."""
    value = 1
    for power in range(255):
        _EXP[power] = value
        _LOG[value] = power
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for power in range(255, 512):
        _EXP[power] = _EXP[power - 255]


_build_tables()


def _poly_multiply(left: list[int], right: list[int]) -> list[int]:
    out = [0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        if not a:
            continue
        for j, b in enumerate(right):
            if b:
                out[i + j] ^= _EXP[(_LOG[a] + _LOG[b]) % 255]
    return out


def _generator(count: int) -> list[int]:
    """(x - a^0)(x - a^1)...(x - a^(count-1)), the RS generator polynomial."""
    poly = [1]
    for power in range(count):
        poly = _poly_multiply(poly, [1, _EXP[power]])
    return poly


def _error_codewords(data: list[int], count: int) -> list[int]:
    generator = _generator(count)
    rest = list(data) + [0] * count
    for i in range(len(data)):
        lead = rest[i]
        if not lead:
            continue
        shift = _LOG[lead]
        for j, factor in enumerate(generator):
            rest[i + j] ^= _EXP[(_LOG[factor] + shift) % 255]
    return rest[len(data):]


def _capacity(version: int) -> int:
    """How many payload bytes fit, after mode and length have taken theirs."""
    ec, g1, d1, g2, d2 = BLOCKS_M[version]
    total = g1 * d1 + g2 * d2
    header_bits = 4 + (8 if version < 10 else 16)
    return total - (header_bits + 7) // 8


def _pick_version(length: int) -> int:
    for version in sorted(BLOCKS_M):
        if length <= _capacity(version):
            return version
    raise ValueError(f"{length} bytes do not fit in a version 12 code")


def _bitstream(payload: bytes, version: int) -> list[int]:
    """Mode, length, payload, terminator, padding — as a list of codewords."""
    ec, g1, d1, g2, d2 = BLOCKS_M[version]
    total = g1 * d1 + g2 * d2
    count_bits = 8 if version < 10 else 16

    bits: list[int] = [0, 1, 0, 0]                       # byte mode
    bits += [(len(payload) >> shift) & 1 for shift in range(count_bits - 1, -1, -1)]
    for byte in payload:
        bits += [(byte >> shift) & 1 for shift in range(7, -1, -1)]

    bits += [0] * min(4, total * 8 - len(bits))          # terminator
    bits += [0] * (-len(bits) % 8)                       # to a byte boundary

    words = [int("".join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    first_pad = len(words)
    while len(words) < total:
        words.append(PAD_BYTES[(len(words) - first_pad) % 2])
    return words


def _interleave(words: list[int], version: int) -> list[int]:
    """Splits into blocks, computes each block's EC, then interleaves both."""
    ec, g1, d1, g2, d2 = BLOCKS_M[version]
    blocks: list[list[int]] = []
    at = 0
    for _ in range(g1):
        blocks.append(words[at:at + d1])
        at += d1
    for _ in range(g2):
        blocks.append(words[at:at + d2])
        at += d2
    checks = [_error_codewords(block, ec) for block in blocks]

    out: list[int] = []
    for i in range(max(len(b) for b in blocks)):
        for block in blocks:
            if i < len(block):
                out.append(block[i])
    for i in range(ec):
        for check in checks:
            out.append(check[i])
    return out


def _empty(version: int) -> tuple[list[list[int | None]], list[list[bool]]]:
    """A blank grid plus a map of the squares the data must not touch."""
    size = version * 4 + 17
    grid: list[list[int | None]] = [[None] * size for _ in range(size)]
    fixed = [[False] * size for _ in range(size)]

    def place(top: int, left: int, pattern: list[list[int]]) -> None:
        for dy, row in enumerate(pattern):
            for dx, value in enumerate(row):
                y, x = top + dy, left + dx
                if 0 <= y < size and 0 <= x < size:
                    grid[y][x] = value
                    fixed[y][x] = True

    finder = [[1, 1, 1, 1, 1, 1, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 1, 1, 1, 0, 1],
              [1, 0, 1, 1, 1, 0, 1], [1, 0, 1, 1, 1, 0, 1], [1, 0, 0, 0, 0, 0, 1],
              [1, 1, 1, 1, 1, 1, 1]]
    for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
        place(top, left, finder)

    def clear(cells) -> None:
        """The separator: the light border between a finder and the data."""
        for y, x in cells:
            if 0 <= y < size and 0 <= x < size:
                grid[y][x] = 0
                fixed[y][x] = True

    clear([(7, x) for x in range(8)] + [(y, 7) for y in range(8)])
    clear([(7, x) for x in range(size - 8, size)]
          + [(y, size - 8) for y in range(8)])
    clear([(size - 8, x) for x in range(8)]
          + [(y, 7) for y in range(size - 8, size)])

    for i in range(8, size - 8):                        # timing patterns
        grid[6][i] = 1 if i % 2 == 0 else 0
        fixed[6][i] = True
        grid[i][6] = 1 if i % 2 == 0 else 0
        fixed[i][6] = True

    centres = ALIGNMENT[version]
    pattern = [[1, 1, 1, 1, 1], [1, 0, 0, 0, 1], [1, 0, 1, 0, 1],
               [1, 0, 0, 0, 1], [1, 1, 1, 1, 1]]
    for cy in centres:
        for cx in centres:
            if (cy, cx) in ((6, 6), (6, centres[-1]), (centres[-1], 6)):
                continue                                # would sit on a finder
            place(cy - 2, cx - 2, pattern)

    # The always-dark module is reserved here but written with the format
    # block, because the mask is scored before either of them exists.
    grid[size - 8][8] = 0
    fixed[size - 8][8] = True

    for i in range(9):                                  # reserved: format blocks
        for y, x in ((8, i), (i, 8)):
            if 0 <= y < size and 0 <= x < size and not fixed[y][x]:
                fixed[y][x] = True
                grid[y][x] = 0
    for i in range(8):
        for y, x in ((8, size - 1 - i), (size - 1 - i, 8)):
            if not fixed[y][x]:
                fixed[y][x] = True
                grid[y][x] = 0
    if version >= 7:                                    # reserved: version blocks
        for i in range(6):
            for j in range(3):
                for y, x in ((i, size - 11 + j), (size - 11 + j, i)):
                    fixed[y][x] = True
                    grid[y][x] = 0
    return grid, fixed


def _place_data(grid, fixed, words: list[int]) -> None:
    """The zigzag walk: two columns at a time, upward then downward."""
    size = len(grid)
    bits = [(word >> shift) & 1 for word in words for shift in range(7, -1, -1)]
    at = 0
    column = size - 1
    upward = True
    while column > 0:
        if column == 6:                                 # the timing column is skipped
            column -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for x in (column, column - 1):
                if not fixed[row][x]:
                    grid[row][x] = bits[at] if at < len(bits) else 0
                    at += 1
        upward = not upward
        column -= 2


def _masked(value: int, row: int, col: int) -> bool:
    if value == 0:
        return (row + col) % 2 == 0
    if value == 1:
        return row % 2 == 0
    if value == 2:
        return col % 3 == 0
    if value == 3:
        return (row + col) % 3 == 0
    if value == 4:
        return (row // 2 + col // 3) % 2 == 0
    if value == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if value == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


def _penalty(grid) -> int:
    """The four rules that decide which mask reads most reliably."""
    size = len(grid)
    score = 0

    for line in list(grid) + [list(column) for column in zip(*grid)]:
        run, previous = 1, line[0]
        for value in line[1:]:
            if value == previous:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run, previous = 1, value
        if run >= 5:
            score += 3 + (run - 5)

    for row in range(size - 1):                         # 2x2 blocks of one colour
        for col in range(size - 1):
            block = (grid[row][col], grid[row][col + 1],
                     grid[row + 1][col], grid[row + 1][col + 1])
            if block[0] == block[1] == block[2] == block[3]:
                score += 3

    # The 1:1:3:1:1 pattern, counted when a light area of up to four modules
    # sits on either side of it, or when it touches the edge of the symbol.
    pattern = [1, 0, 1, 1, 1, 0, 1]
    for line in list(grid) + [list(column) for column in zip(*grid)]:
        at = 0
        while at <= size - 7:
            if line[at:at + 7] != pattern:
                at += 1
                continue
            if (at in (0, size - 7)
                    or not any(line[max(at - 4, 0):at])
                    or not any(line[at + 7:at + 11])):
                score += 40
                at += 7
            else:
                # Not enough light around it. The next possible match starts
                # at the middle dark run, not one module along.
                at += 4

    dark = sum(sum(row) for row in grid)
    percent = dark * 100 / (size * size)
    score += 10 * int(abs(percent - 50) // 5)
    return score


def _format_bits(mask: int) -> list[int]:
    value = (EC_INDICATOR_M << 3) | mask
    remainder = value << 10
    while remainder.bit_length() >= 11:
        remainder ^= 0b10100110111 << (remainder.bit_length() - 11)
    bits = ((value << 10) | remainder) ^ 0b101010000010010
    # Most significant first: entry 0 is the bit the placement table puts first.
    return [(bits >> shift) & 1 for shift in range(14, -1, -1)]


def _version_bits(version: int) -> list[int]:
    remainder = version << 12
    while remainder.bit_length() >= 13:
        remainder ^= 0b1111100100101 << (remainder.bit_length() - 13)
    bits = (version << 12) | remainder
    return [(bits >> shift) & 1 for shift in range(18)]


def _write_format(grid, mask: int) -> None:
    size = len(grid)
    grid[size - 8][8] = 1                               # the always-dark module
    bits = _format_bits(mask)
    # Copy one: around the top-left finder, skipping the timing row and column.
    # Position k in this list takes format bit k, least significant first.
    positions = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
                 (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    for bit, (row, col) in zip(bits, positions):
        grid[row][col] = bit
    # Copy two: split between the other two finders.
    for i in range(7):
        grid[size - 1 - i][8] = bits[i]
    for i in range(8):
        grid[8][size - 8 + i] = bits[7 + i]


def _write_version(grid, version: int) -> None:
    if version < 7:
        return
    size = len(grid)
    bits = _version_bits(version)
    for i in range(18):
        row, col = i // 3, i % 3
        grid[row][size - 11 + col] = bits[i]
        grid[size - 11 + col][row] = bits[i]


def matrix(payload: bytes) -> list[list[int]]:
    """The finished grid: 1 is a dark module, 0 a light one."""
    version = _pick_version(len(payload))
    words = _interleave(_bitstream(payload, version), version)

    def with_mask(mask: int):
        grid, fixed = _empty(version)
        _place_data(grid, fixed, words)
        for row in range(len(grid)):
            for col in range(len(grid)):
                if not fixed[row][col] and _masked(mask, row, col):
                    grid[row][col] ^= 1
        return grid

    # Scored before the format and version blocks go in: those squares are
    # not part of the data region, and counting them would let the level
    # indicator decide the mask. On a tie the lower mask number wins.
    best_mask, best_score = 0, None
    for mask in range(8):
        score = _penalty(with_mask(mask))
        if best_score is None or score < best_score:
            best_mask, best_score = mask, score

    grid = with_mask(best_mask)
    _write_format(grid, best_mask)
    _write_version(grid, version)
    return grid


def svg(grid: list[list[int]], *, quiet: int = 4, scale: int = 5) -> str:
    """One <svg> element, drawn as a single path. No image file, no request."""
    size = len(grid)
    span = size + quiet * 2
    runs = []
    for row in range(size):
        col = 0
        while col < size:
            if grid[row][col]:
                start = col
                while col < size and grid[row][col]:
                    col += 1
                runs.append(f"M{start + quiet} {row + quiet}h{col - start}v1h-{col - start}z")
            else:
                col += 1
    path = "".join(runs)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {span} {span}" '
            f'width="{span * scale}" height="{span * scale}" shape-rendering="crispEdges" '
            f'role="img" aria-label="QR-Code zum Einrichten der Zwei-Faktor-Anmeldung">'
            f'<rect width="{span}" height="{span}" fill="#fff"/>'
            f'<path d="{path}" fill="#000"/></svg>')
