package bootstrap

import (
	"archive/zip"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"
)

func TestPinnedRecoveryRepairsMissingRuntimeAndPreservesUserData(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	if err := os.MkdirAll(filepath.Join(app, "runtime"), 0o755); err != nil {
		t.Fatal(err)
	}
	writeTestFile(t, filepath.Join(app, "VERSION"), "0.0.1")
	writeTestFile(t, filepath.Join(app, "python", "obsolete.pyd"), "obsolete")
	writeTestFile(t, filepath.Join(app, "python", "Lib", "__pycache__", "site.pyc"), "runtime-cache")
	writeTestFile(t, filepath.Join(app, "python", "Lib", "__pycache__", "extra.pyc"), "extra-cache")
	writeTestFile(t, filepath.Join(app, "runtime", "user-output.json"), "keep-me")

	files := map[string][]byte{
		"KFPS.exe":                                          []byte("launcher"),
		"KloudysFH6Painter/VERSION":                         []byte("9.8.7\n"),
		"KloudysFH6Painter/python/python.exe":               []byte("python"),
		"KloudysFH6Painter/python/Lib/site.py":              []byte("site"),
		"KloudysFH6Painter/python/Lib/__pycache__/site.pyc": []byte("built-cache"),
		"KloudysFH6Painter/KFPS.UI/app.py":                  []byte("print('app')\n"),
		"KloudysFH6Painter/assets/app/KFPS Logo.json":       []byte("{}\n"),
	}
	release := ReleaseManifest{Schema: ReleaseSchema, Version: "9.8.7", Commit: strings.Repeat("a", 40), Kind: "recommended", SourceTimestampUTC: time.Now().UTC().Format(time.RFC3339)}
	for path, payload := range files {
		release.Files = append(release.Files, FileRecord{Path: path, Size: int64(len(payload)), SHA256: sha256Bytes(payload)})
	}
	sortFileRecords(release.Files)
	manifestPayload, _ := json.MarshalIndent(release, "", "  ")
	manifestPayload = append(manifestPayload, '\n')
	archive := filepath.Join(t.TempDir(), "recovery.zip")
	writeZip(t, archive, "KFPS-9.8.7/", files, map[string][]byte{"RELEASE-MANIFEST.json": manifestPayload})
	archiveInfo, _ := os.Stat(archive)
	archiveHash, _ := sha256File(archive)

	state := filepath.Join(t.TempDir(), "state")
	logger := testLogger(t, state, "recovery")
	engine, err := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.0",
		Layout:           Layout{InstallRoot: install, AppRoot: app},
		StateDir:         state,
		Logger:           logger,
		ForceRecovery:    true,
		RecoveryArchive:  archive,
		Recovery: RecoveryConfig{
			Version:        release.Version,
			Commit:         release.Commit,
			ManifestSHA256: sha256Bytes(manifestPayload),
			ManifestSize:   int64(len(manifestPayload)),
			Artifact:       Artifact{URL: "https://invalid.example/recovery.zip", Size: archiveInfo.Size(), SHA256: archiveHash},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	result, err := engine.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !result.Summary.Success || result.Summary.FilesReplaced == 0 || result.Summary.FilesRemoved != 1 {
		t.Fatalf("unexpected summary: %#v", result.Summary)
	}
	assertFileContent(t, filepath.Join(app, "VERSION"), "9.8.7\n")
	assertFileContent(t, filepath.Join(app, "python", "python.exe"), "python")
	assertFileContent(t, filepath.Join(app, "python", "Lib", "__pycache__", "site.pyc"), "runtime-cache")
	assertFileContent(t, filepath.Join(app, "python", "Lib", "__pycache__", "extra.pyc"), "extra-cache")
	assertFileContent(t, filepath.Join(app, "runtime", "user-output.json"), "keep-me")
	if _, err := os.Stat(filepath.Join(app, "python", "obsolete.pyd")); !os.IsNotExist(err) {
		t.Fatal("obsolete Python runtime file was not removed")
	}
	if _, err := os.Stat(filepath.Join(install, "RELEASE-MANIFEST.json")); err != nil {
		t.Fatal("pinned release manifest was not installed")
	}

	secondLogger := testLogger(t, state, "recovery-second")
	secondEngine, _ := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.0", Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state,
		Logger: secondLogger, ForceRecovery: true, RecoveryArchive: archive,
		Recovery: RecoveryConfig{Version: release.Version, Commit: release.Commit, ManifestSHA256: sha256Bytes(manifestPayload), ManifestSize: int64(len(manifestPayload)), Artifact: Artifact{URL: "https://invalid.example/recovery.zip", Size: archiveInfo.Size(), SHA256: archiveHash}},
	})
	second, err := secondEngine.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if second.Summary.FilesReplaced != 0 || second.Summary.FilesRemoved != 0 {
		t.Fatalf("healthy second recovery was not a no-op: %#v", second.Summary)
	}
}

