import math
import random
import pyxel
from dataclasses import dataclass

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
            self.y - self.z,
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
                self.y - self.z + 2 + i * 2 - o,
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


def load_city(cx: int, cy: int, max_height: float, gapx: int, gapy: int):
    blocks = []
    xs, ys = [], []
    tm = pyxel.tilemaps[0]
    for row in range(16):
        for col in range(16):
            tile = tm.pget(cx + col, cy + row)
            if tile == (0, 0):
                continue
            height = 1 + int(max_height * random.random() ** 4)
            x = row * (10 + gapx) - col * (10 + gapy)
            y = row * (5 + gapx // 2) + col * (5 + gapy // 2)
            xs.append(x)
            ys.append(y)
            match tile:
                case (0, 1) | (3, 1):
                    base = Block(x, y, z=0, sprite=(3, 0), fixed=True)
                case (1, 1):
                    base = Road(x, y, z=0, sprite=(3, 1), fixed=True)
                case (1, 0):
                    base = Road(x, y, z=0, sprite=(3, 1), fixed=True, flipped=True)
            prev = base
            blocks.append(prev)
            if tile != (0, 1):
                continue
            for h in range(height):
                sprite = 1 + int(8 * random.random() ** 3)
                b = Block(
                    x,
                    y,
                    z=h * 8 + 8,
                    sprite=(0, sprite),
                    below=prev,
                )
                if prev:
                    prev.above = b
                blocks.append(b)
                prev = b
    for b in blocks:
        b.x += (pyxel.width - max(xs) + min(xs)) // 2 - min(xs) - 8
        b.y += 80 + (pyxel.height - max(ys) + min(ys)) // 2 - min(ys) - 8
    return blocks


player = Player(100, 100)
blocks = load_city(cx=16, cy=0, max_height=5, gapx=2, gapy=4)


def closest_block(x: float, y: float, grab: bool):
    closest = None
    closest_dist = float("inf")
    for block in blocks:
        if block.above or block.fixed and grab:
            continue
        dx = block.x + block.width / 2 - (x + player.width / 2)
        dy = block.y + block.height / 2 - block.z - (y + player.height / 2)
        dist = math.hypot(dx, dy)
        if dist < closest_dist:
            closest = block
            closest_dist = dist
    return closest


def update():
    ACCELERATION = 0.8
    GRAVITY = 0.06
    DRAG = 0.02
    if pyxel.btn(pyxel.KEY_LEFT):
        player.vx -= ACCELERATION
    if pyxel.btn(pyxel.KEY_RIGHT):
        player.vx += ACCELERATION
    if pyxel.btn(pyxel.KEY_UP):
        player.vy -= ACCELERATION
    if pyxel.btn(pyxel.KEY_DOWN):
        player.vy += ACCELERATION
    player.vy += GRAVITY
    player.x += player.vx
    player.y += player.vy
    v = math.hypot(player.vx, player.vy)
    player.vx /= 1 + DRAG * v * v
    player.vy /= 1 + DRAG * v * v
    if player.y > pyxel.height - player.height:
        player.y = pyxel.height - player.height
        player.vy = 0
    if player.y < 0:
        player.y = 0
        player.vy = 0
    if player.x > pyxel.width - player.width:
        player.x = pyxel.width - player.width
        player.vx = 0
    if player.x < 0:
        player.x = 0
        player.vx = 0
    if pyxel.btnp(pyxel.KEY_SPACE):
        if player.carrying:
            b = closest_block(player.x, player.y + 18, grab=False)
            nb = Block(
                x=b.x,
                y=b.y,
                z=b.z + 8,
                sprite=player.carrying,
                below=b,
            )
            b.above = nb
            blocks.append(nb)
            player.carrying = None
        else:
            b = closest_block(player.x, player.y + 10, grab=True)
            blocks.remove(b)
            if b.below:
                b.below.above = None
            player.carrying = b.sprite


def draw():
    pyxel.cls(1)
    for block in sorted(blocks, key=lambda b: (b.y, b.z)):
        block.draw()
    if player.carrying:
        cb = closest_block(player.x, player.y + 18, grab=False)
        outline_block(cb.x, cb.y - cb.z - 8)
    else:
        cb = closest_block(player.x, player.y + 10, grab=True)
        outline_block(cb.x, cb.y - cb.z)
    player.draw()


pyxel.run(update, draw)
