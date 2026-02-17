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
