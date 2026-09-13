package bootstrap

import (
	"path/filepath"
	"testing"
)

func TestEditorMoveRollbackPreservesNewerRecovery(t *testing.T) {
	install, state, stage := t.TempDir(), t.TempDir(), t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	old := filepath.Join(app, "tools", "fabric-editor", "editor.js")
	current := filepath.Join(app, "KFPS.Editor", "web", "editor.js")
	recovery := filepath.Join(app, "runtime", "fabric-editor", "autosave.json")
	floor := filepath.Join(app, "runtime", "fabric-editor", "recovery-floor.json")
	writeTestFile(t, old, "old-editor")
	writeTestFile(t, recovery, "revision-10")
	writeTestFile(t, floor, "floor-9")
	payload := filepath.Join(stage, "editor.js")
	writeTestFile(t, payload, "new-editor")
	logger := testLogger(t, state, "editor-move-rollback")
	transaction, err := NewTransaction(state, "editor-move", Layout{InstallRoot: install, AppRoot: app}, []Change{
		{Kind: ReplaceFile, Destination: current, Staged: payload},
		{Kind: RemoveFile, Destination: old},
		{Kind: ReplaceFile, Destination: filepath.Join(app, "KFPS.Editor", "editor.py"), Staged: filepath.Join(stage, "missing")},
	}, logger)
	if err != nil {
		t.Fatal(err)
	}
	if err := transaction.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := transaction.Apply(); err == nil {
		t.Fatal("injected interruption did not fail")
	}
	writeTestFile(t, recovery, "revision-11")
	writeTestFile(t, floor, "floor-11")
	if err := transaction.Rollback(); err != nil {
		t.Fatal(err)
	}
	assertFileContent(t, old, "old-editor")
	if fileExists(current) {
		t.Fatal("partial new program survived rollback")
	}
	assertFileContent(t, recovery, "revision-11")
	assertFileContent(t, floor, "floor-11")
}
