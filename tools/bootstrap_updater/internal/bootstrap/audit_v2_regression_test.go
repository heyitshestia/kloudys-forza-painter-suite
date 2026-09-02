package bootstrap

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestAuditV2LockRejectsLinkedLeafWithoutClobberingTarget(t *testing.T) {
	root := t.TempDir()
	state := filepath.Join(root, "state")
	if err := os.MkdirAll(state, 0o700); err != nil {
		t.Fatal(err)
	}
	victim := filepath.Join(root, "victim.txt")
	writeTestFile(t, victim, "preserve-me")
	if err := os.Symlink(victim, filepath.Join(state, "updater.lock")); err != nil {
		t.Skipf("file symlinks are unavailable: %v", err)
	}
	if lock, err := AcquireUpdateLock(state, 10*time.Millisecond); err == nil {
		lock.Close()
		t.Fatal("linked lock leaf was accepted")
	}
	assertFileContent(t, victim, "preserve-me")
}

func TestAuditV2LockRejectsHardLinkedLeafWithoutClobberingTarget(t *testing.T) {
	root := t.TempDir()
	state := filepath.Join(root, "state")
	if err := os.MkdirAll(state, 0o700); err != nil {
		t.Fatal(err)
	}
	victim := filepath.Join(root, "victim.txt")
	writeTestFile(t, victim, "preserve-me")
	if err := os.Link(victim, filepath.Join(state, "updater.lock")); err != nil {
		t.Skipf("hard links are unavailable: %v", err)
	}
	if lock, err := AcquireUpdateLock(state, 10*time.Millisecond); err == nil {
		lock.Close()
		t.Fatal("multi-link lock leaf was accepted")
	}
	assertFileContent(t, victim, "preserve-me")
}

