package bootstrap

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestResolveLayoutFromReleaseRootAndAppRoot(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	if err := os.MkdirAll(app, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(app, "VERSION"), []byte("3.1.54\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	fromInstall, err := ResolveLayout(install, "", "")
	if err != nil {
		t.Fatal(err)
	}
	fromApp, err := ResolveLayout(app, "", "")
	if err != nil {
		t.Fatal(err)
	}
	if fromInstall != fromApp || fromInstall.InstallRoot != install || fromInstall.AppRoot != app {
		t.Fatalf("unexpected layouts: %#v %#v", fromInstall, fromApp)
	}
}

func TestResolveLayoutRejectsArbitraryExplicitDirectory(t *testing.T) {
	invalid := t.TempDir()
	valid := t.TempDir()
	writeTestFile(t, filepath.Join(valid, "VERSION"), "1.0.0\n")
	if err := os.MkdirAll(filepath.Join(valid, "KFPS.UI"), 0o755); err != nil {
		t.Fatal(err)
	}
	if _, err := ResolveLayout(invalid, "", valid); err == nil {
		t.Fatal("an arbitrary directory was accepted as a KFPS installation")
	}
}

func TestResolveLayoutAcceptsBrokenPackageWithBootstrapMarker(t *testing.T) {
	install := t.TempDir()
	writeTestFile(t, filepath.Join(install, "KFPS-Updater.exe"), "bootstrap")
	layout, err := ResolveLayout(install, "", "")
	if err != nil {
		t.Fatal(err)
	}
	if layout.InstallRoot != install || layout.AppRoot != filepath.Join(install, "KloudysFH6Painter") {
		t.Fatalf("unexpected recovery layout: %#v", layout)
	}
}

func TestResolveLayoutTreatsExplicitLegacyFlatRootAsIncompletePackage(t *testing.T) {
	install := t.TempDir()
	writeTestFile(t, filepath.Join(install, "KFPS-Updater.exe"), "bootstrap")
	writeTestFile(t, filepath.Join(install, "VERSION"), "1.6.1\n")
	writeTestFile(t, filepath.Join(install, "app.py"), "print('legacy')\n")

	layout, err := ResolveLayout(install, "", "")
	if err != nil {
		t.Fatal(err)
	}
	if layout.InstallRoot != install || layout.AppRoot != filepath.Join(install, "KloudysFH6Painter") {
		t.Fatalf("legacy flat package resolved incorrectly: %#v", layout)
	}
}

func TestResolveLayoutKeepsExplicitModernSourceLayout(t *testing.T) {
	root := t.TempDir()
	writeTestFile(t, filepath.Join(root, "KFPS-Updater.exe"), "bootstrap")
	writeTestFile(t, filepath.Join(root, "VERSION"), "3.1.54\n")
	if err := os.MkdirAll(filepath.Join(root, "KFPS.UI"), 0o755); err != nil {
		t.Fatal(err)
	}

	layout, err := ResolveLayout(root, "", "")
	if err != nil {
		t.Fatal(err)
	}
	if layout.InstallRoot != root || layout.AppRoot != root {
		t.Fatalf("modern source layout resolved incorrectly: %#v", layout)
	}
}

func TestUpdaterStateMustBeSeparateFromInstall(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	if err := os.MkdirAll(app, 0o755); err != nil {
		t.Fatal(err)
	}
	layout := Layout{InstallRoot: install, AppRoot: app}
	for _, state := range []string{install, app, filepath.Join(app, "runtime", "updater"), filepath.Dir(install)} {
		if _, err := ValidateUpdaterStateDir(state, layout); err == nil {
			t.Fatalf("unsafe updater state directory was accepted: %s", state)
		}
	}
	safe := filepath.Join(t.TempDir(), "state")
	if resolved, err := ValidateUpdaterStateDir(safe, layout); err != nil || resolved == "" {
		t.Fatalf("separate updater state was rejected: %q %v", resolved, err)
	}
}

func TestContainedPathsRejectTraversal(t *testing.T) {
	root := t.TempDir()
	for _, value := range []string{"../escape", "/absolute", "C:/absolute", "safe/../../escape", `safe\file.txt`, "safe//file.txt", "safe/./file.txt"} {
		if _, err := joinContained(root, value); err == nil {
			t.Fatalf("unsafe path accepted: %s", value)
		}
	}
	path, err := joinContained(root, "safe/file.txt")
	if err != nil || path != filepath.Join(root, "safe", "file.txt") {
		t.Fatalf("safe path failed: %s %v", path, err)
	}
}

func TestContainedPathsRejectWindowsDeviceAndInvalidNames(t *testing.T) {
	root := t.TempDir()
	for _, value := range []string{"CON", "NUL.txt", "safe/COM1.log", "bad?.txt", "trailing./file", "safe/space ", "control\x01.txt"} {
		if _, err := joinContained(root, value); err == nil {
			t.Fatalf("Windows-incompatible path accepted: %q", value)
		}
	}
}

func TestComponentCannotOverwriteUserData(t *testing.T) {
	component := Component{Name: "application", Target: "app-root"}
	for _, value := range []string{"runtime", "runtime/log.txt", "imgs", "imgs/generated.json", "webui-data", "webui-data/token", "node_modules", ".wrangler", ".venv", "user.kfpskey", ".git", ".git/config", "python/python.exe"} {
		if err := validateComponentPath(component, value); err == nil {
			t.Fatalf("protected path accepted: %s", value)
		}
	}
	python := Component{Name: "python-runtime", Target: "app-root"}
	if err := validateComponentPath(python, "python/python.exe"); err != nil {
		t.Fatalf("python runtime path rejected: %v", err)
	}
}

func TestExpectedFileDirectoryRequiresManualRemediation(t *testing.T) {
	destination := filepath.Join(t.TempDir(), "program.py")
	if err := os.MkdirAll(destination, 0o755); err != nil {
		t.Fatal(err)
	}
	record := FileRecord{Path: "program.py", Size: 1, SHA256: sha256Bytes([]byte("x"))}
	if _, err := fileNeedsRepair(destination, record); err == nil || !strings.Contains(err.Error(), "manual remediation") {
		t.Fatalf("non-regular destination was not reported precisely: %v", err)
	}
}

func TestCrossComponentRemovalCollisionFailsBeforeDownload(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeTestFile(t, filepath.Join(app, "retired.txt"), "old")
	artifact := Artifact{URL: "https://example.invalid/component.zip", Size: 1, SHA256: strings.Repeat("0", 64)}
	manifest := UpdateManifest{Version: "1.0.0", Sequence: 1, Components: []Component{
		{Name: "first", Target: "app-root", Archive: artifact, Files: []FileRecord{{Path: "first.txt", Size: 1, SHA256: strings.Repeat("1", 64)}}, RetiredFiles: []string{"retired.txt"}},
		{Name: "second", Target: "app-root", Archive: artifact, Files: []FileRecord{{Path: "second.txt", Size: 1, SHA256: strings.Repeat("2", 64)}}, RetiredFiles: []string{"retired.txt"}},
	}}
	state := t.TempDir()
	logger := testLogger(t, state, "removal-collision")
	downloader := NewDownloader(logger, false)
	_, err := PrepareComponentUpdate(context.Background(), downloader, manifest, filepath.Join(state, "stage"), Layout{InstallRoot: install, AppRoot: app}, logger)
	if err == nil || !strings.Contains(err.Error(), "collision") {
		t.Fatalf("cross-component removal collision was accepted: %v", err)
	}
	if downloader.Bytes != 0 {
		t.Fatalf("collision was detected after downloading %d bytes", downloader.Bytes)
	}
}

func TestComponentCannotInstallAndRetireSamePath(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	writeTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	record := FileRecord{Path: "VERSION", Size: int64(len("1.0.0\n")), SHA256: sha256Bytes([]byte("1.0.0\n"))}
	manifest := UpdateManifest{
		Version: "1.0.0", Sequence: 1,
		Components: []Component{{
			Name: "application", Target: "app-root",
			Archive: Artifact{URL: "https://example.invalid/application.zip", Size: 1, SHA256: strings.Repeat("0", 64)},
			Files:   []FileRecord{record}, RetiredFiles: []string{"VERSION"},
		}},
	}
	logger := testLogger(t, filepath.Join(t.TempDir(), "state"), "install-retire-collision")
	if _, err := PrepareComponentUpdate(context.Background(), NewDownloader(logger, false), manifest, filepath.Join(t.TempDir(), "stage"), Layout{InstallRoot: install, AppRoot: app}, logger); err == nil || !strings.Contains(err.Error(), "collision") {
		t.Fatalf("install/retire collision was accepted: %v", err)
	}
}
