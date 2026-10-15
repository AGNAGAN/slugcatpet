"""操控输入：InputPackage 是一帧输入，InputBuffer 存最近 10 帧。"""

from __future__ import annotations
from dataclasses import dataclass

BUFFER_LEN = 10


@dataclass
class InputPackage:
    x: int = 0  # ∈{-1,0,1}
    y: int = 0
    jmp: bool = False
    thrw: bool = False
    pckp: bool = False
    mp: bool = False  # 占位
    spec: bool = False  # 占位
    crouchToggle: bool = False  # 占位
    downDiagonal: int = 0  # 按下时的横向分量，由 x、y 算出

    def __post_init__(self):
        self.downDiagonal = self.x if (self.y < 0 and self.x != 0) else 0


class InputBuffer:
    """输入历史，[0] 是最新一帧。"""

    def __init__(self, length: int = BUFFER_LEN):
        self._len = int(length)
        self._frames = [InputPackage() for _ in range(self._len)]

    def push(self, pkg: InputPackage) -> None:
        self._frames.insert(0, pkg)
        self._frames.pop()

    def __getitem__(self, i: int) -> InputPackage:
        if 0 <= i < len(self._frames):
            return self._frames[i]
        return InputPackage()  # 越界返回空输入

    def __len__(self) -> int:
        return self._len

    def __repr__(self) -> str:
        return f"InputBuffer({self._frames!r})"
