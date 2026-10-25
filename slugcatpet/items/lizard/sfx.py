"""蜥蜴 app 的音效：原版 room.PlaySound 的等价。

声音表照原版 sounds.txt（只含蜥蜴用到的条目），播放走共用混音器 audio/sfx。
"""

from __future__ import annotations

from ...audio.sfx import Bank, Handle, is_muted, set_listener_width, set_muted, shutdown, stop_all, warmup
from .assets import LIZARD_SOUNDS, lizard_sounds_dir

__all__ = ["Handle", "is_muted", "set_listener_width", "set_muted", "shutdown", "stop_all", "warmup"]

# SoundID -> (PLAYALL, 触发器 (minVol, maxVol), 触发器 (minPitch, maxPitch), 指令列表)
# 指令 = (片名元组, minVol, maxVol, minPitch, maxPitch)；非 PLAYALL 时按片名数加权随机选一条
_SOUNDS = {
    "Puffball_Eplode": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (
                (
                    "puffA_1",
                    "puffA_2",
                    "puffA_3",
                    "puffA_4",
                ),
                0.6,
                0.6,
                1.0,
                1.0,
            ),
        ),
    ),
    "Lizard_Head_Shield_Deflect": (
        True,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (("Wobble1A",), 0.3, 0.3, 0.8, 1.2),
            (("Clang1A",), 0.2, 0.2, 1.0, 1.0),
        ),
    ),
    "Lizard_Jaws_Shut_Miss_Creature": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (
                (
                    "lizBite3A",
                    "lizBite3B",
                    "lizBite3C",
                    "lizBite3D",
                    "lizBite3E",
                    "lizBite3F",
                    "lizBite3G",
                ),
                0.5,
                0.5,
                1.0,
                1.0,
            ),
        ),
    ),
    "Lizard_Jaws_Grab_NPC": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (
                (
                    "lizBite2A",
                    "lizBite2B",
                    "lizBite2C",
                    "lizBite2D",
                    "lizBite2E",
                    "lizBite2F",
                    "lizBite2G",
                ),
                0.3,
                0.3,
                1.0,
                1.0,
            ),
        ),
    ),
    "Lizard_Jaws_Grab_Player": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (
                (
                    "lizBite2A",
                    "lizBite2B",
                    "lizBite2C",
                    "lizBite2D",
                    "lizBite2E",
                    "lizBite2F",
                    "lizBite2G",
                ),
                0.5,
                0.5,
                1.0,
                1.0,
            ),
        ),
    ),
    "Lizard_Prepare_Lunge_Attack_Init": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (("lizCharge1A",), 0.3, 0.3, 0.8, 1.2),
            (
                (
                    "lizCharge1B",
                    "lizCharge1C",
                ),
                0.3,
                0.3,
                1.0,
                1.0,
            ),
            (("lizCharge1D",), 0.3, 0.3, 0.8, 1.2),
            (("lizCharge1E",), 0.3, 0.3, 1.0, 1.0),
        ),
    ),
    "Lizard_Light_Terrain_Impact": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (("thuds1A",), 0.1, 0.1, 0.8, 1.0),
            (("thuds1C",), 0.1, 0.1, 1.0, 1.0),
            (("thuds1D",), 0.2, 0.2, 0.8, 1.2),
            (("thuds1E",), 0.1, 0.1, 1.0, 1.0),
        ),
    ),
    "Lizard_Heavy_Terrain_Impact": (
        True,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (("bassOnly",), 0.4, 0.4, 0.6, 0.8),
            (("thuds1E",), 0.2, 0.2, 1.0, 1.0),
        ),
    ),
    "Lizard_Grab_Pole": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (
                (
                    "gravel1N",
                    "gravel1K",
                ),
                0.3,
                0.4,
                0.5,
                1.3,
            ),
        ),
    ),
    "Lizard_Green_Foot_Release": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (("gravel1A",), 0.6, 0.6, 1.0, 1.0),
            (("gravel1B",), 0.5, 0.5, 1.0, 1.0),
            (("gravel1C",), 0.4, 0.4, 1.0, 1.0),
            (("gravel1D",), 0.5, 0.5, 1.0, 1.0),
            (("gravel1E",), 0.6, 0.6, 1.0, 1.0),
            (("gravel1F",), 0.4, 0.4, 1.0, 1.0),
            (
                (
                    "gravel1G",
                    "gravel1H",
                ),
                0.6,
                0.6,
                1.0,
                1.0,
            ),
        ),
    ),
    "Lizard_BlueWhite_Foot_Release": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (("gravel1A",), 0.2, 0.2, 1.0, 1.0),
            (("gravel1B",), 0.3, 0.3, 1.0, 1.0),
            (("gravel1C",), 0.2, 0.2, 1.0, 1.0),
            (
                (
                    "gravel1D",
                    "gravel1E",
                ),
                0.3,
                0.3,
                1.0,
                1.0,
            ),
            (
                (
                    "gravel1F",
                    "gravel1G",
                ),
                0.2,
                0.2,
                1.0,
                1.0,
            ),
            (("gravel1H",), 0.3, 0.3, 1.0, 1.0),
        ),
    ),
    "Lizard_PinkYellowRed_Foot_Release": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (("gravel1A",), 0.3, 0.3, 1.0, 1.0),
            (("gravel1B",), 0.4, 0.4, 1.0, 1.0),
            (("gravel1C",), 0.3, 0.3, 1.0, 1.0),
            (
                (
                    "gravel1D",
                    "gravel1E",
                ),
                0.4,
                0.4,
                1.0,
                1.0,
            ),
            (("gravel1F",), 0.3, 0.3, 1.0, 1.0),
            (
                (
                    "gravel1G",
                    "gravel1H",
                ),
                0.4,
                0.4,
                1.0,
                1.0,
            ),
        ),
    ),
    "Lizard_Prepare_To_Shoot_Tongue": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        ((("lizCharge1D",), 0.3, 0.3, 0.8, 1.1),),
    ),
    "Blue_Lizard_Tongue_Shoot_Out": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (
                (
                    "lizSpit1B",
                    "lizSpit1E",
                    "lizSpit1G",
                ),
                0.3,
                0.3,
                1.0,
                1.0,
            ),
        ),
    ),
    "White_Lizard_Tongue_Shoot_Out": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        (
            (
                (
                    "lizSpit1A",
                    "lizSpit1C",
                    "lizSpit1D",
                    "lizSpit1G",
                    "lizSpit1H",
                ),
                0.4,
                0.4,
                1.0,
                1.0,
            ),
        ),
    ),
    "Lizard_Tongue_Attatch_Player": (False, (1.0, 1.0), (1.0, 1.0), ((("Squish1B",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Tongue_Attatch_NPC": (False, (1.0, 1.0), (1.0, 1.0), ((("Squish1A",), 0.4, 0.4, 0.8, 1.1),)),
    "Lizard_Tongue_Attatch_Terrain": (False, (1.0, 1.0), (1.0, 1.0), ((("Squish1A",), 0.3, 0.3, 0.8, 1.1),)),
    "Lizard_Tongue_Detatch_Player": (False, (1.0, 1.0), (1.0, 1.0), ((("Squish2G",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Tongue_Detatch_NPC_Or_Terrain": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        ((("Squish2G",), 0.4, 0.4, 0.8, 1.1),),
    ),
    "Lizard_Tongue_Go_Back_In_Mouth": (False, (1.0, 1.0), (1.0, 1.0), ((("Squish2I",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Voice_Pink_A": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoicePinkA",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Voice_Pink_B": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoicePinkB",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Voice_Pink_C": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoicePinkC",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Voice_Pink_D": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoicePinkD",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Voice_Pink_E": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoicePinkE",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Voice_Green_A": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoiceGreenA",), 0.3, 0.3, 1.0, 1.0),)),
    "Cyan_Lizard_Prepare_Small_Jump": (
        False,
        (0.8, 0.8),
        (1.0, 1.0),
        ((("CyanChargeSm",), 1.0, 1.0, 1.0, 1.0),),
    ),
    "Cyan_Lizard_Prepare_Medium_Jump": (
        False,
        (0.8, 0.8),
        (1.0, 1.0),
        ((("CyanChargeM",), 1.0, 1.0, 1.0, 1.0),),
    ),
    "Cyan_Lizard_Prepare_Powerful_Jump": (
        False,
        (0.8, 0.8),
        (1.0, 1.0),
        ((("CyanChargeL",), 1.0, 1.0, 1.0, 1.0),),
    ),
    "Cyan_Lizard_Small_Jump": (
        True,
        (0.4, 0.4),
        (0.8, 0.8),
        (
            (("Flip3C",), 1.0, 1.0, 1.0, 1.0),
            (("Clang2A",), 0.6, 0.6, 1.0, 1.0),
            (("CoralBreakA_7",), 0.3, 0.3, 2.0, 2.0),
        ),
    ),
    "Cyan_Lizard_Medium_Jump": (
        True,
        (0.7, 0.7),
        (1.0, 1.0),
        (
            (("Flip3C",), 1.0, 1.0, 1.0, 1.0),
            (("Clang1H",), 0.7, 0.7, 0.6, 0.6),
            (("CoralBreakA_7",), 0.4, 0.4, 2.5, 2.5),
        ),
    ),
    "Cyan_Lizard_Powerful_Jump": (
        True,
        (1.0, 1.0),
        (1.2, 1.2),
        (
            (("Flip3C",), 1.0, 1.0, 1.0, 1.0),
            (("Clang1G",), 0.8, 0.8, 0.8, 0.8),
            (("CoralBreakA_7",), 0.5, 0.5, 3.0, 3.0),
        ),
    ),
    "Cyan_Lizard_Gas_Leak_LOOP": (
        False,
        (1.0, 1.0),
        (1.0, 1.0),
        ((("VultureJetLOOP2",), 0.6, 0.6, 2.0, 2.0),),
    ),
    "Lizard_Voice_Blue_A": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoiceBlueA",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Voice_White_A": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoiceWhiteA",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Voice_White_B": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoiceWhiteB",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Voice_White_C": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoiceWhiteC",), 0.3, 0.3, 1.0, 1.0),)),
    "Lizard_Voice_Red_A": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoiceRedA",), 0.4, 0.4, 1.0, 1.0),)),
    "Lizard_Voice_Cyan_A": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoiceCyanA",), 0.4, 0.4, 1.0, 1.0),)),
    "Lizard_Voice_Cyan_B": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoiceCyanB",), 0.4, 0.4, 1.0, 1.0),)),
    "Lizard_Voice_Cyan_C": (False, (1.0, 1.0), (1.0, 1.0), ((("LizardVoiceCyanC",), 0.4, 0.4, 1.0, 1.0),)),
}


_bank = Bank(_SOUNDS, lizard_sounds_dir)
has_sound = _bank.has_sound
is_ready = _bank.is_ready
play = _bank.play


def load_all() -> None:
    """同步加载全部蜥蜴音效（几十毫秒），启动时在开始 tick 之前调，播放就不会因没加载而跳过。"""
    _bank.load_all(LIZARD_SOUNDS)
