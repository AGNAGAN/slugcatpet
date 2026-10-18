# 角色定义（开发者 / fork 用）

内置角色一只猫一个文件，放在 `slugcatpet/resources/characters/<key>.json`。加新角色只要加一个 json，不用写代码。

角色写有哪些能力、数值和性格。字段写错，启动时会直接报错。

## 例子（工匠）

```json
{
  "format": 1,
  "key": "artificer",
  "order": 5,
  "notes": "复仇爆破手：快而重、好动强健、极不亲人……",
  "body_color": "#70233C",
  "eye_color": "#FFFFFF",
  "layout": "artificer.json",
  "atlases": ["base", "msc"],
  "frames": {
    "head": "base/HeadA",
    "face": "msc/FaceC",
    "face_mirror": "msc/FaceD",
    "face_blink": "base/FaceB",
    "legs_walk": "base/LegsA",
    "legs_crawl": "base/LegsACrawling",
    "legs_air": "base/LegsAAir0"
  },
  "abilities": {"pyro": {}},
  "behaviors": {},
  "stats": {"runspeed_fac": 1.2, "max_food": 9, "drown_threshold": 0.5, "karma_cap": 0},
  "personality": {"energy": 0.75, "sympathy": 0.2, "diet": "carnivore", "meat": 4,
                  "toy_pref": {"pyro_romp": 1.4}}
}
```

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `format` | | 固定 `1` |
| `key` | ✓ | 角色的唯一名字，存档和界面文案 `variant_<key>` 都用它 |
| `order` | | 在选猫列表里的顺序，小的在前（默认 1000） |
| `name` | | 显示名，字符串或 `{"zh": "...", "en": "..."}`；不写则用界面文案 `variant_<key>`（i18n.py） |
| `notes` | | 备注，程序不读 |
| `body_color` / `eye_color` | ✓ | `#RRGGBB`。写 `#FFFFFF` 时脸按贴图原色显示 |
| `layout` | ✓ | `slugcatpet/resources/layouts/` 下的部件摆位文件 |
| `atlases` | ✓ | 用到的原版图集：`base` / `msc` / `ui` / `uimsc` |
| `frames` | ✓ | 语义帧名 → `"图集/帧名前缀"`，见下表 |
| `tail_rad` | | 原皮尾巴每段半径（从根到尖，2–15 段），不写就是游戏默认 `[6, 4, 2.5, 1]`。皮肤设了尾巴参数时以皮肤为准 |
| `abilities` | | 能力 → 参数覆盖（`{}` = 默认）。可用能力和参数见 [PARAMS.md](PARAMS.md) |
| `behaviors` | | 行为例外：`false` 关掉，对象 = 覆盖参数。原生行为每只猫都有，其余行为按身体标签自动挂上（如骨针去掉 `mouth`，用嘴吃的行为就不挂），通常不用写。发呆、休息、游泳关不掉 |
| `stats` | | 数值，只写和默认不同的。字段和默认值见 `characters/stats.py` |
| `personality` | | 性格，只写和默认不同的。见下面「性格」 |
| `wip` | | `true` 表示还没做完，选猫列表里会标出来 |
| `pup` | | `true` 表示猫种本身是幼崽，固定幼崽形态，菜单和外观里不显示幼崽开关 |

### frames

| 语义名 | 必填 | 用途 |
|---|---|---|
| `head` | ✓ | 头（圣徒是 `msc/HeadB`，猫崽是 `msc/HeadC`，其余 `base/HeadA`） |
| `face` | ✓ | 平时的脸 |
| `face_blink` | ✓ | 眨眼 |
| `legs_walk` / `legs_crawl` / `legs_air` | ✓ | 走 / 趴行 / 空中的腿 |
| `face_open` | | 超度时睁眼的脸 |
| `face_mirror` | | 朝另一侧时换用的脸（工匠的疤不随翻转换边） |

帧名只写前缀，程序会依次找 `前缀0`、`前缀1`……。皮肤会按帧名替换这些图。

### 性格

| 字段 | 默认 | 说明 |
|---|---|---|
| `energy` | 0.5 | 精力：低的懒散，高的活泼 |
| `sympathy` | 0.5 | 亲和：低的冷淡，高的亲人 |
| `vary` | 0 | 新猫的精力、亲和在默认值附近随机的幅度，1 为全范围（猫崽 1） |
| `kin` | `{}` | 猫种 → 和这种猫一见面的关系（-1–1），如僧侣和白猫互写 0.5 |
| `stamina` | 1.0 | 耐力，越低越容易累 |
| `cold_gain_fac` | 1.0 | 变冷的速度 |
| `swim_zeal` | 0.5 | 喜不喜欢水，0.5 及以下视为中性 |
| `diet` | `omnivore` | `omnivore` 杂食 / `carnivore` 肉食（偏好肉，吃一样只得 1/4 格，蛋虫蛋除外）/ `vegetarian` 素食（不吃肉）/ `special` 同素食 |
| `meat` | 0 | 啃尸体每口得几个 1/4 格，0 为不啃（猎手、工匠 4，大胃王 2） |
| `toy_pref` | `{}` | 心情名 → 权重乘子 |

每个字段具体作用在哪，见 [PARAMS.md](PARAMS.md) 的「性格」一节。

`energy` 和 `sympathy` 是猫种的默认值。每只猫新建时按它（和 `vary`）定一份自己的，存进存档，用户可以在设置里每只猫那行的「性格」按钮里用滑条改。其余字段跟着猫种走。

猫闲下来挑到「玩」时，会在玩的心情里按权重抽一个，`toy_pref[心情名]` 会乘到对应的权重上。心情名见 [PARAMS.md](PARAMS.md)。去爬架待着不是心情。

### 外观

角色 JSON 里只写默认颜色和帧。皮肤（整套或分部位混搭）、各部位颜色、尾巴形状、配件是每只猫在「外观」里单独设的，存在存档里，不写进角色。
配件默认戴在哪些猫种上，由配件自己声明（`accessories/<key>/` 的 `default_on`）。

## 加一只新角色

1. 复制一个现有的 json，改 `key`、`order`、颜色和帧。
2. 部件摆位一般可以用现有的；要新的就在 `resources/layouts/` 加一个。
3. 写上 `name`，或者在 `slugcatpet/i18n.py` 里加 `variant_<key>`。
4. 要特殊能力就写进 `abilities`。要做全新的能力、行为、物品或配件，见 [ARCHITECTURE.md](ARCHITECTURE.md)。
5. 跑一下 `python tests/behavior_check.py check`。只加角色的话，原有的猫不会受影响。
