from __future__ import annotations

from math import cos, floor, sin
from pathlib import Path

from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    LineSegs,
    SamplerState,
    TextNode,
    Vec3,
    WindowProperties,
    loadPrcFileData,
)

loadPrcFileData("", "window-title Python Minecraft-Style Starter")
loadPrcFileData("", "show-frame-rate-meter #t")

WORLD_SIZE = 28
BASE_HEIGHT = 3
HEIGHT_VARIATION = 2
MAX_HEIGHT = 7

PLAYER_HEIGHT = 1.75
PLAYER_RADIUS = 0.28
WALK_SPEED = 5.0
SPRINT_SPEED = 8.0
GRAVITY = 24.0
JUMP_SPEED = 8.5
REACH_DISTANCE = 7.5
MOUSE_SENSITIVITY = 0.12

BLOCK_TEXTURE_FILES = {
    "grass": "grass_block.png",
    "dirt": "dirt_block.png",
    "stone": "stone_block.png",
}


def terrain_height(x: int, z: int) -> int:
    wave = sin(x * 0.32) + cos(z * 0.29)
    height = int(BASE_HEIGHT + wave * HEIGHT_VARIATION)
    return max(1, min(MAX_HEIGHT, height))


def block_type_for_layer(y: int, top: int) -> str:
    if y == top - 1:
        return "grass"
    if y >= top - 3:
        return "dirt"
    return "stone"


