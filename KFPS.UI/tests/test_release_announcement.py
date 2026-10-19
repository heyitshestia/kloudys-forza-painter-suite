import concurrent.futures
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.kfps_release_announcement import ReleaseAnnouncement, publication_metadata
from tools import kfps_display_language

NOW = 1767225600.0
RUN = ROOT / 'runtime/test-runs/release-announcement-unit'


def contender(root, content, ready, start, output):
    service = ReleaseAnnouncement(Path(root), state_root=Path(root) / 'state',
        content_path=Path(content), clock=lambda: NOW + 10, language='en')
    ready.put(True)
    start.wait(10)
    output.put(service.dispatch({'action': 'claim', 'client': os.urandom(16).hex()}))


class AnnouncementTests(unittest.TestCase):
    def setUp(self):
        RUN.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=RUN)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.content = self.root / 'notice.json'
        self.data = json.loads((ROOT / 'KFPS.UI/content/release-announcement.json').read_text(encoding='utf-8'))
        self.data.update(publication_metadata('test-release', '2026-01-01T00:00:00Z'))
        self.write()
        self.now = NOW + 10
        self.opened = []
        self.service = self.make()

    def write(self):
        self.content.write_text(json.dumps(self.data), encoding='utf-8')

    def make(self, **kw):
        return ReleaseAnnouncement(self.root, state_root=self.root / 'state', content_path=self.content,
            clock=lambda: self.now, language=kw.pop('language', 'en'), opener=self.opened.append, **kw)

    def claim(self, service=None, client='a' * 32):
        return (service or self.service).dispatch({'action': 'claim', 'client': client})

    def test_source_schedule_is_unpublished_or_valid(self):
        data = json.loads((ROOT / 'KFPS.UI/content/release-announcement.json').read_text(encoding='utf-8'))
        if data['releaseId'] is None:
            self.assertIsNone(data['publishedAt'])
            self.assertIsNone(data['expiresAt'])
        else:
            expected = publication_metadata(data['releaseId'], data['publishedAt'])
            self.assertEqual({key:data[key] for key in expected}, expected)

    def test_activity_disclosure_and_approved_closing_are_preserved(self):
        required = {
            'en': ('not people', 'on by default', 'KFPS Settings', 'without losing any features'),
            'ko': ('사람 수가 아니라', '기본으로 켜져', 'KFPS 설정', '모든 기능을 그대로'),
            'ja': ('人数ではなく', '初期設定ではオン', 'KFPSの設定', 'すべての機能をそのまま'),
        }
        for locale, terms in required.items():
            text = '\n'.join(block['text'] for block in self.data['locales'][locale]['blocks'])
            for term in terms:
                self.assertIn(term, text)
        self.assertEqual(self.data['locales']['en']['closing'],
                         'Now go make something worth showing off. Crash out.')

    def test_publication_window_is_exact_and_not_install_relative(self):
        self.now = NOW - .01
        self.assertFalse(self.claim()['eligible'])
        self.now = NOW
        self.assertTrue(self.claim()['eligible'])
        self.now = NOW + 604800
        self.assertFalse(self.claim()['eligible'])
        self.assertFalse(self.make().dispatch({'action': 'status'})['eligible'])

    def test_late_first_launch_does_not_write_state(self):
        self.now = NOW + 604800 + 1
        self.assertFalse(self.claim()['eligible'])
        self.assertFalse((self.root / 'state').exists())

    def test_unpublished_and_invalid_schedule_do_not_write(self):
        for expiry in (None, '2026-01-09T00:00:00Z', 'tomorrow'):
            self.data['expiresAt'] = expiry
            self.write()
            self.assertFalse(self.claim(self.make())['eligible'])
        self.assertFalse((self.root / 'state').exists())

    def test_claim_is_not_consumption(self):
        result = self.claim()
        self.assertIn('token', result)
        self.assertFalse(self.service.dispatch({'action': 'status'})['acknowledged'])
        self.assertEqual(self.opened, [])

    def test_presented_is_idempotent_and_shared(self):
        result = self.claim()
        action = {'action': 'presented', 'token': result['token']}
        self.assertTrue(self.service.dispatch(action)['acknowledged'])
        self.assertTrue(self.service.dispatch(action)['acknowledged'])
        self.assertNotIn('token', self.claim(self.make(), 'b' * 32))

    def test_competing_hosts_get_one_claim(self):
        services = [self.make() for _ in range(12)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            rows = list(pool.map(lambda pair: self.claim(pair[1], f'{pair[0]:032x}'), enumerate(services)))
        self.assertEqual(sum('token' in row for row in rows), 1)

    def test_process_race_gets_one_claim(self):
        context = multiprocessing.get_context('spawn')
        ready, start, output = context.Queue(), context.Event(), context.Queue()
        children = [context.Process(target=contender, args=(str(self.root), str(self.content), ready, start, output)) for _ in range(4)]
        try:
            for child in children:
                child.start()
            for _ in children:
                ready.get(timeout=15)
            start.set()
            rows = [output.get(timeout=15) for _ in children]
            self.assertEqual(sum('token' in row for row in rows), 1)
        finally:
            for child in children:
                child.join(10)
                if child.is_alive():
                    child.terminate()
                    child.join(5)

    def test_release_and_interrupted_claim_can_be_retried(self):
        first = self.claim()
        self.service.dispatch({'action': 'release', 'token': first['token']})
        second = self.claim(self.make(), 'b' * 32)
        self.assertIn('token', second)
        self.now += 31
        self.assertIn('token', self.claim(self.make(), 'c' * 32))
        self.assertFalse(self.service.dispatch({'action': 'presented', 'token': first['token']})['acknowledged'])

    def test_claim_retry_is_stable_and_shutdown_releases(self):
        first = self.claim()
        self.assertEqual(first['token'], self.claim()['token'])
        self.service.close()
        self.assertIn('token', self.claim(self.make(), 'b' * 32))

    def test_expired_claim_cannot_acknowledge_or_open_support(self):
        claim = self.claim()
        self.now = NOW + 604800
        self.assertFalse(self.service.dispatch({'action': 'presented', 'token': claim['token']})['acknowledged'])
        self.service.dispatch({'action': 'support', 'token': claim['token']})
        self.assertEqual(self.opened, [])

    def test_only_explicit_valid_support_action_opens_fixed_url(self):
        claim = self.claim()
        self.service.dispatch({'action': 'presented', 'token': claim['token']})
        self.assertEqual(self.opened, [])
        self.service.dispatch({'action': 'support', 'token': '0' * 48})
        self.assertEqual(self.opened, [])
        self.service.dispatch({'action': 'support', 'token': claim['token']})
        self.assertEqual(self.opened, ['https://ko-fi.com/O7O020EQNQ'])

    def test_release_ids_do_not_consume_other_releases(self):
        first = self.claim()
        self.service.dispatch({'action': 'presented', 'token': first['token']})
        self.data['releaseId'] = 'next-release'
        self.write()
        self.assertIn('token', self.claim(self.make()))

    def test_language_is_system_derived_not_saved_settings(self):
        for language in ('ko', 'ja', 'de', 'en'):
            with self.subTest(language=language):
                service = self.make(language=language)
                row = self.claim(service)
                self.assertEqual(row['locale'], language if language in ('ko', 'ja') else 'en')
                service.close()

    def test_status_excludes_text_and_tokens(self):
        self.claim()
        status = self.service.dispatch({'action': 'status'})
        self.assertEqual(set(status), {'releaseId','publishedAt','expiresAt','locale','acknowledged','eligible'})

    def test_status_is_read_only_for_new_install(self):
        self.assertTrue(self.service.read_status()['eligible'])
        self.assertFalse((self.root / 'state').exists())

    def test_support_before_presentation_does_not_open(self):
        claim = self.claim()
        self.service.dispatch({'action': 'support', 'token': claim['token']})
        self.assertEqual(self.opened, [])

    def test_locale_follows_windows_display_language_api(self):
        class GetLanguage:
            def __init__(self, value): self.value = value
            def __call__(self): return self.value
        for language_id, expected in ((0x0412, 'ko'), (0x0812, 'ko'), (0x0411, 'ja'), (0x0409, 'en'), (0x0407, 'en')):
            getter = GetLanguage(language_id)
            with patch.object(kfps_display_language.sys, 'platform', 'win32'), patch.object(
                    kfps_display_language.ctypes, 'WinDLL', return_value=SimpleNamespace(GetUserDefaultUILanguage=getter)):
                self.assertEqual(kfps_display_language.display_language(), expected)
                self.assertEqual(kfps_display_language.is_korean_display_language(), expected == 'ko')

    def test_existing_ack_survives_restart_and_expiry(self):
        claim = self.claim()
        self.service.dispatch({'action': 'presented', 'token': claim['token']})
        self.service.close()
        self.now = NOW + 604801
        row = self.make().read_status()
        self.assertTrue(row['acknowledged'])
        self.assertFalse(row['eligible'])

    def test_unrelated_token_cannot_acknowledge_or_release(self):
        first = self.claim()
        for action in ('presented', 'release'):
            row = self.make().dispatch({'action': action, 'token': first['token']})
            self.assertFalse(row['acknowledged'])
        self.assertNotIn('token', self.claim(self.make(), 'b' * 32))

    def test_changed_expiry_and_oversize_content_fail_closed(self):
        self.data['expiresAt'] = '2026-01-07T23:59:59Z'
        self.write()
        self.assertFalse(self.make().read_status()['eligible'])
        self.content.write_bytes(b' ' * 65537)
        self.assertFalse(self.make().read_status()['eligible'])

    def test_support_open_failure_does_not_break_dismissal(self):
        def fail(_): raise OSError('test')
        self.service.opener = fail
        claim = self.claim()
        self.service.dispatch({'action': 'presented', 'token': claim['token']})
        self.assertTrue(self.service.dispatch({'action': 'support', 'token': claim['token']})['acknowledged'])

    def test_malformed_state_shapes_are_preserved(self):
        self.claim()
        path = next((self.root / 'state').glob('*.json'))
        for value in ([], {}, {'seen': False}, {'version': 2}, {'until': float('inf')}):
            raw = json.dumps(value).encode()
            path.write_bytes(raw)
            self.assertFalse(self.make().read_status()['eligible'])
            self.assertNotIn('token', self.claim(self.make(), 'b' * 32))
            self.assertEqual(path.read_bytes(), raw)

    def test_deep_or_non_utf8_optional_content_never_blocks_startup(self):
        for raw in (b'[' * 1500 + b'0' + b']' * 1500, b'\xff'):
            self.content.write_bytes(raw)
            self.assertFalse(self.make().read_status()['eligible'])

    def test_deep_or_non_utf8_state_preserved(self):
        self.claim()
        path = next((self.root / 'state').glob('*.json'))
        for raw in (b'[' * 1000 + b'0' + b']' * 1000, b'\xff'):
            path.write_bytes(raw)
            self.assertFalse(self.make().read_status()['eligible'])
            self.assertNotIn('token', self.claim(self.make()))
            self.assertEqual(path.read_bytes(), raw)

    def test_invalid_requests_rejected(self):
        for body in ({}, [], {'action': 'claim', 'client': '../oops'}, {'action': 'claim','client':'a'*32,'root':'x'},
                     {'action': 'status', 'language':'ko'}, {'action': 'presented','token':1}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.service.dispatch(body)

    def test_corrupt_state_is_preserved(self):
        self.claim()
        path = next((self.root / 'state').glob('*.json'))
        path.write_bytes(b'not json')
        self.assertNotIn('token', self.claim(self.make(), 'b' * 32))
        self.assertEqual(path.read_bytes(), b'not json')

    def test_hardlinked_state_is_never_replaced(self):
        self.claim()
        path = next((self.root / 'state').glob('*.json'))
        other = self.root / 'unrelated.json'
        os.link(path, other)
        before = other.read_bytes()
        self.assertNotIn('token', self.claim(self.make(), 'b' * 32))
        self.assertEqual(other.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
