from pathlib import Path
import unittest

from panda3d.core import Vec3, loadPrcFileData

loadPrcFileData("", "window-type offscreen")
loadPrcFileData("", "audio-library-name null")
loadPrcFileData("", "show-frame-rate-meter #f")
loadPrcFileData("", "win-size 960 540")
loadPrcFileData("", "sync-video #f")

from main import CHUNK_COLLECTS_PER_FRAME, MinecraftClone

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