func TestSignedComponentChannelUpdatesAndRepairs(t *testing.T) {
	publicKey, privateKey, _ := ed25519.GenerateKey(rand.Reader)
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeTestFile(t, filepath.Join(app, "runtime", "user.json"), "keep")
	writeTestFile(t, filepath.Join(app, "python", "old.pyd"), "old")
	writeTestFile(t, filepath.Join(app, "python", "Lib", "__pycache__", "generated.pyc"), "keep-cache")

	applicationFiles := map[string][]byte{"VERSION": []byte("2.0.0\n"), "KFPS.UI/app.py": []byte("new app")}
	pythonFiles := map[string][]byte{"python/python.exe": []byte("python-new"), "python/Lib/site.py": []byte("site-new")}
	serverFiles := map[string][]byte{}
	appRecords, appArchive := componentFixture(t, applicationFiles)
	pythonRecords, pythonArchive := componentFixture(t, pythonFiles)
	serverFiles["/application.zip"] = appArchive
	serverFiles["/python.zip"] = pythonArchive
	updaterPayload := []byte("updater-binary")
	serverFiles["/KFPS-Updater.exe"] = updaterPayload

	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		payload, ok := serverFiles[request.URL.Path]
		if !ok {
			http.NotFound(writer, request)
			return
		}
		writer.Header().Set("Content-Length", fmt.Sprint(len(payload)))
		_, _ = writer.Write(payload)
	}))
	defer server.Close()

	manifest := UpdateManifest{
		Schema: ManifestSchema, Channel: "stable", Sequence: 7, Version: "2.0.0", Commit: strings.Repeat("b", 40), PublishedUTC: time.Now().UTC().Format(time.RFC3339), Relaunch: "KFPS.exe",
		Components: []Component{
			{Name: "application", Target: "app-root", Archive: Artifact{URL: server.URL + "/application.zip", Size: int64(len(appArchive)), SHA256: sha256Bytes(appArchive)}, Files: appRecords},
			{Name: "python-runtime", Target: "app-root", Archive: Artifact{URL: server.URL + "/python.zip", Size: int64(len(pythonArchive)), SHA256: sha256Bytes(pythonArchive)}, Files: pythonRecords, ExactRoots: []string{"python"}},
		},
	}
	manifestPayload, _ := json.MarshalIndent(manifest, "", "  ")
	manifestPayload = append(manifestPayload, '\n')
	manifestSignature, _ := SignBytes(manifestPayload, privateKey)
	serverFiles["/manifest.json"] = manifestPayload
	serverFiles["/manifest.json.sig"] = append(manifestSignature, '\n')
	channel := Channel{
		Schema: ChannelSchema, Channel: "stable", Sequence: 7, PublishedUTC: time.Now().UTC().Format(time.RFC3339), MinimumBootstrap: "1.0.0",
		Updater:  UpdaterArtifact{Version: "1.0.0", Artifact: Artifact{URL: server.URL + "/KFPS-Updater.exe", Size: int64(len(updaterPayload)), SHA256: sha256Bytes(updaterPayload)}},
		Manifest: ManifestReference{Artifact: Artifact{URL: server.URL + "/manifest.json", Size: int64(len(manifestPayload)), SHA256: sha256Bytes(manifestPayload)}, SignatureURL: server.URL + "/manifest.json.sig"},
	}
	channelPayload, _ := json.MarshalIndent(channel, "", "  ")
	channelPayload = append(channelPayload, '\n')
	channelSignature, _ := SignBytes(channelPayload, privateKey)
	serverFiles["/channel.json"] = channelPayload
	serverFiles["/channel.json.sig"] = append(channelSignature, '\n')

	state := filepath.Join(t.TempDir(), "state")
	logger := testLogger(t, state, "channel")
	engine, err := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.1", ChannelURL: server.URL + "/channel.json", ChannelSignature: server.URL + "/channel.json.sig",
		TrustedKey: publicKey, Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state, Logger: logger,
		AllowLocalSources: true, DisableFallback: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	result, err := engine.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !result.Summary.Success || result.Summary.FilesRemoved != 1 {
		t.Fatalf("unexpected summary: %#v", result.Summary)
	}
	assertFileContent(t, filepath.Join(app, "VERSION"), "2.0.0\n")
	assertFileContent(t, filepath.Join(app, "python", "python.exe"), "python-new")
	assertFileContent(t, filepath.Join(app, "python", "Lib", "__pycache__", "generated.pyc"), "keep-cache")
	assertFileContent(t, filepath.Join(app, "runtime", "user.json"), "keep")
	if _, err := os.Stat(filepath.Join(app, "python", "old.pyd")); !os.IsNotExist(err) {
		t.Fatal("exact Python component left an obsolete file")
	}

	writeTestFile(t, filepath.Join(app, "KFPS.UI", "app.py"), "corrupt")
	repairLogger := testLogger(t, state, "channel-repair")
	repairEngine, _ := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.1", ChannelURL: server.URL + "/channel.json", ChannelSignature: server.URL + "/channel.json.sig",
		TrustedKey: publicKey, Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state, Logger: repairLogger,
		AllowLocalSources: true, DisableFallback: true,
	})
	repaired, err := repairEngine.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if repaired.Summary.FilesReplaced != 1 {
		t.Fatalf("expected one repaired file, got %#v", repaired.Summary)
	}
	assertFileContent(t, filepath.Join(app, "KFPS.UI", "app.py"), "new app")
}

