"""Boundary and failure tests for the opt-in browser host."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'KFPS.Editor/src'))
from kfps_editor.browser_page import allowed_request, browser_executable, BrowserPage, window_for_process
from kfps_editor.browser_host import BrowserDesktop


class BrowserBoundaries(unittest.TestCase):
    def test_window_selection_ignores_owned_popups_and_tooltips(self):
        user = Mock()
        user.EnumWindows.side_effect = lambda callback, _: [callback(h, 0) for h in (1, 2, 3, 4)]
        def owner(hwnd, pointer):
            pointer._obj.value = 99 if hwnd != 4 else 100
        def name(hwnd, buffer, size):
            buffer.value = 'Chrome_WidgetWin_1'
        user.GetWindowThreadProcessId.side_effect = owner
        user.GetClassNameW.side_effect = name
        user.IsWindowVisible.return_value = True
        user.GetWindow.side_effect = lambda hwnd, _: 1 if hwnd == 2 else 0
        user.GetWindowLongW.side_effect = lambda hwnd, _: 0x80 if hwnd == 3 else 0
        with patch('kfps_editor.browser_page.ctypes.WinDLL', return_value=user):
            self.assertEqual(window_for_process(99), 1)
            user.GetWindow.side_effect = lambda hwnd, _: 0
            self.assertIsNone(window_for_process(99))

    def test_close_restores_browser_without_overriding_background_request(self):
        host=Mock(_background=True)
        BrowserDesktop._request_browser_close(host)
        host.present_window.assert_called_once_with(background=True)
        host.close.assert_called_once()

    def test_primary_page_destroyed_closes_hidden_host(self):
        page=Mock(target='owned',disposing=False)
        BrowserPage._message(page,json.dumps({'method':'Target.targetDestroyed','params':{'targetId':'other'}}))
        page.closed.emit.assert_not_called()
        BrowserPage._message(page,json.dumps({'method':'Target.targetDestroyed','params':{'targetId':'owned'}}))
        page.closed.emit.assert_called_once()
        page.disposing=True
        BrowserPage._message(page,json.dumps({'method':'Target.targetDestroyed','params':{'targetId':'owned'}}))
        page.closed.emit.assert_called_once()

    def test_navigation_and_resource_scope(self):
        origin='http://127.0.0.1:32123'
        for url in ('about:blank', origin+'/tools/fabric-editor/index.html?project=x#session=y'):
            self.assertTrue(allowed_request(url,origin,True))
        for url in (origin+'/editor.js', 'blob:'+origin+'/123', 'data:image/png;base64,abc'):
            self.assertTrue(allowed_request(url,origin))
        for url in ('https://example.com/',origin+'.evil.test/a','http://127.0.0.1:32124/a',
                    'file:///C:/Users/user/file.txt','http://127.0.0.1:32123@evil.test/a'):
            self.assertFalse(allowed_request(url,origin))
            self.assertFalse(allowed_request(url,origin,True))
        for url in (origin+'/api/fabric-editor/preferences','data:text/html,abc','file:///a'):
            self.assertFalse(allowed_request(url,origin,True))

    def test_missing_browser_is_explicit(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'Google Chrome was not found'):
                browser_executable()

    def test_edge_is_never_a_fallback(self):
        with patch.dict('os.environ', {'ProgramFiles': 'C:/Programs', 'ProgramFiles(x86)': 'C:/Programs32'}, clear=True), \
             patch.object(Path, 'is_file', side_effect=lambda p: p.name == 'msedge.exe', autospec=True):
            with self.assertRaisesRegex(RuntimeError, 'Google Chrome was not found'):
                browser_executable()

    def test_chrome_per_user_and_machine_installations(self):
        variables = {'LocalAppData': 'C:/UserLocal', 'ProgramFiles': 'C:/Programs', 'ProgramFiles(x86)': 'C:/Programs32'}
        for variable in variables:
            expected = Path(variables[variable]) / 'Google/Chrome/Application/chrome.exe'
            with self.subTest(variable=variable), patch.dict('os.environ', variables, clear=True), \
                 patch.object(Path, 'is_file', side_effect=lambda p: p == expected, autospec=True):
                self.assertEqual(browser_executable(), expected)

    def test_browser_failure_keeps_host_ownership(self):
        host=Mock(_stopped=False)
        host.page.dispose.side_effect=RuntimeError('still alive')
        with patch('kfps_editor.browser_host.record_startup'), patch('kfps_editor.host.EditorDesktop.shutdown') as parent:
            self.assertFalse(BrowserDesktop.shutdown(host))
            parent.assert_not_called()

    def test_bridge_rejects_invalid_results(self):
        page=Mock()
        for envelope in ({}, {'id':7,'value':'x'}, {'id':'x','value':{}},
                         {'id':'x'*65,'value':'x'}, {'id':'x','value':'x'*16385}):
            BrowserPage._message(page,json.dumps({'method':'Runtime.bindingCalled',
                'params':{'name':'kfpsEditorBridge','payload':json.dumps(envelope)}}))
        page.commandResult.emit.assert_not_called()

    def test_external_links_cannot_launch_files(self):
        page=Mock()
        with patch('kfps_editor.browser_page.QDesktopServices.openUrl') as opened:
            for url in ('file:///C:/file.exe','javascript:alert(1)','https://user:password@example.com'):
                BrowserPage._message(page,json.dumps({'method':'Runtime.bindingCalled',
                    'params':{'name':'kfpsEditorBridge','payload':json.dumps({'operation':'external','url':url})}}))
            opened.assert_not_called()


if __name__=='__main__':
    unittest.main()
