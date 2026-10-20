"""EWB 5.x .ewb payload codec (outer pair encoding + EWB variant of DCL).

Container format (EncryptionType: 2)
------------------------------------
    <plain text header with CRLF lines>
    /<pair-encoded payload>

Header lines:
    Electronics Workbench Circuit File
    Version: 5
    Charset: ANSI
    Description:
    "<description>" 
    (blank line)
    EncryptionType: 2
    UsingVectorGraphics: 0
    /                       <- slash is the last byte of the header, no newline after

Payload:
    Each compressed block is written as two chars per byte:
        c1 = (b >> 3) + 0x30
        c2 = 4 * (b & 7) + 0x30
    A '$' (0x24) follows *every* block (including the last).
    '!' (0x21) terminates the encoded stream.
    Then 8 lowercase hex digits: checksum.
    A '\n' is inserted after every 65 output characters of the whole
    sequence (including '$', '!' and the checksum digits).  There is no
    trailing newline at EOF.

Checksum:
    split the *uncompressed* document into 1024-byte chunks; for each
    chunk compute CRC-32 (reflected, poly 0xEDB88320) with initial value
    0xFFFFFFFF and no final xor; the checksum is the XOR of the bitwise
    complement of each chunk CRC, printed as %08x.

Compressed block:
    2 header bytes: literal mode (0) and dictionary code (4..6).
    Bits are LSB-first.  flag 0 -> literal: 8 data bits.
    flag 1 -> length code from the 16-symbol table; EOB is length 519
    (symbol 15 + 8 extra bits = 0xFF, i.e. bits 1, 0000000, 11111111).
"""

LEN_LENGTHS = [3, 2, 3, 3, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 7, 7]
LEN_START   = [5, 3, 1, 6, 10, 2, 12, 20, 4, 24, 8, 48, 16, 32, 64, 0]
LEN_EXTRA   = [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8]
LEN_BASE    = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 14, 22, 38, 70, 134, 262]
DIST_LENGTHS = [2, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
                6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
                7, 7, 7, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8,
                8, 8, 8, 8]
DIST_START   = [3, 13, 5, 25, 9, 17, 1, 62, 30, 46, 14, 54, 22, 38, 6, 58,
                26, 42, 10, 50, 18, 34, 66, 2, 124, 60, 92, 28, 108, 44, 76,
                12, 116, 52, 84, 20, 100, 36, 68, 4, 120, 56, 88, 24, 104,
                40, 72, 8, 240, 112, 176, 48, 208, 80, 144, 16, 224, 96, 160,
                32, 192, 64, 128, 0]
END_LENGTH = 519
BLOCK_SIZE = 1024


def build_table(lengths, starts, n):
    tab = bytearray(256)
    for i in range(n - 1, -1, -1):
        l = lengths[i]
        j = starts[i]
        while j < 256:
            tab[j] = i
            j += 1 << l
    return bytes(tab)


LEN_TAB = build_table(LEN_LENGTHS, LEN_START, 16)
DIST_TAB = build_table(DIST_LENGTHS, DIST_START, 64)


class Bits:
    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos
        self.buf = 0
        self.n = 0

    def _fill(self, n):
        while self.n < n:
            if self.pos >= len(self.data):
                return False
            self.buf |= self.data[self.pos] << self.n
            self.pos += 1
            self.n += 8
        return True

    def peek(self, n):
        if not self._fill(n):
            return None
        return self.buf & ((1 << n) - 1)

    def skip(self, n):
        if not self._fill(n):
            return False
        self.buf >>= n
        self.n -= n
        return True


def explode_block(data):
    """Decode one EWB-compressed block to its uncompressed bytes."""
    if len(data) < 3:
        raise ValueError('short block')
    lit_mode, dict_code = data[0], data[1]
    if lit_mode not in (0, 1):
        raise ValueError('lit mode %d' % lit_mode)
    if dict_code < 4 or dict_code > 6:
        raise ValueError('dict %d' % dict_code)
    br = Bits(data, 2)
    out = bytearray()
    while True:
        flag = br.peek(1)
        if flag is None:
            break
        br.skip(1)
        if flag:
            v = br.peek(8)
            if v is None:
                break
            sym = LEN_TAB[v]
            if not br.skip(LEN_LENGTHS[sym]):
                break
            extra = LEN_EXTRA[sym]
            low = br.peek(extra) if extra else 0
            if low is None:
                break
            if extra and not br.skip(extra):
                break
            length = 2 + LEN_BASE[sym] + low
            if length == END_LENGTH:
                break
            dv = br.peek(8)
            if dv is None:
                break
            dsym = DIST_TAB[dv]
            if not br.skip(DIST_LENGTHS[dsym]):
                break
            nbits = 2 if length == 2 else dict_code
            dlow = br.peek(nbits)
            if dlow is None:
                break
            if not br.skip(nbits):
                break
            dist = ((dsym << nbits) | dlow) + 1
            if dist > len(out):
                raise ValueError('distance %d > output %d' % (dist, len(out)))
            for _ in range(length):
                out.append(out[-dist])
        else:
            b = br.peek(8)
            if b is None:
                break
            br.skip(8)
            out.append(b)
    return bytes(out)


