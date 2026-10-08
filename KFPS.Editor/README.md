# KFPS Editor

The editor's authoritative source package. It retains Fabric, the existing tools,
English/Korean interface, shape conversion rules and saved-file formats.

## Source Layout

| Location | Responsibility |
| --- | --- |
| `editor.py` | Standalone Python entry point |
| `src/kfps_editor/` | Native window, IPC, local server, storage and diagnostics |
| `web/` | Editor interface, dedicated owners, workers, locales, Fabric and shapes |
| `manifest.json` | Source roles, ownership, shared dependencies and stable paths |
| `requirements.txt` | Editor-only subset of the qualified Windows Python runtime |
| `retired-files.json` | Exact obsolete program paths consumed by the existing updater |
| `tools/` | Isolated staging and source-inventory utilities |
| `web/tests/` | Unit, native-window, workflow, fault and performance checks |

Shared shape parsing and preview code remain in `kfps_shapes/`,
`geometry_json.py` and `json_preview_renderer.py`. The manifest explicitly lists
them. The editor does not import the main KFPS interface or generator.

## Run From Source

From a complete development checkout with the qualified Python dependencies:

```powershell
py -3.12 KFPS.Editor/editor.py
```

`--background` opens without raising the editor or taking focus; it does not
minimize the window. Normal launches bring the editor forward, restore a minimized
window, and focus its active dialog when one needs attention. Windows may deny
foreground focus after unrelated user input; the editor requests taskbar attention
instead of overriding the user's focus settings.
`--runtime-root` is available for an explicitly isolated test profile.

The native `KFPS Editor.exe` still belongs beside `KFPS.exe` in a combined
installation. The old `KFPS.UI/editor.py` entry and Python import locations are
compatibility adapters. Do not put a second copy of web sources under
`tools/fabric-editor/`.

## Graphics Selection

In KFPS Settings > Maintenance, Editor graphics offers Auto, OpenGL and
Direct3D 11. Both the standalone executable and the in-app launch read the
installation's `runtime/qml-shell-settings.json`. Close and reopen the editor
after changing this setting; it does not change an already-running editor or
the main KFPS renderer.

Auto normally preserves OpenGL. Only the confirmed faulty PCI board and exact
installed driver combination selects Direct3D 11 automatically. Windows device
properties are read afresh at launch; driver updates are not matched using a
cached name or previous result. Unknown or multiple adapters preserve OpenGL,
and an explicit manual choice takes precedence.

## Update Awareness

The standalone editor checks the same published stable update channel as KFPS at
startup and every five minutes, even while the main app is closed. A red UPDATE
indicator appears at the upper left when a newer version is available. Click it
to stop blinking for that version; it stays visible until the installation is
current, and a later version can blink again. Reduced-motion settings disable
the animation. The label and explanation support English and Korean.

This is a reminder, not an automatic installation. Save your work and use KFPS's
normal update workflow when ready. Offline checks do not interrupt editing.

## Data Stays Put

Projects, assets, settings, themes, recovery copies and the WebEngine profile stay
under the existing `runtime/fabric-editor/` locations. Flat exports retain their
existing output location. Source relocation does not migrate data, change the
browser origin, reset favorites or replay acknowledged notices.

See the [editor guide](web/README.md), [architecture](docs/ARCHITECTURE.md),
[validation](docs/VALIDATION.md), and [localization workflow](web/locales/README.md).

## Google Chrome Editor Option

This is an opt-in compatibility option for native-window artifacting,
not a confirmed fix to Qt/Chromium. The ordinary editor remains the default.
An installed Google Chrome is required. Edge and the system's default browser
are not used as fallbacks.
No browser is downloaded and personal browser profiles/extensions are not used.

### English

1. Save your work and close the editor normally. KFPS itself can stay open.
2. Go to Settings > Maintenance and enable
   **Use Google Chrome for editor**. If the status says **Google Chrome: not
   found**, click **Install Google Chrome...** to open Google's official setup
   page and complete the installation there. While Settings is visible, KFPS
   checks automatically and changes the status to **Google Chrome: installed**.
   There is no silent installation or change to your default browser by KFPS.
