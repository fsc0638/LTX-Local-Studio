import tempfile
import unittest
from pathlib import Path

import av
import numpy as np

from scripts.check_output import check_output


def create_video(path, frames=9, width=256, height=256, fps=24, black=False):
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=fps)
        stream.width, stream.height, stream.pix_fmt = width, height, "yuv420p"
        for index in range(frames):
            pixels = np.zeros((height, width, 3), dtype=np.uint8)
            if not black:
                pixels[:] = (30 + index * 15) % 220
                pixels[:, (index * 13) % width:((index * 13) % width) + 20, 0] = 240
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fixture.mp4"
        self.expected = dict(frames=9, width=256, height=256, fps=24, audio=False)

    def tearDown(self):
        self.temp.cleanup()

    def test_full_decode_matches_dimensions_timing_and_frames(self):
        create_video(self.path)
        result = check_output(self.path, self.expected)
        self.assertTrue(result["quality_control"]["passed"], result)
        self.assertEqual(result["measured_media"]["frames"], 9)
        self.assertAlmostEqual(result["measured_media"]["video_seconds"], 9 / 24)
        self.assertEqual(result["measured_media"]["measurement"], "full_decode")

    def test_corrupt_file_fails(self):
        self.path.write_bytes(b"not an mp4")
        self.assertIn("decode_failed", check_output(self.path, self.expected)["quality_control"]["errors"])

    def test_frame_dimension_fps_and_missing_audio_mismatch(self):
        create_video(self.path)
        for changed, error in (({"frames": 17}, "frame_count_mismatch"),
                               ({"width": 512}, "dimension_mismatch"), ({"fps": 30}, "fps_mismatch"),
                               ({"audio": True}, "missing_audio_stream")):
            result = check_output(self.path, {**self.expected, **changed})
            self.assertFalse(result["measured_media"]["verified"])
            self.assertIn(error, result["quality_control"]["errors"])

    def test_visual_warnings_do_not_claim_creative_failure(self):
        create_video(self.path, black=True)
        report = check_output(self.path, self.expected)["quality_control"]
        self.assertTrue(report["passed"])
        self.assertTrue(report["visual_review_required"])
        self.assertIn("near_black_frames_detected", report["warnings"])
        self.assertIn("near_static_frames_detected", report["warnings"])
