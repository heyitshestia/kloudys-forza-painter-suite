from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MethodType, SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / 'src'), str(UI.parent)]
from kfps_ui.community_gallery_service import CommunityGalleryService, utc_schedule, png_thumbnail
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage


def solid_png(color):
    image = QImage(160, 100, QImage.Format_RGB32)
    image.fill(color)
    output = QBuffer()
    output.open(QIODevice.WriteOnly)
    image.save(output, 'PNG')
    return bytes(output.data())


class GalleryLiveryCoverTests(unittest.TestCase):
    def test_upload_keeps_game_cover_with_zero_through_three_photos(self):
        cover = solid_png('blue')
        for count in range(4):
            with self.subTest(count=count):
                service = SimpleNamespace(busy=False, community=Mock(_app_version='3.1.91'), _call=Mock(),
                    _pending=dict(kind='livery', payload=b'package', preview=cover, photos=[solid_png('red')] * count))
                CommunityGalleryService.publish(service, dict(title='Car', rights=True))
                service._call.call_args.args[0]()
                path, metadata, files = service.community.sessionClient().multipart.call_args.args
                self.assertEqual(path, 'liveries')
                self.assertEqual(metadata['photo_count'], count)
                self.assertEqual(files['preview'][1], png_thumbnail(cover, 900, 700))
                self.assertEqual(files['thumbnail'][1], png_thumbnail(files['preview'][1]))
                self.assertEqual(len([key for key in files if key.startswith('photo')]), count)

    def test_missing_cover_and_four_photos_do_not_send(self):
        for cover, photos in ((b'', []), (solid_png('blue'), [b'p'] * 4)):
            service = SimpleNamespace(busy=False, community=Mock(_app_version='3.1.91'), _call=Mock(),
                _pending=dict(kind='livery', payload=b'package', preview=cover, photos=photos))
            CommunityGalleryService.publish(service, dict(title='Car', rights=True))
            with self.assertRaises(ValueError): service._call.call_args.args[0]()
            service.community.sessionClient().multipart.assert_not_called()

    def test_cover_is_first_media_with_zero_through_three_extras(self):
        for count in range(4):
            record = dict(preview_url='game-cover', photo_urls=[f'photo{i}' for i in range(count)])
            service = SimpleNamespace(_selected=dict(id='car', kind='livery', locked=False),
                _records={'car': record}, authenticated=True, _image_url=lambda r, k, p, *args: p)
            CommunityGalleryService._selected_media(service)
            self.assertEqual(service._selected['previewUrl'], 'game-cover')
            self.assertEqual(service._selected['photoUrls'], ['game-cover'] + record['photo_urls'])
        service._selected['locked'] = True
        service._selected['photoUrls'] = []
        CommunityGalleryService._selected_media(service)
        self.assertEqual(service._selected['photoUrls'], [])

    def test_livery_tab_query_and_exit_keep_filters_consistent(self):
        service = SimpleNamespace(_scope='Timed Releases', refresh=Mock(), _filters=dict(
            kind='vinyl', sort='Newest', creator='', search='', game='All', category='All',
            classification='All', supporters=False))
        CommunityGalleryService.filter(service, 'scope', 'Livery')
        query = parse_qs(urlparse(CommunityGalleryService._path(service, 2)).query)
        self.assertEqual(query['scope'], ['browse'])
        self.assertEqual(query['kind'], ['livery'])
        self.assertEqual(query['page'], ['2'])
        creator = parse_qs(urlparse(CommunityGalleryService._path(service, 1, 'Artist')).query)
        self.assertNotIn('kind', creator)
        CommunityGalleryService.filter(service, 'scope', 'Browse')
        self.assertEqual(service._filters['kind'], 'All')
        CommunityGalleryService.filter(service, 'scope', 'Livery')
        CommunityGalleryService.filter(service, 'kind', 'vinyl')
        self.assertEqual(service._scope, 'Browse')

    def test_legacy_cover_is_not_repeated_as_an_extra_photo(self):
        record = dict(preview_url='cover', photo_urls=['photo0'], cover_is_first_photo=True)
        service = SimpleNamespace(_selected=dict(id='car', kind='livery', locked=False),
            _records={'car': record}, authenticated=True, _image_url=lambda r, k, p, *args: p)
        CommunityGalleryService._selected_media(service)
        self.assertEqual(service._selected['photoUrls'], ['photo0'])
        service.authenticated = False
        CommunityGalleryService._selected_media(service)
        self.assertEqual(service._selected['photoUrls'], ['cover'])

    def test_tab_order_and_bilingual_optional_photo_copy(self):
        qml = (UI / 'qml/community-preview/CommunityPreview.qml').read_text(encoding='utf-8')
        self.assertLess(qml.index('key:"Timed Releases"'), qml.index('key:"Livery"'))
        self.assertLess(qml.index('key:"Livery"'), qml.index('key:"Favorites"'))
        upload = (UI / 'qml/community-preview/PreviewUpload.qml').read_text(encoding='utf-8')
        self.assertIn('Additional photos (optional, up to 3)', upload)
        self.assertIn('추가 사진 (선택, 최대 3장)', upload)


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