func TestNewerBootstrapDoesNotHandoffToOlderUpdater(t *testing.T) {
	state := filepath.Join(t.TempDir(), "state")
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "2.0.0\n")
	current := filepath.Join(t.TempDir(), "KFPS-Updater.exe")
	writeTestFile(t, current, "newer-updater")
	engine, err := NewEngine(EngineConfig{
		BootstrapVersion:  "2.0.0",
		Layout:            Layout{InstallRoot: install, AppRoot: app},
		StateDir:          state,
		CurrentExecutable: current,
		Logger:            testLogger(t, state, "newer-bootstrap"),
	})
	if err != nil {
		t.Fatal(err)
	}
	handoff, err := engine.prepareSelfUpdate(context.Background(), Channel{
		MinimumBootstrap: "1.0.0",
		Updater: UpdaterArtifact{
			Version:  "1.0.0",
			Artifact: Artifact{URL: "https://invalid.example/old.exe", Size: 3, SHA256: sha256Bytes([]byte("old"))},
		},
	})
	if err != nil || handoff.Path != "" {
		t.Fatalf("newer bootstrap attempted a downgrade: path=%q err=%v", handoff, err)
	}
}

func TestVerifiedSelfUpdateHandoffIsReportedAsSuccessful(t *testing.T) {
	publicKey, privateKey, _ := ed25519.GenerateKey(rand.Reader)
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	current := filepath.Join(t.TempDir(), "KFPS-Updater.exe")
	writeTestFile(t, current, "old-updater")
	updaterPayload := []byte("new-updater")
	serverFiles := map[string][]byte{"/KFPS-Updater.exe": updaterPayload}
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		payload, ok := serverFiles[request.URL.Path]
		if !ok {
			http.NotFound(writer, request)
			return
		}
		writer.Header().Set("Content-Length", fmt.Sprint(len(payload)))
		_, _ = writer.Write(payload)
	}))
	defer server.Close()
	channel := Channel{
		Schema: ChannelSchema, Channel: "stable", Sequence: 1, PublishedUTC: time.Now().UTC().Format(time.RFC3339), MinimumBootstrap: "2.0.0",
		Updater:  UpdaterArtifact{Version: "2.0.0", Artifact: Artifact{URL: server.URL + "/KFPS-Updater.exe", Size: int64(len(updaterPayload)), SHA256: sha256Bytes(updaterPayload)}},
		Manifest: ManifestReference{Artifact: Artifact{URL: server.URL + "/manifest.json", Size: 1, SHA256: strings.Repeat("0", 64)}, SignatureURL: server.URL + "/manifest.json.sig"},
	}
	channelPayload, _ := json.MarshalIndent(channel, "", "  ")
	channelPayload = append(channelPayload, '\n')
	channelSignature, _ := SignBytes(channelPayload, privateKey)
	serverFiles["/channel.json"] = channelPayload
	serverFiles["/channel.json.sig"] = append(channelSignature, '\n')
	state := filepath.Join(t.TempDir(), "state")
	engine, err := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.0", ChannelURL: server.URL + "/channel.json", ChannelSignature: server.URL + "/channel.json.sig",
		TrustedKey: publicKey, Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state,
		CurrentExecutable: current, Logger: testLogger(t, state, "handoff"), AllowLocalSources: true, DisableFallback: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	result, err := engine.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if result.Handoff.Path == "" || result.Summary.Success || result.Summary.Status != "handoff-pending" {
		t.Fatalf("verified handoff had an ambiguous result: %#v", result)
	}
	assertFileContent(t, result.Handoff.Path, "new-updater")
}

