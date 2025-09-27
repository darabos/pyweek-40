import abc
import collections
import enum
import math
import random
import pyxel
import threading
import textwrap
from dataclasses import dataclass
from collections.abc import Callable


pyxel.init(240, 320, quit_key=pyxel.KEY_NONE)
pyxel.load("assets/art.pyxres")


# Bitmap font definitions
_FONT_SPLEEN_32x64 = pyxel.Font("assets/spleen-32x64.bdf")
_FONT_SPLEEN_16x32 = pyxel.Font("assets/spleen-16x32.bdf")
_FONT_SPLEEN_8x16  = pyxel.Font("assets/spleen-8x16.bdf")

# Features.
_ENABLE_INVADERS = False

# Sound channel definitions
_CHANNEL_SFX = 3

# Sound bank definitions
_SOUND_PICK_UP = 0
_SOUND_DROP = 1


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
    carrying: "Block | None" = None

    def draw(self):
        if self.carrying:
            self.carrying.x = self.x
            self.carrying.y = self.y + 10
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
                drop_spot = self.game.city.closest_drop_spot(self.x + self.width / 2, self.y + self.height / 2 + 18, self.carrying)
                if drop_spot is None or not drop_spot[3]:
                    # TODO: failed drop sound effect
                    pass
                else:
                    col, row, altitude, valid = drop_spot
                    self.game.city.add(col, row, self.carrying)
                    self.carrying = None
                    pyxel.play(_CHANNEL_SFX, _SOUND_PICK_UP)
            else:
                b = self.game.city.closest_block(self.x + self.width / 2, self.y + self.height / 2 + 10)
                if b:
                    if self.game.city.remove(b):
                        self.carrying = b
                        pyxel.play(_CHANNEL_SFX, _SOUND_DROP)
                    else:
                        # TODO: failed pick-up sound effect
                        pass


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


NormalBlocks = [
    BlockType(footprint=(
        BlockPart(sprites=(BlockSprite(0, 0, 0, 16 + i * 16, 16, 16), )), )
              )
    for i in range(8)]
RedBlocks = [
    BlockType(footprint=(
        BlockPart(sprites=(BlockSprite(0, 0, 48, 16 + i * 16, 16, 16), )), )
              )
    for i in range(2)]
Skybridge = BlockType(
    footprint=(BlockPart(sprites=(BlockSprite(0, 0, 0, 16, 16, 16), ),
                         col=0, row=0, altitude=0),
               BlockPart(sprites=(BlockSprite(0, -7, 120, 33, 30, 23), ),
                         col=-1, row=0, altitude=0)))
