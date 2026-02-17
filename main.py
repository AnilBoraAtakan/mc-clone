from __future__ import annotations

from math import cos, floor, sin
from pathlib import Path

from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    BitMask32,
    LineSegs,
    RigidBodyCombiner,
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

PLAYER_HEIGHT = 2.0
PLAYER_RADIUS = 0.49
CAMERA_OFFSET_FROM_TOP = 0.5
WALK_SPEED = 5.0
SPRINT_SPEED = 8.0
GRAVITY = 24.0
JUMP_SPEED = 8.5
REACH_DISTANCE = 7.5
MOUSE_SENSITIVITY = 0.12
CHUNK_SIZE = 8
CHUNK_COLLECTS_PER_FRAME = 2
CAMERA_NEAR_CLIP = 0.05

BLOCK_TEXTURE_FILES = {
    "grass": "grass_block.png",
    "dirt": "dirt_block.png",
    "stone": "stone_block.png",
}

NEIGHBOR_OFFSETS = (
    (1, 0, 0),
    (-1, 0, 0),
    (0, 1, 0),
    (0, -1, 0),
    (0, 0, 1),
    (0, 0, -1),
)


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
    def __init__(self, capture_mouse: bool = True):
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.49, 0.72, 0.98, 1)
        self.camLens.setNear(CAMERA_NEAR_CLIP)
        self.world_camera_mask = BitMask32.bit(1)
        self.cam.node().setCameraMask(self.world_camera_mask)
        self.capture_mouse = capture_mouse
        self.mouse_capture_enabled = False

        self.texture_dir = Path(__file__).resolve().parent / "assets" / "textures"
        self.block_textures = self.load_block_textures()

        self.blocks: dict[tuple[int, int, int], str] = {}
        self.block_nodes = {}
        self.column_tops: dict[tuple[int, int], int] = {}
        self.column_layers: dict[tuple[int, int], set[int]] = {}
        self.chunk_combiners: dict[tuple[int, int], RigidBodyCombiner] = {}
        self.chunk_roots = {}
        self.block_chunk_keys = {}
        self.dirty_chunk_keys: set[tuple[int, int]] = set()

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
        self.create_player_model()
        self.create_crosshair()
        self.create_help_text()
        if self.capture_mouse:
            self.mouse_capture_enabled = self.enable_mouse_capture()
        self.update_player_model()
        self.update_camera()

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

    def create_player_model(self):
        self.player_model_root = self.render.attachNewNode("player_model")
        self.player_model_root.hide(self.world_camera_mask)

        self.player_lower_block = self.cube_model.copyTo(self.player_model_root)
        self.player_lower_block.setTexture(self.block_textures["dirt"], 1)
        self.player_lower_block.setPos(0, 0, 0.5)

        self.player_upper_block = self.cube_model.copyTo(self.player_model_root)
        self.player_upper_block.setTexture(self.block_textures["stone"], 1)
        self.player_upper_block.setPos(0, 0, 1.5)

    def update_player_model(self):
        feet_z = self.player_pos.z - PLAYER_HEIGHT
        self.player_model_root.setPos(self.player_pos.x, self.player_pos.y, feet_z)
        self.player_model_root.setHpr(self.yaw, 0, 0)

    def world_to_block_key(self, world_x: float, world_y: float, world_z: float) -> tuple[int, int, int]:
        # Panda3D axes are (x, y, z) where z is vertical.
        return (int(floor(world_x)), int(floor(world_z)), int(floor(world_y)))

    def block_key_to_world_center(self, key: tuple[int, int, int]) -> Vec3:
        x, y, z = key
        return Vec3(x, z, y)

    def chunk_key_from_block_key(self, key: tuple[int, int, int]) -> tuple[int, int]:
        x, _, z = key
        return (x // CHUNK_SIZE, z // CHUNK_SIZE)

    def ensure_chunk(self, chunk_key: tuple[int, int]):
        chunk_root = self.chunk_roots.get(chunk_key)
        if chunk_root is not None:
            return chunk_root

        chunk_combiner = RigidBodyCombiner(f"chunk_{chunk_key[0]}_{chunk_key[1]}")
        chunk_root = self.render.attachNewNode(chunk_combiner)
        self.chunk_combiners[chunk_key] = chunk_combiner
        self.chunk_roots[chunk_key] = chunk_root
        return chunk_root

    def collect_dirty_chunks(self, max_chunks: int):
        if not self.dirty_chunk_keys:
            return

        chunk_keys = list(self.dirty_chunk_keys)[:max_chunks]
        for chunk_key in chunk_keys:
            chunk_combiner = self.chunk_combiners.get(chunk_key)
            if chunk_combiner is not None:
                chunk_combiner.collect()
            self.dirty_chunk_keys.discard(chunk_key)

    def create_block_node(self, key: tuple[int, int, int], block_type: str):
        chunk_key = self.chunk_key_from_block_key(key)
        chunk_root = self.ensure_chunk(chunk_key)
        node = self.cube_model.copyTo(chunk_root)
        node.setPos(self.block_key_to_world_center(key))
        node.setTexture(self.block_textures[block_type], 1)
        self.block_nodes[key] = node
        self.block_chunk_keys[key] = chunk_key
        self.dirty_chunk_keys.add(chunk_key)

    def remove_block_node(self, key: tuple[int, int, int]):
        node = self.block_nodes.pop(key, None)
        chunk_key = self.block_chunk_keys.pop(key, None)
        if node is not None:
            node.removeNode()
        if chunk_key is not None:
            self.dirty_chunk_keys.add(chunk_key)

    def insert_block_data(self, key: tuple[int, int, int], block_type: str):
        self.blocks[key] = block_type
        x, y, z = key
        column_key = (x, z)
        if column_key not in self.column_layers:
            self.column_layers[column_key] = set()
        self.column_layers[column_key].add(y)

        top = self.column_tops.get(column_key)
        if top is None or y > top:
            self.column_tops[column_key] = y

    def delete_block_data(self, key: tuple[int, int, int]):
        del self.blocks[key]
        x, y, z = key
        column_key = (x, z)
        layers = self.column_layers.get(column_key)

        if layers is None:
            self.column_tops.pop(column_key, None)
            return

        layers.discard(y)
        if not layers:
            del self.column_layers[column_key]
            self.column_tops.pop(column_key, None)
            return

        if self.column_tops.get(column_key) == y:
            self.column_tops[column_key] = max(layers)

    def is_block_exposed(self, key: tuple[int, int, int]) -> bool:
        x, y, z = key
        for dx, dy, dz in NEIGHBOR_OFFSETS:
            neighbor_key = (x + dx, y + dy, z + dz)
            if neighbor_key not in self.blocks:
                return True
        return False

    def refresh_block_visibility(self, key: tuple[int, int, int]):
        if key not in self.blocks:
            self.remove_block_node(key)
            return

        if self.is_block_exposed(key):
            if key not in self.block_nodes:
                self.create_block_node(key, self.blocks[key])
            return

        self.remove_block_node(key)

    def refresh_visibility_around(self, key: tuple[int, int, int]):
        self.refresh_block_visibility(key)
        x, y, z = key
        for dx, dy, dz in NEIGHBOR_OFFSETS:
            neighbor_key = (x + dx, y + dy, z + dz)
            self.refresh_block_visibility(neighbor_key)

    def add_block(self, key: tuple[int, int, int], block_type: str):
        if key in self.blocks:
            return
        self.insert_block_data(key, block_type)
        self.refresh_visibility_around(key)

    def remove_block(self, key: tuple[int, int, int]):
        if key not in self.blocks:
            return
        self.delete_block_data(key)
        self.refresh_visibility_around(key)

    def generate_world(self, size: int):
        for x in range(size):
            for z in range(size):
                top = terrain_height(x, z)
                for y in range(top):
                    self.insert_block_data((x, y, z), block_type_for_layer(y, top))

        for key, block_type in self.blocks.items():
            if self.is_block_exposed(key):
                self.create_block_node(key, block_type)
        self.collect_dirty_chunks(max(len(self.dirty_chunk_keys), 1))

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

    def enable_mouse_capture(self) -> bool:
        if self.win is None:
            return False
        if not hasattr(self.win, "requestProperties") or not hasattr(self.win, "movePointer"):
            return False

        props = WindowProperties()
        props.setCursorHidden(True)
        self.win.requestProperties(props)
        self.center_pointer()
        return True

    def center_pointer(self):
        if self.win is None or not hasattr(self.win, "movePointer"):
            return
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
        if not self.mouse_capture_enabled:
            return
        if self.win is None or not hasattr(self.win, "getPointer"):
            return

        window_props = self.win.getProperties()
        if hasattr(window_props, "getForeground") and not window_props.getForeground():
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

    def highest_layer_below_limit(self, column_key: tuple[int, int], limit: float) -> int | None:
        layers = self.column_layers.get(column_key)
        if not layers:
            return None

        top = self.column_tops.get(column_key)
        if top is not None and top <= limit:
            return top

        best = None
        for layer in layers:
            if layer <= limit and (best is None or layer > best):
                best = layer
        return best

    def highest_ground_z(self, world_x: float, world_y: float, feet_z: float, support_tolerance: float) -> float:
        corner_offsets = (
            (-PLAYER_RADIUS, -PLAYER_RADIUS),
            (PLAYER_RADIUS, -PLAYER_RADIUS),
            (-PLAYER_RADIUS, PLAYER_RADIUS),
            (PLAYER_RADIUS, PLAYER_RADIUS),
        )

        highest = -9999.0
        max_support_layer = feet_z + support_tolerance - 1.0
        for offset_x, offset_y in corner_offsets:
            bx = int(floor(world_x + offset_x))
            bz = int(floor(world_y + offset_y))
            column_top = self.highest_layer_below_limit((bx, bz), max_support_layer)
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

        feet_z = self.player_pos.z - PLAYER_HEIGHT
        support_tolerance = max(0.3, min(1.5, (-self.player_velocity_z * dt) + 0.05))
        ground_z = self.highest_ground_z(self.player_pos.x, self.player_pos.y, feet_z, support_tolerance)

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
        self.camera.setPos(
            self.player_pos.x,
            self.player_pos.y,
            self.player_pos.z - CAMERA_OFFSET_FROM_TOP,
        )
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
        if hit_key:
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
        self.apply_horizontal_movement(dt)
        self.apply_vertical_physics(dt)
        self.update_player_model()
        self.update_camera()
        self.collect_dirty_chunks(CHUNK_COLLECTS_PER_FRAME)
        return task.cont


if __name__ == "__main__":
    game = MinecraftClone()
    game.run()
