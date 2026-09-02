package main

import (
	"archive/zip"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/heyitshestia/kloudys-forza-painter-suite/tools/bootstrap_updater/internal/bootstrap"
)

func TestMain(testingMain *testing.M) {
	if os.Getenv("KFPS_TEST_UPDATER_HELPER") == "1" {
		fmt.Printf("{\"schema\":\"kfps.bootstrap-build.v1\",\"version\":%q,\"key_id\":%q,\"platform\":\"windows/amd64\"}\n", os.Getenv("KFPS_TEST_UPDATER_VERSION"), os.Getenv("KFPS_TEST_UPDATER_KEY_ID"))
		os.Exit(0)
	}
	os.Exit(testingMain.Run())
}

func TestBuildPayloadCreatesSignedSeparatedComponents(t *testing.T) {
	root := t.TempDir()
	app := filepath.Join(root, "app")
	python := filepath.Join(root, "python-source")
	output := filepath.Join(root, "payload")
	updater := filepath.Join(root, "KFPS-Updater.exe")
	privatePath := filepath.Join(root, "private.key")
	publicPath := filepath.Join(root, "public.key")

	writeBuildTestFile(t, filepath.Join(app, "VERSION"), "4.5.6\n")
	writeBuildTestFile(t, filepath.Join(app, "KFPS.exe"), "launcher")
	writeBuildTestFile(t, filepath.Join(app, "KFPS.UI", "app.py"), "app")
	writeBuildTestFile(t, filepath.Join(app, "03_update_from_github.bat"), "legacy updater")
	writeBuildTestFile(t, filepath.Join(app, "update_from_github.bat"), "legacy wrapper")
	writeBuildTestFile(t, filepath.Join(app, "runtime", "user.json"), "preserve")
	writeBuildTestFile(t, filepath.Join(app, "secret.kfpskey"), "preserve")
	writeBuildTestFile(t, filepath.Join(python, "python.exe"), "python")
	writeBuildTestFile(t, filepath.Join(python, "Lib", "site.py"), "site")
	writeBuildTestFile(t, filepath.Join(python, "Lib", "__pycache__", "site.pyc"), "cache")

	runGit(t, app, "init", "-b", "main")
	runGit(t, app, "config", "user.name", "KFPS Test")
	runGit(t, app, "config", "user.email", "test@example.invalid")
	runGit(t, app, "config", "core.autocrlf", "false")
	runGit(t, app, "add", ".")
	runGit(t, app, "commit", "-m", "fixture")
	commit := strings.TrimSpace(runGit(t, app, "rev-parse", "HEAD"))

	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	writeBuildTestFile(t, privatePath, bootstrap.EncodePrivateKey(privateKey)+"\n")
	writeBuildTestFile(t, publicPath, bootstrap.EncodePublicKey(publicKey)+"\n")
	writeBuildTestUpdater(t, updater, "1.0.0", bootstrap.KeyID(publicKey))
	err = buildPayload([]string{
		"--app-root", app,
		"--python-root", python,
		"--updater", updater,
		"--private", privatePath,
		"--public", publicPath,
		"--output", output,
		"--base-url", "https://updates.example.invalid/stable",
		"--version", "4.5.6",
		"--commit", commit,
		"--bootstrap-version", "1.0.0",
		"--sequence", "42",
		"--published-utc", "2026-09-01T12:00:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}

	channelPayload := readBuildTestFile(t, filepath.Join(output, "channel.json"))
	channelSignature := readBuildTestFile(t, filepath.Join(output, "channel.json.sig"))
	if err := bootstrap.VerifyBytes(channelPayload, channelSignature, publicKey); err != nil {
		t.Fatal(err)
	}
	var channel bootstrap.Channel
	if err := json.Unmarshal(channelPayload, &channel); err != nil {
		t.Fatal(err)
	}
	if channel.Sequence != 42 || channel.Updater.Version != "1.0.0" {
		t.Fatalf("unexpected channel: %#v", channel)
	}
	manifestPath := filepath.Join(output, "kfps-update-4.5.6.json")
	manifestPayload := readBuildTestFile(t, manifestPath)
	manifestSignature := readBuildTestFile(t, manifestPath+".sig")
	if err := bootstrap.VerifyBytes(manifestPayload, manifestSignature, publicKey); err != nil {
		t.Fatal(err)
	}
	var manifest bootstrap.UpdateManifest
	if err := json.Unmarshal(manifestPayload, &manifest); err != nil {
		t.Fatal(err)
	}
	if len(manifest.Components) != 3 {
		t.Fatalf("expected three components, got %d", len(manifest.Components))
	}
	applicationNames := zipNames(t, filepath.Join(output, "kfps-4.5.6-application.zip"))
	if !applicationNames["KFPS.UI/app.py"] || !applicationNames["VERSION"] || !applicationNames["KFPS-Updater.exe"] || applicationNames["runtime/user.json"] || applicationNames["secret.kfpskey"] {
		t.Fatalf("application component has wrong inventory: %#v", applicationNames)
	}
	if applicationNames["03_update_from_github.bat"] || applicationNames["update_from_github.bat"] {
		t.Fatalf("legacy BAT updaters leaked into the signed component: %#v", applicationNames)
	}
	application := manifest.Components[0]
	if !containsBuildString(application.RetiredFiles, "03_update_from_github.bat") || !containsBuildString(application.RetiredFiles, "update_from_github.bat") {
		t.Fatalf("signed application component does not retire both legacy BAT updaters: %#v", application.RetiredFiles)
	}
	pythonNames := zipNames(t, filepath.Join(output, "kfps-4.5.6-python-runtime.zip"))
	if !pythonNames["python/python.exe"] || !pythonNames["python/Lib/site.py"] || pythonNames["python/Lib/__pycache__/site.pyc"] {
		t.Fatalf("Python component has wrong inventory: %#v", pythonNames)
	}
	if _, err := os.Stat(filepath.Join(output, "SHA256SUMS.txt")); err != nil {
		t.Fatal("checksum inventory was not generated")
	}
}

func TestVersionFilePayloadAcceptsOneNativeLineEnding(t *testing.T) {
	tests := []struct {
		name    string
		payload string
		valid   bool
	}{
		{name: "lf", payload: "3.1.54\n", valid: true},
		{name: "crlf", payload: "3.1.54\r\n", valid: true},
		{name: "missing line ending", payload: "3.1.54", valid: false},
		{name: "extra line", payload: "3.1.54\n\n", valid: false},
		{name: "leading whitespace", payload: " 3.1.54\n", valid: false},
		{name: "trailing whitespace", payload: "3.1.54 \n", valid: false},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if actual := validVersionFilePayload([]byte(test.payload), "3.1.54"); actual != test.valid {
				t.Fatalf("validVersionFilePayload(%q) = %v; want %v", test.payload, actual, test.valid)
			}
		})
	}
}

