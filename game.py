import abc
import bisect
import collections
import enum
import math
import random
import pyxel
import textwrap
from dataclasses import dataclass
from collections.abc import Callable


# Graphics options
_GRAPHICS_FPS = 30

pyxel.init(240, 320, fps=_GRAPHICS_FPS, quit_key=pyxel.KEY_NONE)
pyxel.load("assets/art.pyxres")

# Bitmap font definitions
_FONT_SPLEEN_32x64 = pyxel.Font("assets/spleen-32x64.bdf")
_FONT_SPLEEN_16x32 = pyxel.Font("assets/spleen-16x32.bdf")
_FONT_SPLEEN_8x16  = pyxel.Font("assets/spleen-8x16.bdf")

# Features.
_ENABLE_INVADERS = False
_RELEASE_MODE = False

# Sound channel definitions
_CHANNEL_SFX = 3

# Sound bank definitions
_SOUND_DROP = 0
_SOUND_PICK_UP = 1
_SOUND_FAILED_DROP = 2
_SOUND_FAILED_PICK_UP = 3

_CYCLE_COLORS = (pyxel.COLOR_RED, pyxel.COLOR_PINK, pyxel.COLOR_PEACH, pyxel.COLOR_GRAY, pyxel.COLOR_WHITE, pyxel.COLOR_GRAY, pyxel.COLOR_PEACH, pyxel.COLOR_PINK)


def AssertButNotInRelease(text='Something unexpected happened.'):
    if _RELEASE_MODE:
        return
    assert False, text


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
    maximum_altitude: int = 0
    carrying: "Block | None" = None
    carrying_new: bool = False

    def draw(self):
        if self.carrying:
            self.carrying.x = self.x + 8 - self.carrying.blocktype.x_center
            self.carrying.y = self.y + 8 - self.carrying.blocktype.y_min // 2
            self.carrying.draw()
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
        ACCELERATION = 0.8
        GRAVITY = 0.06
        DRAG = 0.02

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
                drop_spot = self.game.closest_drop_spot(self.x + self.width / 2, self.y + self.height / 2 + 12, self.carrying)
                if drop_spot is None or not drop_spot.valid:
                    pyxel.play(_CHANNEL_SFX, _SOUND_FAILED_DROP)
                else:
                    if isinstance(drop_spot, DropInCity):
                        self.game.city.add(drop_spot.col, drop_spot.row, self.carrying)
                        self.maximum_altitude = max(self.maximum_altitude, 80 - self.carrying.y)
                        if self.carrying_new:
                            self.game.new_block_area.placed()
                    elif isinstance(drop_spot, DropInNewArea):
                        self.game.new_block_area.returned_block()
                    else:
                        AssertButNotInRelease()
                    self.carrying = None
                    pyxel.play(_CHANNEL_SFX, _SOUND_DROP)
            else:
                b, is_new = self.game.closest_pickup_spot(self.x + self.width / 2, self.y + self.height / 2 + 10)
                if b:
                    if is_new or self.game.city.remove(b):
                        if is_new:
                            self.game.new_block_area.picked_up(b)
                        self.carrying = b
                        self.carrying_new = is_new
                        pyxel.play(_CHANNEL_SFX, _SOUND_PICK_UP)
                    else:
                        pyxel.play(_CHANNEL_SFX, _SOUND_FAILED_PICK_UP)


