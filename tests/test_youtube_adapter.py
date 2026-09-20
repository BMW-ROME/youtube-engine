import unittest
from unittest.mock import patch

from control_plane.core.youtube_adapter import run_youtube_production


class YoutubeAdapterTests(unittest.TestCase):
    @patch("control_plane.core.youtube_adapter.run_pipeline")
    def test_adapter_preserves_pipeline_result_contract(self, mock_run):
        from core.pipeline import PipelineResult

        mock_run.return_value = PipelineResult(
            topic="test",
            channel_codename="finance",
            video_id=123,
            script="script",
            voice_path=None,
            music_path=None,
            image_paths=[],
            thumbnail_path=None,
            effect_clip_paths=[],
            final_video_path=None,
            chapter_markers=[],
            seo_result=None,
            shorts_paths=[],
            upload_result=None,
            failed_stages=[],
        )

        result = run_youtube_production(topic="test", channel_codename="finance")
        self.assertTrue(result["success"])
        self.assertEqual(result["video_id"], 123)
        mock_run.assert_called_once()
