"""原版命令包装器 — 为扩展提供类型化的 Minecraft 命令接口（全命令）。"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yasl.main import MinecraftServer


class CommandHelper:
    """通过 MinecraftServer.send_command_async() 封装的类型化原版命令。"""

    __slots__ = ("_server",)

    def __init__(self, server: MinecraftServer | None = None) -> None:
        self._server = server

    def bind(self, server: MinecraftServer) -> None:
        self._server = server

    async def _run(self, cmd: str, timeout: float = 5.0) -> list[str]:
        if self._server is None:
            return []
        result = await self._server.send_command_async(cmd, timeout=timeout)
        return result.get("lines", [])

    async def raw(self, command: str, timeout: float = 5.0) -> list[str]:
        """直接发送任意命令（绕过类型化接口）。"""
        return await self._run(command, timeout=timeout)

    # ================================================================
    # 玩家管理
    # ================================================================
    async def ban(self, player: str, reason: str = "") -> list[str]:
        r = f" {reason}" if reason else ""
        return await self._run(f"ban {player}{r}")

    async def ban_ip(self, target: str, reason: str = "") -> list[str]:
        r = f" {reason}" if reason else ""
        return await self._run(f"ban-ip {target}{r}")

    async def banlist(self, ban_type: str = "players") -> list[str]:
        return await self._run(f"banlist {ban_type}")

    async def pardon(self, player: str) -> list[str]:
        return await self._run(f"pardon {player}")

    async def pardon_ip(self, target: str) -> list[str]:
        return await self._run(f"pardon-ip {target}")

    async def op(self, player: str) -> list[str]:
        return await self._run(f"op {player}")

    async def deop(self, player: str) -> list[str]:
        return await self._run(f"deop {player}")

    async def kick(self, player: str, reason: str = "") -> list[str]:
        r = f" {reason}" if reason else ""
        return await self._run(f"kick {player}{r}")

    async def whitelist_add(self, player: str) -> list[str]:
        return await self._run(f"whitelist add {player}")

    async def whitelist_remove(self, player: str) -> list[str]:
        return await self._run(f"whitelist remove {player}")

    async def whitelist_list(self) -> list[str]:
        return await self._run("whitelist list")

    async def whitelist_on(self) -> list[str]:
        return await self._run("whitelist on")

    async def whitelist_off(self) -> list[str]:
        return await self._run("whitelist off")

    async def whitelist_reload(self) -> list[str]:
        return await self._run("whitelist reload")

    async def transfer(self, player: str, host: str, port: int = 25565) -> list[str]:
        return await self._run(f"transfer {player} {host} {port}")

    async def setidletimeout(self, minutes: int) -> list[str]:
        return await self._run(f"setidletimeout {minutes}")

    # ================================================================
    # 聊天 / 消息
    # ================================================================
    async def say(self, message: str) -> list[str]:
        return await self._run(f"say {message}")

    async def msg(self, player: str, message: str) -> list[str]:
        return await self._run(f"msg {player} {message}")

    async def tell(self, player: str, message: str) -> list[str]:
        return await self._run(f"tell {player} {message}")

    async def w(self, player: str, message: str) -> list[str]:
        return await self._run(f"w {player} {message}")

    async def tellraw(self, player: str, raw_json: str) -> list[str]:
        return await self._run(f'tellraw {player} {raw_json}')

    async def me(self, action: str) -> list[str]:
        return await self._run(f"me {action}")

    async def teammsg(self, message: str) -> list[str]:
        return await self._run(f"teammsg {message}")

    # ================================================================
    # 游戏模式 / 难度 / 规则
    # ================================================================
    async def gamemode(self, mode: str, player: str = "@s") -> list[str]:
        return await self._run(f"gamemode {mode} {player}")

    async def defaultgamemode(self, mode: str) -> list[str]:
        return await self._run(f"defaultgamemode {mode}")

    async def difficulty(self, level: str) -> list[str]:
        return await self._run(f"difficulty {level}")

    async def gamerule(self, rule: str, value: str | int | bool = "") -> list[str]:
        v = f" {value}" if value != "" else ""
        return await self._run(f"gamerule {rule}{v}")

    # ================================================================
    # 时间 / 天气
    # ================================================================
    async def time_set(self, value: str | int) -> list[str]:
        return await self._run(f"time set {value}")

    async def time_add(self, value: int) -> list[str]:
        return await self._run(f"time add {value}")

    async def time_query(self, query: str) -> list[str]:
        return await self._run(f"time query {query}")

    async def weather(self, weather_type: str, duration: int | None = None) -> list[str]:
        d = f" {duration}" if duration is not None else ""
        return await self._run(f"weather {weather_type}{d}")

    # ================================================================
    # 世界管理
    # ================================================================
    async def seed(self) -> list[str]:
        return await self._run("seed")

    async def setworldspawn(self, x: str = "", y: str = "", z: str = "") -> list[str]:
        pos = f" {x} {y} {z}" if x and y and z else ""
        return await self._run(f"setworldspawn{pos}")

    async def spawnpoint(self, player: str = "@s", x: str = "", y: str = "", z: str = "",
                         angle: str = "") -> list[str]:
        args = f" {player}"
        if x and y and z:
            args += f" {x} {y} {z}"
        if angle:
            args += f" {angle}"
        return await self._run(f"spawnpoint{args}")

    async def worldborder_add(self, size: float, time: int = 0) -> list[str]:
        return await self._run(f"worldborder add {size} {time}")

    async def worldborder_set(self, size: float, time: int = 0) -> list[str]:
        return await self._run(f"worldborder set {size} {time}")

    async def worldborder_center(self, x: float, z: float) -> list[str]:
        return await self._run(f"worldborder center {x} {z}")

    async def worldborder_damage_amount(self, amount: float) -> list[str]:
        return await self._run(f"worldborder damage amount {amount}")

    async def worldborder_damage_buffer(self, buffer: float) -> list[str]:
        return await self._run(f"worldborder damage buffer {buffer}")

    async def worldborder_get(self) -> list[str]:
        return await self._run("worldborder get")

    async def worldborder_warning_distance(self, distance: int) -> list[str]:
        return await self._run(f"worldborder warning distance {distance}")

    async def worldborder_warning_time(self, time: int) -> list[str]:
        return await self._run(f"worldborder warning time {time}")

    # ================================================================
    # 传送 / 移动
    # ================================================================
    async def tp(self, target: str, destination: str = "") -> list[str]:
        d = f" {destination}" if destination else ""
        return await self._run(f"tp {target}{d}")

    async def teleport(self, *args: str) -> list[str]:
        return await self._run(f"teleport {' '.join(args)}")

    async def spreadplayers(self, x: float, z: float, spread_distance: float,
                            max_range: float, respect_teams: str = "",
                            targets: str = "@a") -> list[str]:
        teams = f" {respect_teams}" if respect_teams else ""
        return await self._run(
            f"spreadplayers {x} {z} {spread_distance} {max_range}{teams} {targets}"
        )

    async def ride_mount(self, target: str) -> list[str]:
        return await self._run(f"ride {target} mount @s")

    async def ride_dismount(self, target: str) -> list[str]:
        return await self._run(f"ride {target} dismount")

    async def rotate(self, target: str, yaw: float = 0, pitch: float = 0) -> list[str]:
        return await self._run(f"rotate {target} {yaw} {pitch}")

    async def spectate(self, target: str, player: str = "@s") -> list[str]:
        return await self._run(f"spectate {target} {player}")

    # ================================================================
    # 效果 / 属性 / 附魔
    # ================================================================
    async def effect_give(self, target: str, effect: str, seconds: int = 30,
                          amplifier: int = 0, hide_particles: bool = False) -> list[str]:
        h = " true" if hide_particles else ""
        return await self._run(f"effect give {target} {effect} {seconds} {amplifier}{h}")

    async def effect_clear(self, target: str = "@a", effect: str = "") -> list[str]:
        e = f" {effect}" if effect else ""
        return await self._run(f"effect clear {target}{e}")

    async def attribute_get(self, target: str, attribute: str, scale: float = 1.0) -> list[str]:
        return await self._run(f"attribute {target} {attribute} get {scale}")

    async def attribute_base_set(self, target: str, attribute: str, value: float) -> list[str]:
        return await self._run(f"attribute {target} {attribute} base set {value}")

    async def attribute_base_get(self, target: str, attribute: str, scale: float = 1.0) -> list[str]:
        return await self._run(f"attribute {target} {attribute} base get {scale}")

    async def attribute_modifier_add(self, target: str, attribute: str, uuid: str,
                                     name: str, value: float, operation: str) -> list[str]:
        return await self._run(
            f"attribute {target} {attribute} modifier add {uuid} {name} {value} {operation}"
        )

    async def attribute_modifier_remove(self, target: str, attribute: str,
                                        uuid: str) -> list[str]:
        return await self._run(f"attribute {target} {attribute} modifier remove {uuid}")

    async def enchant(self, player: str, enchantment: str, level: int = 1) -> list[str]:
        return await self._run(f"enchant {player} {enchantment} {level}")

    async def damage(self, target: str, amount: float,
                     damage_type: str = "") -> list[str]:
        dt = f" {damage_type}" if damage_type else ""
        return await self._run(f"damage {target} {amount}{dt}")

    async def kill(self, target: str = "@s") -> list[str]:
        return await self._run(f"kill {target}")

    # ================================================================
    # 物品 / 经验
    # ================================================================
    async def give(self, player: str, item: str, count: int = 1) -> list[str]:
        return await self._run(f"give {player} {item} {count}")

    async def clear(self, player: str = "@s", item: str = "",
                    max_count: int = -1) -> list[str]:
        args = f"{player}"
        if item:
            args += f" {item}"
            if max_count >= 0:
                args += f" {max_count}"
        return await self._run(f"clear {args}")

    async def item_replace_block(self, x: int, y: int, z: int, slot: str,
                                 item: str, count: int = 1) -> list[str]:
        return await self._run(
            f"item replace block {x} {y} {z} {slot} with {item} {count}"
        )

    async def item_replace_entity(self, target: str, slot: str,
                                  item: str, count: int = 1) -> list[str]:
        return await self._run(
            f"item replace entity {target} {slot} with {item} {count}"
        )

    async def xp_add(self, player: str, amount: int,
                     xp_type: str = "points") -> list[str]:
        return await self._run(f"xp add {player} {amount} {xp_type}")

    async def xp_set(self, player: str, amount: int,
                     xp_type: str = "points") -> list[str]:
        return await self._run(f"xp set {player} {amount} {xp_type}")

    async def xp_query(self, player: str, xp_type: str = "points") -> list[str]:
        return await self._run(f"xp query {player} {xp_type}")

    async def loot_give(self, player: str, loot_table: str) -> list[str]:
        return await self._run(f"loot give {player} loot {loot_table}")

    async def loot_insert(self, x: int, y: int, z: int, loot_table: str) -> list[str]:
        return await self._run(
            f"loot insert {x} {y} {z} loot {loot_table}"
        )

    async def loot_spawn(self, x: float, y: float, z: float,
                         loot_table: str) -> list[str]:
        return await self._run(f"loot spawn {x} {y} {z} loot {loot_table}")

    async def recipe_give(self, player: str, recipe: str = "*") -> list[str]:
        return await self._run(f"recipe give {player} {recipe}")

    async def recipe_take(self, player: str, recipe: str = "*") -> list[str]:
        return await self._run(f"recipe take {player} {recipe}")

    # ================================================================
    # 记分板
    # ================================================================
    async def scoreboard_objectives_add(self, name: str, criteria: str = "dummy",
                                        display_name: str = "") -> list[str]:
        dn = f" {display_name}" if display_name else ""
        return await self._run(f"scoreboard objectives add {name} {criteria}{dn}")

    async def scoreboard_objectives_remove(self, name: str) -> list[str]:
        return await self._run(f"scoreboard objectives remove {name}")

    async def scoreboard_objectives_setdisplay(self, slot: str,
                                               objective: str = "") -> list[str]:
        o = f" {objective}" if objective else ""
        return await self._run(f"scoreboard objectives setdisplay {slot}{o}")

    async def scoreboard_players_add(self, player: str, objective: str,
                                     value: int = 1) -> list[str]:
        return await self._run(f"scoreboard players add {player} {objective} {value}")

    async def scoreboard_players_set(self, player: str, objective: str,
                                     value: int) -> list[str]:
        return await self._run(f"scoreboard players set {player} {objective} {value}")

    async def scoreboard_players_get(self, player: str, objective: str) -> list[str]:
        return await self._run(f"scoreboard players get {player} {objective}")

    async def scoreboard_players_reset(self, player: str,
                                       objective: str = "") -> list[str]:
        o = f" {objective}" if objective else ""
        return await self._run(f"scoreboard players reset {player}{o}")

    async def scoreboard_players_operation(self, target: str, target_obj: str,
                                           op: str, source: str,
                                           source_obj: str) -> list[str]:
        return await self._run(
            f"scoreboard players operation {target} {target_obj} {op} {source} {source_obj}"
        )

    async def scoreboard_players_enable(self, player: str, objective: str) -> list[str]:
        return await self._run(f"scoreboard players enable {player} {objective}")

    async def scoreboard_players_list(self, player: str = "*") -> list[str]:
        return await self._run(f"scoreboard players list {player}")

    # ================================================================
    # 队伍
    # ================================================================
    async def team_add(self, name: str, display_name: str = "") -> list[str]:
        dn = f" {display_name}" if display_name else ""
        return await self._run(f"team add {name}{dn}")

    async def team_remove(self, name: str) -> list[str]:
        return await self._run(f"team remove {name}")

    async def team_empty(self, name: str) -> list[str]:
        return await self._run(f"team empty {name}")

    async def team_join(self, team: str, members: str = "@s") -> list[str]:
        return await self._run(f"team join {team} {members}")

    async def team_leave(self, members: str = "@s") -> list[str]:
        return await self._run(f"team leave {members}")

    async def team_modify_color(self, team: str, color: str) -> list[str]:
        return await self._run(f"team modify {team} color {color}")

    async def team_modify_friendlyfire(self, team: str, enabled: bool) -> list[str]:
        return await self._run(f"team modify {team} friendlyFire {str(enabled).lower()}")

    async def team_modify_prefix(self, team: str, prefix: str) -> list[str]:
        return await self._run(f'team modify {team} prefix "{prefix}"')

    async def team_modify_suffix(self, team: str, suffix: str) -> list[str]:
        return await self._run(f'team modify {team} suffix "{suffix}"')

    # ================================================================
    # 标签
    # ================================================================
    async def tag_add(self, target: str, name: str) -> list[str]:
        return await self._run(f"tag {target} add {name}")

    async def tag_remove(self, target: str, name: str) -> list[str]:
        return await self._run(f"tag {target} remove {name}")

    async def tag_list(self, target: str) -> list[str]:
        return await self._run(f"tag {target} list")

    # ================================================================
    # Bossbar
    # ================================================================
    async def bossbar_add(self, bossbar_id: str, name: str) -> list[str]:
        return await self._run(f'bossbar add {bossbar_id} "{name}"')

    async def bossbar_remove(self, bossbar_id: str) -> list[str]:
        return await self._run(f"bossbar remove {bossbar_id}")

    async def bossbar_set_value(self, bossbar_id: str, value: int,
                                max_value: int) -> list[str]:
        return await self._run(f"bossbar set {bossbar_id} value {value}")
        _ = max_value

    async def bossbar_set_max(self, bossbar_id: str, max_value: int) -> list[str]:
        return await self._run(f"bossbar set {bossbar_id} max {max_value}")

    async def bossbar_set_players(self, bossbar_id: str,
                                  players: str = "@a") -> list[str]:
        return await self._run(f"bossbar set {bossbar_id} players {players}")

    async def bossbar_set_visible(self, bossbar_id: str,
                                  visible: bool) -> list[str]:
        return await self._run(
            f"bossbar set {bossbar_id} visible {str(visible).lower()}"
        )

    async def bossbar_get(self, bossbar_id: str, key: str = "value") -> list[str]:
        return await self._run(f"bossbar get {bossbar_id} {key}")

    async def bossbar_list(self) -> list[str]:
        return await self._run("bossbar list")

    # ================================================================
    # 方块 / 区域操作
    # ================================================================
    async def fill(self, x1: int, y1: int, z1: int, x2: int, y2: int, z2: int,
                   block: str, mode: str = "") -> list[str]:
        m = f" {mode}" if mode else ""
        return await self._run(f"fill {x1} {y1} {z1} {x2} {y2} {z2} {block}{m}")

    async def clone(self, x1: int, y1: int, z1: int, x2: int, y2: int, z2: int,
                    dx: int, dy: int, dz: int, mask_mode: str = "replace",
                    clone_mode: str = "normal") -> list[str]:
        return await self._run(
            f"clone {x1} {y1} {z1} {x2} {y2} {z2} {dx} {dy} {dz} {mask_mode} {clone_mode}"
        )

    async def setblock(self, x: int, y: int, z: int, block: str,
                       mode: str = "replace") -> list[str]:
        return await self._run(f"setblock {x} {y} {z} {block} {mode}")

    async def fillbiome(self, x1: int, y1: int, z1: int, x2: int, y2: int,
                        z2: int, biome: str) -> list[str]:
        return await self._run(f"fillbiome {x1} {y1} {z1} {x2} {y2} {z2} {biome}")

    async def setworldspawn_at(self, x: str, y: str, z: str) -> list[str]:
        return await self._run(f"setworldspawn {x} {y} {z}")

    # ================================================================
    # 生成 / 粒子 / 音效
    # ================================================================
    async def summon(self, entity: str, x: str = "~", y: str = "~",
                     z: str = "~", nbt: str = "") -> list[str]:
        n = f" {nbt}" if nbt else ""
        return await self._run(f"summon {entity} {x} {y} {z}{n}")

    async def particle(self, name: str, x: float, y: float, z: float, dx: float = 0,
                       dy: float = 0, dz: float = 0, speed: float = 0,
                       count: int = 1, player: str = "@a") -> list[str]:
        return await self._run(
            f"particle {name} {x} {y} {z} {dx} {dy} {dz} {speed} {count} "
            f"normal {player}"
        )

    async def playsound(self, sound: str, player: str = "@a", x: str = "~",
                        y: str = "~", z: str = "~", volume: float = 1.0,
                        pitch: float = 1.0, min_volume: float = 1.0) -> list[str]:
        return await self._run(
            f"playsound {sound} master {player} {x} {y} {z} {volume} {pitch} "
            f"{min_volume}"
        )

    async def stopsound(self, player: str, category: str = "",
                        sound: str = "") -> list[str]:
        args = f"{player}"
        if category:
            args += f" {category}"
        if sound:
            args += f" {sound}"
        return await self._run(f"stopsound {args}")

    async def place_feature(self, feature: str, x: int = 0, y: int = 0,
                            z: int = 0) -> list[str]:
        pos = f" {x} {y} {z}" if x or y or z else ""
        return await self._run(f"place feature {feature}{pos}")

    # ================================================================
    # 进度
    # ================================================================
    async def advancement_grant(self, player: str, advancement: str = "",
                                criterion: str = "*") -> list[str]:
        adv = f" {advancement}" if advancement else ""
        return await self._run(f"advancement grant {player} only{adv} {criterion}")

    async def advancement_revoke(self, player: str, advancement: str = "",
                                 criterion: str = "*") -> list[str]:
        adv = f" {advancement}" if advancement else ""
        return await self._run(f"advancement revoke {player} only{adv} {criterion}")

    # ================================================================
    # 标题 / 对话框
    # ================================================================
    async def title_title(self, player: str, text: str) -> list[str]:
        return await self._run(f'title {player} title {{"text":"{text}"}}')

    async def title_subtitle(self, player: str, text: str) -> list[str]:
        return await self._run(f'title {player} subtitle {{"text":"{text}"}}')

    async def title_actionbar(self, player: str, text: str) -> list[str]:
        return await self._run(f'title {player} actionbar {{"text":"{text}"}}')

    async def title_times(self, player: str, fade_in: int, stay: int,
                          fade_out: int) -> list[str]:
        return await self._run(
            f"title {player} times {fade_in} {stay} {fade_out}"
        )

    async def title_clear(self, player: str) -> list[str]:
        return await self._run(f"title {player} clear")

    async def title_reset(self, player: str) -> list[str]:
        return await self._run(f"title {player} reset")

    # ================================================================
    # 触发器 / 路径点
    # ================================================================
    async def trigger(self, objective: str, value: str = "set 1") -> list[str]:
        return await self._run(f"trigger {objective} {value}")

    async def waypoint_list(self, player: str = "@s") -> list[str]:
        return await self._run(f"waypoint list {player}")

    # ================================================================
    # 服务器管理
    # ================================================================
    async def list_players(self) -> list[str]:
        return await self._run("list")

    async def save_all(self, flush: bool = False) -> list[str]:
        f = " flush" if flush else ""
        return await self._run(f"save-all{f}")

    async def save_on(self) -> list[str]:
        return await self._run("save-on")

    async def save_off(self) -> list[str]:
        return await self._run("save-off")

    async def reload(self) -> list[str]:
        return await self._run("reload")

    async def datapack_disable(self, name: str) -> list[str]:
        return await self._run(f"datapack disable {name}")

    async def datapack_enable(self, name: str) -> list[str]:
        return await self._run(f"datapack enable {name}")

    async def datapack_list(self) -> list[str]:
        return await self._run("datapack list")

    async def forceload_add(self, x1: int, z1: int, x2: int = 0,
                            z2: int = 0) -> list[str]:
        if x2 or z2:
            return await self._run(f"forceload add {x1} {z1} {x2} {z2}")
        return await self._run(f"forceload add {x1} {z1}")

    async def forceload_remove(self, x1: int, z1: int, x2: int = 0,
                               z2: int = 0) -> list[str]:
        if x2 or z2:
            return await self._run(f"forceload remove {x1} {z1} {x2} {z2}")
        return await self._run(f"forceload remove {x1} {z1}")

    async def forceload_query(self, x: int, z: int) -> list[str]:
        return await self._run(f"forceload query {x} {z}")

    async def locate_structure(self, structure: str) -> list[str]:
        return await self._run(f"locate structure {structure}")

    async def locate_biome(self, biome: str) -> list[str]:
        return await self._run(f"locate biome {biome}")

    async def locate_poi(self, poi: str) -> list[str]:
        return await self._run(f"locate poi {poi}")

    async def version(self) -> list[str]:
        return await self._run("version")

    async def help_command(self, command: str = "") -> list[str]:
        c = f" {command}" if command else ""
        return await self._run(f"help{c}")

    async def tick_rate(self, rate: float = 20.0) -> list[str]:
        return await self._run(f"tick rate {rate}")

    async def tick_freeze(self) -> list[str]:
        return await self._run("tick freeze")

    async def tick_unfreeze(self) -> list[str]:
        return await self._run("tick unfreeze")

    async def schedule_function(self, function: str, time: str,
                                append: str = "") -> list[str]:
        a = f" {append}" if append else ""
        return await self._run(f"schedule function {function} {time}{a}")

    async def schedule_clear(self, function: str) -> list[str]:
        return await self._run(f"schedule clear {function}")

    async def function_run(self, name: str) -> list[str]:
        return await self._run(f"function {name}")

    # ================================================================
    # execute 子命令
    # ================================================================
    async def execute_as(self, target: str, subcommand: str) -> list[str]:
        return await self._run(f"execute as {target} run {subcommand}")

    async def execute_at(self, target: str, subcommand: str) -> list[str]:
        return await self._run(f"execute at {target} run {subcommand}")

    async def execute_positioned(self, x: float, y: float, z: float,
                                 subcommand: str) -> list[str]:
        return await self._run(
            f"execute positioned {x} {y} {z} run {subcommand}"
        )

    async def execute_if_entity(self, target: str, subcommand: str) -> list[str]:
        return await self._run(f"execute if entity {target} run {subcommand}")

    async def execute_unless_entity(self, target: str,
                                    subcommand: str) -> list[str]:
        return await self._run(f"execute unless entity {target} run {subcommand}")

    async def execute_if_block(self, x: int, y: int, z: int, block: str,
                               subcommand: str) -> list[str]:
        return await self._run(
            f"execute if block {x} {y} {z} {block} run {subcommand}"
        )

    async def execute_if_score(self, target: str, objective: str, op: str,
                               source: str, source_obj: str,
                               subcommand: str) -> list[str]:
        return await self._run(
            f"execute if score {target} {objective} {op} {source} {source_obj} "
            f"run {subcommand}"
        )

    async def execute_in(self, dimension: str, subcommand: str) -> list[str]:
        return await self._run(f"execute in {dimension} run {subcommand}")

    async def execute_run(self, command: str) -> list[str]:
        return await self._run(f"execute run {command}")

    # ================================================================
    # swing / stopwatch / return / random / data / fetchprofile
    # ================================================================
    async def swing(self, target: str, arm: str = "mainhand") -> list[str]:
        return await self._run(f"swing {target} {arm}")

    async def stopwatch_start(self) -> list[str]:
        return await self._run("stopwatch start")

    async def stopwatch_stop(self) -> list[str]:
        return await self._run("stopwatch stop")

    async def stopwatch_reset(self) -> list[str]:
        return await self._run("stopwatch reset")

    async def perform_return(self, value: int = 0) -> list[str]:
        return await self._run(f"return {value}")

    async def perform_return_fail(self) -> list[str]:
        return await self._run("return fail")

    async def perform_return_run(self, command: str) -> list[str]:
        return await self._run(f"return run {command}")

    async def random_value(self, min_val: int, max_val: int) -> list[str]:
        return await self._run(f"random value {min_val} {max_val}")

    async def random_reset(self, namespace: str = "minecraft") -> list[str]:
        return await self._run(f"random reset * {namespace}")

    async def data_get_block(self, x: int, y: int, z: int, path: str = "",
                             scale: float = 1.0) -> list[str]:
        p = f" {path}" if path else ""
        return await self._run(f"data get block {x} {y} {z}{p} {scale}")

    async def data_get_entity(self, target: str, path: str = "",
                              scale: float = 1.0) -> list[str]:
        p = f" {path}" if path else ""
        return await self._run(f"data get entity {target}{p} {scale}")

    async def data_merge_block(self, x: int, y: int, z: int,
                               nbt: str) -> list[str]:
        return await self._run(f"data merge block {x} {y} {z} {nbt}")

    async def data_merge_entity(self, target: str, nbt: str) -> list[str]:
        return await self._run(f"data merge entity {target} {nbt}")

    async def data_remove_block(self, x: int, y: int, z: int,
                                path: str) -> list[str]:
        return await self._run(f"data remove block {x} {y} {z} {path}")

    async def data_remove_entity(self, target: str, path: str) -> list[str]:
        return await self._run(f"data remove entity {target} {path}")

    async def fetchprofile(self, player: str) -> list[str]:
        return await self._run(f"fetchprofile {player}")

    # ================================================================
    # 服务端专用
    # ================================================================
    async def stop(self) -> list[str]:
        return await self._run("stop")

    async def debug_start(self) -> list[str]:
        return await self._run("debug start")

    async def debug_stop(self) -> list[str]:
        return await self._run("debug stop")

    async def debug_report(self) -> list[str]:
        return await self._run("debug report")

    async def jfr_start(self) -> list[str]:
        return await self._run("jfr start")

    async def jfr_stop(self) -> list[str]:
        return await self._run("jfr stop")

    async def perf_start(self) -> list[str]:
        return await self._run("perf start")

    async def perf_stop(self) -> list[str]:
        return await self._run("perf stop")

    async def test_import(self, filename: str) -> list[str]:
        return await self._run(f"test import {filename}")

    async def test_export(self, path: str) -> list[str]:
        return await self._run(f"test export {path}")

    async def test_create(self, name: str, x: int = 0, y: int = 0,
                          z: int = 0) -> list[str]:
        return await self._run(f"test create {name} {x} {y} {z}")

    async def test_runthis(self, times: int = 1) -> list[str]:
        return await self._run(f"test runthis {times}")

    async def test_runclosest(self, times: int = 1) -> list[str]:
        return await self._run(f"test runclosest {times}")

    async def test_runthese(self, times: int = 1) -> list[str]:
        return await self._run(f"test runthese {times}")