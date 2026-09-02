package bootstrap

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

type signedChannelFixture struct {
	publicKey  ed25519.PublicKey
	server     *httptest.Server
	channelURL string
	files      map[string][]byte
	requests   map[string]int
	mutex      sync.Mutex
}

func newSignedChannelFixture(t *testing.T, manifest UpdateManifest, archives map[string][]byte) *signedChannelFixture {
	t.Helper()
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	fixture := &signedChannelFixture{publicKey: publicKey, files: map[string][]byte{}, requests: map[string]int{}}
	fixture.server = httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		fixture.mutex.Lock()
		fixture.requests[request.URL.Path]++
		payload, ok := fixture.files[request.URL.Path]
		fixture.mutex.Unlock()
		if !ok {
			http.NotFound(writer, request)
			return
		}
		writer.Header().Set("Content-Length", fmt.Sprint(len(payload)))
		_, _ = writer.Write(payload)
	}))
	t.Cleanup(fixture.server.Close)
	for index := range manifest.Components {
		path := manifest.Components[index].Archive.URL
		payload, ok := archives[path]
		if !ok {
			t.Fatalf("missing test component archive %s", path)
		}
		fixture.files[path] = payload
		manifest.Components[index].Archive = Artifact{URL: fixture.server.URL + path, Size: int64(len(payload)), SHA256: sha256Bytes(payload)}
	}
	manifestPayload, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	manifestPayload = append(manifestPayload, '\n')
	manifestSignature, err := SignBytes(manifestPayload, privateKey)
	if err != nil {
		t.Fatal(err)
	}
	fixture.files["/manifest.json"] = manifestPayload
	fixture.files["/manifest.json.sig"] = append(manifestSignature, '\n')
	updaterPayload := []byte("test-updater")
	fixture.files["/KFPS-Updater.exe"] = updaterPayload
	channel := Channel{
		Schema: ChannelSchema, Channel: "stable", Sequence: manifest.Sequence, PublishedUTC: time.Now().UTC().Format(time.RFC3339), MinimumBootstrap: "1.0.0",
		Updater:  UpdaterArtifact{Version: "1.0.0", Artifact: Artifact{URL: fixture.server.URL + "/KFPS-Updater.exe", Size: int64(len(updaterPayload)), SHA256: sha256Bytes(updaterPayload)}},
		Manifest: ManifestReference{Artifact: Artifact{URL: fixture.server.URL + "/manifest.json", Size: int64(len(manifestPayload)), SHA256: sha256Bytes(manifestPayload)}, SignatureURL: fixture.server.URL + "/manifest.json.sig"},
	}
	channelPayload, err := json.MarshalIndent(channel, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	channelPayload = append(channelPayload, '\n')
	channelSignature, err := SignBytes(channelPayload, privateKey)
	if err != nil {
		t.Fatal(err)
	}
	fixture.files["/channel.json"] = channelPayload
	fixture.files["/channel.json.sig"] = append(channelSignature, '\n')
	fixture.channelURL = fixture.server.URL + "/channel.json"
	return fixture
}

func (fixture *signedChannelFixture) requestCount(path string) int {
	fixture.mutex.Lock()
	defer fixture.mutex.Unlock()
	return fixture.requests[path]
}

func signedEngineForFixture(t *testing.T, fixture *signedChannelFixture, install, app, state, logName string) *Engine {
	t.Helper()
	engine, err := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.1", ChannelURL: fixture.channelURL, ChannelSignature: fixture.channelURL + ".sig",
		TrustedKey: fixture.publicKey, Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state,
		Logger: testLogger(t, state, logName), AllowLocalSources: true, DisableFallback: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	return engine
}

