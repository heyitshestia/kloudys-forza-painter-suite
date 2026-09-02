package bootstrap

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestAuditForcedRecoveryRejectsNewerInstallation(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "9.0.0\n")

	files := map[string][]byte{
		"KFPS.exe":                         []byte("launcher"),
		"KloudysFH6Painter/VERSION":        []byte("3.1.54\n"),
		"KloudysFH6Painter/KFPS.UI/app.py": []byte("baseline"),
	}
	release := ReleaseManifest{
		Schema: ReleaseSchema, Version: "3.1.54", Commit: strings.Repeat("a", 40),
		Kind: "recommended", SourceTimestampUTC: time.Now().UTC().Format(time.RFC3339),
	}
	for path, payload := range files {
		release.Files = append(release.Files, FileRecord{Path: path, Size: int64(len(payload)), SHA256: sha256Bytes(payload)})
	}
	sortFileRecords(release.Files)
	manifestPayload, err := json.MarshalIndent(release, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	manifestPayload = append(manifestPayload, '\n')
	archive := filepath.Join(t.TempDir(), "recovery.zip")
	writeZip(t, archive, "KFPS-3.1.54/", files, map[string][]byte{"RELEASE-MANIFEST.json": manifestPayload})
	archiveInfo, err := os.Stat(archive)
	if err != nil {
		t.Fatal(err)
	}
	archiveHash, err := sha256File(archive)
	if err != nil {
		t.Fatal(err)
	}
	state := filepath.Join(t.TempDir(), "state")
	engine, err := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.0", Layout: Layout{InstallRoot: install, AppRoot: app},
		StateDir: state, Logger: testLogger(t, state, "newer-recovery"), ForceRecovery: true,
		RecoveryArchive: archive,
		Recovery: RecoveryConfig{
			Version: release.Version, Commit: release.Commit,
			ManifestSHA256: sha256Bytes(manifestPayload), ManifestSize: int64(len(manifestPayload)),
			Artifact: Artifact{URL: "https://invalid.example/recovery.zip", Size: archiveInfo.Size(), SHA256: archiveHash},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := engine.Run(context.Background()); err == nil || !strings.Contains(strings.ToLower(err.Error()), "newer") {
		t.Fatalf("forced recovery did not reject a newer installation: %v", err)
	}
	assertFileContent(t, filepath.Join(app, "VERSION"), "9.0.0\n")
}

func TestAuditTransactionRejectsDuplicateDestinations(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	destination := filepath.Join(app, "obsolete.txt")
	changes := []Change{
		{Kind: RemoveFile, Relative: "obsolete.txt", Destination: destination},
		{Kind: RemoveFile, Relative: "obsolete.txt", Destination: destination},
	}
	state := filepath.Join(t.TempDir(), "state")
	if _, err := NewTransaction(state, "duplicate-test", Layout{InstallRoot: install, AppRoot: app}, changes, testLogger(t, state, "duplicate")); err == nil {
		t.Fatal("transaction accepted duplicate destinations")
	}
}

func TestAuditResolveLayoutPrefersExecutablePackage(t *testing.T) {
	executableInstall := filepath.Join(t.TempDir(), "executable-package")
	workingInstall := filepath.Join(t.TempDir(), "working-package")
	for _, root := range []string{executableInstall, workingInstall} {
		writeTestFile(t, filepath.Join(root, "KloudysFH6Painter", "VERSION"), "1.0.0\n")
	}
	updater := filepath.Join(executableInstall, "KFPS-Updater.exe")
	writeTestFile(t, updater, "updater")
	layout, err := ResolveLayout("", updater, workingInstall)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.EqualFold(layout.InstallRoot, executableInstall) {
		t.Fatalf("working directory overrode executable-side package: %#v", layout)
	}
}

func TestAuditJoinContainedRejectsLinkedParent(t *testing.T) {
	root := t.TempDir()
	external := t.TempDir()
	linked := filepath.Join(root, "linked")
	if err := os.Symlink(external, linked); err != nil {
		t.Skipf("symbolic links are unavailable on this host: %v", err)
	}
	if _, err := joinContained(root, "linked/program.txt"); err == nil {
		t.Fatal("contained path accepted a linked parent")
	}
}

func TestAuditLoggerRejectsLinkedDirectory(t *testing.T) {
	root := t.TempDir()
	external := t.TempDir()
	linked := filepath.Join(root, "logs")
	if err := os.Symlink(external, linked); err != nil {
		t.Skipf("symbolic links are unavailable on this host: %v", err)
	}
	if _, err := NewLogger(linked, "linked-log", nil); err == nil {
		t.Fatal("logger accepted a linked directory")
	}
	entries, err := os.ReadDir(external)
	if err != nil || len(entries) != 0 {
		t.Fatalf("logger wrote through linked directory: entries=%d err=%v", len(entries), err)
	}
}

func TestAuditEngineRejectsLinkedStagingBeforeExternalWrite(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	state := filepath.Join(t.TempDir(), "state")
	if err := os.MkdirAll(state, 0o755); err != nil {
		t.Fatal(err)
	}
	external := t.TempDir()
	if err := os.Symlink(external, filepath.Join(state, "runs")); err != nil {
		t.Skipf("symbolic links are unavailable on this host: %v", err)
	}
	engine, err := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.0", Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state,
		Logger: testLogger(t, t.TempDir(), "linked-stage"), ForceRecovery: true,
		Recovery: RecoveryConfig{Version: "1.0.0"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := engine.Run(context.Background()); err == nil || !strings.Contains(err.Error(), "linked or reparse-point") {
		t.Fatalf("engine accepted a linked staging root: %v", err)
	}
	entries, err := os.ReadDir(external)
	if err != nil || len(entries) != 0 {
		t.Fatalf("engine wrote through linked staging root: entries=%d err=%v", len(entries), err)
	}
}

func TestAuditInterruptedTransactionRestoresFilesAndUpdaterState(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	destination := filepath.Join(app, "VERSION")
	writeTestFile(t, destination, "1.0.0\n")
	staged := filepath.Join(t.TempDir(), "VERSION")
	writeTestFile(t, staged, "2.0.0\n")
	state := filepath.Join(t.TempDir(), "state")
	oldState := []byte("{\"schema\":\"kfps.update-state.v1\",\"highest_sequence\":1,\"version\":\"1.0.0\",\"commit\":\"" + strings.Repeat("1", 40) + "\"}\n")
	newState := []byte("{\"schema\":\"kfps.update-state.v1\",\"highest_sequence\":2,\"version\":\"2.0.0\",\"commit\":\"" + strings.Repeat("2", 40) + "\"}\n")
	statePath := filepath.Join(state, "state.json")
	if err := writeAtomic(statePath, oldState, 0o600); err != nil {
		t.Fatal(err)
	}
	transaction, err := NewTransaction(state, "state-crash-test", Layout{InstallRoot: install, AppRoot: app}, []Change{{
		Kind: ReplaceFile, Relative: "KloudysFH6Painter/VERSION", Destination: destination, Staged: staged,
		Expected: FileRecord{Path: "KloudysFH6Painter/VERSION", Size: int64(len("2.0.0\n")), SHA256: sha256Bytes([]byte("2.0.0\n"))},
	}}, testLogger(t, state, "state-crash"))
	if err != nil {
		t.Fatal(err)
	}
	if err := transaction.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := transaction.Apply(); err != nil {
		t.Fatal(err)
	}
	if err := transaction.PrepareStateTransition(statePath, oldState, true); err != nil {
		t.Fatal(err)
	}
	if err := writeAtomic(statePath, newState, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := transaction.MarkStateUpdated(); err != nil {
		t.Fatal(err)
	}

	recovered, err := RecoverInterruptedTransaction(state, Layout{InstallRoot: install, AppRoot: app}, testLogger(t, state, "state-recovery"))
	if err != nil {
		t.Fatal(err)
	}
	if !recovered {
		t.Fatal("interrupted transaction was not recovered")
	}
	assertFileContent(t, destination, "1.0.0\n")
	if payload, err := os.ReadFile(statePath); err != nil || string(payload) != string(oldState) {
		t.Fatalf("updater state was not rolled back with files: %q err=%v", payload, err)
	}
}

func TestAuditRecoveryRejectsNewerPersistentStateWithoutVersionFile(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	if err := os.MkdirAll(app, 0o755); err != nil {
		t.Fatal(err)
	}
	state := filepath.Join(t.TempDir(), "state")
	payload, err := json.Marshal(PersistentState{
		Schema: "kfps.update-state.v1", HighestSequence: 99, Version: "9.0.0", Commit: strings.Repeat("9", 40),
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := writeAtomic(filepath.Join(state, "state.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	engine := &Engine{config: EngineConfig{
		Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state,
		Recovery: RecoveryConfig{Version: "3.1.54"},
	}}
	if err := engine.ensureRecoveryEligible(); err == nil || !strings.Contains(err.Error(), "newer") {
		t.Fatalf("newer persistent state did not block recovery: %v", err)
	}
}

func TestAuditEqualSequenceRejectsDifferentSignedIdentity(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "2.0.0\n")
	records, archive := componentFixture(t, map[string][]byte{"VERSION": []byte("2.0.0\n")})
	manifest := UpdateManifest{
		Schema: ManifestSchema, Channel: "stable", Sequence: 44, Version: "2.0.0",
		Commit: strings.Repeat("4", 40), PublishedUTC: time.Now().UTC().Format(time.RFC3339),
		Components: []Component{{Name: "application", Target: "app-root", Archive: Artifact{URL: "/application.zip"}, Files: records}},
	}
	fixture := newSignedChannelFixture(t, manifest, map[string][]byte{"/application.zip": archive})
	payload, err := json.Marshal(PersistentState{
		Schema: "kfps.update-state.v1", HighestSequence: 44, Version: "2.0.0", Commit: strings.Repeat("4", 40),
		ChannelSHA256: strings.Repeat("a", 64), ManifestSHA256: strings.Repeat("b", 64),
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := writeAtomic(filepath.Join(state, "state.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	engine := signedEngineForFixture(t, fixture, install, app, state, "equal-sequence")
	if _, err := engine.Run(context.Background()); err == nil || !strings.Contains(err.Error(), "republished with different content") {
		t.Fatalf("equal sequence accepted different signed identity: %v", err)
	}
}

func TestAuditSequenceRollbackCannotBecomeRecoveryFallback(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "3.1.54\n")
	records, archive := componentFixture(t, map[string][]byte{"VERSION": []byte("3.1.54\n")})
	fixture := newSignedChannelFixture(t, UpdateManifest{
		Schema: ManifestSchema, Channel: "stable", Sequence: 5, Version: "3.1.54",
		Commit: strings.Repeat("5", 40), PublishedUTC: time.Now().UTC().Format(time.RFC3339),
		Components: []Component{{Name: "application", Target: "app-root", Archive: Artifact{URL: "/application.zip"}, Files: records}},
	}, map[string][]byte{"/application.zip": archive})
	payload, err := json.Marshal(PersistentState{Schema: "kfps.update-state.v1", HighestSequence: 6, Version: "3.1.54", Commit: strings.Repeat("6", 40)})
	if err != nil {
		t.Fatal(err)
	}
	if err := writeAtomic(filepath.Join(state, "state.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	engine := signedEngineForFixture(t, fixture, install, app, state, "rollback-no-fallback")
	engine.config.DisableFallback = false
	engine.config.Recovery = RecoveryConfig{Version: "3.1.54"}
	result, err := engine.Run(context.Background())
	if err == nil || !strings.Contains(err.Error(), "signed-channel rollback") {
		t.Fatalf("sequence rollback did not fail closed: result=%#v err=%v", result, err)
	}
	if result.Summary.Mode != "signed-channel" {
		t.Fatalf("sequence rollback was converted to %s", result.Summary.Mode)
	}
}