class BitWriter:
    def __init__(self):
        self.out = bytearray()
        self.cur = 0
        self.n = 0

    def put(self, value, nbits):
        for i in range(nbits):
            self.cur |= ((value >> i) & 1) << self.n
            self.n += 1
            if self.n == 8:
                self.out.append(self.cur)
                self.cur = 0
                self.n = 0

    def finish(self):
        if self.n:
            self.out.append(self.cur)
            self.cur = 0
            self.n = 0
        return bytes(self.out)



# ------------------------------------------------------------- LZ compressor
# Canonical code values recovered from the decode tables above.  A code is
# written LSB-first with the given bit length.
_LEN_CODE = {}
for _v in range(256):
    _s = LEN_TAB[_v]
    _LEN_CODE.setdefault(_s, _v & ((1 << LEN_LENGTHS[_s]) - 1))
_DIST_CODE = {}
for _v in range(256):
    _s = DIST_TAB[_v]
    _DIST_CODE.setdefault(_s, _v & ((1 << DIST_LENGTHS[_s]) - 1))


def _length_symbol(length):
    for sym in range(15, -1, -1):
        base = 2 + LEN_BASE[sym]
        span = 1 << LEN_EXTRA[sym]
        if base <= length < base + span:
            return sym, length - base
    raise ValueError("length %d cannot be encoded" % length)


def _distance_symbol(distance, nbits):
    value = distance - 1
    sym = value >> nbits
    low = value & ((1 << nbits) - 1)
    if sym > 63:
        raise ValueError("distance %d cannot be encoded with %d extra bits"
                         % (distance, nbits))
    return sym, low


def _find_match(data, i, positions, max_len):
    """Longest match for data[i:] in the previous 1024 bytes, length >= 3."""
    if i + 3 > len(data):
        return 0, 0
    key = data[i:i + 3]
    best_len = 0
    best_dist = 0
    candidates = positions.get(key)
    if not candidates:
        return 0, 0
    for j in reversed(candidates):
        if j >= i:
            continue
        dist = i - j
        if dist > 1024:
            break
        limit = min(max_len, len(data) - i)
        length = 3
        while length < limit and data[j + length] == data[i + length]:
            length += 1
        if length > best_len or (length == best_len and dist < best_dist):
            best_len = length
            best_dist = dist
            if length == limit:
                break
    return best_len, best_dist


def compress_lz_block(data):
    """Greedy LZ77 block encoder for the EWB (PKWARE implode) stream."""
    if not data:
        return compress_literal_block(data)
    positions = {}
    for i in range(0, max(0, len(data) - 2)):
        positions.setdefault(data[i:i + 3], []).append(i)
    bw = BitWriter()
    i = 0
    n = len(data)
    while i < n:
        max_len = min(518, n - i)
        length, dist = _find_match(data, i, positions, max_len)
        if length >= 3:
            sym, low = _length_symbol(length)
            bw.put(1, 1)
            bw.put(_LEN_CODE[sym], LEN_LENGTHS[sym])
            if LEN_EXTRA[sym]:
                bw.put(low, LEN_EXTRA[sym])
            nbits = 2 if length == 2 else 4
            dsym, dlow = _distance_symbol(dist, nbits)
            bw.put(_DIST_CODE[dsym], DIST_LENGTHS[dsym])
            bw.put(dlow, nbits)
            i += length
        else:
            bw.put(0, 1)
            bw.put(data[i], 8)
            i += 1
    # End-of-block: length code 15 with 8 extra bits set to 255.
    bw.put(1, 1)
    bw.put(_LEN_CODE[15], LEN_LENGTHS[15])
    bw.put(255, 8)
    return bytes((0, 4)) + bw.finish()

def compress_literal_block(data):
    """Encode a block using literal mode only (valid EWB DCL stream)."""
    bw = BitWriter()
    for b in data:
        bw.put(0, 1)
        bw.put(b, 8)
    bw.put(1, 1)
    bw.put(0, 7)
    bw.put(0xFF, 8)
    return bytes((0, 4)) + bw.finish()