func TestStateWriteFailureRollsBackInstalledFiles(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	records, archive := componentFixture(t, map[string][]byte{"VERSION": []byte("2.0.0\n")})
	fixture := newSignedChannelFixture(t, UpdateManifest{
		Schema: ManifestSchema, Channel: "stable", Sequence: 11, Version: "2.0.0", Commit: strings.Repeat("c", 40), PublishedUTC: time.Now().UTC().Format(time.RFC3339),
		Components: []Component{{Name: "application", Target: "app-root", Archive: Artifact{URL: "/application.zip"}, Files: records}},
	}, map[string][]byte{"/application.zip": archive})
	engine := signedEngineForFixture(t, fixture, install, app, state, "state-failure")
	engine.saveStateOverride = func(PreparedUpdate) error { return errors.New("injected state write failure") }
	result, err := engine.Run(context.Background())
	if err == nil || !strings.Contains(err.Error(), "save updater state") {
		t.Fatalf("state persistence failure was not reported: %v", err)
	}
	if !result.Summary.Rollback || !result.Summary.RollbackSuccess {
		t.Fatalf("state persistence failure did not report rollback: %#v", result.Summary)
	}
	assertFileContent(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	if fileExists(filepath.Join(state, "state.json")) || fileExists(filepath.Join(state, "current-transaction.json")) {
		t.Fatal("failed update left committed state or an active transaction")
	}
}

func TestRemovalOnlyUpdateDoesNotDownloadComponentArchive(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeTestFile(t, filepath.Join(app, "obsolete.txt"), "remove")
	records, archive := componentFixture(t, map[string][]byte{"VERSION": []byte("1.0.0\n")})
	fixture := newSignedChannelFixture(t, UpdateManifest{
		Schema: ManifestSchema, Channel: "stable", Sequence: 12, Version: "1.0.0", Commit: strings.Repeat("d", 40), PublishedUTC: time.Now().UTC().Format(time.RFC3339),
		Components: []Component{{Name: "application", Target: "app-root", Archive: Artifact{URL: "/application.zip"}, Files: records, RetiredFiles: []string{"obsolete.txt"}}},
	}, map[string][]byte{"/application.zip": archive})
	result, err := signedEngineForFixture(t, fixture, install, app, state, "removal-only").Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if result.Summary.FilesRemoved != 1 || result.Summary.FilesReplaced != 0 {
		t.Fatalf("unexpected removal-only summary: %#v", result.Summary)
	}
	if fixture.requestCount("/application.zip") != 0 {
		t.Fatal("component archive was downloaded for a removal-only update")
	}
	if fileExists(filepath.Join(app, "obsolete.txt")) {
		t.Fatal("retired file was not removed")
	}
	var stateRecord PersistentState
	payload, err := os.ReadFile(filepath.Join(state, "state.json"))
	if err != nil || json.Unmarshal(payload, &stateRecord) != nil || stateRecord.HighestSequence != 12 {
		t.Fatalf("signed sequence state was not persisted: %#v %v", stateRecord, err)
	}
}

func TestMismatchedComponentArchiveLeavesInstallUntouched(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	records, _ := componentFixture(t, map[string][]byte{"VERSION": []byte("2.0.0\n")})
	_, wrongArchive := componentFixture(t, map[string][]byte{"wrong.txt": []byte("wrong")})
	fixture := newSignedChannelFixture(t, UpdateManifest{
		Schema: ManifestSchema, Channel: "stable", Sequence: 13, Version: "2.0.0", Commit: strings.Repeat("e", 40), PublishedUTC: time.Now().UTC().Format(time.RFC3339),
		Components: []Component{{Name: "application", Target: "app-root", Archive: Artifact{URL: "/application.zip"}, Files: records}},
	}, map[string][]byte{"/application.zip": wrongArchive})
	if _, err := signedEngineForFixture(t, fixture, install, app, state, "bad-inventory").Run(context.Background()); err == nil || !strings.Contains(err.Error(), "archive") {
		t.Fatalf("mismatched component archive was accepted: %v", err)
	}
	assertFileContent(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	if fileExists(filepath.Join(state, "state.json")) {
		t.Fatal("failed component validation advanced persistent state")
	}
}

func TestProtectedRetiredPathIsRejected(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeTestFile(t, filepath.Join(app, "runtime", "user.json"), "preserve")
	records, archive := componentFixture(t, map[string][]byte{"VERSION": []byte("1.0.0\n")})
	fixture := newSignedChannelFixture(t, UpdateManifest{
		Schema: ManifestSchema, Channel: "stable", Sequence: 14, Version: "1.0.0", Commit: strings.Repeat("f", 40), PublishedUTC: time.Now().UTC().Format(time.RFC3339),
		Components: []Component{{Name: "application", Target: "app-root", Archive: Artifact{URL: "/application.zip"}, Files: records, RetiredFiles: []string{"runtime/user.json"}}},
	}, map[string][]byte{"/application.zip": archive})
	if _, err := signedEngineForFixture(t, fixture, install, app, state, "protected-retired").Run(context.Background()); err == nil || !strings.Contains(err.Error(), "protected") {
		t.Fatalf("protected retirement was accepted: %v", err)
	}
	assertFileContent(t, filepath.Join(app, "runtime", "user.json"), "preserve")
}

func TestUpdaterReportsAreBoundedInStateAndApplication(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	engine, err := NewEngine(EngineConfig{BootstrapVersion: "1.0.0", Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state, Logger: testLogger(t, state, "report-prune")})
	if err != nil {
		t.Fatal(err)
	}
	for _, directory := range []string{filepath.Join(state, "reports"), filepath.Join(app, "runtime", "update-reports")} {
		for index := 0; index < 55; index++ {
			path := filepath.Join(directory, fmt.Sprintf("old-%02d.json", index))
			writeTestFile(t, path, "{}\n")
			old := time.Now().Add(-time.Duration(index+1) * time.Hour)
			if err := os.Chtimes(path, old, old); err != nil {
				t.Fatal(err)
			}
		}
	}
	if err := engine.writeSummary(RunSummary{Schema: "kfps.update-run.v1", RunID: engine.runID, Status: "completed", Success: true}); err != nil {
		t.Fatal(err)
	}
	for _, directory := range []string{filepath.Join(state, "reports"), filepath.Join(app, "runtime", "update-reports")} {
		entries, err := os.ReadDir(directory)
		if err != nil {
			t.Fatal(err)
		}
		if len(entries) != 40 {
			t.Fatalf("report history was not bounded in %s: %d", directory, len(entries))
		}
		if !fileExists(filepath.Join(directory, "update-"+engine.runID+".json")) {
			t.Fatal("current updater report was pruned")
		}
	}
}

func TestHandoffFailureRewritesSuccessfulReport(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	engine, err := NewEngine(EngineConfig{BootstrapVersion: "1.0.0", Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state, Logger: testLogger(t, state, "handoff-failure")})
	if err != nil {
		t.Fatal(err)
	}
	summary := RunSummary{Schema: "kfps.update-run.v1", RunID: engine.runID, Status: "handoff", Success: true}
	if err := engine.writeSummary(summary); err != nil {
		t.Fatal(err)
	}
	if err := engine.RecordHandoffFailure(summary, fmt.Errorf("CreateProcess failed")); err != nil {
		t.Fatal(err)
	}
	payload, err := os.ReadFile(filepath.Join(state, "reports", "update-"+engine.runID+".json"))
	if err != nil {
		t.Fatal(err)
	}
	var recorded RunSummary
	if err := json.Unmarshal(payload, &recorded); err != nil {
		t.Fatal(err)
	}
	if recorded.Success || recorded.Status != "failed" || !strings.Contains(recorded.Error, "CreateProcess") {
		t.Fatalf("handoff failure remained reported as success: %#v", recorded)
	}
}

func TestMatchingBootstrapHashSkipsSelfUpdateDownload(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	current := filepath.Join(t.TempDir(), "KFPS-Updater.exe")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeTestFile(t, current, "same-updater")
	engine, err := NewEngine(EngineConfig{BootstrapVersion: "1.0.0", Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state, CurrentExecutable: current, Logger: testLogger(t, state, "same-bootstrap")})
	if err != nil {
		t.Fatal(err)
	}
	handoff, err := engine.prepareSelfUpdate(context.Background(), Channel{
		MinimumBootstrap: "1.0.0",
		Updater:          UpdaterArtifact{Version: "1.0.0", Artifact: Artifact{URL: "https://invalid.example/updater.exe", Size: int64(len("same-updater")), SHA256: sha256Bytes([]byte("same-updater"))}},
	})
	if err != nil || handoff.Path != "" {
		t.Fatalf("matching bootstrap attempted self-update: path=%q err=%v", handoff, err)
	}
}

func TestFullSignedUpdateDryRunApplyRepairAndNoOp(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(install, "KFPS.exe"), "old-outer-launcher")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeTestFile(t, filepath.Join(app, "KFPS.UI", "app.py"), "old-app")
	writeTestFile(t, filepath.Join(app, "python", "obsolete.pyd"), "obsolete")
	writeTestFile(t, filepath.Join(app, "python", "Lib", "__pycache__", "generated.pyc"), "keep-cache")
	writeTestFile(t, filepath.Join(app, "retired.txt"), "retire")
	writeTestFile(t, filepath.Join(app, "runtime", "user-output.json"), "preserve")
	writeTestFile(t, filepath.Join(app, "user.kfpskey"), "preserve-key")
	if err := os.Chmod(filepath.Join(install, "KFPS.exe"), 0o444); err != nil {
		t.Fatal(err)
	}

	applicationRecords, applicationArchive := componentFixture(t, map[string][]byte{
		"VERSION":          []byte("2.0.0\n"),
		"KFPS.UI/app.py":   []byte("new-app"),
		"KFPS-Updater.exe": []byte("new-inner-updater"),
	})
	pythonRecords, pythonArchive := componentFixture(t, map[string][]byte{
		"python/python.exe":  []byte("new-python"),
		"python/Lib/site.py": []byte("new-site"),
	})
	nativeRecords, nativeArchive := componentFixture(t, map[string][]byte{
		"KFPS.exe":         []byte("new-outer-launcher"),
		"KFPS-Updater.exe": []byte("new-outer-updater"),
	})
	fixture := newSignedChannelFixture(t, UpdateManifest{
		Schema: ManifestSchema, Channel: "stable", Sequence: 21, Version: "2.0.0", Commit: strings.Repeat("1", 40), PublishedUTC: time.Now().UTC().Format(time.RFC3339), Relaunch: "KFPS.exe",
		Components: []Component{
			{Name: "application", Target: "app-root", Archive: Artifact{URL: "/application.zip"}, Files: applicationRecords, RetiredFiles: []string{"retired.txt"}},
			{Name: "python-runtime", Target: "app-root", Archive: Artifact{URL: "/python.zip"}, Files: pythonRecords, ExactRoots: []string{"python"}},
			{Name: "native-launchers", Target: "install-root", Archive: Artifact{URL: "/native.zip"}, Files: nativeRecords},
		},
	}, map[string][]byte{"/application.zip": applicationArchive, "/python.zip": pythonArchive, "/native.zip": nativeArchive})

	dryRun := signedEngineForFixture(t, fixture, install, app, state, "full-dry-run")
	dryRun.config.DryRun = true
	dryResult, err := dryRun.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if dryResult.Summary.Status != "checked" || dryResult.Summary.FilesPlannedReplaced != 7 || dryResult.Summary.FilesPlannedRemoved != 2 || dryResult.Summary.FilesReplaced != 0 || dryResult.Summary.FilesRemoved != 0 {
		t.Fatalf("unexpected full dry-run summary: %#v", dryResult.Summary)
	}
	assertFileContent(t, filepath.Join(install, "KFPS.exe"), "old-outer-launcher")
	assertFileContent(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	if fileExists(filepath.Join(state, "state.json")) {
		t.Fatal("dry run advanced persistent sequence state")
	}

	result, err := signedEngineForFixture(t, fixture, install, app, state, "full-apply").Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !result.Summary.Success || result.Summary.FilesReplaced != 7 || result.Summary.FilesRemoved != 2 {
		t.Fatalf("unexpected full update summary: %#v", result.Summary)
	}
	assertFileContent(t, filepath.Join(install, "KFPS.exe"), "new-outer-launcher")
	assertFileContent(t, filepath.Join(install, "KFPS-Updater.exe"), "new-outer-updater")
	assertFileContent(t, filepath.Join(app, "KFPS-Updater.exe"), "new-inner-updater")
	assertFileContent(t, filepath.Join(app, "KFPS.UI", "app.py"), "new-app")
	assertFileContent(t, filepath.Join(app, "python", "python.exe"), "new-python")
	assertFileContent(t, filepath.Join(app, "python", "Lib", "__pycache__", "generated.pyc"), "keep-cache")
	assertFileContent(t, filepath.Join(app, "runtime", "user-output.json"), "preserve")
	assertFileContent(t, filepath.Join(app, "user.kfpskey"), "preserve-key")
	for _, removed := range []string{filepath.Join(app, "retired.txt"), filepath.Join(app, "python", "obsolete.pyd")} {
		if fileExists(removed) {
			t.Fatalf("managed obsolete file remained: %s", removed)
		}
	}

	componentRequests := map[string]int{}
	for _, path := range []string{"/application.zip", "/python.zip", "/native.zip"} {
		componentRequests[path] = fixture.requestCount(path)
	}
	second, err := signedEngineForFixture(t, fixture, install, app, state, "full-no-op").Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if second.Summary.FilesReplaced != 0 || second.Summary.FilesRemoved != 0 {
		t.Fatalf("healthy signed update was not a no-op: %#v", second.Summary)
	}
	for path, previous := range componentRequests {
		if fixture.requestCount(path) != previous {
			t.Fatalf("healthy no-op downloaded component %s", path)
		}
	}
}

func TestBadLocalRecoveryArchiveLeavesInstallUntouched(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	archive := filepath.Join(t.TempDir(), "recovery.zip")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeTestFile(t, archive, "not the pinned archive")
	engine, err := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.0", Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state,
		Logger: testLogger(t, state, "bad-recovery"), ForceRecovery: true, RecoveryArchive: archive,
		Recovery: RecoveryConfig{Version: "2.0.0", Commit: strings.Repeat("2", 40), ManifestSHA256: strings.Repeat("0", 64), ManifestSize: 1, Artifact: Artifact{URL: "https://invalid.example/recovery.zip", Size: int64(len("not the pinned archive")), SHA256: strings.Repeat("0", 64)}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := engine.Run(context.Background()); err == nil || !strings.Contains(err.Error(), "pinned size and SHA-256") {
		t.Fatalf("bad local recovery archive was accepted: %v", err)
	}
	assertFileContent(t, filepath.Join(app, "VERSION"), "1.0.0\n")
}

func TestRecoveryEligibilityNeverDowngradesNewerInstall(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	writeTestFile(t, filepath.Join(app, "VERSION"), "3.1.55\n")
	engine := &Engine{config: EngineConfig{
		Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state,
		Recovery: RecoveryConfig{Version: "3.1.54"},
	}}
	if err := engine.ensureRecoveryEligible(); err == nil {
		t.Fatal("newer installation was eligible for an older recovery baseline")
	}
}
