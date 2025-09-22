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


@dataclass
class Block:
    x: float
    y: float
    z: float
    sprite: int
    width: int = 16
    height: int = 4


def make_city(radius: int, max_height: float):
    blocks = []
    for row in range(radius * 2):
        for col in range(radius * 2):
            # Streets.
            if row % 3 == 1 or col % 5 == 2:
                continue
            height = 1 + int(max_height * random.random() ** 2)
            for h in range(height):
                blocks.append(
                    Block(
                        112 + row * 12 - col * 12,
                        300 - radius * 24 + row * 6 + col * 6,
                        h * 8,
                        0 if (h + col * 7 + row * 5) % 27 > 1 else 1,
                    )
                )
    return blocks


player = Player(100, 100)
blocks = make_city(radius=5, max_height=3)


def closest_block(x: float, y: float):
    closest = None
    closest_dist = float("inf")
    for block in blocks:
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
    if pyxel.btn(pyxel.KEY_SPACE):
        b = closest_block(player.x, player.y)
        blocks.remove(b)


def draw():
    pyxel.cls(1)
    for block in sorted(blocks, key=lambda b: (b.y, b.z)):
        pyxel.blt(
            block.x,
            block.y - block.z,
            0,
            0,
            16 + block.sprite * 16,
            16,
            16,
            colkey=0,
        )
    pyxel.blt(player.x, player.y, 0, 0, 0, 16, 16, colkey=0)


pyxel.run(update, draw)
