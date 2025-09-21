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
    width: int = 16
    height: int = 4


player = Player(100, 100)
blocks = []

for row in range(10):
    for col in range(10):
        height = random.randint(1, 4) ** 2
        for h in range(height):
            blocks.append(Block(-50 + col * 18, 150 + row * 20, h * 4))


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
        player.vy = -2  # jump


def draw():
    pyxel.cls(1)
    for block in sorted(blocks, key=lambda b: (b.y + b.x, b.z)):
        screen_y = block.y // 2 - block.z
        pyxel.blt(block.x + block.y // 2, screen_y, 0, 16, 0, 16, 16, colkey=0)
    pyxel.blt(player.x, player.y, 0, 0, 0, 16, 16, colkey=0)


pyxel.run(update, draw)
