package bootstrap

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPrepareLegacyMigrationInstallsTwoBootstrapCopiesAndRetiresBatches(t *testing.T) {
	root := t.TempDir()
	install := filepath.Join(root, "KFPS package")
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(root, "state")
	current := filepath.Join(root, "handoff", "KFPS-Updater.exe")
	stage := filepath.Join(state, "runs", "migration-test")
	for _, path := range []string{app, state, filepath.Dir(current)} {
		if err := os.MkdirAll(path, 0o755); err != nil {
			t.Fatal(err)
		}
	}
	writeTestFile(t, current, "verified-bootstrap")
	writeTestFile(t, filepath.Join(app, "KFPS-Updater.exe"), "stale-bootstrap")
	for _, relative := range legacyUpdaterAppFiles {
		writeTestFile(t, filepath.Join(app, relative), "legacy updater")
	}

	recoveryStaged := filepath.Join(stage, "recovery", "03_update_from_github.bat")
	writeTestFile(t, recoveryStaged, "recovery would reinstall this")
	engine := &Engine{
		config: EngineConfig{
			Layout:                  Layout{InstallRoot: install, AppRoot: app},
			CurrentExecutable:       current,
			FinalizeLegacyMigration: true,
		},
		stageDir: stage,
	}
	prepared, err := engine.prepareLegacyMigration(PreparedUpdate{Changes: []Change{{
		Kind: ReplaceFile, Relative: "KloudysFH6Painter/03_update_from_github.bat",
		Destination: filepath.Join(app, "03_update_from_github.bat"), Staged: recoveryStaged,
		Expected: FileRecord{Path: "KloudysFH6Painter/03_update_from_github.bat", Size: int64(len("recovery would reinstall this")), SHA256: sha256Bytes([]byte("recovery would reinstall this"))},
	}}})
	if err != nil {
		t.Fatal(err)
	}
	if len(prepared.Changes) != 4 {
		t.Fatalf("expected one shim, one removal, and two updater replacements, got %#v", prepared.Changes)
	}

	transaction, err := NewTransaction(state, "migration-test", engine.config.Layout, prepared.Changes, testLogger(t, state, "migration"))
	if err != nil {
		t.Fatal(err)
	}
	if err := transaction.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := transaction.Apply(); err != nil {
		t.Fatal(err)
	}
	if err := VerifyPreparedUpdate(prepared); err != nil {
		t.Fatal(err)
	}
	if err := transaction.Commit(); err != nil {
		t.Fatal(err)
	}

	wantHash, err := sha256File(current)
	if err != nil {
		t.Fatal(err)
	}
	for _, updater := range []string{filepath.Join(install, "KFPS-Updater.exe"), filepath.Join(app, "KFPS-Updater.exe")} {
		gotHash, err := sha256File(updater)
		if err != nil || !strings.EqualFold(gotHash, wantHash) {
			t.Fatalf("bootstrap copy did not verify at %s: hash=%s err=%v", updater, gotHash, err)
		}
	}
	primaryPayload, err := os.ReadFile(filepath.Join(app, legacyUpdaterAppFiles[0]))
	if err != nil || string(primaryPayload) != legacyBootstrapShim {
		t.Fatalf("legacy primary updater was not replaced by the bootstrap shim: %v", err)
	}
	if _, err := os.Stat(filepath.Join(app, legacyUpdaterAppFiles[1])); !os.IsNotExist(err) {
		t.Fatalf("legacy wrapper was not retired")
	}

	second, err := engine.prepareLegacyMigration(PreparedUpdate{})
	if err != nil {
		t.Fatal(err)
	}
	if len(second.Changes) != 0 {
		t.Fatalf("healthy migration was not idempotent: %#v", second.Changes)
	}
}

func TestPrepareLegacyMigrationRetiresShimAfterSignedUpdate(t *testing.T) {
	root := t.TempDir()
	install := filepath.Join(root, "install")
	app := filepath.Join(install, "KloudysFH6Painter")
	current := filepath.Join(root, "KFPS-Updater.exe")
	if err := os.MkdirAll(app, 0o755); err != nil {
		t.Fatal(err)
	}
	writeTestFile(t, current, "verified-bootstrap")
	writeTestFile(t, filepath.Join(app, legacyUpdaterAppFiles[0]), legacyBootstrapShim)
	engine := &Engine{
		config:   EngineConfig{Layout: Layout{InstallRoot: install, AppRoot: app}, CurrentExecutable: current, FinalizeLegacyMigration: true},
		stageDir: filepath.Join(root, "stage"),
	}
	prepared, err := engine.prepareLegacyMigration(PreparedUpdate{Sequence: 1})
	if err != nil {
		t.Fatal(err)
	}
	foundRemoval := false
	for _, change := range prepared.Changes {
		if change.Kind == RemoveFile && strings.EqualFold(change.Destination, filepath.Join(app, legacyUpdaterAppFiles[0])) {
			foundRemoval = true
		}
	}
	if !foundRemoval {
		t.Fatalf("signed migration did not retire the compatibility shim: %#v", prepared.Changes)
	}
}

func TestPrepareLegacyMigrationRejectsConflictingUpdaterPlan(t *testing.T) {
	root := t.TempDir()
	install := filepath.Join(root, "install")
	app := filepath.Join(install, "KloudysFH6Painter")
	current := filepath.Join(root, "KFPS-Updater.exe")
	if err := os.MkdirAll(app, 0o755); err != nil {
		t.Fatal(err)
	}
	writeTestFile(t, current, "verified-bootstrap")
	engine := &Engine{
		config: EngineConfig{
			Layout:                  Layout{InstallRoot: install, AppRoot: app},
			CurrentExecutable:       current,
			FinalizeLegacyMigration: true,
		},
		stageDir: filepath.Join(root, "stage"),
	}
	_, err := engine.prepareLegacyMigration(PreparedUpdate{Changes: []Change{{
		Kind: ReplaceFile, Relative: "KFPS-Updater.exe", Destination: filepath.Join(install, "KFPS-Updater.exe"),
		Expected: FileRecord{Path: "KFPS-Updater.exe", Size: 1, SHA256: strings.Repeat("0", 64)},
	}}})
	if err == nil || !strings.Contains(err.Error(), "conflicts with the running bootstrap") {
		t.Fatalf("conflicting updater plan was accepted: %v", err)
	}
}
