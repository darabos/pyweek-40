import enum
import math
import random
import pyxel
import threading
from dataclasses import dataclass
from collections.abc import Callable


pyxel.init(240, 320)
pyxel.load("assets/art.pyxres")

_SPLEEN_32x64 = pyxel.Font("assets/spleen-32x64.bdf")
_SPLEEN_16x32 = pyxel.Font("assets/spleen-16x32.bdf")
_SPLEEN_8x16  = pyxel.Font("assets/spleen-8x16.bdf")


class Direction(enum.IntFlag):
    NONE = 0
    UP = enum.auto()
    DOWN = enum.auto()
    LEFT = enum.auto()
    RIGHT = enum.auto()


@dataclass
class Player:
    game: "Game"
    x: float
    y: float
    vx: float = 0
    vy: float = 0
    width: int = 16
    height: int = 16
    direction: Direction = Direction.NONE.value
    maximum_altitude: int = 300
    carrying: tuple[int, int] | None = None

    def draw(self):
        if self.carrying:
            sx, sy = self.carrying
            pyxel.blt(self.x, self.y + 10, 0, 16 * sx, 16 * sy, 16, 16, colkey=0)
        pyxel.blt(self.x, self.y, 0, 32, 0, 16, 16, colkey=0)

    def handle_keypress(self) -> Direction:
        direction = Direction.NONE.value
        if pyxel.btn(pyxel.KEY_UP):
            direction |= Direction.UP.value
        if pyxel.btn(pyxel.KEY_DOWN):
            direction |= Direction.DOWN.value
        if pyxel.btn(pyxel.KEY_LEFT):
            direction |= Direction.LEFT.value
        if pyxel.btn(pyxel.KEY_RIGHT):
            direction |= Direction.RIGHT.value
        return direction

    def update(self):
        ACCELERATION = 1.0
        GRAVITY = 0.0
        DRAG = 0.08

        direction = self.handle_keypress()
        if direction & Direction.LEFT.value:
            self.vx -= ACCELERATION
        if direction & Direction.RIGHT.value:
            self.vx += ACCELERATION
        if direction & Direction.UP.value:
            self.vy -= ACCELERATION
        if direction & Direction.DOWN.value:
            self.vy += ACCELERATION

        self.vy += GRAVITY
        self.x += self.vx
        self.y += self.vy
        v = math.hypot(self.vx, self.vy)
        self.vx /= 1 + DRAG * v * v
        self.vy /= 1 + DRAG * v * v
        if self.y > pyxel.height - self.height:
            self.y = pyxel.height - self.height
            self.vy = 0
        if self.y < -self.maximum_altitude:
            self.y = -self.maximum_altitude
            self.vy = 0
        if self.x > pyxel.width - self.width:
            self.x = pyxel.width - self.width
            self.vx = 0
        if self.x < 0:
            self.x = 0
            self.vx = 0
        if pyxel.btnp(pyxel.KEY_SPACE):
            if self.carrying:
                b = self.game.closest_block(self.x, self.y + 18, grab=False)
                nb = Block(
                    x=b.x,
                    y=b.y,
                    z=b.z + 8,
                    sprite=self.carrying,
                    below=b,
                )
                b.above = nb
                self.game.city.blocks.append(nb)
                self.carrying = None
            else:
                b = self.game.closest_block(self.x, self.y + 10, grab=True)
                self.game.city.blocks.remove(b)
                if b.below:
                    b.below.above = None
                self.carrying = b.sprite