func containsBuildString(values []string, expected string) bool {
	for _, value := range values {
		if strings.EqualFold(value, expected) {
			return true
		}
	}
	return false
}

func TestBuildPayloadRejectsVersionMismatch(t *testing.T) {
	root := t.TempDir()
	app := filepath.Join(root, "app")
	writeBuildTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeBuildTestFile(t, filepath.Join(app, "KFPS.exe"), "launcher")
	writeBuildTestFile(t, filepath.Join(root, "python", "python.exe"), "python")
	writeBuildTestFile(t, filepath.Join(root, "KFPS-Updater.exe"), "updater")
	runGit(t, app, "init", "-b", "main")
	runGit(t, app, "config", "user.name", "KFPS Test")
	runGit(t, app, "config", "user.email", "test@example.invalid")
	runGit(t, app, "config", "core.autocrlf", "false")
	runGit(t, app, "add", ".")
	runGit(t, app, "commit", "-m", "fixture")
	err := buildPayload([]string{
		"--app-root", app, "--python-root", filepath.Join(root, "python"), "--updater", filepath.Join(root, "KFPS-Updater.exe"),
		"--private", filepath.Join(root, "private.key"), "--public", filepath.Join(root, "public.key"),
		"--output", filepath.Join(root, "payload"), "--base-url", "https://updates.example.invalid/stable",
		"--version", "9.9.9", "--sequence", "1",
	})
	if err == nil || !strings.Contains(err.Error(), "does not match packaged VERSION") {
		t.Fatalf("publisher accepted mismatched release identity: %v", err)
	}
}

func TestBuildPayloadRejectsModifiedTrackedFiles(t *testing.T) {
	root := t.TempDir()
	app := filepath.Join(root, "app")
	python := filepath.Join(root, "python")
	updater := filepath.Join(root, "KFPS-Updater.exe")
	privatePath := filepath.Join(root, "private.key")
	publicPath := filepath.Join(root, "public.key")
	writeBuildTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeBuildTestFile(t, filepath.Join(app, "KFPS.exe"), "launcher")
	writeBuildTestFile(t, filepath.Join(python, "python.exe"), "python")
	writeBuildTestFile(t, updater, "updater")
	runGit(t, app, "init", "-b", "main")
	runGit(t, app, "config", "user.name", "KFPS Test")
	runGit(t, app, "config", "user.email", "test@example.invalid")
	runGit(t, app, "config", "core.autocrlf", "false")
	runGit(t, app, "add", ".")
	runGit(t, app, "commit", "-m", "fixture")
	writeBuildTestFile(t, filepath.Join(app, "VERSION"), "1.0.1\n")
	publicKey, privateKey, _ := ed25519.GenerateKey(rand.Reader)
	writeBuildTestFile(t, privatePath, bootstrap.EncodePrivateKey(privateKey)+"\n")
	writeBuildTestFile(t, publicPath, bootstrap.EncodePublicKey(publicKey)+"\n")
	err := buildPayload([]string{
		"--app-root", app, "--python-root", python, "--updater", updater,
		"--private", privatePath, "--public", publicPath,
		"--output", filepath.Join(root, "payload"),
		"--base-url", "https://updates.example.invalid/stable",
		"--version", "1.0.1", "--sequence", "1",
	})
	if err == nil || !strings.Contains(err.Error(), "modified tracked files") {
		t.Fatalf("dirty release source was accepted: %v", err)
	}
}

