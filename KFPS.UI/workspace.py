"""Shared-window entry. Verify the editor runtime before importing Qt."""
from pathlib import Path
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'KFPS.Editor/src'),str(ROOT/'KFPS.UI/src'),str(ROOT/'KFPS.UI'),str(ROOT)]

class WorkspaceAlreadyOpen(RuntimeError):
    """A duplicate launch must not construct a second shell or service graph."""


class WorkspaceRuntime:
    def __init__(self):
        from kfps_editor.baseline import verify
        from kfps_editor.graphics import select_policy,configure_environment
        from kfps_editor.update_guard import acquire_update_guard,updater_state_root
        self.guard=acquire_update_guard(updater_state_root(ROOT)) if os.name=='nt' else None
        self.workspace_lock = None
        try:
            self.baseline=verify(ROOT)
            self.graphics=select_policy(ROOT)
            configure_environment(os.environ,self.graphics)
            os.environ['KFPS_QML_GRAPHICS']=self.graphics.backend
            from kfps_editor.instance_lock import EditorInstanceLock
            from kfps_ui import workspace_paths
            directory = workspace_paths.workspace_connection_dir(ROOT)
            directory.mkdir(parents=True, exist_ok=True)
            self.workspace_lock = EditorInstanceLock(directory)
            if not self.workspace_lock.tryLock(0):
                raise WorkspaceAlreadyOpen('A workspace for this KFPS installation is already open.')
        except Exception:
            self.close()
            raise
    def borrow_guard(self):
        # Child cleanup cannot release the installation while another page is live.
        class Borrowed:
            def Close(self):pass
        return Borrowed()
    def close(self):
        if self.workspace_lock is not None:
            lock, self.workspace_lock = self.workspace_lock, None
            lock.unlock()
        if self.guard is not None:
            self.guard.Close();self.guard=None

def main():
    from kfps_editor.baseline import CONTRACT,development_root,isolated_environment,launch_command
    development=development_root(ROOT) and not (ROOT/CONTRACT).exists()
    if not development and (Path(sys.executable).resolve().parent!=ROOT/'python' or not sys.flags.isolated
            or not sys.dont_write_bytecode or not sys.pycache_prefix or isolated_environment()!=dict(os.environ)):
        import subprocess
        command,environment=launch_command(ROOT,Path(__file__),sys.argv[1:])
        return subprocess.call(command,cwd=ROOT,env=environment,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        runtime=WorkspaceRuntime()
    except WorkspaceAlreadyOpen as error:
        print(str(error), file=sys.stderr)
        return 0
    try:
        import app
        return app.main(workspace_runtime=runtime)
    finally:runtime.close()

if __name__=='__main__':raise SystemExit(main())