@dataclass
class RandomPlayer(Player):
    """Fake player that takes a random direction every second. Used in the menu background."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.maximum_altitude = 0

        self.timer: threading.Timer | None = None
        self.direction = Direction.NONE.value
        self.change_direction()

    def handle_keypress(self) -> Direction:
        return self.direction

    def change_direction(self):
        self.direction = random.choice(list(Direction.__members__.values()))

        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(1.0, self.change_direction)
        self.timer.start()


@dataclass
class Invader:
    x: float
    y: float
    z: float
    city: "City"
    prev_x: float = 0
    prev_y: float = 0
    prev_z: float = 0
    dead: bool = False

    def draw(self):
        if self.dead:
            return
        pyxel.pset(self.prev_x, self.prev_y - self.prev_z, col=pyxel.COLOR_WHITE)
        pyxel.pset(self.x, self.y - self.z, col=pyxel.COLOR_WHITE)

    def update(self):
        self.prev_x = self.x
        self.prev_y = self.y
        self.prev_z = self.z
        t = self.city.screen_to_tile(self.x, self.y)
        dc, dr = self.city.pathmap.get(t, (0, 0))
        if dc == 0 and dr == 0:
            self.dead = True
            return
        stepx, stepy = 12, 14
        s = 0.1 * random.random()
        self.x += (dr * stepx - dc * stepy) * s
        self.y += (dr * stepx // 2 + dc * stepy // 2) * s


@dataclass
class Block:
    x: float
    y: float
    z: float
    sprite: tuple[int, int]
    width: int = 16
    height: int = 4
    above: "Block | None" = None
    below: "Block | None" = None
    fixed: bool = False

    def draw(self):
        sx, sy = self.sprite
        pyxel.blt(
            self.x,
            self.y - self.z - 8,
            0,
            sx * 16,
            sy * 16,
            16,
            16,
            colkey=0,
        )


@dataclass(kw_only=True)
class Road(Block):
    flipped: bool = False

    def draw(self):
        sx, sy = self.sprite
        s = -1 if self.flipped else 1
        o = 1 if self.flipped else 0
        for i in range(3 + o):
            i -= 1
            pyxel.blt(
                self.x + s * i * 4 + 2 * o,
                self.y - self.z - 6 + i * 2 - o,
                0,
                sx * 16,
                sy * 16,
                s * 16,
                16,
                colkey=0,
            )


def outline_block(x: float, y: float):
    pyxel.blt(x - 1, y - 1, 0, 16, 0, 9, 9, colkey=0)
    pyxel.blt(x + 8, y - 1, 0, 16, 0, -9, 9, colkey=0)
    pyxel.blt(x - 1, y + 8, 0, 16, 0, 9, -9, colkey=0)
    pyxel.blt(x + 8, y + 8, 0, 16, 0, -9, -9, colkey=0)


@dataclass
class City:
    blocks: list[Block]
    tilemap: pyxel.Tilemap
    y_offset_base: int
    screen_to_tile: Callable[[float, float], tuple[int, int]]
    # Direction invaders want to go in each tile cell.
    pathmap: dict[tuple[int, int], tuple[int, int]]

    @staticmethod
    def load(cx: int, cy: int, max_height: float, stepx: int, stepy: int, *, y_offset_base: int):
        blocks = []
        xs, ys = [], []
        tilemap = pyxel.tilemaps[0]
        for row in range(16):
            for col in range(16):
                tile = tilemap.pget(cx + col, cy + row)
                if tile == (0, 0):
                    continue
                height = int(max_height * random.random() ** 4)
                x = row * stepx - col * stepy
                y = row * stepx // 2 + col * stepy // 2
                xs.append(x)
                ys.append(y)
                match tile:
                    case (0, 1):
                        base = Block(x, y, z=0, sprite=(3, 0), fixed=True)
                        sprite_x = 0
                        sprites = 8
                    case (3, 1):
                        base = Block(x, y, z=0, sprite=(3, 0), fixed=True)
                        height = 7
                        sprite_x = 3
                        sprites = 2
                    case (1, 1):
                        base = Road(x, y, z=0, sprite=(3, 3), fixed=True)
                        height = 0
                    case (1, 0):
                        base = Road(x, y, z=0, sprite=(3, 3), fixed=True, flipped=True)
                        height = 0
                prev = base
                blocks.append(prev)
                for h in range(height):
                    sprite = 1 + int(sprites * random.random() ** 3)
                    b = Block(
                        x,
                        y,
                        z=h * 8 + 8,
                        sprite=(sprite_x, sprite),
                        below=prev,
                    )
                    if prev:
                        prev.above = b
                    blocks.append(b)
                    prev = b
        x_off = (pyxel.width - max(xs) + min(xs)) // 2 - min(xs) - 8
        y_off = y_offset_base + (pyxel.height - max(ys) + min(ys)) // 2 - min(ys) - 8
        for b in blocks:
            b.x += x_off
            b.y += y_off

        def screen_to_tile(sx: float, sy: float):
            tx = sx - x_off - 8
            t2y = 2 * (sy - y_off + 8)
            col = (t2y - tx) // 2 // stepy
            row = (t2y + tx) // 2 // stepx
            return cx + col, cy + row

        return City(
            blocks=blocks,
            tilemap=tilemap,
            pathmap=tilemap_to_pathmap(cx, cy, tilemap),
            screen_to_tile=screen_to_tile,
            y_offset_base=y_offset_base,
        )


T_GOAL = 3, 1
T_BLOCK = 0, 1


def tilemap_to_pathmap(cx: int, cy: int, tilemap: pyxel.Tilemap):
    distance = {}
    for row in range(cy, cy + 16):
        for col in range(cx, cx + 16):
            tile = tilemap.pget(col, row)
            if tile == T_GOAL:
                distance[col, row] = 0
            elif tile == T_BLOCK:
                distance[col, row] = float("inf")
    for n in range(16 * 16):
        for row in range(cy, cy + 16):
            for col in range(cx, cx + 16):
                if (col, row) in distance:
                    continue
                best = float("inf")
                for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    if (col + dc, row + dr) in distance:
                        d = distance[col + dc, row + dr]
                        if d + 1 < best:
                            best = d + 1
                if best < 100:
                    distance[col, row] = best
    pathmap = {}
    for row in range(cy, cy + 16):
        for col in range(cx, cx + 16):
            best = float("inf")
            best_dir = 0, 0
            for dc, dr in [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)]:
                if (col + dc, row + dr) in distance:
                    d = distance[col + dc, row + dr]
                    if d < best:
                        best = d
                        best_dir = dc, dr
            pathmap[col, row] = best_dir
    return pathmap


class Background:
    def __init__(self):
        pass

    def update(self):
        pass

    def draw(self, altitude):
        ground_sky_line = 40 + altitude + 48 - 1
        dark_sky_line = int(30 + altitude * 0.7)
        sky_space_line = int(-20 + altitude * 0.7)
        def clip_blt(x, y, u, v, w, h, colkey=0):
            y = int(y)
            h = min(h, ground_sky_line - y)
            pyxel.blt(x, y, 1, u, v, w, h, colkey=colkey)
        if dark_sky_line >= pyxel.height:
            pyxel.cls(0)
        else:
            pyxel.cls(1)
            if sky_space_line > 0:
                pyxel.rect(0, 0, pyxel.width, sky_space_line, 0)
                pyxel.rect(0, sky_space_line, pyxel.width, dark_sky_line - sky_space_line, 5)
                pyxel.rect(0, dark_sky_line, pyxel.width, ground_sky_line - dark_sky_line, 6)
                pass
            elif dark_sky_line > 0:
                pyxel.rect(0, 0, pyxel.width, dark_sky_line, 5)
                pyxel.rect(0, dark_sky_line, pyxel.width, ground_sky_line - dark_sky_line, 6)
            else:
                pyxel.rect(0, 0, pyxel.width, ground_sky_line, 6)
        clip_blt(0, 80 + altitude * 0.7, 24, 0, 32, 48)
        clip_blt(24, 80 + altitude * 0.7, 16, 0, -24, 48)
        for x in range(3, 15):
            clip_blt(x * 16, 80 + altitude * 0.7, 0, 0, 16, 48)
        for x in range(15):
            clip_blt(x * 16, 30 + altitude * 0.7, 48, 0, 16, 48)
        for x in range(15):
            clip_blt(x * 16, -20 + altitude * 0.7, 64, 0, 16, 48, colkey=None)
        pyxel.blt(140, -180 + altitude * 0.7, 1, 96, 0, 16, 16)
        clip_blt(160, 64 + altitude * 0.75, 16, 144, 88, 56)
        clip_blt(0, 56 + altitude * 0.9, 0, 104, pyxel.width, 40)
        pyxel.blt(0, 40 + altitude, 1, 0, 48, pyxel.width, 48, colkey=0)


def make_invader(city: City):
    deg = random.random() * 2 * math.pi
    return Invader(
        city=city,
        x=pyxel.width * 0.5 + math.cos(deg) * 120,
        y=150 + city.y_offset_base + math.sin(deg) * 60,
        z=0,
    )


class Game:

    def __init__(self, *, player_factory: Callable[['Game'], Player], city_y_offset_base: int = 80, adjust_camera_altitude: bool = True):
        self.player = player_factory(self)
        self.city = City.load(cx=16, cy=0, max_height=5, stepx=14, stepy=14, y_offset_base=city_y_offset_base)
        self.invaders = []
        self.background = Background()
        self.adjust_camera_altitude = adjust_camera_altitude
        self.camera_altitude = 0

    def update(self):
        self.background.update()
        self.player.update()
        for invader in self.invaders:
            invader.update()
        self.invaders[:] = [i for i in self.invaders if not i.dead]
        for i in range(20):
            self.invaders.append(make_invader(self.city))

    def draw(self):
        pyxel.camera(0, 0)
        if self.adjust_camera_altitude:
            if self.player.y + self.camera_altitude < 40:
                self.camera_altitude = 40 - self.player.y
            if self.player.y + self.camera_altitude > pyxel.height - 40:
                self.camera_altitude = max(0, pyxel.height - 40 - self.player.y)
        else:
            self.camera_altitude = 0
        self.background.draw(self.camera_altitude)
        pyxel.camera(0, -self.camera_altitude)
        for thing in sorted(self.city.blocks + self.invaders, key=lambda b: (b.y, b.z)):
            thing.draw()
        if self.player.carrying:
            cb = self.closest_block(self.player.x, self.player.y + 18, grab=False)
            outline_block(cb.x, cb.y - cb.z - 16)
        else:
            cb = self.closest_block(self.player.x, self.player.y + 10, grab=True)
            outline_block(cb.x, cb.y - cb.z - 8)
        self.player.draw()

    def closest_block(self, x: float, y: float, grab: bool):
        closest = None
        closest_dist = float("inf")
        for block in self.city.blocks:
            if isinstance(block, Road) or block.above or block.fixed and grab:
                continue
            dx = block.x + block.width / 2 - (x + self.player.width / 2)
            dy = block.y + block.height / 2 - block.z - (y + self.player.height / 2)
            dist = math.hypot(dx, dy)
            if dist < closest_dist:
                closest = block
                closest_dist = dist
        return closest



def text_centered(text: str, y: int, *, font: pyxel.Font, color: int):
    x = pyxel.width // 2
    dx = font.text_width(text) // 2
    pyxel.text(x - dx, y, text, color, font)


class Menu:

    def __init__(self):
        self.selected = 0
        self.cycle_colors = (pyxel.COLOR_RED, pyxel.COLOR_PINK, pyxel.COLOR_PEACH, pyxel.COLOR_GRAY, pyxel.COLOR_WHITE, pyxel.COLOR_GRAY, pyxel.COLOR_PEACH, pyxel.COLOR_PINK)
        self.background_game = Game(
            player_factory=lambda game: RandomPlayer(game, 50, 100),
            city_y_offset_base=96,
            adjust_camera_altitude=False,
        )

        def _PlayGame():
            global game_card
            game_card.active = Game(player_factory=lambda game: Player(game, 100, 100))

        self.menu_items = (
            ("Play Game", _PlayGame),
            ("Settings", lambda: None),
            ("Quit", lambda: pyxel.quit()),
        )

    def update(self):
        self.background_game.update()

        if pyxel.btnp(pyxel.KEY_DOWN):
            self.selected = min(self.selected + 1, len(self.menu_items) - 1)
        if pyxel.btnp(pyxel.KEY_UP):
            self.selected = max(self.selected - 1, 0)
        if pyxel.btnp(pyxel.KEY_RETURN):
            _, action = self.menu_items[self.selected]
            action()

    def draw(self):
        self.background_game.draw()

        pyxel.text(56 - 16, 8, "Consumer", pyxel.COLOR_WHITE, _SPLEEN_16x32)
        pyxel.text(56 + 16, 40, "Consumer", pyxel.COLOR_WHITE, _SPLEEN_16x32)

        for i, (item_text, _) in enumerate(self.menu_items):
            if i == self.selected:
                color = self.cycle_colors[(pyxel.frame_count // 3) % len(self.cycle_colors)]
                text_centered(f"> {item_text} <", 96 + (16 + 8) * i, font=_SPLEEN_8x16, color=color)
            else:
                text_centered(item_text, 96 + (16 + 8) * i, font=_SPLEEN_8x16, color=pyxel.COLOR_WHITE)


class Dispatcher:

    def __init__(self):
        self.active = Menu()

    def update(self):
        self.active.update()

    def draw(self):
        self.active.draw()


game_card = Dispatcher()
pyxel.run(game_card.update, game_card.draw)
