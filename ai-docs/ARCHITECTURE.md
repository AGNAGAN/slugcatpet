# 程序结构（开发者 / fork 用）

物理、绘制、平台这些底层是核心，只在固定的地方留了钩子。
能力、物品、行为、配件、角色各占一个目录，每样东西一个子目录，加新的一般只新建子目录、再在注册表末尾加一行。

## 目录

```
slugcatpet/
  core/         物理：两节质点身体、碰撞、游泳 / 憋气、尾巴、水中上下错开。不认识任何猫种或物品
  items/        物品：果子、石头、矛、竖杆 / 横杆、暖灯、黏菌、蝙蝠。每种一个子目录
  world/        环境：雪、气泡、爆炸特效（水在 core/water.py）
  abilities/    能力：舌头、飞升、爆破、空翻、水生、重压、骨针
  accessories/  配件：疤、鳃、尾巴斑点。纯外观、会动、能单独设颜色
  behaviors/    行为：所有猫会做的事，包括取果、爬杆、发呆、游泳这些原生行为
  brain/        引擎：状态机 fsm、状态基类 state、心情仲裁 desire、多猫协调 social、
                核心状态 core_states（被拖 / 空中 / 晕 / 死）、共用动作 skills/（爬杆、横杆、走位）
  planning/     规划：目标、够取方式 Reach、执行器；通用够取（走、跳、爬竖杆、后空翻）
  characters/   角色：CatDef、数值 stats、性格 personality（含 Traits）、JSON 读取
  appearance.py 一只猫的外观 `Look`（整套皮肤、分部位皮肤与颜色、尾巴形状、配件）和取色优先级
  skins/        DMS 皮肤读取与解析；resolver 按部位组查找图集
  rendering/    绘制：图集、身体各部件、尾巴贴图、绘制录制回放
  audio/        音乐播放器、场景配乐、从游戏资源包重建 ogg
  platform/     系统相关：光标、置顶、单实例、全屏检测、开机自启、AppID、垂直同步
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
| 配件 | 只管外观的额外部件，任何猫都能戴，不带能力 | `accessories/<key>/` | 疤、鳃、尾巴斑点 |
| 角色 | 纯数据：有哪些能力、数值、性格 | `resources/characters/<key>.json` | 圣徒 = 舌头 + 飞升 |

它们之间的关系：

- 角色只写有哪些能力。能力决定身体标签，行为按 `requires` 对照身体标签自动挂上，角色里只写例外。
- 行为不认识具体的物品，只认用法。取果找「能吃的」，扔石头找「能扔的」。
- 配件和能力分开：白猫戴上鳃只是好看，水生体质是溪流的能力。
- 一件事归一个行为管全：用嘴吃的逻辑（取果、水里和失重时就近吃）都在 `behaviors/fetch/`。游泳、发呆这些基础状态只留扩展点，不写别的功能。

### 身体标签

`petunit.tags`，由 `abilities.body_tags()` 算出：默认标签（`BODY_TAGS`，只有 `mouth`）加上各能力 key，再加能力的 `provides`、去掉能力的 `removes`。

- 行为写进 `requires` 的标签不齐就不挂载。取果、留个果子要 `mouth`；矛大师的骨针能力 `removes = ("mouth",)`，于是用嘴吃的行为整套不挂，角色 JSON 里不用逐个关。
- 会不会吃一件东西统一用 `pet.can_eat(物)`：有 `mouth`、物品能吃、食性允许。手部管家、手动控制、鼠标喂蝙蝠都只看它。
- 吃下东西的结算统一走 `body.feed(1/4 格数)`（饱食、好感、体力）。骨针进食也调它。
- 吃完一样东西得几个 1/4 格由 `traits.nourishment(物)` 定：物品的 `food_points`（默认 1），肉食者只得 `food_points` 个 1/4，其余猫得 4 倍。

### 饱食

`body.food` 是整格，`body.food_q` 是攒着的 1/4（0–3，存档里也存）：

- 加 1/4 只在没吃满时生效，攒满 4 个进一格；吃满时清零。扣整格（死亡、冬眠）不动 1/4。
- HUD 的下一个空格按 1/4 画扇形（12 点起顺时针），透明度慢慢呼吸，多攒一个时亮一下。

### 扩展点

基础状态在固定位置跑别的行为挂进来的子任务：`fsm.add_task(扩展点, fn)`，`fn(*参数)` 返回 True 表示这一 tick 由它接管，状态自己的逻辑跳过；只想顺手做点事的返回 False。

| 扩展点 | 在哪跑 | 参数 | 现在挂着的 |
|---|---|---|---|
| `swim` | 游泳：换气、休息之后 | | 取果：游过去抓住、就地啃 |
| `zerog` | 失重待机：最前面 | | 取果：飘过去抓住、就地啃 |
| `zerog_aim` | 失重时朝目标漂之后（闲逛、追食物） | 目标 x, y | 失重吐舌 |

### 技能槽

共用动作里有一步可以由能力换成自己的做法：能力在 `skills` 里登记 `槽名 → 类`，用到的地方 `pet.skill(槽名)` 取一个实例，没有就走默认做法。

| 槽 | 谁用 | 默认 | 现在提供的 |
|---|---|---|---|
| `fetch_assist` | 取果：空中补救（`update / abort / reset / holding`） | 不补救 | 舌头：抢射粘住 |
| `hpole_mount` | 横杆：怎么上杆（`anchor_x(默认)`、`update(锚点)` → `running / grip / giveup`） | 跳起徒手抓 | 舌头：钩着荡一会再收绳 |

器官的收尾统一走 `pet.release_organs()`（状态机里是 `fsm.release_organs()`）：依次调各能力的 `release(pet)`，再解除吊挂。状态被打断、被砸晕、上杆抓住时都调它，通用代码不直接碰某个器官。

### 物品用法

定义在 `items/base.py`：

| 用法 | 提供它的物品 | 用到它的行为 |
|---|---|---|
| `edible` 能吃 | 果子、黏菌、蝙蝠 | 取果 |
| `throwable` 能扔 | 石头、矛 | 生气扔石头 / 矛 |
| `climbable` 能爬 | 竖杆、横杆、扎在墙上的矛 | 爬杆，以及溪流、圣徒的横杆玩法 |
| `warm` 能取暖 | 暖灯 | 取暖 |
| `carryable` 能拿 | 果子、石头、矛、黏菌、蝙蝠 | 手动控制时拾取 |

行为用 `fsm.items(用法)` 取场上的这类物品，顺序和放置顺序一致。

一件物体提供的用法可以随状态变：物品类型设 `varies = True` 并实现 `affords_now(物体, 用法)`。矛在手里、地上时能扔，扎进墙后不能扔、只能爬；扎进或拔出时物体自己调 `win.geometry_changed()`，规划器据此重算路线。

扎得进东西的武器在模型上设 `pierces = True`，按投掷态飞（四向出手、矛身只取水平朝向、可以带瞄准方向）的设 `aims_line = True`。行为和手部管家只看这两个属性，不认具体物品。

大件（矛）在模型上设 `bulky = True`：同时只能拿一件，数值 `dual_wield` 的猫（矛大师）不限。拿之前用 `body.can_hold(物)` 判断，手动控制选拾取目标、生气捡武器都先过它。

猫有两只手，手持物在 `body.grasps`（`l` 为主手，投掷、吃、丢下都先找它）。拿起放下走 `body.grab()` / `release()`，换手用 `start_switch_hands()`。手持物的位置由 `rendering/graphics.py` 每帧贴到手上，爬杆、趴下时跟着手的动作走。物品模型用 `edible` / `throwable` 类属性声明能不能吃、能不能当武器扔。

手持物可以跨状态一直拿着，由 `brain/hands.py` 的手部管家 `fsm.hands` 管：

- 每样手持物记一个理由（`EAT_LATER` 留着吃 / `WEAPON` 当武器 / `None` 没用）。行为收尾时用 `fsm.hands.adopt(物, 理由)` 把没用完的东西交给它，不要自己松手。自己拿起的东西按 `can_eat`、能不能扔推断理由。
- 状态用 `hands` 声明进入时要几只空手（`any` / `one` / `free`），要按情况变就覆盖 `hands_needed()`。不够时管家按理由先放下一样。
- 管家还负责：留着吃的东西揣多久再吃（真饿了不等）、放下没用的东西、消气后放下武器、站着发呆时摆弄手里的东西（挪个地方、换手、低头看）、被拎起时甩太狠脱手或拿武器打光标挣脱、被光标抢走时的反应。
- 肯不肯拿一件东西当武器统一用 `can_wield(身体, 物体)`：扎得进的只在好感低于 `SPEAR_TEMPER` 时用，`spear_toss` 的猫（圣徒）不用。
- 被砸晕、死亡、被收起、重置时一律松手。

### requires

行为的 `requires` 可以写身体标签（含能力 key），也可以写物品用法：

- 写标签：这只猫有这些标签才挂载。
- 写用法：不影响挂载，只说明这个行为会用哪类物品（参数文档里会列出来）。没有这类物品时，行为自己的触发条件不成立，也就不会去做。
- 什么都不写：每只猫都有。`essential = True` 的行为角色里关不掉（发呆、休息、游泳）。

### 性格

性格数据在 `characters/personality.py` 的 `CatPersonality`，换算后的作用在同文件的 `Traits` 里，每只猫算一次。
行为和引擎只读 `fsm.traits`，不读原始数值。每个性格轴作用在哪，登记在同文件的 `EFFECTS`，参数文档会列出来。

- 心情候选的权重统一乘 `traits.mood_weight(心情名)`（`activity` 和 `toy_pref`）。用 `mood_candidate()` 建候选就自动带上。
- 食性用 `traits.eats(物品)` 判断想不想吃，`traits.food_time()` 让肉食者偏好肉。身体能不能吃另算，见上面的 `can_eat`。

### 多猫协调

`brain/social.py`，每个世界 tick 推进一次。行为只经这里了解别的猫，不直接读别的猫的内部状态。

- 感知：`others(我)`、`state_of(猫)`、`others_x(我)`。
- 占用：`claim(我, 槽, 目标, 状态)` 占住一个目标，状态结束、被拖、晕、死时自动失效；
  `free_for(我, 目标)` 判断能不能去，别的猫占着时只有比它近一半以上才抢。取果、捡石头、爬竖杆都是先判断能不能去、选定后占住。去横杆也会登记，但还不判断别的猫占没占。
- 让路：`crowd(我)` 存挤人和让路的计数。让路趴下与普通趴下用同一套物理；对方短暂丢失时，视线沿用最后看到的位置。
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

物理固定 40Hz，绘制按插值因子 `_ts` 在两个物理 tick 之间插值。出帧节拍有三档（`window._set_mode`）：

- `vsync`：有动静时的默认档。`platform/vsync.py` 的后台线程等主屏 vblank，每隔「分频」个 vblank 投递一拍，dt 按刷新周期计，所以画面每次刷新前进的量一样。自动帧率和固定帧率都换算成刷新率的整数分频。主线程没跟上时漏掉的 vblank 计进下一拍；vblank 停了（熄屏、驱动重置）由 250ms 的看门狗定时器兜底。
- `fast`：vblank 不可用（非 Windows、打不开适配器、反复等待失败、`SLUGCATPET_VSYNC=0`）时用精确定时器，dt 用实测时长。换屏或刷新率变了会重试 `vsync`。
- `slow`：省电且没动静时用粗定时器。

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
| 找吃的 30 | FetchFruit | 以上，加体力告急 |
| 活动 20 | 爬杆、横杆、爬墙吊顶、舔光标、扔石头、各种撒欢、让路 | 以上，加饿了 |
| 待机 0 | IdleStand、Airborne、生完气闲逛 | 以上，加被顶住 |

每 tick 先跑优先级高的规则；规则一旦切了状态，后面的低级规则就打不断它。没有对应强制规则的每 tick 回调最后跑，按挂载顺序。

绘制：每帧把绘制调用录一遍、得到实际画到的范围，只刷新这部分，重绘时照着回放（`rendering/display_list.py`）。
身体部件的叠放顺序（`graphics_draw.py` 的 `draw_sprites`），从后到前：远侧臂、身体、尾巴、腿、臀、近侧臂、头、脸。
部件之间有四个槽位给能力和配件用：`over_tail`（尾巴斑点，尾巴、腿、臀之上，近侧臂之下）、`under_face`（鳃）、`behind_face`（疤）、`over_face`（舌头）。
贴在尾巴上的东西用各段的位置和半径现算（见 `accessories/tail_specks` 的 `spine_at`），段数、粗细随皮肤变也贴得上。
物品各层都只画到地面线（`items/host.py` 的 `_draw_kinds`），窗口下延盖住任务栏时地面以下的部分不露出来；猫的腿同理。

### 东张西望

`brain/objectlooker.py`，待机兜底：

- 每 tick 以 `LOOK_UPDATE_PROB`（乘性格的 look 系数）的概率重新评估兴趣，目标不再存在则不看。
- 看腻按评估次数计：超过 `LOOK_INTEREST_DECAY_UPDATES` 次后兴趣打折，更有意思的候选（光标、物体、别的猫）才会取代当前目标。
- 另有 `LOOK_NOTHING_PROB` 的概率谁也不看。

## 接口

### 能力（`abilities/base.py`）

所有钩子可选。每只猫一份实例，`self.p` 是解析后的参数。

| 钩子 | 时机 / 用途 |
|---|---|
| `attach_body(pet, body)` | 身体刚建好：写物理特性，如 `body.aquatic`；也可往 `body.throw_hooks` 登记扔出武器后的回调（重压用它实现扔矛） |
| `build(pet)` | 建器官，返回值存到 `pet.organs[key]` |
| `draw_layers(pet)` | `[(槽位, fn(gfx, painter, atlas, ts))]` |
| `pre_step(pet)` / `post_step(pet)` | 见上面的 tick 顺序 |
| `resize(pet, floor_y)` | 世界尺寸变了 |
| `reaches(pet)` | 给规划器的够取方式（`planning.Reach` 子类实例） |
| `release(pet)` | 状态被打断、晕、死时收回器官（舌头收舌、恢复默认参数） |
| `skills`（类属性） | 技能槽 → 类，见上面「技能槽」 |
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
| `grab_pad` | 设了就能用鼠标拖；抓取点按 `grab_dist()` 算（矛按整根矛身） |
| `varies` | 用法随物体状态变，配合 `affords_now()` |

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
| `fsm.add_task(扩展点, fn())` | 在基础状态的扩展点挂子任务，见上面「扩展点」 |
| `mood_candidate(fsm, 名, p, gate)` + `fsm.register_mood_entry(名, 状态)` | 心情候选：无聊时按权重抽到就进入该状态。参数用 `mood_params(...)` 生成 |
| `fsm.items(用法)` | 场上提供这种用法的物品 |
| `fsm.social` | 多猫协调，见上 |
| `fsm.traits` | 性格 |
| `fsm.provide(名, fn)` / `fsm.ask(名)` | 行为之间互相查询，不直接引用对方 |
| `fsm.on_stun(fn)` | 被砸晕时收尾（松手、放掉占用） |
| `fsm.add_threat_responder(fn)` | 杀死弹窗出现时的应对 |
| `fsm.block_interaction(状态名)` | 该状态期间屏蔽光标交互 |
| `fsm._transition(状态名)` / `fsm.settle()` | 切换状态 / 动作结束回待机或空中 |

状态自己声明 `tier`（优先级）、`energy`（体力档位）、`mood`（心情名）、`hands`（要几只空手）。状态机不按名字特判。

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
4. 要在游泳、失重这些基础状态里也做这件事时，用 `fsm.add_task` 挂到对应扩展点，不要改基础状态本身。
5. 运行 `python tools/params_doc.py` 重新生成参数文档。

### 新能力

1. 建 `abilities/<key>/`：写 `Ability` 子类，按需实现钩子；器官、绘制、够取方式放在同一个包里。
2. 在 `abilities/__init__.py` 导入它，加到 `BUILTIN` 末尾。
3. 需要核心配合时，加一个通用的钩子或身体特性（像 `body.aquatic`），不要在核心里写能力的名字。
4. 身体少了某种通用的本事（像没有嘴），在 `removes` 里去掉对应标签，依赖它的行为自动不挂；多了一种，写进 `provides`。
5. 只是换掉共用动作里的一步（像舌头钩横杆），登记到 `skills`；器官要在被打断时收回，实现 `release(pet)`。通用代码里不要出现这个能力的名字。
6. 写依赖它的行为，在某个角色 JSON 里启用，重新生成参数文档。

### 新角色

只写一个 JSON，见 [CHARACTERS.md](CHARACTERS.md)。

### 外观与皮肤

一只猫的外观是 `appearance.py` 的 `Look`，存档里的 `look` 字段：

| 字段 | 含义 |
|---|---|
| `skin` | 整套皮肤 id，空为原皮 |
| `parts` | 部位组 → 皮肤 id，覆盖整套；`""` 为原皮，`EMPTY` 为隐藏该部位 |
| `part_colors` | 部位组 → 颜色 |
| `colors` | 自定体色 / 脸色 |
| `tail` | 自定尾巴形状 `length` / `wideness` / `roundness`，空则跟随皮肤 |
| `accessories` | 配件 key → 开关与颜色 |

- 部位组：`HEAD`、`FACE`、`BODY`、`ARMS`、`HIPS`、`LEGS`、`TAIL`；配件经 `Accessory.skin_group` 对应 `FACESCAR`、`GILLS`。
- 查找：`skins.resolver_for(atlas, look, species)` 给每个部位组选来源皮肤，建出 `SkinAtlasSet`；皮肤缺该部位时回到原皮。部位的颜色和尾巴形状随它的来源皮肤。
- 换整套（`Look.set_skin`）会清掉部位覆盖、部位颜色和自定尾巴。
- 取色优先级（`base_colors`）：部位颜色 > 自定体色 / 脸色 > 皮肤默认色 > 猫种自带色。
- 皮肤列表里隐藏 Dress My Slugcat 的两个绘制底稿包，其余（含内置的 Saint Shirt）都可选。

### 新配件

1. 建 `accessories/<key>/__init__.py`：写 `Accessory` 子类，设 `key`、`title`、`default_color`、`default_on`（默认戴的猫种），按需设 `color_group`（取色用的皮肤部位组）和 `skin_group`（外观面板里可单独换包的部位组），实现 `post_step` 和 `draw_layers`。
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
python tests/behavior_check.py check     6 个固定种子场景，逐 tick 比对状态、位置和渲染帧
python tests/behavior_check.py record    有意改了行为或画面后重录基线
python tests/social_check.py run         多猫长时间运行，统计抢目标、互相让路、卡住等异常
python tests/spear_check.py              矛的边界情况逐条断言（扎墙、拔出、友伤、串蝙蝠、相撞、带光标等）
python tools/params_doc.py --check       参数文档是否最新
uv run ruff format / uv run ruff check   格式和静态检查（版本与规则在 pyproject.toml）
```

不该改变行为的改动，`check` 必须全过。有意改了手感，确认没问题后再 `record`。
`packaging/build_release.ps1 -Test` 打包前会跑行为检查和参数文档检查。

## 还没模块化的部分

- 爬杆行为还按 `kind == "vertical"` / `"horizontal"` 区分两种杆。
- 世界状态还挂在 `window.py` 的窗口上，没有单独的 World 对象。
- 超度时睁眼的脸是核心绘制直接读 `gfx.ascension`，不是绘制槽位。
- 游泳和无重力时追食物还没走占用登记；横杆位置只登记，不判断。