func TestAuditV2SameSequenceIdentityRejectsBeforeHandoff(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "2.0.0\n")
	current := filepath.Join(t.TempDir(), "current.exe")
	writeTestFile(t, current, "old-updater")
	records, archive := componentFixture(t, map[string][]byte{"VERSION": []byte("2.0.0\n")})
	fixture := newSignedChannelFixture(t, UpdateManifest{
		Schema: ManifestSchema, Channel: "stable", Sequence: 77, Version: "2.0.0", Commit: strings.Repeat("7", 40),
		PublishedUTC: time.Now().UTC().Format(time.RFC3339),
		Components:   []Component{{Name: "application", Target: "app-root", Archive: Artifact{URL: "/application.zip"}, Files: records}},
	}, map[string][]byte{"/application.zip": archive})
	statePayload, err := json.Marshal(PersistentState{
		Schema: "kfps.update-state.v1", HighestSequence: 77, Version: "2.0.0", Commit: strings.Repeat("7", 40),
		ChannelSHA256: strings.Repeat("a", 64), ManifestSHA256: strings.Repeat("b", 64),
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := writeAtomic(filepath.Join(state, "state.json"), statePayload, 0o600); err != nil {
		t.Fatal(err)
	}
	engine := signedEngineForFixture(t, fixture, install, app, state, "same-sequence-before-handoff")
	engine.config.BootstrapVersion = "0.9.0"
	engine.config.CurrentExecutable = current
	result, err := engine.Run(context.Background())
	if err == nil || !strings.Contains(err.Error(), "republished with different content") {
		t.Fatalf("alternate same-sequence channel was not rejected: %#v %v", result, err)
	}
	if result.Handoff.Path != "" {
		t.Fatalf("same-sequence rejection occurred after handoff selection: %#v", result.Handoff)
	}
	if _, statErr := os.Stat(filepath.Join(state, "handoff")); !os.IsNotExist(statErr) {
		t.Fatalf("handoff bytes were created before identity rejection: %v", statErr)
	}
}

func TestAuditV2EqualVersionRecoveryRejectsDifferentCommit(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "3.1.54\n")
	releasePayload, err := json.Marshal(ReleaseManifest{
		Schema: ReleaseSchema, Version: "3.1.54", Commit: strings.Repeat("b", 40), Kind: "recommended",
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(install, "RELEASE-MANIFEST.json"), releasePayload, 0o644); err != nil {
		t.Fatal(err)
	}
	engine, err := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.0", Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state,
		Logger: testLogger(t, state, "same-version-commit"), Recovery: RecoveryConfig{Version: "3.1.54", Commit: strings.Repeat("a", 40)},
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := engine.ensureRecoveryEligible(); err == nil || !strings.Contains(err.Error(), "different commit") {
		t.Fatalf("same-version different-commit recovery was accepted: %v", err)
	}
}

func TestAuditV2DefaultStateIsPerInstallation(t *testing.T) {
	t.Setenv("LOCALAPPDATA", t.TempDir())
	rootA := filepath.Join(t.TempDir(), "package-a")
	rootB := filepath.Join(t.TempDir(), "package-b")
	for _, root := range []string{rootA, rootB} {
		if err := os.MkdirAll(filepath.Join(root, "KloudysFH6Painter"), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	stateA, err := DefaultStateDir(Layout{InstallRoot: rootA, AppRoot: filepath.Join(rootA, "KloudysFH6Painter")})
	if err != nil {
		t.Fatal(err)
	}
	stateB, err := DefaultStateDir(Layout{InstallRoot: rootB, AppRoot: filepath.Join(rootB, "KloudysFH6Painter")})
	if err != nil {
		t.Fatal(err)
	}
	if strings.EqualFold(stateA, stateB) {
		t.Fatalf("portable installations share state: %s", stateA)
	}
}

func TestAuditV2StateBindingRejectsAnotherInstallation(t *testing.T) {
	rootA := filepath.Join(t.TempDir(), "package-a")
	rootB := filepath.Join(t.TempDir(), "package-b")
	appA := filepath.Join(rootA, "KloudysFH6Painter")
	appB := filepath.Join(rootB, "KloudysFH6Painter")
	for _, app := range []string{appA, appB} {
		writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	}
	idA, err := InstallationIdentity(Layout{InstallRoot: rootA, AppRoot: appA})
	if err != nil {
		t.Fatal(err)
	}
	state := filepath.Join(t.TempDir(), "state")
	payload, _ := json.Marshal(PersistentState{Schema: "kfps.update-state.v1", InstallationID: idA, HighestSequence: 1, Version: "1.0.0", Commit: strings.Repeat("1", 40)})
	if err := writeAtomic(filepath.Join(state, "state.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	engine, err := NewEngine(EngineConfig{BootstrapVersion: "1.0.0", Layout: Layout{InstallRoot: rootB, AppRoot: appB}, StateDir: state, Logger: testLogger(t, t.TempDir(), "bound-state")})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := engine.loadState(); err == nil || !strings.Contains(err.Error(), "different KFPS installation") {
		t.Fatalf("state binding was not enforced: %v", err)
	}
}

func TestAuditV2AutomaticLayoutRecoversMissingApplicationDirectory(t *testing.T) {
	install := t.TempDir()
	updater := filepath.Join(install, "KFPS-Updater.exe")
	writeTestFile(t, updater, "updater")
	writeTestFile(t, filepath.Join(install, "KFPS.exe"), "launcher")
	layout, err := ResolveLayout("", updater, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if layout.InstallRoot != install || layout.AppRoot != filepath.Join(install, "KloudysFH6Painter") {
		t.Fatalf("broken package resolved incorrectly: %#v", layout)
	}
}

func TestAuditV2UnsafeRedirectRemainsPolicyFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		http.Redirect(writer, request, "http://example.invalid/payload", http.StatusFound)
	}))
	defer server.Close()
	downloader := NewDownloader(testLogger(t, t.TempDir(), "redirect-policy-v2"), true)
	_, err := downloader.Read(context.Background(), server.URL, 1024)
	if err == nil || !isPolicyError(err) || isAvailabilityError(err) {
		t.Fatalf("redirect policy error was misclassified: %T %v", err, err)
	}
}

func TestAuditV2RetiredDirectoryRequiresManualRemediation(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	if err := os.MkdirAll(filepath.Join(app, "retired.txt"), 0o755); err != nil {
		t.Fatal(err)
	}
	record := FileRecord{Path: "VERSION", Size: int64(len("1.0.0\n")), SHA256: sha256Bytes([]byte("1.0.0\n"))}
	manifest := UpdateManifest{Version: "1.0.0", Sequence: 1, Components: []Component{{
		Name: "application", Target: "app-root", Archive: Artifact{URL: "https://example.invalid/application.zip", Size: 1, SHA256: strings.Repeat("0", 64)},
		Files: []FileRecord{record}, RetiredFiles: []string{"retired.txt"},
	}}}
	logger := testLogger(t, t.TempDir(), "retired-directory")
	_, err := PrepareComponentUpdate(context.Background(), NewDownloader(logger, false), manifest, filepath.Join(t.TempDir(), "stage"), Layout{InstallRoot: install, AppRoot: app}, logger)
	if err == nil || !strings.Contains(err.Error(), "manual remediation") {
		t.Fatalf("retired directory was silently ignored: %v", err)
	}
}

func TestAuditV2OpenedHandoffRemainsBoundToVerifiedFile(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "handoff.exe")
	replacement := filepath.Join(root, "replacement.exe")
	writeTestFile(t, path, "verified")
	writeTestFile(t, replacement, "substitute")
	opened, err := openVerifiedExecutable(path)
	if err != nil {
		t.Fatal(err)
	}
	defer opened.close()
	if err := verifyOpenedExecutable(opened, Artifact{Size: int64(len("verified")), SHA256: sha256Bytes([]byte("verified"))}); err != nil {
		t.Fatal(err)
	}
	renameErr := os.Rename(replacement, path)
	if runtime.GOOS == "windows" {
		if renameErr == nil {
			t.Fatal("Windows allowed replacement while the verified image handle was held")
		}
		return
	}
	if renameErr != nil {
		t.Fatal(renameErr)
	}
	if _, err := opened.file.Seek(0, 0); err != nil {
		t.Fatal(err)
	}
	payload, err := os.ReadFile(opened.commandPath)
	if err != nil || string(payload) != "verified" {
		t.Fatalf("descriptor command path no longer referenced verified bytes: %q %v", payload, err)
	}
}
