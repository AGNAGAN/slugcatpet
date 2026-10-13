# 程序结构（开发者 / fork 用）

物理、绘制、平台这些底层是核心，只在固定的地方留了钩子。
能力、物品、行为、配件、角色各占一个目录，每样东西一个子目录，加新的一般只新建子目录、再在注册表末尾加一行。

## 目录

```
slugcatpet/
  core/         物理：两节质点身体、碰撞、游泳 / 憋气、尾巴、水中上下错开。不认识任何猫种或物品
  items/        物品：果子、石头、竖杆 / 横杆、暖灯、黏菌、蝙蝠。每种一个子目录
  world/        环境：雪、气泡、爆炸特效（水在 core/water.py）
  abilities/    能力：舌头、飞升、爆破、空翻、水生
  accessories/  配件：疤、鳃。纯外观、会动、能单独设颜色
  behaviors/    行为：所有猫会做的事，包括取果、爬杆、发呆、游泳这些原生行为
  brain/        引擎：状态机 fsm、状态基类 state、心情仲裁 desire、多猫协调 social、
                核心状态 core_states（被拖 / 空中 / 晕 / 死）、共用动作 skills/（爬杆、横杆、走位、咀嚼）
  planning/     规划：目标、够取方式 Reach、执行器；通用够取（走、跳、爬竖杆、后空翻）
  characters/   角色：CatDef、数值 stats、性格 personality（含 Traits）、JSON 读取
  appearance.py 一只猫的外观（皮肤、颜色、配件）和取色优先级
  skins/        DMS 皮肤读取与解析
  rendering/    绘制：图集、身体各部件、尾巴贴图、绘制录制回放
  audio/        音乐播放器、场景配乐、从游戏资源包重建 ogg
  platform/     系统相关：光标、置顶、单实例、全屏检测、开机自启、AppID
  control/      手动控制（键盘操控一只猫）
  ui/           界面：theme/（配色与样式表）、panels/（各面板）、widgets/（通用小部件）
  resources/    characters/*.json（内置角色）、layouts/（部件摆位）、icons/
  tuning.py     几处共用的常量
  petunit.py    一只猫：把身体、图形、能力、配件、状态机组装起来，每 tick 推进
  window.py     桌面窗口与世界：tick 循环、环境、绘制顺序
tests/          行为检查（见文末）、多猫互动统计
tools/          params_doc.py（生成 ai-docs/PARAMS.md）、gen_vorbis_setups.py
```

## 五种模块

| | 是什么 | 放在哪 | 例子 |
|---|---|---|---|
| 能力 | 身体能做什么：器官、物理特性、绘制、够取方式、手动控制 | `abilities/<key>/` | 舌头、爆破、水生 |
| 物品 | 世界里的东西：物理、绘制、放置 / 移除 / 拖拽、提供哪些用法 | `items/<key>/` | 果子能吃、石头能扔、杆能爬 |
| 行为 | 猫想做什么、怎么做：状态、强制规则、心情候选 | `behaviors/<key>/` | 取果、扔石头、舔光标 |
| 配件 | 只管外观的额外部件，任何猫都能戴，不带能力 | `accessories/<key>/` | 疤、鳃 |
| 角色 | 纯数据：有哪些能力、数值、性格 | `resources/characters/<key>.json` | 圣徒 = 舌头 + 飞升 |

它们之间的关系：

- 角色只写有哪些能力。行为按 `requires` 自动挂上，角色里只写例外。
- 行为不认识具体的物品，只认用法。取果找「能吃的」，扔石头找「能扔的」。
- 配件和能力分开：白猫戴上鳃只是好看，水生体质是溪流的能力。

### 物品用法

定义在 `items/base.py`：

| 用法 | 提供它的物品 | 用到它的行为 |
|---|---|---|
| `edible` 能吃 | 果子、黏菌、蝙蝠 | 取果 |
| `throwable` 能扔 | 石头 | 生气扔石头 |
| `climbable` 能爬 | 竖杆、横杆 | 爬杆，以及溪流、圣徒的横杆玩法 |
| `warm` 能取暖 | 暖灯 | 取暖 |
| `carryable` 能拿 | 果子、石头、黏菌、蝙蝠 | 目前只作标记 |