@dataclass
class RandomPlayer(Player):
    """Fake player that takes a random direction every second. Used in the menu background."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.maximum_altitude = 0
        self.direction = Direction.NONE.value
        self.change_direction()

    def handle_keypress(self) -> Direction:
        return self.direction

    def update(self):
        super().update()
        if pyxel.frame_count % _GRAPHICS_FPS == 0:
            self.change_direction()

    def change_direction(self):
        self.direction = random.choice(list(Direction.__members__.values()))


class BlockSprite(collections.namedtuple('BlockSprite', 'x y sx sy w h')):
    def draw(self, x, y):
        pyxel.blt(
            x + self.x, y + self.y,
            0,
            self.sx, self.sy,
            self.w, self.h,
            colkey=0,
        )


@dataclass(frozen=True)
class BlockPart:
    sprites: tuple[BlockSprite, ...]
    # Offsets (in blocks) from the base coordinate.
    col: int = 0
    row: int = 0
    altitude: int = 0


@dataclass(frozen=True)
class BlockType:
    # Sequence of tiles occupied.
    footprint: tuple[BlockPart, ...]

    def __post_init__(self):
        xs = []
        ys = []
        for part in self.footprint:
            for sprite in part.sprites:
                xs.append(sprite.x)
                xs.append(sprite.x + sprite.w)
                ys.append(sprite.y)
                ys.append(sprite.y + sprite.h)
        object.__setattr__(self, 'x_center', (min(xs) + max(xs)) // 2)
        object.__setattr__(self, 'y_center', (min(ys) + max(ys)) // 2)
        object.__setattr__(self, 'y_min', min(ys))


def MakeBlocksFromHalves(sprite_x, sprite_y, num_sprites):
    blocktypes = []
    for left in range(num_sprites):
        for right in range(num_sprites):
            if left == right:
                bt = BlockType(footprint=(
                    BlockPart(sprites=(
                        BlockSprite(0, 0, sprite_x, sprite_y + left * 16, 16, 16), )), ))
            else:
                bt = BlockType(footprint=(
                    BlockPart(sprites=(
                        BlockSprite(0, 0, sprite_x, sprite_y + left * 16, 8, 16),
                        BlockSprite(8, 0, sprite_x + 8, sprite_y + right * 16, 8, 16),
                    )), ))
            blocktypes.append(bt)
    return blocktypes

NormalBlocks = MakeBlocksFromHalves(0, 16, 8) + MakeBlocksFromHalves(0, 16 + 8 * 16, 2) * 4 + MakeBlocksFromHalves(0, 16 + 10 * 16, 3) * 4
RedBlocks = [
    BlockType(footprint=(
        BlockPart(sprites=(BlockSprite(0, 0, 48, 16 + i * 16, 16, 16), )), )
              )
    for i in range(2)]

def MakeSkybridgesRight(base_x, base_y, base_num,
                        bridge_x, bridge_y, bridge_num):
    bts = []
    for bridge_idx in range(bridge_num):
        for _ in range(4):
            left = random.randrange(base_num)
            right = random.randrange(base_num)
            righter = random.randrange(base_num)
            bts.append(BlockType(
                footprint=(
                    BlockPart(sprites=(
                        BlockSprite(0, 0, base_x, base_y + left * 16, 8, 16),
                        BlockSprite(8, 0, base_x + 8, base_y + left * 16, 8, 16)),
                              col=0, row=0, altitude=0),
                    BlockPart(sprites=(
                        BlockSprite(14 + 8, -7, base_x + 8, base_y + righter * 16, 8, 16),
                        BlockSprite(14 - 3, -7, bridge_x, bridge_y + bridge_idx * 24, 11, 17)),
                                     col=-1, row=0, altitude=0))))
    return bts
def MakeSkybridgesLeft(base_x, base_y, base_num,
                       bridge_x, bridge_y, bridge_num):
    bts = []
    for bridge_idx in range(bridge_num):
        for _ in range(4):
            left = random.randrange(base_num)
            right = random.randrange(base_num)
            lefter = random.randrange(base_num)
            bts.append(BlockType(
                footprint=(
                    BlockPart(sprites=(
                        BlockSprite(0, 0, base_x, base_y + left * 16, 8, 16),
                        BlockSprite(8, 0, base_x + 8, base_y + left * 16, 8, 16)),
                              col=0, row=0, altitude=0),
                    BlockPart(sprites=(
                        BlockSprite(-16, -8, base_x, base_y + lefter * 16, 8, 16),
                        BlockSprite(-8, -8, bridge_x, bridge_y + bridge_idx * 24, 12, 18)),
                                     col=0, row=-1, altitude=0))))
    return bts
Skybridges = (
    MakeSkybridgesRight(0, 16, 8, 163, 9, 3)
    +
    MakeSkybridgesLeft(0, 16, 8, 168, 104, 3))

def MakeSkyrampsRightUp(base_x, base_y, base_num,
                        bridge_x, bridge_y, bridge_num):
    bts = []
    for bridge_idx in range(bridge_num):
        for _ in range(4):
            left = random.randrange(base_num)
            right = random.randrange(base_num)
            righter = random.randrange(base_num)
            bts.append(BlockType(
                footprint=(
                    BlockPart(sprites=(
                        BlockSprite(0, 0, base_x, base_y + left * 16, 8, 16),
                        BlockSprite(8, 0, base_x + 8, base_y + left * 16, 8, 16)),
                              col=0, row=0, altitude=0),
                    BlockPart(sprites=(
                        BlockSprite(14 + 8, -15, base_x + 8, base_y + righter * 16, 8, 16),
                        BlockSprite(14 - 4, -15, bridge_x, bridge_y + bridge_idx * 32, 12, 25)),
                                     col=-1, row=0, altitude=1))))
    return bts
def MakeSkyrampsRightDown(base_x, base_y, base_num,
                        bridge_x, bridge_y, bridge_num):
    bts = []
    for bridge_idx in range(bridge_num):
        for _ in range(4):
            left = random.randrange(base_num)
            right = random.randrange(base_num)
            righter = random.randrange(base_num)
            bts.append(BlockType(
                footprint=(
                    BlockPart(sprites=(
                        BlockSprite(0, 0, base_x, base_y + righter * 16, 16, 16), ),
                                     col=0, row=0, altitude=0),
                    BlockPart(sprites=(
                        BlockSprite(-14, -1, base_x, base_y + left * 16, 8, 16),
                        BlockSprite(-6, -1, base_x + 8, base_y + left * 16, 8, 16),
                        BlockSprite(0, 4, bridge_x, bridge_y + bridge_idx * 16, 8, 16)),
                              col=1, row=0, altitude=1),
                       )))
    return bts
def MakeSkyrampsLeftUp(base_x, base_y, base_num,
                       bridge_x, bridge_y, bridge_num):
    bts = []
    for bridge_idx in range(bridge_num):
        for _ in range(4):
            left = random.randrange(base_num)
            right = random.randrange(base_num)
            lefter = random.randrange(base_num)
            bts.append(BlockType(
                footprint=(
                    BlockPart(sprites=(
                        BlockSprite(0, 0, base_x, base_y + left * 16, 8, 16),
                        BlockSprite(8, 0, base_x + 8, base_y + left * 16, 8, 16)),
                              col=0, row=0, altitude=0),
                    BlockPart(sprites=(
                        BlockSprite(-16, -16, base_x, base_y + lefter * 16, 8, 16),
                        BlockSprite(-8, -16, bridge_x, bridge_y + bridge_idx * 32, 23, 28)),
                                     col=0, row=-1, altitude=1))))
    return bts
def MakeSkyrampsLeftDown(base_x, base_y, base_num,
                         bridge_x, bridge_y, bridge_num):
    bts = []
    for bridge_idx in range(bridge_num):
        for _ in range(4):
            left = random.randrange(base_num)
            right = random.randrange(base_num)
            lefter = random.randrange(base_num)
            bts.append(BlockType(
                footprint=(
                    BlockPart(sprites=(
                        BlockSprite(16, 0, base_x, base_y + left * 16, 8, 16),
                        BlockSprite(24, 0, base_x + 8, base_y + left * 16, 8, 16)),
                              col=0, row=1, altitude=1),
                    BlockPart(sprites=(
                        BlockSprite(0, 0, base_x, base_y + lefter * 16, 16, 16),
                        BlockSprite(8, 3, bridge_x, bridge_y + bridge_idx * 16, 8, 13)),
                                     col=0, row=0, altitude=0))))
    return bts
Skyramps = (
    MakeSkyrampsRightUp(0, 16, 8, 194, 33, 2)
    +
    MakeSkyrampsRightDown(0, 16, 8, 222, 9 + 16, 1)  # Hard to visually read the blank wall, so don't use that sprite.
    +
    MakeSkyrampsLeftUp(0, 16, 8, 192, 112, 2)
    +
    MakeSkyrampsLeftDown(0, 16, 8, 224, 67 + 16, 1)  # Hard to visually read the blank wall, so don't use that sprite.
    )
AllBlocks = NormalBlocks + RedBlocks * 4 + Skybridges + Skyramps


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
        stepx, stepy = 16, 14
        s = 0.1 * random.random()
        self.x += (dr * stepx - dc * stepy) * s
        self.y += (dr * stepx // 2 + dc * stepy // 2) * s


@dataclass
class Block:
    x: int
    y: int

    # The next three are None if the block is not currently part of the city.
    col: int | None
    row: int | None
    altitude: int | None

    blocktype: BlockType

    def draw(self, index=None):
        if index is None:
            for part in self.blocktype.footprint:
                for sprite in part.sprites:
                    sprite.draw(self.x, self.y)
        else:
            for sprite in self.blocktype.footprint[index].sprites:
                sprite.draw(self.x, self.y)


def outline_block(x: float, y: float, color: int | None = None):
    if color is not None:
        pyxel.pal(10, color)
    pyxel.blt(x - 1, y - 1, 0, 16, 0, 9, 9, colkey=0)
    pyxel.blt(x + 8, y - 1, 0, 16, 0, -9, 9, colkey=0)
    pyxel.blt(x - 1, y + 8, 0, 16, 0, 9, -9, colkey=0)
    pyxel.blt(x + 8, y + 8, 0, 16, 0, -9, -9, colkey=0)
    if color is not None:
        pyxel.pal()


def cross_block(x: float, y: float, color: int):
    x0, y0 = x, y + 4
    x1, y1 = x + 16, y + 16 - 4
    pyxel.line(x0, y0, x1, y1, color)
    pyxel.line(x1, y0, x0, y1, color)


@dataclass
class Foundation(abc.ABC):
    x: float
    y: float

    @abc.abstractmethod
    def draw(self):
        pass


@dataclass()
class FoundationSprite(Foundation):
    sprite: (int, int) = 3, 0

    def draw(self):
        sx, sy = self.sprite
        pyxel.blt(
            self.x,
            self.y,
            0,
            sx * 16,
            sy * 16,
            16,
            16,
            colkey=0,
        )


@dataclass()
class Road(Foundation):
    flipped: bool = False
    sprite: (int, int) = 3, 3

    def draw(self):
        sx, sy = self.sprite
        s = -1 if self.flipped else 1
        o = 1 if self.flipped else 0
        for i in range(3 + o):
            i -= 1
            pyxel.blt(
                self.x + s * i * 4 + 2 * o,
                self.y + 2 + i * 2 - o,
                0,
                sx * 16,
                sy * 16,
                s * 16,
                16,
                colkey=0,
            )


# Index is the index into the blocktype footprint array of the part of
# the block that occupies this tile.
TileBlock = collections.namedtuple('TileBlock', 'block index')


@dataclass
class Tile:
    foundation: Foundation
    blocks : list[TileBlock] | None = None  # None means blocks can't be placed on this tile.

    def draw(self):
        self.foundation.draw()
        if self.blocks:
            for b, idx in self.blocks:
                b.draw(idx)


@dataclass
class City:
    tiles: list[list[Tile]]
    x_off: int
    y_off: int

    y_offset_base: int
    screen_to_tile: Callable[[float, float], tuple[int, int]]
    # Direction invaders want to go in each tile cell.
    pathmap: dict[tuple[int, int], tuple[int, int]]

    stepx: int = 16
    stepy: int = 14
    block_height: int = 8

    base_score: int = 0

    def __post_init__(self):
        self.base_score = self.score()

    @staticmethod
    def base_tile_to_screen(col, row, altitude):
        x = row * City.stepx - col * City.stepy
        y = row * City.stepx // 2 + col * City.stepy // 2 - altitude * City.block_height
        return x, y

    def tile_to_screen(self, col, row, altitude):
        x, y = City.base_tile_to_screen(col, row, altitude)
        return x + self.x_off, y + self.y_off

    def draw(self):
        for tile_col in self.tiles:
            for tile in tile_col:
                if tile:
                    tile.draw()

    def add(self, base_col, base_row, block):
        base_tile = self.tiles[base_row][base_col]
        base_altitude = len(base_tile.blocks)
        block.col = base_col
        block.row = base_row
        block.altitude = base_altitude
        block.x, block.y = self.tile_to_screen(base_col, base_row, base_altitude)
        for idx, part in enumerate(block.blocktype.footprint):
            col = part.col + base_col
            row = part.row + base_row
            altitude = part.altitude + base_altitude
            tile = self.tiles[row][col]
            tile.blocks.append(TileBlock(block, idx))

    def remove(self, block):
        bt = block.blocktype
        to_pop = []
        for part in bt.footprint:
            col = part.col + block.col
            row = part.row + block.row
            altitude = part.altitude + block.altitude
            tile = self.tiles[row][col]
            if len(tile.blocks) != altitude + 1:
                return False
            to_pop.append(tile.blocks)
        for tb in to_pop:
            tb.pop()
        block.col = block.row = block.altitude = None
        return True

    def valid_drop_spot(self, base_col: int, base_row: int, base_altitude: int, block: Block):
        bt = block.blocktype
        for part in bt.footprint:
            col = part.col + base_col
            row = part.row + base_row
            altitude = part.altitude + base_altitude
            if row < 0 or row >= len(self.tiles):
                return False
            if col < 0 or col >= len(self.tiles[0]):
                return False
            tile = self.tiles[row][col]
            if tile is None or tile.blocks is None:
                return False
            if altitude != len(tile.blocks):
                return False
        return True

    def score(self):
        score = 0
        for tile_col in self.tiles:
            for tile in tile_col:
                if tile and tile.blocks:
                    score += len(tile.blocks) * (len(tile.blocks) - 1) // 2
        return score - self.base_score

    def highest_building(self):
        highest = 0
        for tile_col in self.tiles:
            for tile in tile_col:
                if tile and tile.blocks:
                    highest = max(highest, len(tile.blocks))
        return highest

    @staticmethod
    def load(cx: int, cy: int, max_height: int, buildings, *, y_offset_base: int):
        for b in buildings:
            if b > max_height:
              AssertButNotInRelease("height higher than max_height: %d > %d" % (b, max_height) )
        tiles = [[None] * 16 for _ in range(16)]
        tilemap = pyxel.tilemaps[0]
        xs = []
        ys = []
        for row, col in ((0, 0), (15, 0), (0, 15), (15, 15)):
            x, y = City.base_tile_to_screen(col, row, -1)
            xs.append(x)
            ys.append(y)
        x_off = (pyxel.width - max(xs) + min(xs)) // 2 - min(xs) - 12
        y_off = y_offset_base + (pyxel.height - max(ys) + min(ys)) // 2 - min(ys) - 8

        for row in range(16):
            for col in range(16):
                tile = tilemap.pget(cx + col, cy + row)
                if tile == (0, 0):
                    continue
                x, y = City.base_tile_to_screen(col, row, -1)
                x += x_off
                y += y_off
                match tile:
                    # blue tile
                    case (0, 1):
                        base = FoundationSprite(x, y, sprite=(3, 0))
                        sprites = NormalBlocks
                        buildable = True
                        rando = random.random()
                        ## progressively increase the
                        if ((len(buildings) > 0)
                            and ((row < 10 and rando < 0.25)
                            or (row == 8 and rando < 0.30)
                            or (row == 9 and rando < 0.55)
                            or (row == 10 and rando < 0.65)
                            or (row == 11 and rando < 0.75)
                            or (row == 12))
                           ):
                            # height = int(max_height * random.random() ** 4)
                            bldi = random.randint(0, len(buildings)-1)
                            height = buildings.pop(bldi)
                        else:
                            height = 0
                    # red tile
                    case (3, 1):
                        base = FoundationSprite(x, y, sprite=(3, 0))
                        height = 7
                        sprites = RedBlocks
                        buildable = True
                    # road vertical
                    case (1, 1):
                        base = Road(x, y, sprite=(3, 3))
                        height = 0
                        buildable = False
                    # road horizontal
                    case (1, 0):
                        base = Road(x, y, sprite=(3, 3), flipped=True)
                        height = 0
                        buildable = False
                    case _:
                        AssertButNotInRelease("This should not happen! city initial tilemap has undefined stuff: " + tile)
                tile = Tile(base)
                tiles[row][col] = tile
                if buildable:
                    tile.blocks = []
                    for h in range(height):
                        sprite = int(len(sprites) * random.random())
                        x, y = City.base_tile_to_screen(col, row, h)
                        x += x_off
                        y += y_off
                        b = Block(x, y, col, row, h, sprites[sprite])
                        tile.blocks.append(TileBlock(b, 0))

        def screen_to_tile(sx: float, sy: float):
            tx = sx - x_off - 8
            t2y = 2 * (sy - y_off - 8)
            col = (t2y - tx) // 2 // City.stepy
            row = (t2y + tx) // 2 // City.stepx
            return cx + col, cy + row

        return City(
            tiles=tiles,
            x_off=x_off,
            y_off=y_off,
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
        self.planet_x = -32
        self.randomize_planet_y()

    def update(self):
        self.planet_x += 0.75
        if self.planet_x > pyxel.width + 32:
            self.planet_x = -32
            self.randomize_planet_y()

    def randomize_planet_y(self):
        self.planet_y = random.randint(-200, -100)

    def draw(self, altitude):
        ground_sky_line = 40 + altitude + 48 - 1
        dark_sky_line = int(30 + altitude * 0.7)
        sky_space_line = int(-20 + altitude * 0.7)
        def clip_blt(x, y, u, v, w, h, colkey=0):
            y = int(y)
            h = min(h, ground_sky_line - y)
            if h <= 0:
                return
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
        clip_blt(0, 80 + 48 + altitude * 0.7, 24, 40, 32, 8)
        clip_blt(24, 80 + 48 + altitude * 0.7, 16, 40, -24, 8)
        for x in range(3, 15):
            clip_blt(x * 16, 80 + altitude * 0.7, 0, 0, 16, 48)
            clip_blt(x * 16, 80 + 48 + + altitude * 0.7, 0, 40, 16, 8)
        for x in range(15):
            clip_blt(x * 16, 30 + altitude * 0.7, 48, 0, 16, 48)
        for x in range(15):
            clip_blt(x * 16, -20 + altitude * 0.7, 64, 0, 16, 48, colkey=None)
        pyxel.blt(self.planet_x, self.planet_y + altitude * 0.7, 1, 96, 16, 16, 16, colkey=pyxel.COLOR_BLACK)  # ringed planet
        pyxel.blt(140, -180 + altitude * 0.7, 1, 96, 0, 16, 16, colkey=pyxel.COLOR_BLACK)  # moon
        clip_blt(160, 64 + altitude * 0.75, 16, 152, 88, 56)
        clip_blt(0, 56 + altitude * 0.9, 0, 104, pyxel.width, 48)
        pyxel.blt(0, 40 + altitude, 1, 0, 48, pyxel.width, 56, colkey=0)


def make_invader(city: City):
    deg = random.random() * 2 * math.pi
    return Invader(
        city=city,
        x=pyxel.width * 0.5 + math.cos(deg) * 120,
        y=150 + city.y_offset_base + math.sin(deg) * 60,
        z=0,
    )


@dataclass
class NewBlockArea:
    blocks: list[Block]

    carried_src_x: int
    carried_src_y: int
    carried_idx: int | None = None

    num: int = 4
    x_origin: int = 56
    y_origin: int = 35
    block_width: int = 32
    height: int = 32
    border: int = 2

    def __init__(self):
        self.blocks = [None] * self.num
        # Populate an initial set of blocks.
        self.update(0)

    def coords_for_idx(self, idx, camera_altitude, center=False):
        x = self.x_origin + self.border + self.block_width * idx
        y = self.y_origin + self.border - camera_altitude
        if center:
            x += self.block_width // 2
            y += self.height // 2
        return x, y

    def update(self, camera_altitude):
        for idx in range(len(self.blocks)):
            if idx == self.carried_idx:
                continue
            x, y = self.coords_for_idx(idx, camera_altitude)
            if self.blocks[idx] is None:
                self.blocks[idx] = Block(x, y, None, None, None, random.choice(AllBlocks))
            x_center = self.blocks[idx].blocktype.x_center
            y_center = self.blocks[idx].blocktype.y_center
            self.blocks[idx].x = x + self.block_width // 2 - x_center
            self.blocks[idx].y = y + self.height // 2 - y_center

    def picked_up(self, block):
        for idx in range(len(self.blocks)):
            if self.blocks[idx] is block:
                self.carried_idx = idx
                self.carried_src_x = block.x
                self.carried_src_y = block.y
                break

    def placed(self):
        self.blocks[self.carried_idx] = None
        self.carried_idx = None

    def returned_block(self):
        self.carried_idx = None

    def draw(self, camera_altitude):
        pyxel.camera(0, 0)
        pyxel.dither(0.5)
        pyxel.rect(self.x_origin, self.y_origin,
                   self.border * 2 + self.block_width * self.num,
                   self.border * 2 + self.height,
                   pyxel.COLOR_BLACK)
        pyxel.dither(1.0)
        for b in range(self.border // 2 + 1):
            pyxel.rectb(self.x_origin - b, self.y_origin - b,
                        b * 2 + self.border * 2 + self.block_width * self.num,
                        b * 2 + self.border * 2 + self.height,
                        pyxel.COLOR_GRAY)
        pyxel.dither(0.5)
        if self.carried_idx is not None:
            pyxel.rect(self.x_origin + self.border + self.block_width * self.carried_idx + 1,
                       self.y_origin + self.border + 1,
                       self.block_width - 2,
                       self.height - 2,
                       9)
        pyxel.dither(1.0)
        pyxel.camera(0, -camera_altitude)
        for idx, b in enumerate(self.blocks):
            if idx == self.carried_idx:
                continue
            if b:
                b.draw()


@dataclass(frozen=True)
class DropSpot:
    valid: bool

@dataclass(frozen=True)
class DropInCity(DropSpot):
    col: int
    row: int
    altitude: int

@dataclass(frozen=True)
class DropInNewArea(DropSpot):
    x: int
    y: int


class Game:
    class State(enum.IntEnum):
        INTRO_MESSAGE = 1
        INTRO_COUNTDOWN_3 = 2
        INTRO_COUNTDOWN_2 = 3
        INTRO_COUNTDOWN_1 = 4
        INTRO_GO = 5
        PLAY = 6
        TIMES_UP = 7
    state: State

    camera_altitude: int = 0

    def __init__(self, *, player_factory: Callable[['Game'], Player], city_y_offset_base: int = 80, demo_mode: bool = False, time_limit: int = 120):
        self.player = player_factory(self)
        self.invaders = []
        # a set of starting heights, pick them at random.
        buildings = [5] + 3*[4] + 3*[3] + 3*[2] + 2*[1]
        self.city = City.load(cx=16, cy=0, max_height=5, buildings=buildings, y_offset_base=city_y_offset_base)
        self.background = Background()
        self.demo_mode = demo_mode
        self.time_limit = time_limit
        if not self.demo_mode:
            self.new_block_area = NewBlockArea()
            self.state = Game.State.INTRO_MESSAGE
            self.deadline = pyxel.frame_count + 2 * _GRAPHICS_FPS
        else:
            self.new_block_area = None
            self.state = Game.State.PLAY

    def update(self):
        global game_card

        if not self.demo_mode:
            if pyxel.btnp(pyxel.KEY_ESCAPE):
                game_card.active = Menu()
                return

        if self.state != Game.State.PLAY:
            if self.state == Game.State.TIMES_UP:
                if pyxel.frame_count > self.deadline:
                    game_card.active = ScoreScreen(self.city, self.background, self.camera_altitude)
                return

            if pyxel.btnp(pyxel.KEY_SPACE):
                self.state = Game.State.PLAY
                self.deadline = pyxel.frame_count + _GRAPHICS_FPS * self.time_limit
            elif pyxel.frame_count > self.deadline:
                self.state += 1
                self.deadline = pyxel.frame_count + _GRAPHICS_FPS
                if self.state == Game.State.PLAY:
                    self.deadline = pyxel.frame_count + _GRAPHICS_FPS * self.time_limit
            return

        if not self.demo_mode:
            if pyxel.frame_count > self.deadline:
                self.state = Game.State.TIMES_UP
                self.deadline = pyxel.frame_count + _GRAPHICS_FPS
                return

        self.background.update()
        self.player.update()
        if not self.demo_mode:
            if self.player.y + self.camera_altitude < 40:
                self.camera_altitude = 40 - self.player.y
            if self.player.y + self.camera_altitude > pyxel.height - 40:
                self.camera_altitude = max(0, pyxel.height - 40 - self.player.y)
        else:
            self.camera_altitude = 0
        if self.new_block_area:
            self.new_block_area.update(self.camera_altitude)

        if not _ENABLE_INVADERS:
            return
        for invader in self.invaders:
            invader.update()
        self.invaders[:] = [i for i in self.invaders if not i.dead]
        for i in range(20):
            self.invaders.append(make_invader(self.city))

    def draw(self):
        pyxel.camera(0, 0)
        self.background.draw(self.camera_altitude)

        if self.state != Game.State.PLAY:
            pyxel.camera(0, -self.camera_altitude)
            self.city.draw()
            pyxel.camera(0, 0)

            pyxel.dither(1 - 0.25 * (self.state - 1))
            pyxel.rect(0, 0, pyxel.width, pyxel.height, pyxel.COLOR_BLACK)
            pyxel.dither(1.0)
            if self.state == Game.State.INTRO_MESSAGE:
                text_centered('Build as high as', 140, font=_FONT_SPLEEN_8x16, color=pyxel.COLOR_WHITE)
                text_centered('you can in', 160, font=_FONT_SPLEEN_8x16, color=pyxel.COLOR_WHITE)
                text_centered('%i seconds!' % self.time_limit, 180, font=_FONT_SPLEEN_8x16, color=pyxel.COLOR_WHITE)
            elif self.state == Game.State.INTRO_COUNTDOWN_3:
                text_centered('3', 140, font=_FONT_SPLEEN_32x64, color=pyxel.COLOR_WHITE)
            elif self.state == Game.State.INTRO_COUNTDOWN_2:
                text_centered('2', 140, font=_FONT_SPLEEN_32x64, color=pyxel.COLOR_WHITE)
            elif self.state == Game.State.INTRO_COUNTDOWN_1:
                text_centered('1', 140, font=_FONT_SPLEEN_32x64, color=pyxel.COLOR_WHITE)
            elif self.state == Game.State.INTRO_GO:
                text_centered('Go!', 140, font=_FONT_SPLEEN_32x64, color=pyxel.COLOR_WHITE)
            elif self.state == Game.State.TIMES_UP:
                pyxel.rect(20, 135, pyxel.width - 40, 42, pyxel.COLOR_BLACK)
                text_centered('Time\'s up!', 140, font=_FONT_SPLEEN_16x32, color=pyxel.COLOR_WHITE)
            return

        if not self.demo_mode:
            score = self.city.score()
            pyxel.text(5, 5, 'Score: %i' % score, pyxel.COLOR_WHITE, _FONT_SPLEEN_8x16)
            time_left = (self.deadline - pyxel.frame_count) / _GRAPHICS_FPS
            pyxel.text(140, 5, 'Time: %3.1fs' % time_left, pyxel.COLOR_WHITE, _FONT_SPLEEN_8x16)

        pyxel.camera(0, -self.camera_altitude)
        for thing in sorted(self.invaders, key=lambda b: (b.y, b.z)):
            thing.draw()
        self.city.draw()
        if self.new_block_area:
            self.new_block_area.draw(self.camera_altitude)
            pyxel.camera(0, -self.camera_altitude)
        if self.player.carrying:
            drop_spot = self.closest_drop_spot(
                self.player.x + self.player.width / 2,
                self.player.y + self.player.height / 2 + 12,
                self.player.carrying)
            if drop_spot is not None:
                self.draw_drop_indicator(drop_spot, self.player.carrying)
        else:
            cb, is_new = self.closest_pickup_spot(
                self.player.x + self.player.width / 2,
                self.player.y + self.player.height / 2 + 10)
            if cb:
                self.draw_pickup_indicator(cb, is_new)
        self.player.draw()

    def closest_pickup_spot(self, x: float, y: float):
        closest = None
        closest_is_new = None
        closest_dist = 40
        for row, tile_col in enumerate(self.city.tiles):
            for col, tile in enumerate(tile_col):
                if not tile or not tile.blocks:
                    continue
                top_x, top_y = self.city.tile_to_screen(col, row, len(tile.blocks) - 1)
                dx = top_x + 8 - x
                dy = top_y + 8 - y
                dist = math.hypot(dx, dy)
                if dist <= closest_dist:
                    closest = tile.blocks[-1].block
                    closest_dist = dist
                    closest_is_new = False
        if self.new_block_area:
            for b in self.new_block_area.blocks:
                dx = b.x + b.blocktype.x_center - x
                dy = b.y + b.blocktype.y_center - y
                dist = math.hypot(dx, dy)
                if dist <= closest_dist:
                    closest = b
                    closest_dist = dist
                    closest_is_new = True
        return closest, closest_is_new

    def closest_drop_spot(self, x: float, y: float, block: Block):
        closest = None
        closest_dist = max_dist = 40
        closest_is_valid = False
        for row, tile_col in enumerate(self.city.tiles):
            for col, tile in enumerate(tile_col):
                if not tile or tile.blocks is None:
                    continue
                altitude = len(tile.blocks)
                top_x, top_y = self.city.tile_to_screen(col, row, altitude)
                dx = top_x + 8 - x
                dy = top_y + 8 - y
                dist = math.hypot(dx, dy)
                if dist > max_dist:
                    continue
                valid = self.city.valid_drop_spot(col, row, altitude, block)
                if (valid and not closest_is_valid) or (dist <= closest_dist and valid == closest_is_valid):
                    closest_is_valid = valid
                    closest = DropInCity(closest_is_valid, col, row, altitude)
                    closest_dist = dist
        if self.new_block_area and self.new_block_area.carried_idx is not None:
            bx, by = self.new_block_area.coords_for_idx(self.new_block_area.carried_idx, self.camera_altitude, center=True)
            dx = bx - x
            dy = by - y
            dist = math.hypot(dx, dy)
            if dist < closest_dist:
                closest_is_valid = True
                x = self.new_block_area.carried_src_x
                y = self.new_block_area.carried_src_y
                closest = DropInNewArea(True, x, y)
                closest_dist = dist
        return closest

    def draw_drop_indicator(self, drop_spot, block):
        # TODO: this has an annoying amount of duplication with valid_drop_spot.
        bt = block.blocktype
        if isinstance(drop_spot, DropInCity):
            for part in bt.footprint:
                col = part.col + drop_spot.col
                row = part.row + drop_spot.row
                altitude = part.altitude + drop_spot.altitude
                valid = True
                if row < 0 or row >= len(self.city.tiles):
                    valid = False
                elif col < 0 or col >= len(self.city.tiles[0]):
                    valid = False
                else:
                    tile = self.city.tiles[row][col]
                    if tile is None or tile.blocks is None:
                        valid = False
                    elif altitude != len(tile.blocks):
                        valid = False
                if valid:
                    outline_block(*self.city.tile_to_screen(col, row, altitude))
                else:
                    outline_block(*self.city.tile_to_screen(col, row, altitude),
                                  color=8)
                    cross_block(*self.city.tile_to_screen(col, row, altitude), pyxel.COLOR_RED)
        elif isinstance(drop_spot, DropInNewArea):
            for part in bt.footprint:
                x, y = drop_spot.x, drop_spot.y
                dx, dy = City.base_tile_to_screen(part.col, part.row, part.altitude)
                x += dx
                y += dy
                outline_block(x, y)
        else:
            AssertButNotInRelease()

    def draw_pickup_indicator(self, block, is_new):
        bt = block.blocktype
        for part in bt.footprint:
            if is_new:
                valid = True
                x, y = block.x, block.y
                dx, dy = City.base_tile_to_screen(part.col, part.row, part.altitude)
                x += dx
                y += dy
            else:
                col = part.col + block.col
                row = part.row + block.row
                altitude = part.altitude + block.altitude
                tile = self.city.tiles[row][col]
                valid = len(tile.blocks) == altitude + 1
                x, y = self.city.tile_to_screen(col, row, altitude)
            if valid:
                outline_block(x, y)
            else:
                outline_block(x, y, color=8)
                cross_block(*self.city.tile_to_screen(col, row, altitude), pyxel.COLOR_RED)


def text_width(text: str, font: pyxel.Font):
    """Because pyxel.Font's `text_width` doesn't handle newlines."""
    width = 0
    for line in text.splitlines():
        width = max(width, font.text_width(line))
    return width


def text_centered(text: str, y: int, *, font: pyxel.Font, color: int):
    x = pyxel.width // 2
    dx = text_width(text, font) // 2
    pyxel.text(x - dx, y, text, color, font)


class ScoreScreen:
    def __init__(self, city, background, camera_altitude):
        self.city = city
        self.background = background
        self.camera_altitude = camera_altitude
        self.camera_direction = -1
        self.camera_move_delay = 0
        self.maximum_altitude = max(0, self.city.highest_building() * 8 - 160)

        self.score_table = [
            ('Grandmaster', 5000, False),
            ('Master', 2000, False),
            ('Expert', 1000, False),
            ('Veteran', 500, False),
            ('Learner', 250, False),
            ('Novice', 125, False),
            ('Asleep', 0, False),
            ]
        score = city.score()
        if score < 0:
            text = 'How did you do that?'
        else:
            text = 'You!'
        bisect.insort_left(self.score_table, (text, score, True),
                           key=lambda x: -x[1])

        pyxel.play(0, 'T130 @2 O3 V80 Q50 E C E C', loop=True)
        pyxel.play(1, 'T130 @1 O4 V80 Q70 G2 Q50 G8. E16 G8. > C16 < Q70 G1 G2 Q50 G8. E16 C8. E16 < Q70 G1', loop=True)

    def update(self):
        self.background.update()

        global game_card
        if pyxel.btnp(pyxel.KEY_ESCAPE) or pyxel.btnp(pyxel.KEY_SPACE):
            pyxel.stop()
            game_card.active = Menu()

        if pyxel.btn(pyxel.KEY_UP):
            self.camera_move_delay = pyxel.frame_count + _GRAPHICS_FPS
            if self.camera_altitude + 3 < self.maximum_altitude:
                self.camera_altitude += 3
            elif self.camera_altitude < self.maximum_altitude:
                self.camera_altitude = self.maximum_altitude
        if pyxel.btn(pyxel.KEY_DOWN):
            self.camera_move_delay = pyxel.frame_count + _GRAPHICS_FPS
            self.camera_altitude -= 3
            if self.camera_altitude < 0:
                self.camera_altitude = 0

        if pyxel.frame_count > self.camera_move_delay:
            self.camera_altitude += self.camera_direction
            if self.camera_altitude < 0:
                self.camera_altitude = 0
                self.camera_direction = 1
            if self.camera_altitude > self.maximum_altitude:
                if self.camera_direction > 0:
                    self.camera_altitude = self.maximum_altitude
                self.camera_direction = -1

    def draw(self):
        pyxel.camera(0, 0)
        self.background.draw(self.camera_altitude)
        pyxel.camera(0, -self.camera_altitude)
        self.city.draw()
        pyxel.camera(0, 0)

        text_centered('Scores!', 20, font=_FONT_SPLEEN_16x32, color=pyxel.COLOR_WHITE)

        font = _FONT_SPLEEN_8x16
        for idx, (name, score, player) in enumerate(self.score_table):
            if player:
                color = _CYCLE_COLORS[(pyxel.frame_count // 3) % len(_CYCLE_COLORS)]
            else:
                color = pyxel.COLOR_WHITE
            y = 60 + idx * 20
            pyxel.text(30, y, name, color, font)
            score_text = str(score)
            pyxel.text(pyxel.width - 30 - text_width(score_text, font),
                       y,
                       score_text, color, font)


class Credits:

    TEXT = textwrap.dedent("""\
        Consumer
          Consumer

    Brought to you by:

    Alexander Malmberg
    Daniele Cocca
    Dániel Darabos
    Gökdeniz Karadag
    """)

    def __init__(self):
        self.y = pyxel.height * 0.8
        self.blocks = [self.Block0, self.Block1, self.Block2, self.Block3]
        self.bld_l = [random.randint(0, len(self.blocks)-1) for _ in range(int(((pyxel.height / 10) * 7 / 16)))]
        self.bld_r = [random.randint(0, len(self.blocks)-1) for _ in range(int(((pyxel.height / 10) * 5 / 16)))]

        pyxel.play(0, 'T120 @2  V40 O4 B B E2 B B E2 B D E- B- C A B2', loop=True)
        pyxel.play(1, 'T120 @1  V50 O2 G B > C2 < G B > C2 < G B > C D E F# G2', loop=True)

    def update(self):
        if pyxel.btnp(pyxel.KEY_ESCAPE):
            pyxel.stop()
            global game_card
            game_card.active = Menu()

    def Block0(self, x, y):
        pyxel.blt(x, y, 0, 16, 16, 32, 32, colkey=0)
    def Block1(self, x, y):
        pyxel.blt(x, y, 0, 16, 48, 32, 32, colkey=0)
    def Block2(self, x, y):
        pyxel.blt(x, y, 0, 16, 80, 32, 32, colkey=0)
    def Block3(self, x, y):
        pyxel.blt(x, y, 0, 16, 112, 32, 32, colkey=0)
    def draw(self):
        pyxel.cls(pyxel.COLOR_BLACK)
        text_centered(self.TEXT, self.y, font=_FONT_SPLEEN_8x16, color=pyxel.COLOR_RED)
        self.y -= 0.5
        if -self.y > (pyxel.height * 0.5):
          self.y = pyxel.height
        start_l_x, start_l_y = 8, pyxel.height
        start_r_x, start_r_y = pyxel.width-40, pyxel.height
        for i, blk in enumerate(self.bld_l):
            self.blocks[blk](start_l_x, start_l_y - (i * 16) )
        for i, blk in enumerate(self.bld_r):
            self.blocks[blk](start_r_x, start_r_y - (i * 16) )




class Menu:

    def __init__(self):
        self.selected = 0
        self.background_game = Game(
            player_factory=lambda game: RandomPlayer(game, 50, 100),
            city_y_offset_base=96,
            demo_mode=True,
        )
        pyxel.play(0, 'T128 V30 @1 @VIB1 { 48, 12, 50 } O5 L1 C# C# C# C#  D C#2 < B2 A G#', loop=True)
        pyxel.play(1, 'T128 V40 @1 @VIB1 { 48, 12, 50 } O4 L1 F# G# A B  F# F# D C#', loop=True)
        pyxel.play(2, 'T128 V40 @2 O3 L16 < [ F# R A R F# R > C R C# R < C# R A R G# R ] 4 [ B R > D R < B R > F R F# R < F# R > D R C# R < ] 3 B R > D R < B R > F R F# R C# R < A R G# R', loop=True)
        pyxel.play(3, 'T128 Q50 @3 L16 @ENV1{30,8,0} O7 [ RRRR FRRR RRFF RRRR ] 7 [ RRFF RFFR FFRR RFRF ] 1', loop=True)

        def _PlayGame():
            global game_card
            pyxel.stop()
            game_card.active = Game(player_factory=lambda game: Player(game, 100, 100))

        def _ShowCredits():
            global game_card
            pyxel.stop()
            game_card.active = Credits()

        self.menu_items = (
            ("Play Game", _PlayGame),
            ("Credits", _ShowCredits),
            ("Quit", lambda: pyxel.quit()),
        )

    def update(self):
        if pyxel.btnp(pyxel.KEY_ESCAPE):
            pyxel.quit()
        if pyxel.btnp(pyxel.KEY_DOWN):
            self.selected = min(self.selected + 1, len(self.menu_items) - 1)
        if pyxel.btnp(pyxel.KEY_UP):
            self.selected = max(self.selected - 1, 0)
        if pyxel.btnp(pyxel.KEY_RETURN) or pyxel.btnp(pyxel.KEY_SPACE):
            _, action = self.menu_items[self.selected]
            action()

        self.background_game.update()

    def draw(self):
        self.background_game.draw()

        pyxel.text(56 - 16, 8, "Consumer", pyxel.COLOR_WHITE, _FONT_SPLEEN_16x32)
        pyxel.text(56 + 16, 40, "Consumer", pyxel.COLOR_WHITE, _FONT_SPLEEN_16x32)

        for i, (item_text, _) in enumerate(self.menu_items):
            if i == self.selected:
                color = _CYCLE_COLORS[(pyxel.frame_count // 3) % len(_CYCLE_COLORS)]
                text_centered(f"> {item_text} <", 96 + (16 + 8) * i, font=_FONT_SPLEEN_8x16, color=color)
            else:
                text_centered(item_text, 96 + (16 + 8) * i, font=_FONT_SPLEEN_8x16, color=pyxel.COLOR_WHITE)


class Dispatcher:

    def __init__(self):
        self.active = Menu()

    def update(self):
        self.active.update()

    def draw(self):
        self.active.draw()


game_card = Dispatcher()
pyxel.run(game_card.update, game_card.draw)
