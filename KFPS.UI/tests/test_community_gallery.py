from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MethodType, SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / 'src'), str(UI.parent)]
from kfps_ui.community_gallery_service import CommunityGalleryService, utc_schedule


class GalleryLifecycleTests(unittest.TestCase):
    def test_closing_while_downloading_cannot_reopen_renderer(self):
        selected = {'id': 'test', 'kind': 'livery'}
        service = SimpleNamespace(busy=False, _selected=selected, _records={'test': selected},
                                  community=Mock(), _render_session=None, _render_id='',
                                  _render_generation=0, _call=Mock(), root=Path('.'), repo=Path('.'))
        service.closeRender = MethodType(CommunityGalleryService.closeRender, service)
        CommunityGalleryService.openRender(service)
        callback = service._call.call_args.args[1]
        service.closeRender()
        with patch('kfps_ui.community_preview_livery.PreviewLiverySession') as renderer:
            callback(b'completed after closing')
            renderer.assert_not_called()
        self.assertIsNone(service._render_session)

    def test_repeated_close_stops_renderer_once(self):
        renderer = Mock()
        service = SimpleNamespace(_render_session=renderer, _render_id='test', _render_generation=0,
                                  renderChanged=Mock(), renderClosed=Mock())
        CommunityGalleryService.closeRender(service)
        CommunityGalleryService.closeRender(service)
        renderer.close.assert_called_once()
        self.assertEqual(service._render_generation, 2)

    def test_schedule_has_utc_dates_and_disabling_removes_both(self):
        start = datetime.now(timezone(timedelta(hours=9))) + timedelta(hours=1)
        result = utc_schedule({'timed': True, 'starts': start.isoformat(),
                               'ends': (start + timedelta(hours=3)).isoformat()})
        self.assertTrue(all(value.endswith('Z') for value in result.values()))
        self.assertAlmostEqual(datetime.fromisoformat(result['starts_at']).timestamp(), start.timestamp(), places=2)
        self.assertEqual(utc_schedule({'timed': False}), {'starts_at': None, 'ends_at': None})

    def test_invalid_schedule_fails_before_upload(self):
        with self.assertRaises(ValueError):
            utc_schedule({'timed': True, 'starts': '2020-01-01T10:00Z', 'ends': '2020-01-01T09:00Z'})


if __name__ == '__main__':
    unittest.main()