行为用 `fsm.items(用法)` 取场上的这类物品，顺序和放置顺序一致。

### requires

行为的 `requires` 可以写能力 key，也可以写物品用法：

- 写能力：这只猫有这些能力才挂载。
- 写用法：不影响挂载，只说明这个行为会用哪类物品（参数文档里会列出来）。没有这类物品时，行为自己的触发条件不成立，也就不会去做。
- 什么都不写：每只猫都有。`essential = True` 的行为角色里关不掉（发呆、休息、游泳）。

### 性格

性格数据在 `characters/personality.py` 的 `CatPersonality`，换算后的作用在同文件的 `Traits` 里，每只猫算一次。
行为和引擎只读 `fsm.traits`，不读原始数值。每个性格轴作用在哪，登记在同文件的 `EFFECTS`，参数文档会列出来。

- 心情候选的权重统一乘 `traits.mood_weight(心情名)`（`activity` 和 `toy_pref`）。用 `mood_candidate()` 建候选就自动带上。
- 食性统一用 `traits.eats(物品)` 判断会不会吃，`traits.food_time()` 让肉食者偏好肉。

### 多猫协调

`brain/social.py`，每个世界 tick 推进一次。行为只经这里了解别的猫，不直接读别的猫的内部状态。

- 感知：`others(我)`、`state_of(猫)`、`others_x(我)`。
- 占用：`claim(我, 槽, 目标, 状态)` 占住一个目标，状态结束、被拖、晕、死时自动失效；
  `free_for(我, 目标)` 判断能不能去，别的猫占着时只有比它近一半以上才抢。取果、捡石头、爬竖杆都是先判断能不能去、选定后占住。去横杆也会登记，但还不判断别的猫占没占。
- 让路：`crowd(我)` 存挤人和让路的计数；同一对猫让过一次，600 tick 内不再互让，挡路的一方改为跳过去。
- 杆顶：谁站在哪根杆顶、谁被挤下来，都记在这里。

## 一个 tick

```
window._do_tick
  ├─ 水位
  ├─ social.tick
  ├─ 每只猫 PetUnit.step
  │    ├─ fsm.update      每 tick 回调 → 强制规则（按优先级）→ 当前状态 tick → 体力 → 心情新鲜度
  │    ├─ ability.pre_step
  │    ├─ body.step       物理
  │    ├─ 寒冷结算、gfx.update
  │    ├─ ability.post_step、accessory.post_step
  │    └─ 尾巴
  ├─ 物品推进、物体间碰撞、碰撞后推进的物品（灯）
  └─ 雪
```

### 优先级

每个状态有一个优先级 `tier`，每条强制规则也有一个（`brain/state.py` 的 `RULE_TIER`）。
规则只能打断优先级比它低的状态；同级和更高的状态不会被打断，等它自己做完。被打断的状态先收尾（`brk`）再切换。

| 优先级 | 状态 | 能打断它们的规则 |
|---|---|---|
| 死亡、超度 100 | Dead、Ascension | 无 |
| 被砸中 90 | | 砸晕 |
| 躲杀 80 | DodgeKill | 砸晕 |
| 被拖 70 | Dragged | 砸晕、杀死弹窗 |
| 晕、游泳 60 | Stunned、Swimming | 以上，加被抓 |
| 取暖、起身 40 | SeekWarmth、WakeSequence | 以上，加入水、无重力 |
| 趴下、睡觉 35 | LieDown、Sleep | 以上，加寒冷 |
| 取果 30 | FetchFruit | 以上，加体力告急 |
| 活动 20 | 爬杆、横杆、爬墙吊顶、舔光标、扔石头、各种撒欢、让路 | 以上，加饿了 |
| 待机 0 | IdleStand、Airborne、生完气闲逛 | 以上，加被顶住 |

每 tick 先跑优先级高的规则；规则一旦切了状态，后面的低级规则就打不断它。没有对应强制规则的每 tick 回调最后跑，按挂载顺序。

绘制：每帧把绘制调用录一遍、得到实际画到的范围，只刷新这部分，重绘时照着回放（`rendering/display_list.py`）。
身体部件之间有三个槽位给能力和配件用：`under_face`（鳃）、`behind_face`（疤）、`over_face`（舌头）。