func TestBadChannelSignatureLeavesInstallationUntouched(t *testing.T) {
	publicKey, _, _ := ed25519.GenerateKey(rand.Reader)
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if strings.HasSuffix(request.URL.Path, ".sig") {
			_, _ = writer.Write([]byte(`{"schema":"kfps.detached-signature.v1","algorithm":"ed25519","key_id":"wrong","signature":"bad"}`))
			return
		}
		_, _ = writer.Write([]byte(`{"schema":"kfps.update-channel.v1"}`))
	}))
	defer server.Close()
	state := filepath.Join(t.TempDir(), "state")
	engine, _ := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.0", ChannelURL: server.URL + "/channel", ChannelSignature: server.URL + "/channel.sig",
		TrustedKey: publicKey, Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state,
		Logger: testLogger(t, state, "bad-signature"), AllowLocalSources: true, DisableFallback: true,
	})
	if _, err := engine.Run(context.Background()); err == nil {
		t.Fatal("invalid signature was accepted")
	}
	assertFileContent(t, filepath.Join(app, "VERSION"), "1.0.0\n")
}

func TestSignedChannelSequenceRollbackIsRejected(t *testing.T) {
	publicKey, privateKey, _ := ed25519.GenerateKey(rand.Reader)
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "2.0.0\n")
	updaterPayload := []byte("updater")
	channel := Channel{
		Schema: ChannelSchema, Channel: "stable", Sequence: 7, PublishedUTC: time.Now().UTC().Format(time.RFC3339), MinimumBootstrap: "1.0.0",
		Updater:  UpdaterArtifact{Version: "1.0.0", Artifact: Artifact{URL: "https://example.invalid/updater.exe", Size: int64(len(updaterPayload)), SHA256: sha256Bytes(updaterPayload)}},
		Manifest: ManifestReference{Artifact: Artifact{URL: "https://example.invalid/manifest.json", Size: 1, SHA256: strings.Repeat("0", 64)}, SignatureURL: "https://example.invalid/manifest.json.sig"},
	}
	channelPayload, _ := json.MarshalIndent(channel, "", "  ")
	channelPayload = append(channelPayload, '\n')
	channelSignature, _ := SignBytes(channelPayload, privateKey)
	serverFiles := map[string][]byte{"/channel.json": channelPayload, "/channel.json.sig": append(channelSignature, '\n')}
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		payload, ok := serverFiles[request.URL.Path]
		if !ok {
			http.NotFound(writer, request)
			return
		}
		_, _ = writer.Write(payload)
	}))
	defer server.Close()
	state := filepath.Join(t.TempDir(), "state")
	statePayload, _ := json.Marshal(PersistentState{Schema: "kfps.update-state.v1", HighestSequence: 8, Version: "2.0.0"})
	if err := writeAtomic(filepath.Join(state, "state.json"), statePayload, 0o600); err != nil {
		t.Fatal(err)
	}
	engine, _ := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.1", ChannelURL: server.URL + "/channel.json", ChannelSignature: server.URL + "/channel.json.sig",
		TrustedKey: publicKey, Layout: Layout{InstallRoot: install, AppRoot: app}, StateDir: state,
		Logger: testLogger(t, state, "rollback-sequence"), AllowLocalSources: true, DisableFallback: true,
	})
	if _, err := engine.Run(context.Background()); err == nil || !strings.Contains(err.Error(), "rollback") {
		t.Fatalf("older signed sequence was accepted: %v", err)
	}
}

