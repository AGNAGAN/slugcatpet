"""蜥蜴叫声：原版 LizardVoice + CreatureVoice（只含绿 / 粉蜥蜴会用到的部分）。

叫声是一条按 articulation 曲线调音量 / 音高的声音，口型可视化取自正在播放的片段的频谱。
"""

from __future__ import annotations

import math
import random

from . import sfx
from .rw import clamped_random_variation, inverse_lerp, lerp, lerp_map


class Emotion:
    """LizardVoice.Emotion 的名字，值为原版枚举名；ORDER 的下标即原版 Index。"""

    SpottedPreyFirstTime = "SpottedPreyFirstTime"
    ReSpottedPrey = "ReSpottedPrey"
    GeneralSmallNoise = "GeneralSmallNoise"
    Curious = "Curious"
    Dominance = "Dominance"
    Submission = "Submission"
    PainImpact = "PainImpact"
    PainIdle = "PainIdle"
    Frustration = "Frustration"
    Fear = "Fear"
    Boredom = "Boredom"
    BloodLust = "BloodLust"
    OutOfShortcut = "OutOfShortcut"

    ORDER = (
        SpottedPreyFirstTime,
        ReSpottedPrey,
        GeneralSmallNoise,
        Curious,
        Dominance,
        Submission,
        PainImpact,
        PainIdle,
        Frustration,
        Fear,
        Boredom,
        BloodLust,
        OutOfShortcut,
    )


# 口型可视化：IntensityVisualizer(lowerCutoff, upperCeiling, exponent)
_VIS_LOWER, _VIS_UPPER, _VIS_EXPONENT = 0.0002, 0.003, 0.5

# 每种情绪的 (基础长度 tick, 最大音量)；没列出的用 (40, 1)
_EMOTION_SHAPE = {
    Emotion.SpottedPreyFirstTime: (50.0, 1.0),
    Emotion.GeneralSmallNoise: (12.0, 0.5),
    Emotion.ReSpottedPrey: (12.0, 0.5),
    Emotion.Curious: (40.0, 0.4),
    Emotion.Dominance: (40.0, 0.8),
    Emotion.Submission: (20.0, 0.5),
    Emotion.PainImpact: (20.0, 1.0),
    Emotion.PainIdle: (50.0, 0.1),
    Emotion.Boredom: (30.0, 0.2),
    Emotion.BloodLust: (35.0, 0.5),
    Emotion.OutOfShortcut: (30.0, 0.5),
}

# 品种 -> (SoundID 中的名字, 变体后缀)
# 青 / 白 / 红：原版只在 MMF 的 cfgExtraLizardSounds 开启时才有叫声；这里按开启处理
_VOICE_SETS = {
    "pink": ("Pink", "ABCDE"),
    "green": ("Green", "A"),
    "blue": ("Blue", "A"),
    "cyan": ("Cyan", "ABC"),
    "white": ("White", "ABC"),
    "red": ("Red", "A"),
}


class VoiceArticulation:
    def __init__(self, rng: random.Random, length: float, max_volume: float):
        self.length = length
        self.max_volume = max_volume
        rows = 2 + int(length / 20.0)
        self.modifier = [[rng.random(), rng.random()] for _ in range(rows)]

    def return_mod(self, f: float, m: int) -> float:
        rows = len(self.modifier)
        f *= rows - 1
        num = math.floor(f)
        f -= num
        return lerp(self.modifier[num][m], self.modifier[min(num + 1, rows - 1)][m], f)