## 接口

### 能力（`abilities/base.py`）

所有钩子可选。每只猫一份实例，`self.p` 是解析后的参数。

| 钩子 | 时机 / 用途 |
|---|---|
| `attach_body(pet, body)` | 身体刚建好：写物理特性，如 `body.aquatic` |
| `build(pet)` | 建器官，返回值存到 `pet.organs[key]` |
| `draw_layers(pet)` | `[(槽位, fn(gfx, painter, atlas, ts))]` |
| `pre_step(pet)` / `post_step(pet)` | 见上面的 tick 顺序 |
| `resize(pet, floor_y)` | 世界尺寸变了 |
| `reaches(pet)` | 给规划器的够取方式（`planning.Reach` 子类实例） |
| `fetch_assist(pet)` | 取果时的空中补救器（舌头抢射） |
| `mount(fsm)` | 状态机建好后：挂回调、致死特效等 |
| `control(pet, body)` | 进入手动控制时挂操控器 |

### 物品（`items/base.py` 的 `ItemKind`）

常用的类属性：

| 属性 | 用途 |
|---|---|
| `key` | 放置模式名；界面文案用 `tip_<key>`、`toast_max_<key>` |
| `store` | 物体存在窗口的哪个属性上（自动建好）。`single = True` 时只有一件 |
| `affords` | 提供的用法 |
| `cap` | 上限，`None` 不限 |
| `layer` | 绘制层：`mid`（猫身后、手前）/ `front` / `top`（水之上） |
| `collides` | 参与物体间碰撞互推 |
| `grab_pad` | 设了就能用鼠标拖 |

要写的方法：`make()`（放置时造物体）、`draw()`、`paint_icon()`（侧边栏图标）。
按需覆盖：`draw_hint()`（放置预览）、`hit()` / `draw_mark()`（移除模式的判定和高亮）、`drop()`、`on_grab()`、`on_release()`、`after_step()`、`floor_shift()`。
物体本身（模型）至少要有 `x, y, last_x, last_y, rad, state` 和 `step(WL, HL)`。

### 行为（`behaviors/base.py`）

`mount(fsm)` 里可以用：

| 接口 | 用途 |
|---|---|
| `fsm.add_state(StateSubclass)` | 注册状态，返回状态实例（钩子与声明见 `brain/state.py`） |
| `fsm.register_rule(fn(cursor), 规则)` | 每 tick 的强制规则；规则是 `RULE_TIER` 里的名字，不写就是普通每 tick 回调 |
| `fsm.interrupt(规则, 状态名)` / `fsm.blocked(规则)` | 按优先级打断当前状态 / 当前状态挡不挡这条规则 |
| `fsm.register_ticker(fn())` | 每 tick 最先调用 |
| `mood_candidate(fsm, 名, p, gate)` + `fsm.register_mood_entry(名, 状态)` | 心情候选：无聊时按权重抽到就进入该状态。参数用 `mood_params(...)` 生成 |
| `fsm.items(用法)` | 场上提供这种用法的物品 |
| `fsm.social` | 多猫协调，见上 |
| `fsm.traits` | 性格 |
| `fsm.provide(名, fn)` / `fsm.ask(名)` | 行为之间互相查询，不直接引用对方 |
| `fsm.on_stun(fn)` | 被砸晕时收尾（松手、放掉占用） |
| `fsm.add_threat_responder(fn)` | 杀死弹窗出现时的应对 |
| `fsm.block_interaction(状态名)` | 该状态期间屏蔽光标交互 |
| `fsm._transition(状态名)` / `fsm.settle()` | 切换状态 / 动作结束回待机或空中 |

状态自己声明 `tier`（优先级）、`energy`（体力档位）、`mood`（心情名）。状态机不按名字特判。

各注册表（`abilities/`、`items/`、`behaviors/`、`accessories/` 的 `__init__.py` 里的 `BUILTIN`）的顺序会影响心情抽签、规则、推进和绘制的先后。新模块加在末尾，原有的猫就不受影响。

## 怎么加东西

### 新物品