Skyramp = BlockType(
    footprint=(BlockPart(sprites=(BlockSprite(0, 0, 0, 16, 16, 16), ),
                         col=0, row=0, altitude=0),
               BlockPart(sprites=(BlockSprite(0, -15, 120, 65, 30, 31), ),
                         col=-1, row=0, altitude=1)))


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

    def closest_block(self, x: float, y: float):
        closest = None
        closest_dist = 40
        for row, tile_col in enumerate(self.tiles):
            for col, tile in enumerate(tile_col):
                if not tile or not tile.blocks:
                    continue
                top_x, top_y = self.tile_to_screen(col, row, len(tile.blocks) - 1)
                dx = top_x + 8 - x
                dy = top_y + 8 - y
                dist = math.hypot(dx, dy)
                if dist <= closest_dist:
                    closest = tile.blocks[-1].block
                    closest_dist = dist
        return closest

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

    def closest_drop_spot(self, x: float, y: float, block: Block):
        closest = None
        closest_dist = max_dist = 40
        closest_is_valid = False
        for row, tile_col in enumerate(self.tiles):
            for col, tile in enumerate(tile_col):
                if not tile or tile.blocks is None:
                    continue
                altitude = len(tile.blocks)
                top_x, top_y = self.tile_to_screen(col, row, altitude)
                dx = top_x + 8 - x
                dy = top_y + 8 - y
                dist = math.hypot(dx, dy)
                if dist > max_dist:
                    continue
                valid = self.valid_drop_spot(col, row, altitude, block)
                if (valid and not closest_is_valid) or (dist <= closest_dist and valid == closest_is_valid):
                    closest_is_valid = valid
                    closest = col, row, altitude, closest_is_valid
                    closest_dist = dist
        return closest

    @staticmethod
    def load(cx: int, cy: int, max_height: int, *, y_offset_base: int):
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
                height = int(max_height * random.random() ** 4)
                x, y = City.base_tile_to_screen(col, row, -1)
                x += x_off
                y += y_off
                match tile:
                    case (0, 1):
                        base = FoundationSprite(x, y, sprite=(3, 0))
                        sprites = NormalBlocks
                        buildable = True
                    case (3, 1):
                        base = FoundationSprite(x, y, sprite=(3, 0))
                        height = 7
                        sprites = RedBlocks
                        buildable = True
                    case (1, 1):
                        base = Road(x, y, sprite=(3, 3))
                        height = 0
                        buildable = False
                    case (1, 0):
                        base = Road(x, y, sprite=(3, 3), flipped=True)
                        height = 0
                        buildable = False
                tile = Tile(base)
                tiles[row][col] = tile
                if buildable:
                    tile.blocks = []
                    for h in range(height):
                        sprite = int(len(sprites) * random.random() ** 3)
                        x, y = City.base_tile_to_screen(col, row, h)
                        x += x_off
                        y += y_off
                        b = Block(x, y, col, row, h, sprites[sprite])
                        tile.blocks.append(TileBlock(b, 0))

        # TODO: temp code for testing
        x, y = City.base_tile_to_screen(12, 11, 0)
        x += x_off
        y += y_off
        b = Block(x, y, 12, 11, 0, Skybridge)
        tiles[11][12].blocks = [TileBlock(b, 0)]
        tiles[11][11].blocks = [TileBlock(b, 1)]
        x, y = City.base_tile_to_screen(12, 11, 1)
        x += x_off
        y += y_off
        b = Block(x, y, 12, 11, 1, NormalBlocks[0])
        tiles[11][12].blocks.append(TileBlock(b, 0))

        x, y = City.base_tile_to_screen(9, 12, 0)
        x += x_off
        y += y_off
        b = Block(x, y, 9, 12, 0, Skyramp)
        x, y = City.base_tile_to_screen(8, 12, 0)
        x += x_off
        y += y_off
        nb = Block(x, y, 8, 12, 0, NormalBlocks[0])
        tiles[12][9].blocks = [TileBlock(b, 0)]
        tiles[12][8].blocks = [TileBlock(nb, 0), TileBlock(b, 1)]

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
        pyxel.blt(self.planet_x, self.planet_y + altitude * 0.9, 1, 96, 16, 16, 16, colkey=pyxel.COLOR_BLACK)  # ringed planet
        pyxel.blt(140, -180 + altitude * 0.7, 1, 96, 0, 16, 16)  # moon
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
        self.invaders = []
        self.city = City.load(cx=16, cy=0, max_height=5, y_offset_base=city_y_offset_base)
        self.background = Background()
        self.adjust_camera_altitude = adjust_camera_altitude
        self.camera_altitude = 0

    def update(self):
        if pyxel.btnp(pyxel.KEY_ESCAPE):
            global game_card
            game_card.active = Menu()

        self.background.update()
        self.player.update()
        if not _ENABLE_INVADERS:
            return
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
        for thing in sorted(self.invaders, key=lambda b: (b.y, b.z)):
            thing.draw()
        self.city.draw()
        if self.player.carrying:
            drop_spot = self.city.closest_drop_spot(
                self.player.x + self.player.width / 2,
                self.player.y + self.player.height / 2 + 18,
                self.player.carrying)
            if drop_spot is not None:
                col, row, altitude, valid = drop_spot
                self.draw_drop_indicator(col, row, altitude, self.player.carrying)
        else:
            cb = self.city.closest_block(
                self.player.x + self.player.width / 2,
                self.player.y + self.player.height / 2 + 10)
            if cb:
                self.draw_pickup_indicator(cb)
        self.player.draw()

    def draw_drop_indicator(self, base_col, base_row, base_altitude, block):
        # TODO: this has an annoying amount of duplication with valid_drop_spot.
        bt = block.blocktype
        for part in bt.footprint:
            col = part.col + base_col
            row = part.row + base_row
            altitude = part.altitude + base_altitude
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

    def draw_pickup_indicator(self, block):
        bt = block.blocktype
        for part in bt.footprint:
            col = part.col + block.col
            row = part.row + block.row
            altitude = part.altitude + block.altitude
            tile = self.city.tiles[row][col]
            valid = len(tile.blocks) == altitude + 1
            if valid:
                outline_block(*self.city.tile_to_screen(col, row, altitude))
            else:
                outline_block(*self.city.tile_to_screen(col, row, altitude),
                              color=8)


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


class Credits:

    TEXT = textwrap.dedent("""\
        Consumer
          Consumer

    Brought to you by:

    Alexander Malmberg
    Daniele Cocca
    Dániel Darabos
    """)

    def __init__(self):
        self.y = pyxel.height // 3

    def update(self):
        if pyxel.btnp(pyxel.KEY_ESCAPE):
            global game_card
            game_card.active = Menu()

    def draw(self):
        pyxel.cls(pyxel.COLOR_BLACK)
        text_centered(self.TEXT, self.y, font=_FONT_SPLEEN_8x16, color=pyxel.COLOR_RED)
        self.y -= 0.5


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

        def _ShowCredits():
            global game_card
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
        if pyxel.btnp(pyxel.KEY_RETURN):
            _, action = self.menu_items[self.selected]
            action()

        self.background_game.update()

    def draw(self):
        self.background_game.draw()

        pyxel.text(56 - 16, 8, "Consumer", pyxel.COLOR_WHITE, _FONT_SPLEEN_16x32)
        pyxel.text(56 + 16, 40, "Consumer", pyxel.COLOR_WHITE, _FONT_SPLEEN_16x32)

        for i, (item_text, _) in enumerate(self.menu_items):
            if i == self.selected:
                color = self.cycle_colors[(pyxel.frame_count // 3) % len(self.cycle_colors)]
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
