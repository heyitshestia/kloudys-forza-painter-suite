KFPS BOOTSTRAP UPDATER 1.0.2

WHAT IT IS
This is a self-contained Windows x64 updater and repair tool. It does not need
Git, Python, Node.js, .NET, or an already working KFPS runtime.

HOW TO USE IT
1. Close KFPS.
2. Put KFPS-Updater.exe beside the outer KFPS.exe in the downloaded KFPS folder.
3. Double-click KFPS-Updater.exe.
4. Leave the window open until it reports success or a clear failure.

The terminal reports each active phase and periodic file-check progress. A
failure keeps an interactive window open and prints the failed phase, reason,
log path, and JSON report path. Successful in-app updates close the updater
after KFPS relaunches.

The updater also recognizes a package when it is started from inside the
KloudysFH6Painter folder. For an explicit location, run:

  KFPS-Updater.exe --root "C:\path\to\KFPS-package"

REPAIR MODE
Use this only when directed or when an old package has missing program files:

  KFPS-Updater.exe --root "C:\path\to\KFPS-package" --recover

Recovery is pinned to the exact public KFPS 3.1.54 recommended bundle. It will
not downgrade a newer installation.

CHECK MODE
For support or automation, --check never changes installation files. Exit 0
means healthy, exit 3 means verified repairs are needed, exit 1 means the check
failed, and exit 2 means the command or package location was invalid.
Scripts can add --no-pause to retain immediate non-interactive exits.

SELF-UPDATE STATUS
For a normal update only, exit 4 means a verified updater child started and the
final update result is still pending. It is not a failure and is not final
success. The child writes the final JSON report and log.

WHAT IT PRESERVES
Generated images, JSON outputs, runtime data, community downloads, supporter
keys, local Worker data, and unrelated files are not update targets. The bundled
python directory is program-owned and can be repaired as a complete component.

DIAGNOSTICS
Logs and JSON reports are stored under:

  %LOCALAPPDATA%\KloudysFH6Painter\updater\installations\<installation-id>

A report copy is also written under:

  KloudysFH6Painter\runtime\update-reports

For support, send the newest JSON report and the log_path named inside it. Do
not send supporter key files.

SECURITY
Update metadata is signed with Ed25519. Downloads and installed files are
verified by exact size and SHA-256 before an update is accepted. Failed or
interrupted file transactions roll back.

The updater rejects symlinks, junctions, and other reparse points in every path
it would write, clean, stage, back up, log, or report through.