class MinecraftClone(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.49, 0.72, 0.98, 1)

        self.texture_dir = Path(__file__).resolve().parent / "assets" / "textures"
        self.block_textures = self.load_block_textures()

        self.blocks: dict[tuple[int, int, int], str] = {}
        self.block_nodes = {}
        self.column_tops: dict[tuple[int, int], int] = {}

        self.cube_model = self.loader.loadModel("models/box")
        self.generate_world(WORLD_SIZE)

        start_x = WORLD_SIZE // 2
        start_z = WORLD_SIZE // 2
        start_ground = self.column_tops.get((start_x, start_z), terrain_height(start_x, start_z) - 1) + 1

        self.player_pos = Vec3(start_x + 0.5, start_z + 0.5, start_ground + PLAYER_HEIGHT + 6.0)
        self.player_velocity_z = 0.0
        self.player_grounded = False
        self.yaw = 45.0
        self.pitch = -18.0

        self.keys = {
            "w": False,
            "a": False,
            "s": False,
            "d": False,
            "shift": False,
        }

        self.setup_controls()
        self.create_crosshair()
        self.create_help_text()
        self.enable_mouse_capture()

        self.taskMgr.add(self.update, "update")

    def load_block_textures(self):
        textures = {}
        for block_type, file_name in BLOCK_TEXTURE_FILES.items():
            texture_path = self.texture_dir / file_name
            texture = self.loader.loadTexture(str(texture_path))
            texture.setMagfilter(SamplerState.FT_nearest)
            texture.setMinfilter(SamplerState.FT_nearest)
            textures[block_type] = texture
        return textures

    def world_to_block_key(self, world_x: float, world_y: float, world_z: float) -> tuple[int, int, int]:
        # Panda3D axes are (x, y, z) where z is vertical.
        return (int(floor(world_x)), int(floor(world_z)), int(floor(world_y)))

    def block_key_to_world_center(self, key: tuple[int, int, int]) -> Vec3:
        x, y, z = key
        return Vec3(x, z, y)

    def add_block(self, key: tuple[int, int, int], block_type: str):
        if key in self.blocks:
            return

        node = self.cube_model.copyTo(self.render)
        node.setPos(self.block_key_to_world_center(key))
        node.setTexture(self.block_textures[block_type], 1)
        self.block_nodes[key] = node
        self.blocks[key] = block_type

        x, y, z = key
        column_key = (x, z)
        current_top = self.column_tops.get(column_key)
        if current_top is None or y > current_top:
            self.column_tops[column_key] = y

    def remove_block(self, key: tuple[int, int, int]):
        if key not in self.blocks:
            return

        self.block_nodes[key].removeNode()
        del self.block_nodes[key]
        del self.blocks[key]

        x, _, z = key
        column_key = (x, z)

        top = None
        for candidate_key in self.blocks:
            bx, by, bz = candidate_key
            if bx == x and bz == z and (top is None or by > top):
                top = by

        if top is None:
            self.column_tops.pop(column_key, None)
        else:
            self.column_tops[column_key] = top

    def generate_world(self, size: int):
        for x in range(size):
            for z in range(size):
                top = terrain_height(x, z)
                for y in range(top):
                    self.add_block((x, y, z), block_type_for_layer(y, top))

    def setup_controls(self):
        for key in ("w", "a", "s", "d", "shift"):
            self.accept(key, self.set_key, [key, True])
            self.accept(f"{key}-up", self.set_key, [key, False])

        self.accept("space", self.try_jump)
        self.accept("mouse1", self.on_left_click)
        self.accept("mouse3", self.on_right_click)
        self.accept("escape", self.userExit)

    def set_key(self, key: str, value: bool):
        self.keys[key] = value

    def enable_mouse_capture(self):
        props = WindowProperties()
        props.setCursorHidden(True)
        self.win.requestProperties(props)
        self.center_pointer()

    def center_pointer(self):
        center_x = self.win.getXSize() // 2
        center_y = self.win.getYSize() // 2
        self.win.movePointer(0, center_x, center_y)

    def create_crosshair(self):
        gap = 0.012
        segment_length = 0.02

        crosshair = LineSegs("crosshair")
        crosshair.setThickness(2.0)
        crosshair.setColor(0.82, 0.82, 0.82, 1.0)

        crosshair.moveTo(-(gap + segment_length), 0, 0)
        crosshair.drawTo(-gap, 0, 0)

        crosshair.moveTo(gap, 0, 0)
        crosshair.drawTo(gap + segment_length, 0, 0)

        crosshair.moveTo(0, 0, -(gap + segment_length))
        crosshair.drawTo(0, 0, -gap)

        crosshair.moveTo(0, 0, gap)
        crosshair.drawTo(0, 0, gap + segment_length)

        self.aspect2d.attachNewNode(crosshair.create())

    def create_help_text(self):
        OnscreenText(
            text="WASD move | Mouse look | Shift sprint | Space jump | LMB place | RMB remove | Esc quit",
            pos=(-1.32, -0.95),
            scale=0.04,
            fg=(0.78, 0.9, 1, 1),
            align=TextNode.ALeft,
            mayChange=False,
        )

    def update_mouse_look(self):
        if not self.win.getProperties().getForeground():
            return

        center_x = self.win.getXSize() // 2
        center_y = self.win.getYSize() // 2
        pointer = self.win.getPointer(0)
        delta_x = pointer.getX() - center_x
        delta_y = pointer.getY() - center_y

        self.yaw -= delta_x * MOUSE_SENSITIVITY
        self.pitch -= delta_y * MOUSE_SENSITIVITY
        self.pitch = max(-89.0, min(89.0, self.pitch))

        self.center_pointer()

    def try_jump(self):
        if self.player_grounded:
            self.player_velocity_z = JUMP_SPEED
            self.player_grounded = False

    def block_exists_at_world(self, world_x: float, world_y: float, world_z: float) -> bool:
        key = self.world_to_block_key(world_x, world_y, world_z)
        return key in self.blocks

    def collides_with_block(self, next_x: float, next_y: float, next_z: float) -> bool:
        foot_z = next_z - PLAYER_HEIGHT
        body_samples = (0.08, PLAYER_HEIGHT * 0.55, PLAYER_HEIGHT * 0.95)
        corner_offsets = (
            (-PLAYER_RADIUS, -PLAYER_RADIUS),
            (PLAYER_RADIUS, -PLAYER_RADIUS),
            (-PLAYER_RADIUS, PLAYER_RADIUS),
            (PLAYER_RADIUS, PLAYER_RADIUS),
        )

        for offset_x, offset_y in corner_offsets:
            sample_x = next_x + offset_x
            sample_y = next_y + offset_y
            for sample_height in body_samples:
                sample_z = foot_z + sample_height
                if self.block_exists_at_world(sample_x, sample_y, sample_z):
                    return True
        return False

    def highest_ground_z(self, world_x: float, world_y: float) -> float:
        corner_offsets = (
            (-PLAYER_RADIUS, -PLAYER_RADIUS),
            (PLAYER_RADIUS, -PLAYER_RADIUS),
            (-PLAYER_RADIUS, PLAYER_RADIUS),
            (PLAYER_RADIUS, PLAYER_RADIUS),
        )

        highest = -9999.0
        for offset_x, offset_y in corner_offsets:
            bx = int(floor(world_x + offset_x))
            bz = int(floor(world_y + offset_y))
            column_top = self.column_tops.get((bx, bz))
            if column_top is not None:
                highest = max(highest, column_top + 1.0)
        return highest

    def apply_horizontal_movement(self, dt: float):
        input_x = float(self.keys["d"]) - float(self.keys["a"])
        input_y = float(self.keys["w"]) - float(self.keys["s"])

        if input_x == 0.0 and input_y == 0.0:
            return

        forward = self.camera.getQuat(self.render).getForward()
        right = self.camera.getQuat(self.render).getRight()
        forward.z = 0
        right.z = 0
        if forward.length_squared() > 0:
            forward.normalize()
        if right.length_squared() > 0:
            right.normalize()

        move = (forward * input_y) + (right * input_x)
        if move.length_squared() <= 0:
            return

        move.normalize()
        speed = SPRINT_SPEED if self.keys["shift"] else WALK_SPEED
        movement = move * speed * dt

        next_x = self.player_pos.x + movement.x
        next_y = self.player_pos.y
        next_z = self.player_pos.z
        if not self.collides_with_block(next_x, next_y, next_z):
            self.player_pos.x = next_x

        next_x = self.player_pos.x
        next_y = self.player_pos.y + movement.y
        if not self.collides_with_block(next_x, next_y, next_z):
            self.player_pos.y = next_y

    def apply_vertical_physics(self, dt: float):
        self.player_velocity_z -= GRAVITY * dt
        self.player_pos.z += self.player_velocity_z * dt

        ground_z = self.highest_ground_z(self.player_pos.x, self.player_pos.y)
        feet_z = self.player_pos.z - PLAYER_HEIGHT

        if feet_z < ground_z:
            self.player_pos.z = ground_z + PLAYER_HEIGHT
            self.player_velocity_z = 0.0
            self.player_grounded = True
        else:
            self.player_grounded = False

        if self.player_pos.z < -25:
            center = WORLD_SIZE // 2
            ground = self.column_tops.get((center, center), terrain_height(center, center) - 1) + 1
            self.player_pos = Vec3(center + 0.5, center + 0.5, ground + PLAYER_HEIGHT + 6.0)
            self.player_velocity_z = 0.0

    def update_camera(self):
        self.camera.setPos(self.player_pos)
        self.camera.setHpr(self.yaw, self.pitch, 0)

    def raycast_block(self):
        origin = self.camera.getPos(self.render)
        direction = self.render.getRelativeVector(self.camera, Vec3(0, 1, 0))
        direction.normalize()

        step = 0.1
        previous_key = None

        for index in range(int(REACH_DISTANCE / step)):
            distance = index * step
            point = origin + direction * distance
            block_key = self.world_to_block_key(point.x, point.y, point.z)

            if block_key in self.blocks:
                return block_key, previous_key

            previous_key = block_key

        return None, None

    def on_right_click(self):
        hit_key, _ = self.raycast_block()
        if hit_key and hit_key[1] > 0:
            self.remove_block(hit_key)

    def block_overlaps_player(self, key: tuple[int, int, int]) -> bool:
        x, y, z = key
        block_min_x = x
        block_max_x = x + 1
        block_min_y = z
        block_max_y = z + 1
        block_min_z = y
        block_max_z = y + 1

        player_min_x = self.player_pos.x - PLAYER_RADIUS
        player_max_x = self.player_pos.x + PLAYER_RADIUS
        player_min_y = self.player_pos.y - PLAYER_RADIUS
        player_max_y = self.player_pos.y + PLAYER_RADIUS
        player_min_z = self.player_pos.z - PLAYER_HEIGHT
        player_max_z = self.player_pos.z

        overlap_x = block_min_x < player_max_x and block_max_x > player_min_x
        overlap_y = block_min_y < player_max_y and block_max_y > player_min_y
        overlap_z = block_min_z < player_max_z and block_max_z > player_min_z
        return overlap_x and overlap_y and overlap_z

    def on_left_click(self):
        hit_key, place_key = self.raycast_block()
        if not hit_key or not place_key:
            return

        if place_key in self.blocks:
            return

        if self.block_overlaps_player(place_key):
            return

        self.add_block(place_key, "grass")

    def update(self, task):
        dt = globalClock.getDt()
        self.update_mouse_look()
        self.update_camera()
        self.apply_horizontal_movement(dt)
        self.apply_vertical_physics(dt)
        self.update_camera()
        return task.cont


if __name__ == "__main__":
    game = MinecraftClone()
    game.run()
