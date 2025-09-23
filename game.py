import math
import random
import pyxel
from dataclasses import dataclass
from collections.abc import Callable

pyxel.init(240, 320)
pyxel.load("art.pyxres")


@dataclass
class Player:
    x: float
    y: float
    vx: float = 0
    vy: float = 0
    width: int = 16
    height: int = 16
    carrying: tuple[int, int] | None = None

    def draw(self):
        if self.carrying:
            sx, sy = self.carrying
            pyxel.blt(self.x, self.y + 10, 0, 16 * sx, 16 * sy, 16, 16, colkey=0)
        pyxel.blt(self.x, self.y, 0, 32, 0, 16, 16, colkey=0)

    def update(self):
        ACCELERATION = 0.8
        GRAVITY = 0.06
        DRAG = 0.02
        if pyxel.btn(pyxel.KEY_LEFT):
            self.vx -= ACCELERATION
        if pyxel.btn(pyxel.KEY_RIGHT):
            self.vx += ACCELERATION
        if pyxel.btn(pyxel.KEY_UP):
            self.vy -= ACCELERATION
        if pyxel.btn(pyxel.KEY_DOWN):
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
        if self.y < 0:
            self.y = 0
            self.vy = 0
        if self.x > pyxel.width - self.width:
            self.x = pyxel.width - self.width
            self.vx = 0
        if self.x < 0:
            self.x = 0
            self.vx = 0
        if pyxel.btnp(pyxel.KEY_SPACE):
            if self.carrying:
                b = closest_block(self.x, self.y + 18, grab=False)
                nb = Block(
                    x=b.x,
                    y=b.y,
                    z=b.z + 8,
                    sprite=self.carrying,
                    below=b,
                )
                b.above = nb
                city.blocks.append(nb)
                self.carrying = None
            else:
                b = closest_block(self.x, self.y + 10, grab=True)
                city.blocks.remove(b)
                if b.below:
                    b.below.above = None
                self.carrying = b.sprite


@dataclass
class Invader:
    x: float
    y: float
    z: float
    prev_x: float = 0
    prev_y: float = 0
    prev_z: float = 0

    def draw(self):
        pyxel.pset(self.prev_x, self.prev_y - self.prev_z, col=7)
        pyxel.pset(self.x, self.y - self.z, col=7)

    def update(self):
        self.prev_x = self.x
        self.prev_y = self.y
        self.prev_z = self.z
        self.z -= 0.5
        self.x += random.randint(-1, 1)
        self.y += random.randint(-1, 1)
        if self.z < 0:
            self.z = 200


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
    screen_to_tile: Callable[[float, float], tuple[int, int]]

    @staticmethod
    def load(cx: int, cy: int, max_height: float, stepx: int, stepy: int):
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
        y_off = 80 + (pyxel.height - max(ys) + min(ys)) // 2 - min(ys) - 8
        for b in blocks:
            b.x += x_off
            b.y += y_off

        def screen_to_tile(sx: float, sy: float):
            # x = row * stepx - col * stepy
            # y = row * stepx // 2 + col * stepy // 2
            # 2y = row * stepx + col * stepy
            # x + 2y = 2 * row * stepx
            # 2y - x = 2 * col * stepy
            tx = sx - x_off - 8
            t2y = 2 * (sy - y_off + 8)
            col = (t2y - tx) // 2 // stepy
            row = (t2y + tx) // 2 // stepx
            return cx + col, cy + row

        return City(blocks=blocks, tilemap=tilemap, screen_to_tile=screen_to_tile)


player = Player(100, 100)
city = City.load(cx=16, cy=0, max_height=5, stepx=12, stepy=14)
invaders = []
for i in range(10000):
    invaders.append(
        Invader(
            x=random.randint(0, pyxel.width),
            y=200 + random.randint(0, 100),
            z=random.randint(0, 200),
        )
    )


def closest_block(x: float, y: float, grab: bool):
    closest = None
    closest_dist = float("inf")
    for block in city.blocks:
        if isinstance(block, Road) or block.above or block.fixed and grab:
            continue
        dx = block.x + block.width / 2 - (x + player.width / 2)
        dy = block.y + block.height / 2 - block.z - (y + player.height / 2)
        dist = math.hypot(dx, dy)
        if dist < closest_dist:
            closest = block
            closest_dist = dist
    return closest


def update():
    player.update()
    for invader in invaders:
        invader.update()


def draw():
    pyxel.cls(1)
    for thing in sorted(city.blocks + invaders, key=lambda b: (b.y, b.z)):
        thing.draw()
    if player.carrying:
        cb = closest_block(player.x, player.y + 18, grab=False)
        outline_block(cb.x, cb.y - cb.z - 16)
    else:
        cb = closest_block(player.x, player.y + 10, grab=True)
        outline_block(cb.x, cb.y - cb.z - 8)
    player.draw()


pyxel.run(update, draw)