func TestSignOverwriteReplacesExistingSignature(t *testing.T) {
	root := t.TempDir()
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	privatePath := filepath.Join(root, "private.key")
	inputPath := filepath.Join(root, "payload.json")
	outputPath := filepath.Join(root, "payload.json.sig")
	writeBuildTestFile(t, privatePath, bootstrap.EncodePrivateKey(privateKey)+"\n")
	writeBuildTestFile(t, inputPath, "signed payload\n")
	writeBuildTestFile(t, outputPath, "old signature\n")
	if err := sign([]string{"--private", privatePath, "--input", inputPath, "--output", outputPath, "--overwrite"}); err != nil {
		t.Fatal(err)
	}
	if err := bootstrap.VerifyBytes(readBuildTestFile(t, inputPath), readBuildTestFile(t, outputPath), publicKey); err != nil {
		t.Fatalf("replacement signature did not verify: %v", err)
	}
}

func TestBuildPayloadRejectsMismatchedUpdaterIdentity(t *testing.T) {
	root := t.TempDir()
	app := filepath.Join(root, "app")
	python := filepath.Join(root, "python")
	privatePath := filepath.Join(root, "private.key")
	publicPath := filepath.Join(root, "public.key")
	writeBuildTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeBuildTestFile(t, filepath.Join(app, "KFPS.exe"), "launcher")
	writeBuildTestFile(t, filepath.Join(python, "python.exe"), "python")
	runGit(t, app, "init", "-b", "main")
	runGit(t, app, "config", "user.name", "KFPS Test")
	runGit(t, app, "config", "user.email", "test@example.invalid")
	runGit(t, app, "config", "core.autocrlf", "false")
	runGit(t, app, "add", ".")
	runGit(t, app, "commit", "-m", "fixture")
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	writeBuildTestFile(t, privatePath, bootstrap.EncodePrivateKey(privateKey)+"\n")
	writeBuildTestFile(t, publicPath, bootstrap.EncodePublicKey(publicKey)+"\n")

	for _, test := range []struct {
		name, updaterVersion, keyID, expected string
	}{
		{name: "version", updaterVersion: "0.9.0", keyID: bootstrap.KeyID(publicKey), expected: "reports version"},
		{name: "key", updaterVersion: "1.0.0", keyID: "0000000000000000", expected: "trusts key"},
	} {
		t.Run(test.name, func(t *testing.T) {
			updater := filepath.Join(root, "updater-"+test.name+".exe")
			writeBuildTestUpdater(t, updater, test.updaterVersion, test.keyID)
			err := buildPayload([]string{
				"--app-root", app, "--python-root", python, "--updater", updater,
				"--private", privatePath, "--public", publicPath,
				"--output", filepath.Join(root, "payload-"+test.name),
				"--base-url", "https://updates.example.invalid/stable",
				"--version", "1.0.0", "--bootstrap-version", "1.0.0", "--sequence", "1",
			})
			if err == nil || !strings.Contains(err.Error(), test.expected) {
				t.Fatalf("mismatched updater identity was accepted: %v", err)
			}
		})
	}
}

func runGit(t *testing.T, directory string, arguments ...string) string {
	t.Helper()
	command := exec.Command("git", append([]string{"-C", directory}, arguments...)...)
	payload, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v failed: %v\n%s", arguments, err, payload)
	}
	return string(payload)
}

func writeBuildTestFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func writeBuildTestUpdater(t *testing.T, path, version, keyID string) {
	t.Helper()
	current, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	input, err := os.Open(current)
	if err != nil {
		t.Fatal(err)
	}
	defer input.Close()
	output, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o755)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := io.Copy(output, input); err != nil {
		output.Close()
		t.Fatal(err)
	}
	if err := output.Close(); err != nil {
		t.Fatal(err)
	}
	t.Setenv("KFPS_TEST_UPDATER_HELPER", "1")
	t.Setenv("KFPS_TEST_UPDATER_VERSION", version)
	t.Setenv("KFPS_TEST_UPDATER_KEY_ID", keyID)
}

func readBuildTestFile(t *testing.T, path string) []byte {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return payload
}

func zipNames(t *testing.T, path string) map[string]bool {
	t.Helper()
	archive, err := zip.OpenReader(path)
	if err != nil {
		t.Fatal(err)
	}
	defer archive.Close()
	names := map[string]bool{}
	for _, entry := range archive.File {
		names[entry.Name] = true
	}
	return names
}
