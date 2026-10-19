package bootstrap

import (
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestStudioPathsAndPersonalStateBoundaries(t *testing.T) {
	application := Component{Name: "application", Target: "app-root"}
	for _, name := range []string{
		"imgs/livery-projects/toyota-1/projects/project.json",
		"imgs/livery-projects/toyota-1/recovery/recovery.sqlite3",
		"tools/livery-studio/settings/local-launch.json",
		"tools/livery-studio/settings/confirmations.json",
		"tools/livery-studio/recovery/legacy.sqlite3",
		"tools/livery-studio/runs/studio-browser/Default/Preferences",
		"tools/livery-studio/runs/studio-launch/instance.json",
		"tools/livery-studio/runs/diagnostics/studio.jsonl",
		"tools/livery-studio/runs/component-converter/gr86/car.glb",
		"tools/livery-studio/runs/component-converter/converter/publish/unreviewed.exe",
	} {
		if err := validateComponentPath(application, name); err == nil {
			t.Errorf("accepted private Studio destination %s", name)
		}
	}
	for _, name := range []string{
		"tools/livery-studio/src/kfps_livery_lab/launcher.py",
		"tools/livery-studio/runs/component-converter/converter/build-manifest.json",
		"tools/livery-studio/runs/component-converter/converter/publish/Kfps.LiveryLab.Converter.exe",
	} {
		if err := validateComponentPath(application, name); err != nil {
			t.Errorf("rejected program-owned Studio destination %s: %v", name, err)
		}
	}
	outer := Component{Name: "native-launchers", Target: "install-root"}
	if err := validateComponentPath(outer, "KFPSLiverySudio.exe"); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"other.exe", "sub/KFPSLiverySudio.exe", "../KFPSLiverySudio.exe"} {
		if err := validateComponentPath(outer, name); err == nil {
			t.Errorf("accepted arbitrary outer executable %s", name)
		}
	}
}

func TestStudioLauncherRequiresNewBootstrapContract(t *testing.T) {
	stamp := time.Now().UTC().Format(time.RFC3339)
	artifact := Artifact{URL: "https://updates.example.invalid/component.zip", SHA256: strings.Repeat("a", 64), Size: 1}
	channel := Channel{Schema: ChannelSchema, Channel: "stable", Sequence: 1, PublishedUTC: stamp,
		MinimumBootstrap: "1.0.5", Manifest: ManifestReference{Artifact: artifact, SignatureURL: "https://updates.example.invalid/manifest.sig"},
		Updater: UpdaterArtifact{Version: "1.0.5", Artifact: artifact}}
	manifest := UpdateManifest{Schema: ManifestSchema, Channel: "stable", Sequence: 1, PublishedUTC: stamp,
		Version: "3.1.105", Commit: strings.Repeat("b", 40), Components: []Component{{
			Name: "native-launchers", Target: "install-root", Archive: artifact,
			Files: []FileRecord{{Path: "KFPSLiverySudio.exe", Size: 1, SHA256: strings.Repeat("a", 64)}},
		}}}
	if err := ValidatePublishedContract(channel, manifest); err != nil {
		t.Fatal(err)
	}
	channel.MinimumBootstrap = "1.0.4"
	if err := ValidatePublishedContract(channel, manifest); err == nil || !strings.Contains(err.Error(), "minimum bootstrap 1.0.5") {
		t.Fatalf("accepted incompatible Studio bootstrap: %v", err)
	}
}

func TestStudioLauncherActivationOrder(t *testing.T) {
	root := t.TempDir()
	app := filepath.Join(root, "KloudysFH6Painter")
	changes := []Change{
		{Destination: filepath.Join(root, "KFPS-Updater.exe")},
		{Destination: filepath.Join(root, "KFPSLiverySudio.exe")},
		{Destination: filepath.Join(app, "KFPSLiverySudio.exe")},
		{Destination: filepath.Join(app, "tools", "livery-studio", "src", "launch_studio.py")},
	}
	sortChanges(changes, root)
	want := []string{
		filepath.Join(app, "tools", "livery-studio", "src", "launch_studio.py"),
		filepath.Join(app, "KFPSLiverySudio.exe"), filepath.Join(root, "KFPSLiverySudio.exe"),
		filepath.Join(root, "KFPS-Updater.exe"),
	}
	for i := range want {
		if changes[i].Destination != want[i] {
			t.Fatalf("activation order: %#v", changes)
		}
	}
}
