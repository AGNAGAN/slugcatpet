"""喵声表：照 Push to Meow 的 sounds.txt 和 custom_meows.json，按猫种、幼崽、长短选 SoundID、音高和音量倍数。"""

from __future__ import annotations

PUP_PITCH = 1.3  # 没有专门幼崽声音的猫种，幼崽用成年声音升调
PANIC_PITCH = (0.2, 0.35)  # 被光标拎着：惊叫
UNDERWATER_PITCH = (0.1, 0.25)  # 水下：降调
RIVULET_VOL = 0.8


def _entry(*names):
    """sounds.txt 一行：各变体音量 0.6、音高 0.9–1.1，等概率选一个。"""
    return (False, (1.0, 1.0), (1.0, 1.0), ((names, 0.6, 0.6, 0.9, 1.1),))


def _series(prefix, n):
    return _entry(*(f"{prefix}{i}" for i in range(1, n + 1)))


SOUNDS = {
    "SlugcatMeowNormal": _series("MeowNormal", 8),
    "SlugcatMeowNormalShort": _series("MeowNormalShort", 8),
    "SlugcatMeowPup": _series("MeowPup", 8),
    "SlugcatMeowPupShort": _series("MeowPupShort", 8),
    "SlugcatMeowFat": _series("MeowFat", 8),
    "SlugcatMeowFatShort": _series("MeowFatShort", 8),
    "SlugcatMeowCoarse": _series("MeowCoarse", 8),
    "SlugcatMeowCoarseShort": _series("MeowCoarseShort", 8),
    "SlugcatMeowSpear": _series("MeowSpear", 4),
    "SlugcatMeowSpearShort": _series("MeowSpearShort", 4),
    "SlugcatMeowSaint": _series("MeowWhispery", 8),
    "SlugcatMeowSaintShort": _series("MeowWhisperyShort", 8),
    "SlugcatMeowSofanthiel": _entry("MeowSofanthiel"),
    "SlugcatMeowSofanthielShort": _entry("MeowSofanthielShort"),
    "SlugcatMeowRivuletA": _series("MeowRivuletA", 8),
    "SlugcatMeowRivuletAShort": _series("MeowRivuletAShort", 8),
}
CLIPS = tuple(sorted({n for spec in SOUNDS.values() for ins in spec[3] for n in ins[0]}))

_NORMAL = ("SlugcatMeowNormalShort", "SlugcatMeowNormal")
_PUP = ("SlugcatMeowPupShort", "SlugcatMeowPup")
# 猫种 → (短, 长, 幼崽版 (短, 长) 或 None, 音量倍数)；溪流在原版是写死的分支，效果相同
SPECIES = {
    "survivor": (*_NORMAL, _PUP, 1.0),
    "monk": (*_NORMAL, _PUP, 1.0),
    "hunter": (*_NORMAL, _PUP, 1.0),
    "gourmand": ("SlugcatMeowFatShort", "SlugcatMeowFat", None, 1.15),
    "artificer": ("SlugcatMeowCoarseShort", "SlugcatMeowCoarse", None, 1.2),
    "spearmaster": ("SlugcatMeowSpearShort", "SlugcatMeowSpear", None, 0.55),
    "saint": ("SlugcatMeowSaintShort", "SlugcatMeowSaint", None, 1.0),
    "inv": ("SlugcatMeowSofanthielShort", "SlugcatMeowSofanthiel", None, 1.0),
    "rivulet": ("SlugcatMeowRivuletAShort", "SlugcatMeowRivuletA", None, RIVULET_VOL),
}


def choose(species, pup, short, panic, underwater, rng):
    """返回 (SoundID, 音高, 音量倍数)。

    表里没有的猫种（猫崽、自定义角色）用普通喵，幼崽用幼崽喵且照样升调，和原版缺省分支一致。
    """
    pitch = PUP_PITCH if pup else 1.0
    spec = SPECIES.get(species)
    if spec is None:
        sid = (_PUP if pup else _NORMAL)[0 if short else 1]
        vol = 1.0
    else:
        short_id, long_id, pups, vol = spec
        if pup and pups is not None:
            short_id, long_id = pups
            pitch = 1.0
        sid = short_id if short else long_id
    if panic:
        pitch += PANIC_PITCH[0] + rng.random() * (PANIC_PITCH[1] - PANIC_PITCH[0])
    if underwater:
        pitch -= UNDERWATER_PITCH[0] + rng.random() * (UNDERWATER_PITCH[1] - UNDERWATER_PITCH[0])
    return sid, pitch, vol
