from pathlib import Path
import unittest

from panda3d.core import (
    GeomVertexReader,
    OrthographicLens,
    PNMImage,
    Point2,
    Point3,
    SamplerState,
    Texture,
    Vec3,
    loadPrcFileData,
)

loadPrcFileData("", "window-type offscreen")
loadPrcFileData("", "audio-library-name null")
loadPrcFileData("", "show-frame-rate-meter #f")
loadPrcFileData("", "win-size 960 540")
loadPrcFileData("", "sync-video #f")

from main import CHUNK_COLLECTS_PER_FRAME, PLAYER_HEIGHT, MinecraftClone

ARTIFACT_DIR = Path("test_artifacts")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


class HeadlessE2ETest(unittest.TestCase):
    def step_world(self, game: MinecraftClone, frames: int, dt: float = 1.0 / 60.0):
        for _ in range(frames):
            game.apply_horizontal_movement(dt)
            game.apply_vertical_physics(dt)
            game.update_player_model()
            game.update_camera()
            game.collect_dirty_chunks(CHUNK_COLLECTS_PER_FRAME)
            game.graphicsEngine.renderFrame()

    def render_frames(self, game: MinecraftClone, frames: int = 2):
        for _ in range(frames):
            game.graphicsEngine.renderFrame()

    def clear_world(self, game: MinecraftClone):
        for key in list(game.blocks.keys()):
            game.remove_block(key)
        game.collect_dirty_chunks(max(len(game.dirty_chunk_keys), 1))

    def add_platform_under_logs(
        self,
        game: MinecraftClone,
        center_x: int,
        center_z: int,
        size: int = 3,
        y: int = -1,
        block_type: str = "stone",
    ):
        half = size // 2
        for x in range(center_x - half, center_x + half + 1):
            for z in range(center_z - half, center_z + half + 1):
                game.add_block((x, y, z), block_type)

    def distance_to_first_block_ahead(self, game: MinecraftClone, max_distance: float = 5.0) -> float | None:
        origin = game.camera.getPos(game.render)
        direction = game.render.getRelativeVector(game.camera, Vec3(0, 1, 0))
        direction.normalize()

        step = 0.01
        for index in range(int(max_distance / step)):
            distance = index * step
            sample = origin + direction * distance
            key = game.world_to_block_key(sample.x, sample.y, sample.z)
            if key in game.blocks:
                return distance
        return None

    def chest_keys(self, game: MinecraftClone) -> list[tuple[int, int, int]]:
        keys = []
        for key, block_type in game.blocks.items():
            if block_type == "chest":
                keys.append(key)
        keys.sort()
        return keys

    def world_to_pixel(
        self,
        game: MinecraftClone,
        lens: OrthographicLens,
        screenshot: PNMImage,
        world_point: Point3,
    ) -> tuple[int, int]:
        camera_space = game.camera.getRelativePoint(game.render, world_point)
        projected = Point2()
        self.assertTrue(
            lens.project(camera_space, projected),
            msg=f"Failed to project world point {world_point} into screenshot space",
        )
        x = int(round(((projected.x + 1.0) * 0.5) * (screenshot.getXSize() - 1)))
        y = int(round(((projected.y + 1.0) * 0.5) * (screenshot.getYSize() - 1)))
        x = max(0, min(screenshot.getXSize() - 1, x))
        y = max(0, min(screenshot.getYSize() - 1, y))
        return (x, y)

    def pixel_luminance(self, screenshot: PNMImage, x: int, y: int) -> float:
        color = screenshot.getXel(x, y)
        return float((color[0] + color[1] + color[2]) / 3.0)

    def luminance_centroid(self, image: PNMImage) -> tuple[float, float]:
        width = image.getXSize()
        height = image.getYSize()
        values = []
        total = 0.0
        for y in range(height):
            for x in range(width):
                color = image.getXel(x, y)
                luminance = float((color[0] + color[1] + color[2]) / 3.0)
                values.append((x, y, luminance))
                total += luminance

        mean = total / (width * height)
        weight_sum = 0.0
        x_sum = 0.0
        y_sum = 0.0
        for x, y, luminance in values:
            weight = abs(luminance - mean)
            weight_sum += weight
            x_sum += weight * x
            y_sum += weight * y

        self.assertGreater(weight_sum, 1e-8, msg="Texture has no luminance variation")
        return (x_sum / weight_sum, y_sum / weight_sum)

    def center_marker_texture(
        self,
        name: str,
        marker_rgb: tuple[float, float, float],
        bg_rgb: tuple[float, float, float] = (0.07, 0.07, 0.07),
    ) -> Texture:
        texture = Texture(name)
        image = PNMImage(16, 16, 4)
        image.fill(*bg_rgb)
        image.alphaFill(1.0)
        for y in range(6, 10):
            for x in range(6, 10):
                image.setXelA(x, y, marker_rgb[0], marker_rgb[1], marker_rgb[2], 1.0)
        texture.load(image)
        texture.setMagfilter(SamplerState.FT_nearest)
        texture.setMinfilter(SamplerState.FT_nearest)
        return texture

    def test_log_texture_art_is_centered(self):
        texture_dir = Path("assets/textures")
        end_path = texture_dir / "log_top_bottom.png"
        side_path = texture_dir / "log_side.png"

        end_image = PNMImage()
        side_image = PNMImage()
        self.assertTrue(end_image.read(str(end_path)), msg=f"Failed to read {end_path}")
        self.assertTrue(side_image.read(str(side_path)), msg=f"Failed to read {side_path}")
        self.assertEqual((end_image.getXSize(), end_image.getYSize()), (16, 16))
        self.assertEqual((side_image.getXSize(), side_image.getYSize()), (16, 16))

        expected_center = 7.5

        end_cx, end_cy = self.luminance_centroid(end_image)
        self.assertAlmostEqual(
            end_cx,
            expected_center,
            delta=0.45,
            msg=f"log_top_bottom.png is horizontally off-center: centroid_x={end_cx:.3f}",
        )
        self.assertAlmostEqual(
            end_cy,
            expected_center,
            delta=0.45,
            msg=f"log_top_bottom.png is vertically off-center: centroid_y={end_cy:.3f}",
        )

        _, side_cy = self.luminance_centroid(side_image)
        self.assertAlmostEqual(
            side_cy,
            expected_center,
            delta=0.45,
            msg=f"log_side.png is vertically off-center: centroid_y={side_cy:.3f}",
        )

    def test_render_and_save_screenshot(self):
        game = MinecraftClone(capture_mouse=False)
        try:
            self.step_world(game, frames=12)
            self.render_frames(game)

            screenshot = game.win.getScreenshot()
            self.assertGreater(screenshot.getXSize(), 0)
            self.assertGreater(screenshot.getYSize(), 0)

            screenshot_path = ARTIFACT_DIR / "headless_e2e_frame.png"
            wrote_file = screenshot.write(str(screenshot_path))
            self.assertTrue(wrote_file)
            self.assertTrue(screenshot_path.exists())
            self.assertGreater(screenshot_path.stat().st_size, 0)
        finally:
            game.destroy()

    def test_spawn_is_seed_deterministic_and_valid(self):
        runs = 10
        seed = 1357911
        spawn_positions = []

        for _ in range(runs):
            game = MinecraftClone(capture_mouse=False, seed=seed)
            try:
                spawn = game.player_pos
                spawn_positions.append((spawn.x, spawn.y, spawn.z))

                self.assertFalse(
                    game.collides_with_block(spawn.x, spawn.y, spawn.z),
                    msg=f"Spawned inside a block at {spawn}",
                )

                feet_z = spawn.z - PLAYER_HEIGHT
                ground_z = game.highest_ground_z(
                    spawn.x,
                    spawn.y,
                    feet_z,
                    support_tolerance=0.1,
                )
                self.assertGreaterEqual(
                    feet_z,
                    ground_z,
                    msg=f"Spawned below platform/ground. feet_z={feet_z:.2f}, ground_z={ground_z:.2f}",
                )
            finally:
                game.destroy()

        self.assertEqual(
            len(set(spawn_positions)),
            1,
            msg=f"Spawn changed across runs for the same seed {seed}",
        )

        by_seed_positions = []
        for candidate_seed in range(8):
            game = MinecraftClone(capture_mouse=False, seed=candidate_seed)
            try:
                spawn = game.player_pos
                by_seed_positions.append((spawn.x, spawn.y, spawn.z))
            finally:
                game.destroy()

        self.assertGreater(
            len(set(by_seed_positions)),
            1,
            msg="Spawn is identical across different seeds; expected seed-based variation",
        )

    def test_chest_locations_are_seed_deterministic_and_grounded(self):
        seed = 24681357
        runs = 4
        chest_sets = []

        for _ in range(runs):
            game = MinecraftClone(capture_mouse=False, seed=seed)
            try:
                chest_sets.append(tuple(self.chest_keys(game)))
            finally:
                game.destroy()

        self.assertEqual(
            len(set(chest_sets)),
            1,
            msg=f"Chest locations changed across runs for seed {seed}",
        )

        game = MinecraftClone(capture_mouse=False, seed=seed)
        try:
            chests = self.chest_keys(game)
            self.assertGreaterEqual(len(chests), 1, msg="Expected at least one chest in the world")
            for x, y, z in chests:
                expected_y = game.terrain_height(x, z)
                self.assertEqual(
                    y,
                    expected_y,
                    msg=f"Chest at {(x, y, z)} is not above terrain surface (expected y={expected_y})",
                )
                self.assertIn(
                    (x, y - 1, z),
                    game.blocks,
                    msg=f"No supporting ground block under chest {(x, y, z)}",
                )
        finally:
            game.destroy()

        across_seed_chest_sets = []
        for candidate_seed in range(16):
            game = MinecraftClone(capture_mouse=False, seed=candidate_seed)
            try:
                across_seed_chest_sets.append(tuple(self.chest_keys(game)))
            finally:
                game.destroy()

        self.assertGreater(
            len(set(across_seed_chest_sets)),
            1,
            msg="Chest locations are identical across tested seeds; expected seed-based variation",
        )

    def test_log_texture_is_centered_per_block(self):
        game = MinecraftClone(capture_mouse=False, seed=1)
        try:
            # Hide 2D overlays so center pixel samples are unaffected by crosshair/text.
            game.aspect2d.hide()
            self.clear_world(game)

            end_texture = self.center_marker_texture(
                "log_end_centering_test",
                marker_rgb=(0.95, 0.95, 0.20),
                bg_rgb=(0.07, 0.07, 0.07),
            )
            side_texture = self.center_marker_texture(
                "log_side_centering_test",
                marker_rgb=(0.20, 0.85, 0.20),
                bg_rgb=(0.05, 0.05, 0.05),
            )

            game.block_textures["log"] = side_texture
            game.block_textures["log_end"] = end_texture
            game.log_model_template.removeNode()
            game.log_model_template = game.create_log_model_template()

            self.add_platform_under_logs(game, center_x=1, center_z=1, size=3, y=-1, block_type="stone")
            for x in range(3):
                for z in range(3):
                    key = (x, 0, z)
                    game.add_block(key, "log")
            game.collect_dirty_chunks(max(len(game.dirty_chunk_keys), 1))

            top_lens = OrthographicLens()
            top_lens.setFilmSize(4.0, 4.0)
            top_lens.setNearFar(-50, 50)
            game.cam.node().setLens(top_lens)
            game.camera.setPos(1.5, 1.5, 6.0)
            game.camera.setHpr(0, -90, 0)
            self.render_frames(game, frames=4)

            top_texture = game.win.getScreenshot()
            top_image = PNMImage()
            self.assertTrue(
                top_texture.store(top_image),
                msg="Failed to convert top-down screenshot texture to pixel image",
            )
            top_artifact_path = ARTIFACT_DIR / "log_top_alignment.png"
            self.assertTrue(top_image.write(str(top_artifact_path)))

            block_centers = []
            for x in range(3):
                for z in range(3):
                    px, py = self.world_to_pixel(
                        game,
                        top_lens,
                        top_image,
                        Point3(float(x) + 0.5, float(z) + 0.5, 1.0),
                    )
                    block_centers.append(self.pixel_luminance(top_image, px, py))

            shared_intersections = []
            for x in (1.0, 2.0):
                for z in (1.0, 2.0):
                    px, py = self.world_to_pixel(game, top_lens, top_image, Point3(x, z, 1.0))
                    shared_intersections.append(self.pixel_luminance(top_image, px, py))

            self.assertLess(
                max(block_centers) - min(block_centers),
                0.12,
                msg=f"Per-block top texture centers are inconsistent: {block_centers}",
            )
            self.assertGreater(
                min(block_centers),
                max(shared_intersections) + 0.15,
                msg=(
                    "Top log texture center is offset toward shared block intersections. "
                    f"centers={block_centers}, intersections={shared_intersections}"
                ),
            )

            self.clear_world(game)
            self.add_platform_under_logs(game, center_x=0, center_z=0, size=3, y=-1, block_type="stone")
            for y in range(3):
                key = (0, y, 0)
                game.add_block(key, "log")
            game.collect_dirty_chunks(max(len(game.dirty_chunk_keys), 1))

            side_lens = OrthographicLens()
            side_lens.setFilmSize(2.4, 4.0)
            side_lens.setNearFar(-50, 50)
            game.cam.node().setLens(side_lens)
            game.camera.setPos(0.5, -6.0, 1.5)
            game.camera.setHpr(0, 0, 0)
            self.render_frames(game, frames=4)

            side_texture_screenshot = game.win.getScreenshot()
            side_image = PNMImage()
            self.assertTrue(
                side_texture_screenshot.store(side_image),
                msg="Failed to convert side screenshot texture to pixel image",
            )
            side_artifact_path = ARTIFACT_DIR / "log_side_alignment.png"
            self.assertTrue(side_image.write(str(side_artifact_path)))

            vertical_centers = []
            for y in range(3):
                px, py = self.world_to_pixel(game, side_lens, side_image, Point3(0.5, 0.0, float(y) + 0.5))
                vertical_centers.append(self.pixel_luminance(side_image, px, py))

            vertical_boundaries = []
            for z in (1.0, 2.0):
                px, py = self.world_to_pixel(game, side_lens, side_image, Point3(0.5, 0.0, z))
                vertical_boundaries.append(self.pixel_luminance(side_image, px, py))

            self.assertLess(
                max(vertical_centers) - min(vertical_centers),
                0.12,
                msg=f"Per-block side texture centers are inconsistent by height: {vertical_centers}",
            )
            self.assertGreater(
                min(vertical_centers),
                max(vertical_boundaries) + 0.15,
                msg=(
                    "Side log texture center is offset vertically toward block boundaries. "
                    f"centers={vertical_centers}, boundaries={vertical_boundaries}"
                ),
            )
        finally:
            game.destroy()

    def test_log_on_block_on_platform_screenshot(self):
        game = MinecraftClone(capture_mouse=False, seed=1)
        try:
            game.aspect2d.hide()
            self.clear_world(game)

            center_x = 10
            center_z = 10
            self.add_platform_under_logs(game, center_x, center_z, size=9, y=-1, block_type="stone")
            game.add_block((center_x, 0, center_z), "stone")
            game.add_block((center_x, 1, center_z), "log")
            game.collect_dirty_chunks(max(len(game.dirty_chunk_keys), 1))

            target = game.block_key_to_world_center((center_x, 1, center_z)) + Vec3(0.5, 0.5, 0.5)
            game.camera.setPos(target + Vec3(-6.0, -8.0, 4.5))
            game.camera.lookAt(target)
            self.render_frames(game, frames=3)

            screenshot = game.win.getScreenshot()
            self.assertGreater(screenshot.getXSize(), 0)
            self.assertGreater(screenshot.getYSize(), 0)

            screenshot_path = ARTIFACT_DIR / "log_on_block_on_platform.png"
            wrote_file = screenshot.write(str(screenshot_path))
            self.assertTrue(wrote_file)
            self.assertTrue(screenshot_path.exists())
            self.assertGreater(screenshot_path.stat().st_size, 0)
        finally:
            game.destroy()

    def test_chest_on_block_on_platform_screenshot(self):
        game = MinecraftClone(capture_mouse=False, seed=1)
        try:
            game.aspect2d.hide()
            self.clear_world(game)

            center_x = 10
            center_z = 10
            self.add_platform_under_logs(game, center_x, center_z, size=9, y=-1, block_type="stone")
            game.add_block((center_x, 0, center_z), "stone")
            game.add_block((center_x, 1, center_z), "chest")
            game.collect_dirty_chunks(max(len(game.dirty_chunk_keys), 1))

            target = game.block_key_to_world_center((center_x, 1, center_z)) + Vec3(0.5, 0.5, 0.5)
            game.camera.setPos(target + Vec3(-6.0, -8.0, 4.5))
            game.camera.lookAt(target)
            self.render_frames(game, frames=3)

            screenshot = game.win.getScreenshot()
            self.assertGreater(screenshot.getXSize(), 0)
            self.assertGreater(screenshot.getYSize(), 0)

            screenshot_path = ARTIFACT_DIR / "chest_on_block_on_platform.png"
            wrote_file = screenshot.write(str(screenshot_path))
            self.assertTrue(wrote_file)
            self.assertTrue(screenshot_path.exists())
            self.assertGreater(screenshot_path.stat().st_size, 0)
        finally:
            game.destroy()

    def test_log_face_geometry_and_uv_are_centered_per_block(self):
        game = MinecraftClone(capture_mouse=False, seed=1)
        try:
            faces = game.log_model_template.findAllMatches("**/log_face_*")
            self.assertEqual(faces.getNumPaths(), 6, msg="Log model should have 6 textured faces")

            plane_keys = set()
            expected_uvs = {(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)}
            epsilon = 1e-4

            for face in faces:
                geom = face.node().getGeom(0)
                vdata = geom.getVertexData()
                vertex_reader = GeomVertexReader(vdata, "vertex")
                uv_reader = GeomVertexReader(vdata, "texcoord")
                transform = face.getMat(game.log_model_template)

                transformed = []
                while not vertex_reader.isAtEnd():
                    point = transform.xformPoint(vertex_reader.getData3f())
                    transformed.append((float(point[0]), float(point[1]), float(point[2])))

                uvs = []
                while not uv_reader.isAtEnd():
                    uv = uv_reader.getData2f()
                    uvs.append((float(uv[0]), float(uv[1])))

                xs = [value[0] for value in transformed]
                ys = [value[1] for value in transformed]
                zs = [value[2] for value in transformed]
                ranges = (
                    (min(xs), max(xs)),
                    (min(ys), max(ys)),
                    (min(zs), max(zs)),
                )

                fixed_axes = [index for index, axis_range in enumerate(ranges) if abs(axis_range[1] - axis_range[0]) <= epsilon]
                self.assertEqual(len(fixed_axes), 1, msg=f"Face {face.getName()} is not planar on one block boundary")
                fixed_axis = fixed_axes[0]
                fixed_value = ranges[fixed_axis][0]
                self.assertTrue(
                    min(abs(fixed_value - 0.0), abs(fixed_value - 1.0)) <= epsilon,
                    msg=f"Face {face.getName()} is not aligned to 0 or 1 boundary (value={fixed_value:.4f})",
                )

                for axis_index, axis_range in enumerate(ranges):
                    if axis_index == fixed_axis:
                        continue
                    self.assertTrue(
                        abs(axis_range[0] - 0.0) <= epsilon and abs(axis_range[1] - 1.0) <= epsilon,
                        msg=f"Face {face.getName()} extents are not aligned in block space: {axis_range}",
                    )

                rounded_uvs = {(round(u, 4), round(v, 4)) for u, v in uvs}
                self.assertEqual(
                    rounded_uvs,
                    expected_uvs,
                    msg=f"Face {face.getName()} UVs are offset; expected full 0..1 mapping",
                )

                plane_keys.add((fixed_axis, round(fixed_value, 4)))

            expected_planes = {
                (0, 0.0),
                (0, 1.0),
                (1, 0.0),
                (1, 1.0),
                (2, 0.0),
                (2, 1.0),
            }
            self.assertEqual(
                plane_keys,
                expected_planes,
                msg=f"Log faces are not aligned to all six block boundary planes: {plane_keys}",
            )
        finally:
            game.destroy()

    def test_camera_does_not_clip_into_wall_in_test_environment(self):
        platform_size = 8
        platform_level = 0
        wall_side_z = platform_size - 1

        game = MinecraftClone(capture_mouse=False)
        try:
            self.clear_world(game)

            for x in range(platform_size):
                for z in range(platform_size):
                    game.add_block((x, platform_level, z), "stone")

            for x in range(platform_size):
                game.add_block((x, platform_level + 1, wall_side_z), "dirt")
                game.add_block((x, platform_level + 2, wall_side_z), "dirt")

            game.collect_dirty_chunks(max(len(game.dirty_chunk_keys), 1))

            game.player_pos = Vec3(platform_size / 2 - 0.5, 2.0, 3.0)
            game.player_velocity_z = 0.0
            game.yaw = 0.0
            game.pitch = 0.0
            game.update_player_model()
            game.update_camera()
            self.render_frames(game)

            start_path = ARTIFACT_DIR / "camera_wall_start.png"
            at_wall_path = ARTIFACT_DIR / "camera_wall_at_wall.png"

            self.assertTrue(game.win.getScreenshot().write(str(start_path)))
            self.assertTrue(start_path.exists())
            self.assertGreater(start_path.stat().st_size, 0)

            game.set_key("w", True)
            self.step_world(game, frames=240)
            game.set_key("w", False)
            self.render_frames(game)

            self.assertTrue(game.win.getScreenshot().write(str(at_wall_path)))
            self.assertTrue(at_wall_path.exists())
            self.assertGreater(at_wall_path.stat().st_size, 0)

            camera_pos = game.camera.getPos(game.render)
            camera_key = game.world_to_block_key(camera_pos.x, camera_pos.y, camera_pos.z)
            self.assertNotIn(
                camera_key,
                game.blocks,
                msg=f"Camera entered a solid block at {camera_key} with position {camera_pos}",
            )

            first_hit_distance = self.distance_to_first_block_ahead(game)
            near_clip_distance = game.camLens.getNear()

            self.assertIsNotNone(first_hit_distance, msg="No wall block detected ahead of the camera")
            self.assertGreaterEqual(
                first_hit_distance,
                near_clip_distance,
                msg=(
                    "Camera is too close to the wall for current near clip. "
                    f"hit={first_hit_distance:.2f}, near={near_clip_distance:.2f}"
                ),
            )
        finally:
            game.destroy()

    def test_player_does_not_teleport_up_under_reverse_l_overhang(self):
        platform_size = 12
        platform_level = 0
        wall_row_z = platform_size - 2
        wall_start_x = 4
        wall_end_x = 8

        game = MinecraftClone(capture_mouse=False)
        try:
            self.clear_world(game)

            for x in range(platform_size):
                for z in range(platform_size):
                    game.add_block((x, platform_level, z), "stone")

            for x in range(wall_start_x, wall_end_x):
                game.add_block((x, platform_level + 1, wall_row_z), "dirt")
                game.add_block((x, platform_level + 2, wall_row_z), "dirt")
                game.add_block((x, platform_level + 3, wall_row_z), "dirt")

            for x in range(wall_start_x, wall_end_x):
                for z in (wall_row_z - 1, wall_row_z - 2, wall_row_z - 3):
                    game.add_block((x, platform_level + 4, z), "dirt")

            game.collect_dirty_chunks(max(len(game.dirty_chunk_keys), 1))

            game.player_pos = Vec3((wall_start_x + wall_end_x) / 2.0, 3.0, 3.0)
            game.player_velocity_z = 0.0
            game.yaw = 0.0
            game.pitch = 0.0
            game.update_player_model()
            game.update_camera()
            self.step_world(game, frames=10)
            self.render_frames(game)

            start_path = ARTIFACT_DIR / "reverse_l_overhang_start.png"
            under_path = ARTIFACT_DIR / "reverse_l_overhang_under.png"

            self.assertTrue(game.win.getScreenshot().write(str(start_path)))
            self.assertTrue(start_path.exists())
            self.assertGreater(start_path.stat().st_size, 0)

            start_height = game.player_pos.z
            start_block_vertical_y = game.world_to_block_key(
                game.player_pos.x, game.player_pos.y, game.player_pos.z
            )[1]

            game.set_key("w", True)
            self.step_world(game, frames=55)
            game.set_key("w", False)
            self.render_frames(game)

            self.assertTrue(game.win.getScreenshot().write(str(under_path)))
            self.assertTrue(under_path.exists())
            self.assertGreater(under_path.stat().st_size, 0)

            end_height = game.player_pos.z
            end_block_vertical_y = game.world_to_block_key(
                game.player_pos.x, game.player_pos.y, game.player_pos.z
            )[1]

            self.assertGreaterEqual(
                game.player_pos.y,
                wall_row_z - 3.5,
                msg="Player did not reach the reverse-L overhang area",
            )
            self.assertLessEqual(
                end_height,
                start_height + 0.25,
                msg=(
                    "Player teleported upward while moving under overhang. "
                    f"start_z={start_height:.2f}, end_z={end_height:.2f}"
                ),
            )
            self.assertLessEqual(
                end_block_vertical_y,
                start_block_vertical_y,
                msg=(
                    "Player block vertical y increased under overhang. "
                    f"start_y={start_block_vertical_y}, end_y={end_block_vertical_y}"
                ),
            )
        finally:
            game.destroy()

    def test_player_cannot_phase_up_through_low_overhang_when_jumping(self):
        platform_size = 12
        platform_level = 0
        wall_row_z = platform_size - 2
        wall_start_x = 4
        wall_end_x = 8

        game = MinecraftClone(capture_mouse=False)
        try:
            self.clear_world(game)

            for x in range(platform_size):
                for z in range(platform_size):
                    game.add_block((x, platform_level, z), "stone")

            for x in range(wall_start_x, wall_end_x):
                game.add_block((x, platform_level + 1, wall_row_z), "dirt")
                game.add_block((x, platform_level + 2, wall_row_z), "dirt")
                game.add_block((x, platform_level + 3, wall_row_z), "dirt")

            # Low overhang: underside is at player head height when standing on the platform.
            for x in range(wall_start_x, wall_end_x):
                for z in (wall_row_z - 1, wall_row_z - 2, wall_row_z - 3):
                    game.add_block((x, platform_level + 3, z), "dirt")

            game.collect_dirty_chunks(max(len(game.dirty_chunk_keys), 1))

            game.player_pos = Vec3((wall_start_x + wall_end_x) / 2.0, wall_row_z - 2.2, 3.0)
            game.player_velocity_z = 0.0
            game.yaw = 0.0
            game.pitch = 0.0
            game.update_player_model()
            game.update_camera()
            self.step_world(game, frames=8)
            self.render_frames(game)

            start_path = ARTIFACT_DIR / "low_overhang_jump_start.png"
            jump_path = ARTIFACT_DIR / "low_overhang_jump_after.png"

            self.assertTrue(game.win.getScreenshot().write(str(start_path)))
            self.assertTrue(start_path.exists())
            self.assertGreater(start_path.stat().st_size, 0)

            start_height = game.player_pos.z
            start_block_vertical_y = game.world_to_block_key(
                game.player_pos.x, game.player_pos.y, game.player_pos.z
            )[1]

            game.try_jump()

            max_height_during_jump = game.player_pos.z
            max_block_vertical_y = start_block_vertical_y
            for _ in range(40):
                self.step_world(game, frames=1)
                max_height_during_jump = max(max_height_during_jump, game.player_pos.z)
                current_block_vertical_y = game.world_to_block_key(
                    game.player_pos.x, game.player_pos.y, game.player_pos.z
                )[1]
                max_block_vertical_y = max(max_block_vertical_y, current_block_vertical_y)

            self.render_frames(game)

            self.assertTrue(game.win.getScreenshot().write(str(jump_path)))
            self.assertTrue(jump_path.exists())
            self.assertGreater(jump_path.stat().st_size, 0)

            self.assertLessEqual(
                max_height_during_jump,
                start_height + 0.20,
                msg=(
                    "Player phased upward through low overhang while jumping. "
                    f"start_z={start_height:.2f}, max_z={max_height_during_jump:.2f}"
                ),
            )
            self.assertLessEqual(
                max_block_vertical_y,
                start_block_vertical_y,
                msg=(
                    "Player moved into a higher vertical block layer under low overhang. "
                    f"start_y={start_block_vertical_y}, max_y={max_block_vertical_y}"
                ),
            )
        finally:
            game.destroy()
