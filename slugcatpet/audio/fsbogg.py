"""把 FSB5 里的 Vorbis 数据原样重新封装成 Ogg，不解码、不依赖原生库。

FSB5 头解析与重建流程改写自 python-fsb5（MIT，见同目录 LICENSE.python-fsb5），
setup 头取自 vorbis_setups（由 tools/gen_vorbis_setups.py 用 libvorbis 生成，BSD，见 LICENSE.libvorbis）。
"""

from __future__ import annotations

import struct
import zlib

VORBIS_FORMAT = 15
_CHUNK_FREQUENCY = 2
_CHUNK_VORBISDATA = 11
_FREQ = {1: 8000, 2: 11000, 3: 11025, 4: 16000, 5: 22050, 6: 24000, 7: 32000, 8: 44100, 9: 48000}
_VENDOR = b"SlugcatPet"
_PAGE_FILL = 4096
FORMAT = 2  # 输出格式版本；变了旧的提取结果会重新生成


def _bits(v, start, n):
    return (v >> start) & ((1 << n) - 1)


def parse_fsb5(data: bytes) -> dict:
    """单样本 FSB5 → {channels, rate, crc32, frames, 包数据}。"""
    if data[:4] != b"FSB5":
        raise ValueError("not FSB5")
    version, nsamples, shdr_size, name_size, data_size, mode = struct.unpack_from("<6I", data, 4)
    if mode != VORBIS_FORMAT:
        raise ValueError(f"not Vorbis (mode {mode})")
    if nsamples != 1:
        raise ValueError(f"expected 1 sample, got {nsamples}")
    pos = 60 + (4 if version == 0 else 0)
    head_end = pos + shdr_size
    (raw,) = struct.unpack_from("<Q", data, pos)
    pos += 8
    more = _bits(raw, 0, 1)
    rate = _FREQ.get(_bits(raw, 1, 4))
    channels = _bits(raw, 5, 1) + 1
    offset = _bits(raw, 6, 28) * 16
    frames = _bits(raw, 34, 30)
    crc = None
    while more:
        (c,) = struct.unpack_from("<I", data, pos)
        pos += 4
        more, size, kind = _bits(c, 0, 1), _bits(c, 1, 24), _bits(c, 25, 7)
        if kind == _CHUNK_FREQUENCY:
            (rate,) = struct.unpack_from("<I", data, pos)
        elif kind == _CHUNK_VORBISDATA:
            (crc,) = struct.unpack_from("<I", data, pos)
        pos += size
    if crc is None or rate is None:
        raise ValueError("missing vorbis/frequency info")
    start = head_end + name_size + offset
    return {
        "channels": channels,
        "rate": rate,
        "crc32": crc,
        "frames": frames,
        "data": data[start : start + data_size - offset],
    }


# Ogg 的 CRC（多项式 0x04C11DB7、非反射、初值 0）= 字节位反转后的 zlib CRC 再整体位反转
_REV = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))


def _ogg_crc(buf: bytes) -> int:
    raw = zlib.crc32(buf.translate(_REV), 0xFFFFFFFF) ^ 0xFFFFFFFF
    return int(f"{raw:032b}"[::-1], 2)


class _OggStream:
    """按 libogg 的分页规则写页（同样输入得到同样字节）"""

    def __init__(self, serial: int):
        self.serial, self.seq = serial, 0
        self.lacing: list[int] = []  # 段长，0x100 标记包首段
        self.granules: list[int] = []
        self.body = bytearray()
        self.bos = self.eos = False
        self.out = bytearray()

    def packetin(self, pkt: bytes, granule: int, eos: bool = False):
        n = len(pkt) // 255 + 1
        start = len(self.lacing)
        self.lacing += [255] * (n - 1) + [len(pkt) % 255]
        self.granules += [granule] * n
        self.lacing[start] |= 0x100
        self.body += pkt
        self.eos = self.eos or eos

    def pageout(self, force: bool = False):
        while self._page(force or (self.eos and self.lacing) or (self.lacing and not self.bos)):
            pass

    def _page(self, force) -> bool:
        maxvals = min(len(self.lacing), 255)
        if not maxvals:
            return False
        granule, acc, vals = -1, 0, 0
        if not self.bos:
            granule = 0
            for vals in range(maxvals):
                if (self.lacing[vals] & 0xFF) < 255:
                    vals += 1
                    break
            else:
                vals = maxvals
        else:
            done = just = 0
            for vals in range(maxvals + 1):
                if vals == maxvals:
                    break
                if acc > _PAGE_FILL and just >= 4:
                    force = True
                    break
                acc += self.lacing[vals] & 0xFF
                if (self.lacing[vals] & 0xFF) < 255:
                    granule = self.granules[vals]
                    done += 1
                    just = done
                else:
                    just = 0
            if vals == 255:
                force = True
        if not force:
            return False
        flags = (0 if self.lacing[0] & 0x100 else 1) | (0 if self.bos else 2)
        if self.eos and len(self.lacing) == vals:
            flags |= 4
        self.bos = True
        segs = bytes(v & 0xFF for v in self.lacing[:vals])
        size = sum(segs)
        head = bytearray(
            b"OggS\x00"
            + bytes([flags])
            + struct.pack("<qIII", granule, self.serial, self.seq, 0)
            + bytes([vals])
            + segs
        )
        body = bytes(self.body[:size])
        struct.pack_into("<I", head, 22, _ogg_crc(bytes(head) + body))
        self.out += head + body
        self.seq += 1
        del self.lacing[:vals], self.granules[:vals], self.body[:size]
        return True


def _id_header(channels, rate, short, long_) -> bytes:
    exp = (short.bit_length() - 1) | ((long_.bit_length() - 1) << 4)
    return b"\x01vorbis" + struct.pack("<IBIiiiBB", 0, channels, rate, 0, 0, 0, exp, 1)


def _comment_header() -> bytes:
    return b"\x03vorbis" + struct.pack("<I", len(_VENDOR)) + _VENDOR + struct.pack("<I", 0) + b"\x01"


def fsb_to_ogg(data: bytes) -> bytes:
    """FSB5（单个 Vorbis 样本）→ 完整 Ogg 文件字节；setup 头未知时抛 ValueError。"""
    from .vorbis_setups import SETUPS

    s = parse_fsb5(data)
    info = SETUPS.get(s["crc32"])
    if info is None:
        raise ValueError(f"unknown vorbis setup crc32={s['crc32']}")
    short, long_, setup, modes = info
    if zlib.crc32(setup) != s["crc32"]:
        raise ValueError("setup header mismatch")
    st = _OggStream(1)
    st.packetin(_id_header(s["channels"], s["rate"], short, long_), 0)
    st.pageout()
    st.packetin(_comment_header(), 0)
    st.packetin(setup, 0)
    st.pageout(force=True)
    body, pos, granule, prev = s["data"], 0, 0, 0
    size = struct.unpack_from("<H", body, 0)[0] if len(body) >= 2 else 0
    while size:
        pkt = body[pos + 2 : pos + 2 + size]
        pos += 2 + size
        size = struct.unpack_from("<H", body, pos)[0] if pos + 2 <= len(body) else 0
        flag = modes[(pkt[0] >> 1) & 0x7F] if pkt else "x"
        if flag == "x" or pkt[0] & 1:
            raise ValueError("bad audio packet")
        block = long_ if flag == "1" else short
        granule = granule + (block + prev) // 4 if prev else 0
        prev = block
        st.packetin(pkt, granule, eos=not size)
        st.pageout()
    return bytes(st.out)