class LizardVoice:
    def __init__(self, lizard):
        self.lizard = lizard
        self.my_pitch = 1.0
        self.current_articulation_progression = 0.0
        self.articulation_index = -1
        self.current_emotion_intensity = 0.0
        # CreatureVoice
        self.sound_id: str | None = None
        self._last_sound_id: str | None = None
        self.sound_a: sfx.Handle | None = None
        self._vol = 1.0
        self._pitch = 1.0
        self.visualizer_intensity = 0.0

        rng = random.Random(lizard.seed)  # 原版 InitState(RandomSeed)，随机序列只用于构造
        self._trigger: str | None = None
        self._trigger_id = self._pick_voice_trigger(rng)  # 随机数只和条目有关，与片段是否已提取无关
        self.my_pitch = clamped_random_variation(rng, 0.5, 0.2, 0.8) * 2.0
        num = lerp(0.5, 1.5, rng.random())
        num2 = lerp(0.7, 1.3, rng.random())
        if lizard.lizard_params.key == "red":
            num2 = lerp(1.0, 1.3, rng.random())
        base = VoiceArticulation(rng, 80.0, 1.0)
        self.articulations: list[VoiceArticulation] = []
        for emotion in Emotion.ORDER:
            length, max_vol = _EMOTION_SHAPE.get(emotion, (40.0, 1.0))
            art = VoiceArticulation(rng, length * num, max_vol * num2)
            self.articulations.append(art)
            rows = len(art.modifier)
            mod = art.modifier
            for j in range(rows):
                t = j / (rows - 1)
                if emotion == Emotion.SpottedPreyFirstTime:
                    mod[j][0] = max(mod[j][1], math.sin(t * math.pi))
                    mod[j][1] = lerp(mod[j][1], math.sin(t * math.pi), 0.5)
                elif emotion == Emotion.ReSpottedPrey:
                    mod[1][0] = 1.0
                    if t == 0.0:
                        mod[j][1] = 1.0
                    elif t == 1.0:
                        mod[j][1] = 0.0
                elif emotion == Emotion.Curious:
                    mod[j][1] = lerp(mod[j][1], t, 0.5)
                    if t == 1.0:
                        mod[j][1] = 1.0
                elif emotion == Emotion.Dominance:
                    mod[j][0] = lerp(mod[j][0], 1.0, (1.0 - t) ** 0.5)
                    mod[j][1] = lerp(mod[j][1], math.sin(t * math.pi) * 0.5, 0.5)
                elif emotion == Emotion.Submission:
                    mod[j][0] = lerp(mod[j][0], 0.0, t)
                    mod[j][1] = lerp(mod[j][1], 1.0, (1.0 - t) * 0.5)
                for k in range(2):
                    mod[j][k] = lerp(mod[j][k], base.return_mod(t, k), 0.5)

    # ---- CreatureVoice ----

    @property
    def volume(self) -> float:
        return self._vol

    @volume.setter
    def volume(self, v: float) -> None:
        self._vol = v
        if self.sound_a is not None:
            self.sound_a.volume = v

    @property
    def pitch(self) -> float:
        return self._pitch

    @pitch.setter
    def pitch(self, v: float) -> None:
        self._pitch = v
        if self.sound_a is not None:
            self.sound_a.pitch = v

    @property
    def making_a_sound(self) -> bool:
        return self.sound_id is not None and self.volume > 0.0

    @property
    def visualized_intensity(self) -> float:
        return self.visualizer_intensity * self.volume

    @property
    def current_art(self) -> VoiceArticulation:
        return self.articulations[self.articulation_index]

    def _drop_sound(self) -> None:
        if self.sound_a is not None:
            self.sound_a.stop()  # 原版靠 requireActiveUpkeep 停掉，不再续命就是停
            self.sound_a = None

    def _base_update(self) -> None:
        if (
            self.sound_id is None
            or self.volume == 0.0
            or self.sound_id != self._last_sound_id
            or (self.sound_a is not None and not self.sound_a.alive)
        ):
            self._drop_sound()
        self._last_sound_id = self.sound_id
        if self.sound_a is None and self.sound_id is not None and self.volume > 0.0:
            self.sound_a = sfx.play(self.sound_id, self.lizard.body_chunks[0].pos, self.volume, self.pitch)
        elif self.sound_a is not None:
            self.sound_a.set_pos(self.lizard.body_chunks[0].pos)
        a = self.sound_a
        self.visualizer_intensity = (
            inverse_lerp(_VIS_LOWER, _VIS_UPPER, a.spectrum()) ** _VIS_EXPONENT if a is not None else 0.0
        )

    # ---- LizardVoice ----

    def update(self) -> None:
        lz = self.lizard
        self._base_update()
        if self.articulation_index > -1:
            self.current_articulation_progression += 1.0 / (
                self.current_art.length * lerp_map(self.current_emotion_intensity, 0.0, 2.0, 0.5, 1.5)
            )
            if self.current_articulation_progression >= 1.0:
                self.sound_id = None
                self.articulation_index = -1
            else:
                prog = self.current_articulation_progression
                self.volume = (
                    self.current_art.return_mod(prog, 0)
                    * self.current_art.max_volume
                    * lerp_map(self.current_emotion_intensity, 0.0, 2.0, 0.4, 3.0)
                    * (1.0 - lz.jaw_forced_shut)
                )
                self.pitch = lerp(0.5, 1.5, self.current_art.return_mod(prog, 1)) * self.my_pitch
        if lz.grasps[0] is not None:
            self._drop_sound()
        g = getattr(lz, "graphics_module", None)
        if g is not None:
            g.last_voice_visualization_intensity = g.voice_visualization_intensity
            g.voice_visualization_intensity = 1.0 if self.making_a_sound else 0.0
            g.last_voice_visualization = g.voice_visualization
            g.voice_visualization = self.visualized_intensity

    def make_sound(self, emotion, intensity: float | None = None) -> None:
        """emotion 为 Emotion 成员（或其名字）；intensity 缺省时随机 0.8~1.2。"""
        lz = self.lizard
        if intensity is None:
            intensity = lerp(0.8, 1.2, lz.rng.random())
        gm = getattr(lz, "graphics_module", None)
        camo_mute = lz.lizard_params.key == "white" and gm is not None and gm.camouflaged > 0.2
        if (
            lz.consious
            and not intensity < self.current_emotion_intensity / 2.0
            and lz.grasps[0] is None
            and not camo_mute
        ):
            self.current_articulation_progression = 0.0
            self.articulation_index = Emotion.ORDER.index(str(emotion))
            self.sound_id = self.my_voice_trigger
            self.current_emotion_intensity = intensity

    @property
    def my_voice_trigger(self) -> str | None:
        """原版 GetMyVoiceTrigger 的结果；片段还没提取出来时为 None，提取好后自动生效。"""
        if self._trigger is None and self._trigger_id is not None and sfx.is_ready(self._trigger_id):
            self._trigger = self._trigger_id
        return self._trigger

    def _pick_voice_trigger(self, rng: random.Random) -> str | None:
        name, variants = _VOICE_SETS.get(self.lizard.lizard_params.key, ("", ""))
        found = [f"Lizard_Voice_{name}_{v}" for v in variants if sfx.has_sound(f"Lizard_Voice_{name}_{v}")]
        return found[rng.randrange(len(found))] if found else None