def compress_document(doc):
    """Split document into 1024-byte chunks and compress each one."""
    return [compress_lz_block(doc[i:i + BLOCK_SIZE])
            for i in range(0, len(doc), BLOCK_SIZE)] or [compress_lz_block(b'')]


# ---------------------------------------------------------------- checksum

CRCTAB = []
for _n in range(256):
    _c = _n
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    CRCTAB.append(_c)


def crc_update(state, data):
    for b in data:
        state = (state >> 8) ^ CRCTAB[(state ^ b) & 0xFF]
    return state


def document_checksum(doc):
    acc = 0
    for off in range(0, len(doc), BLOCK_SIZE):
        chunk = doc[off:off + BLOCK_SIZE]
        acc ^= (~crc_update(0xFFFFFFFF, chunk)) & 0xFFFFFFFF
    return acc


# ------------------------------------------------------------ outer layer

def decode_payload(raw):
    """Split the encoded payload into compressed blocks.

    Whitespace (CR/LF) is removed *before* pairing, because a newline may
    fall between the two characters of a pair.
    """
    clean = bytes(b for b in raw if b not in (10, 13))
    blocks = []
    cur = bytearray()
    i = 0
    n = len(clean)
    while i < n:
        c = clean[i]
        if c == 0x21:
            break
        if c == 0x24:
            blocks.append(bytes(cur))
            cur = bytearray()
            i += 1
            continue
        if i + 1 >= n:
            raise ValueError('odd number of encoded characters')
        c2 = clean[i + 1]
        if not (0x30 <= c <= 0x50 and 0x30 <= c2 <= 0x4C and (c2 - 0x30) % 4 == 0):
            raise ValueError('invalid encoded pair %02x %02x at %d' % (c, c2, i))
        cur.append((8 * (c - 0x30) + ((c2 - 0x30) >> 2)) & 0xFF)
        i += 2
    return blocks


def encode_payload(blocks, checksum):
    """Encode compressed blocks, separator, terminator and checksum."""
    chars = []
    for b in blocks:
        for x in b:
            chars.append(chr((x >> 3) + 0x30))
            chars.append(chr(4 * (x & 7) + 0x30))
        chars.append('$')
    chars.append('!')
    chars.extend('%08x' % checksum)
    out = []
    col = 0
    for ch in chars:
        out.append(ch)
        col += 1
        if col == 65:
            out.append('\n')
            col = 0
    return ''.join(out)


def split_file(raw):
    """Return (header, blocks, plains, document, checksum)."""
    k = raw.find(b'\r\n/')
    if k < 0:
        raise ValueError('payload marker not found')
    header = raw[:k + 3]
    j = raw.find(b'!', k + 3)
    if j < 0:
        raise ValueError('terminator not found')
    blocks = decode_payload(raw[k + 3:j])
    plains = [explode_block(b) for b in blocks]
    doc = b''.join(plains)
    digits = bytes(x for x in raw[j + 1:j + 16] if x not in (10, 13))[:8]
    try:
        checksum = int(digits, 16)
    except ValueError:
        raise ValueError('bad checksum digits %r' % digits)
    return header, blocks, plains, doc, checksum


def make_header(description='', version='5', charset='ANSI',
                encryption_type=2, vector_graphics=0):
    esc = description.replace('\r', ' ').replace('\n', ' ')
    return ("Electronics Workbench Circuit File\r\n"
            "Version: %s\r\n"
            "Charset: %s\r\n"
            "Description: \r\n"
            "\"%s\" \r\n"
            "\r\n"
            "EncryptionType: %d\r\n"
            "UsingVectorGraphics: %d\r\n"
            "/" % (version, charset, esc, encryption_type, vector_graphics)).encode('latin1')


def build_ewb(document, header=None, description=''):
    if header is None:
        header = make_header(description)
    blocks = compress_document(document)
    checksum = document_checksum(document)
    return header + encode_payload(blocks, checksum).encode('latin1')


def read_ewb(path):
    raw = open(path, 'rb').read()
    header, blocks, plains, doc, checksum = split_file(raw)
    return {
        'header': header,
        'blocks': blocks,
        'plains': plains,
        'document': doc,
        'checksum': checksum,
        'raw': raw,
    }


def write_ewb(path, document, header=None, description=''):
    data = build_ewb(document, header=header, description=description)
    with open(path, 'wb') as f:
        f.write(data)
    return data


def rebuild_from_blocks(header, blocks, checksum):
    return header + encode_payload(blocks, checksum).encode('latin1')


if __name__ == '__main__':
    import sys
    info = read_ewb(sys.argv[1])
    sys.stdout.write(info['document'].decode('latin1'))
