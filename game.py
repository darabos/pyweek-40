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
    carrying: int = 0

    def draw(self):
        if self.carrying:
            pyxel.blt(self.x, self.y + 10, 0, 0, 16 * self.carrying, 16, 16, colkey=0)
        pyxel.blt(self.x, self.y, 0, 0, 0, 16, 16, colkey=0)


@dataclass
class Block:
    x: float
    y: float
    z: float
    sprite: int
    width: int = 16
    height: int = 4
    above: "Block | None" = None
    below: "Block | None" = None

    def draw(self):
        pyxel.blt(
            self.x,
            self.y - self.z,
            0,
            0,
            self.sprite * 16,
            16,
            16,
            colkey=0,
        )


def outline_block(x: float, y: float):
    pyxel.blt(x - 1, y - 1, 0, 16, 0, 9, 9, colkey=0)
    pyxel.blt(x + 8, y - 1, 0, 16, 0, -9, 9, colkey=0)
    pyxel.blt(x - 1, y + 8, 0, 16, 0, 9, -9, colkey=0)
    pyxel.blt(x + 8, y + 8, 0, 16, 0, -9, -9, colkey=0)


def make_city(radius: int, max_height: float):
    blocks = []
    for row in range(radius * 2):
        for col in range(radius * 2):
            # Streets.
            if row % 3 == 1 or col % 5 == 2:
                continue
            height = 1 + int(max_height * random.random() ** 4)
            prev = None
            for h in range(height):
                sprite = 1 + int(5 * random.random() ** 5)
                b = Block(
                    x=112 + row * 12 - col * 12,
                    y=300 - radius * 24 + row * 6 + col * 6,
                    z=h * 8,
                    sprite=sprite,
                    below=prev,
                )
                if prev:
                    prev.above = b
                blocks.append(b)
                prev = b
    return blocks


player = Player(100, 100)
blocks = make_city(radius=5, max_height=5)


def closest_block(x: float, y: float):
    closest = None
    closest_dist = float("inf")
    for block in blocks:
        if block.above:
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
            b = closest_block(player.x, player.y + 18)
            nb = Block(
                x=b.x,
                y=b.y,
                z=b.z + 8,
                sprite=player.carrying,
                below=b,
            )
            b.above = nb
            blocks.append(nb)
            player.carrying = 0
        else:
            b = closest_block(player.x, player.y + 10)
            blocks.remove(b)
            if b.below:
                b.below.above = None
            player.carrying = b.sprite


def draw():
    pyxel.cls(1)
    for block in sorted(blocks, key=lambda b: (b.y, b.z)):
        block.draw()
    if player.carrying:
        cb = closest_block(player.x, player.y + 18)
        outline_block(cb.x, cb.y - cb.z - 8)
    else:
        cb = closest_block(player.x, player.y + 10)
        outline_block(cb.x, cb.y - cb.z)
    player.draw()


pyxel.run(update, draw)