func TestPinnedRecoveryRejectsDirectSourceLayout(t *testing.T) {
	root := t.TempDir()
	writeTestFile(t, filepath.Join(root, "VERSION"), "3.1.54\n")
	if err := os.MkdirAll(filepath.Join(root, "KFPS.UI"), 0o755); err != nil {
		t.Fatal(err)
	}
	state := filepath.Join(t.TempDir(), "state")
	engine, _ := NewEngine(EngineConfig{
		BootstrapVersion: "1.0.0", Layout: Layout{InstallRoot: root, AppRoot: root}, StateDir: state,
		Logger: testLogger(t, state, "direct-source"), ForceRecovery: true, Recovery: RecoveryConfig{Version: "3.1.54"},
	})
	if _, err := engine.Run(context.Background()); err == nil || !strings.Contains(err.Error(), "packaged KFPS layouts") {
		t.Fatalf("release recovery accepted a source layout: %v", err)
	}
}

func componentFixture(t *testing.T, files map[string][]byte) ([]FileRecord, []byte) {
	t.Helper()
	records := make([]FileRecord, 0, len(files))
	for path, payload := range files {
		records = append(records, FileRecord{Path: path, Size: int64(len(payload)), SHA256: sha256Bytes(payload)})
	}
	sortFileRecords(records)
	path := filepath.Join(t.TempDir(), "component.zip")
	writeZip(t, path, "", files, nil)
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return records, payload
}

func writeZip(t *testing.T, path, prefix string, files map[string][]byte, extra map[string][]byte) {
	t.Helper()
	output, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	archive := zip.NewWriter(output)
	all := map[string][]byte{}
	for name, payload := range files {
		all[prefix+filepath.ToSlash(name)] = payload
	}
	for name, payload := range extra {
		all[prefix+filepath.ToSlash(name)] = payload
	}
	names := make([]string, 0, len(all))
	for name := range all {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		header := &zip.FileHeader{Name: name, Method: zip.Deflate}
		header.SetModTime(time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC))
		writer, err := archive.CreateHeader(header)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := writer.Write(all[name]); err != nil {
			t.Fatal(err)
		}
	}
	if err := archive.Close(); err != nil {
		t.Fatal(err)
	}
	if err := output.Close(); err != nil {
		t.Fatal(err)
	}
}

func sortFileRecords(records []FileRecord) {
	sort.Slice(records, func(left, right int) bool { return records[left].Path < records[right].Path })
}

func writeTestFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func testLogger(t *testing.T, state, name string) *Logger {
	t.Helper()
	logger, err := NewLogger(filepath.Join(state, "logs"), name, io.Discard)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = logger.Close() })
	return logger
}
