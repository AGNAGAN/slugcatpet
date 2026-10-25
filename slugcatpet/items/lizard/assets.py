"""蜥蜴音效素材：从玩家本机的游戏资源包提取到 assets/lizard。"""

from __future__ import annotations

from pathlib import Path

from ..._paths import assets_dir
from ...gameassets import _SFX_BUNDLES, _bundle_clips, _extract_sfx, _sfx_missing

# Vorbis 编码的片段（其余是 PCM）：提取时先封成 ogg 再解码成 wav，setup 头由 tools/gen_vorbis_setups.py 生成
LIZARD_VORBIS_SOUNDS = (
    "LizardVoiceCyanA",
    "LizardVoiceCyanB",
    "LizardVoiceCyanC",
    "LizardVoiceRedA",
    "LizardVoiceWhiteA",
    "LizardVoiceWhiteB",
    "LizardVoiceWhiteC",
)
LIZARD_SOUNDS = (
    "Clang1A",
    "Clang1G",
    "Clang1H",
    "Clang2A",
    "CoralBreakA_7",
    "CyanChargeL",
    "CyanChargeM",
    "CyanChargeSm",
    "Flip3C",
    "LizardVoiceBlueA",
    "LizardVoiceCyanA",
    "LizardVoiceCyanB",
    "LizardVoiceCyanC",
    "LizardVoiceGreenA",
    "LizardVoicePinkA",
    "LizardVoicePinkB",
    "LizardVoicePinkC",
    "LizardVoicePinkD",
    "LizardVoicePinkE",
    "LizardVoiceRedA",
    "LizardVoiceWhiteA",
    "LizardVoiceWhiteB",
    "LizardVoiceWhiteC",
    "Squish1A",
    "Squish1B",
    "Squish2G",
    "Squish2I",
    "VultureJetLOOP2",
    "Wobble1A",
    "bassOnly",
    "gravel1A",
    "gravel1B",
    "gravel1C",
    "gravel1D",
    "gravel1E",
    "gravel1F",
    "gravel1G",
    "gravel1H",
    "gravel1K",
    "gravel1N",
    "lizBite2A",
    "lizBite2B",
    "lizBite2C",
    "lizBite2D",
    "lizBite2E",
    "lizBite2F",
    "lizBite2G",
    "lizBite3A",
    "lizBite3B",
    "lizBite3C",
    "lizBite3D",
    "lizBite3E",
    "lizBite3F",
    "lizBite3G",
    "lizCharge1A",
    "lizCharge1B",
    "lizCharge1C",
    "lizCharge1D",
    "lizCharge1E",
    "lizSpit1A",
    "lizSpit1B",
    "lizSpit1C",
    "lizSpit1D",
    "lizSpit1E",
    "lizSpit1G",
    "lizSpit1H",
    "puffA_1",
    "puffA_2",
    "puffA_3",
    "puffA_4",
    "thuds1A",
    "thuds1C",
    "thuds1D",
    "thuds1E",
)


def lizard_sounds_dir() -> Path:
    return assets_dir() / "lizard"


def lizard_sounds_missing() -> list[str]:
    d = lizard_sounds_dir()
    pcm = tuple(n for n in LIZARD_SOUNDS if n not in LIZARD_VORBIS_SOUNDS)
    vorbis = [n for n in LIZARD_VORBIS_SOUNDS if not (d / f"{n}.wav").is_file()]
    return _sfx_missing(pcm, d) + vorbis


def decode_ogg_to_wav(ogg: Path, wav: Path) -> None:
    """用 Qt 的 QAudioDecoder 把 ogg 解成 16 位 PCM 写成 wav；要有 QCoreApplication，同步等到解完。"""
    import wave

    import numpy as np
    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

    fmt = QAudioFormat()
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    dec = QAudioDecoder()
    dec.setAudioFormat(fmt)
    dec.setSource(QUrl.fromLocalFile(str(ogg)))
    chunks, info = [], []
    loop = QEventLoop()

    def on_ready():
        while dec.bufferAvailable():
            b = dec.read()
            f = b.format()
            info[:] = [f.sampleRate(), f.channelCount()]
            raw = bytes(b.constData())
            if f.sampleFormat() == QAudioFormat.SampleFormat.Float:  # 后端不一定遵守 Int16 的请求
                raw = (np.clip(np.frombuffer(raw, "<f4"), -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
            chunks.append(raw)

    dec.bufferReady.connect(on_ready)
    dec.finished.connect(loop.quit)
    dec.error.connect(loop.quit)
    QTimer.singleShot(15000, loop.quit)
    dec.start()
    loop.exec()
    dec.stop()
    if not chunks or not info:
        raise ValueError("ogg 解码失败")
    tmp = wav.with_suffix(".wav.part")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(info[1])
        w.setsampwidth(2)
        w.setframerate(info[0])
        w.writeframes(b"".join(chunks))
    tmp.replace(wav)


def extract_lizard_sounds(install: Path) -> list[str]:
    """蜥蜴的叫声与咬、撞击等音效；返回这次写出的片名。在引导面板的后台线程里跑，要有 QCoreApplication。

    PCM 片段直接封成 wav；Vorbis 片段先封成 ogg，再用 Qt 解码成 wav（要有 QCoreApplication），ogg 随后删掉。
    """
    from ...audio.fsbogg import fsb_to_ogg

    d = lizard_sounds_dir()
    todo = lizard_sounds_missing()
    done = _extract_sfx(install, [n for n in todo if n not in LIZARD_VORBIS_SOUNDS], d)
    vorbis = [n for n in todo if n in LIZARD_VORBIS_SOUNDS]
    need = [n for n in vorbis if not (d / f"{n}.ogg").is_file()]
    if need:
        for name, fsb in _bundle_clips(Path(install), need, _SFX_BUNDLES).items():
            try:
                data = fsb_to_ogg(fsb)
            except ValueError:
                continue
            tmp = d / f"{name}.ogg.part"
            tmp.write_bytes(data)
            tmp.replace(d / f"{name}.ogg")
    for name in vorbis:
        ogg = d / f"{name}.ogg"
        if ogg.is_file():
            try:
                decode_ogg_to_wav(ogg, d / f"{name}.wav")
            except Exception:
                continue
            ogg.unlink(missing_ok=True)
            done.append(name)
    return done