3. Launch the Editor from KFPS or `KFPS Editor.exe`. Both respect this setting.
4. Open a saved project, move and group a few shapes, then save and reopen it.
   Use the project/background colors that caused the original flickering.
5. Close the window normally. Save, Discard and Cancel use the existing editor
   close checks; Discard still keeps the recovery copy.
6. To return to the normal editor, turn the setting off, close the editor and
   reopen it. Nothing has to be uninstalled. The previous Editor graphics choice
   is retained and applies again in the normal editor.

`KFPS.Editor/Launch Browser Editor.cmd` remains a one-launch Chrome override.
It does not change the saved setting. The setting is stored in the existing
`runtime/qml-shell-settings.json` file as the Boolean `editorUseChrome`.

If an editor is already open, either launcher activates that existing instance;
it does not switch its display mode or start a second writer. Projects, saved
assets, preferences and disk autosaves remain in `runtime/fabric-editor`.
The separate browser cache/recovery profile is `runtime/fabric-editor/browser-profile`.
Do not delete it while the browser editor is running. Do not use Chrome's reload
or developer tools while editing; F5/Ctrl+R are intercepted to protect the session.

For feedback, state whether flickering remained, whether saving/reopening worked,
and roughly how long you edited. Use KFPS's normal Report a problem action with
technical details enabled. Browser version/startup and normal editor diagnostics
are recorded locally; screenshots may miss a display-only fault, so attach a
short recording if it happens again.

### 한국어

1. 작업을 저장하고 에디터를 정상적으로 닫아 주세요. KFPS 본체는 켜 두셔도 됩니다.
2. 설정 > Maintenance에서 **Use Google Chrome for editor**를
   켜 주세요. **Google Chrome: not found**가 표시되면 **Install Google Chrome...**으로
   Google 공식 설치 페이지를 열고 설치를 완료해 주세요. 설정 화면이 열려 있으면
   KFPS가 자동으로 확인하여 **Google Chrome: installed**로 표시합니다.
   KFPS가 몰래 설치하거나 기본 브라우저를 변경하지는 않습니다.
3. KFPS의 에디터 버튼이나 `KFPS Editor.exe`로 실행해 주세요. 두 실행 방법 모두
   같은 설정을 사용합니다.
4. 저장한 프로젝트를 열고 도형 이동이나 그룹 편집을 해 본 뒤, 저장하고 다시 열어 주세요.
   화면 깨짐이 발생했던 프로젝트와 배경색으로 확인해 주시면 좋습니다.
5. 창을 평소처럼 닫아 주세요. 저장, 변경 사항 버리기, 취소는 기존 에디터와 같은
   확인 절차를 거칩니다. 변경 사항을 버려도 복구용 임시 저장본은 유지됩니다.
6. 기존 에디터로 돌아가려면 위 설정을 끈 뒤 에디터를 닫고 다시 실행해 주세요.
   따로 삭제할 항목은 없습니다. 이전 Editor graphics 설정은 유지되며 기존
   에디터로 돌아왔을 때 다시 적용됩니다.

에디터가 이미 열려 있으면 새 창을 만들지 않고 기존 창으로 연결됩니다.
프로젝트, 에셋, 설정, 디스크 자동 저장본은 기존 위치를 그대로 사용합니다.
Google Chrome이 설치되어 있어야 하며 Edge나 기본 브라우저로 대신 실행하지
않습니다. 개인 브라우저의 로그인 정보나 확장
프로그램은 사용하지 않습니다. 작업 중에는 브라우저 새로고침이나 개발자 도구를
사용하지 말아 주세요. F5와 Ctrl+R은 작업 보호를 위해 차단됩니다.

테스트 후에는 화면 깨짐이 다시 발생했는지, 저장 후 다시 열기가 정상인지,
대략 몇 분 동안 작업했는지 알려 주세요. KFPS의 문제 신고에서 기술 정보 포함을
선택해 보내 주시면 됩니다. 다시 깨지는 경우에는 짧은 영상도 함께 부탁드립니다.
일반 캡처에는 화면 표시 오류가 잡히지 않을 수 있습니다.