1. 建 `items/<key>/model.py`：物体的物理，见上面「物品」的最低要求。行为相近的可以直接继承已有的模型。
2. 建 `items/<key>/__init__.py`：写 `ItemKind` 子类，设 `key`、`store`、`affords`，实现 `make()`、`draw()`、`paint_icon()`；文件末尾 `KIND = 子类()`。
3. 在 `items/__init__.py` 导入它，加到 `BUILTIN` 末尾。
4. 在 `i18n.py` 加 `tip_<key>` 和 `toast_max_<key>`。

侧边栏按钮、放置、移除、拖拽、绘制都会自动带上。猫会不会用它，取决于它提供的用法有没有行为在用。

### 新的物品用法

1. 在 `items/base.py` 加一个常量，并放进 `USES`。
2. 给提供它的物品写进 `affords`，再写一个用它的行为。

### 新行为

1. 建 `behaviors/<key>/__init__.py`：写 `Behavior` 子类，设 `key`、`title`、`doc`、`requires`、`params`，实现 `mount`。状态可以放在同目录的其他文件里，每个状态按上面的表定一个 `tier`。
2. 在 `behaviors/__init__.py` 导入它，加到 `BUILTIN` 末尾。
3. 会和别的猫争同一个目标时，选目标前用 `fsm.social.free_for` 过滤，选定后用 `fsm.social.claim` 占住。
4. 运行 `python tools/params_doc.py` 重新生成参数文档。

### 新能力

1. 建 `abilities/<key>/`：写 `Ability` 子类，按需实现钩子；器官、绘制、够取方式放在同一个包里。
2. 在 `abilities/__init__.py` 导入它，加到 `BUILTIN` 末尾。
3. 需要核心配合时，加一个通用的钩子或身体特性（像 `body.aquatic`），不要在核心里写能力的名字。
4. 写依赖它的行为，在某个角色 JSON 里启用，重新生成参数文档。

### 新角色

只写一个 JSON，见 [CHARACTERS.md](CHARACTERS.md)。

### 新配件

1. 建 `accessories/<key>/__init__.py`：写 `Accessory` 子类，设 `key`、`title`、`default_color`、`default_on`（默认戴的猫种），按需设 `color_group`（皮肤里对应的部位组），实现 `post_step` 和 `draw_layers`。
2. 在 `accessories/__init__.py` 导入它，加到 `BUILTIN` 末尾。

外观弹窗会自动列出它。配件只管外观，需要能力的部分写成能力。

### 新性格轴

1. 在 `characters/personality.py` 的 `CatPersonality` 加字段和默认值（中性值）。
2. 在 `Traits` 里换算成行为要用的量。
3. 在 `EFFECTS` 登记它作用在哪。
4. 在需要它的行为里读 `fsm.traits`。角色 JSON 的 `personality` 里就能写这个字段了。

界面样式：配色在 `ui/theme/palette.py`，样式表在 `ui/theme/qss.py`。

## 测试

```
python tests/behavior_check.py check     4 个固定种子场景，逐 tick 比对状态、位置和渲染帧
python tests/behavior_check.py record    有意改了行为或画面后重录基线
python tests/social_check.py run         多猫长时间运行，统计抢目标、互相让路、卡住等异常
python tools/params_doc.py --check       参数文档是否最新
uv run ruff format / uv run ruff check   格式和静态检查（版本与规则在 pyproject.toml）
```

不该改变行为的改动，`check` 必须全过。有意改了手感，确认没问题后再 `record`。
`packaging/build_release.ps1 -Test` 打包前会跑行为检查和参数文档检查。

## 还没模块化的部分

- 猫手里拿东西还按种类分：`core/creature.py` 里有 `carried_fruit` 和 `carried_stone` 两套。新的可拿物品要让猫拿起来，得改这里。
- 爬杆行为还按 `kind == "vertical"` / `"horizontal"` 区分两种杆。
- 世界状态还挂在 `window.py` 的窗口上，没有单独的 World 对象。
- 超度时睁眼的脸是核心绘制直接读 `gfx.ascension`，不是绘制槽位。
- 游泳和无重力时追食物还没走占用登记；横杆位置只登记，不判断。
