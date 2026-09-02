package main

import (
	"io"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/heyitshestia/kloudys-forza-painter-suite/tools/bootstrap_updater/internal/bootstrap"
)

func TestProductionOptionsRejectCustomTrustInputs(t *testing.T) {
	t.Setenv("KFPS_UPDATER_TEST_MODE", "")
	for _, arguments := range [][]string{
		{"--channel-url", "https://example.invalid/channel.json"},
		{"--channel-signature-url", "https://example.invalid/channel.sig"},
		{"--state-dir", filepath.Join(t.TempDir(), "state")},
		{"--allow-sequence-reset"},
	} {
		if _, err := parseOptions(arguments); err == nil {
			t.Fatalf("production accepted test-only arguments: %v", arguments)
		}
	}
}

func TestTestModeAcceptsLocalHarnessOptions(t *testing.T) {
	previous := testFeatures
	testFeatures = "enabled"
	t.Cleanup(func() { testFeatures = previous })
	t.Setenv("KFPS_UPDATER_TEST_MODE", "1")
	state := filepath.Join(t.TempDir(), "state")
	parsed, err := parseOptions([]string{
		"--channel-url", "http://127.0.0.1:9999/channel.json",
		"--channel-signature-url", "http://127.0.0.1:9999/channel.json.sig",
		"--state-dir", state,
		"--allow-sequence-reset",
		"--check",
	})
	if err != nil {
		t.Fatal(err)
	}
	if parsed.stateDir != state || !parsed.allowSequenceReset || !parsed.dryRun {
		t.Fatalf("test options were not preserved: %#v", parsed)
	}
}

func TestOptionsRejectNegativeWaitPIDAndUnexpectedArguments(t *testing.T) {
	previous := testFeatures
	testFeatures = "enabled"
	t.Cleanup(func() { testFeatures = previous })
	t.Setenv("KFPS_UPDATER_TEST_MODE", "1")
	if _, err := parseOptions([]string{"--wait-pid", "-1"}); err == nil {
		t.Fatal("negative wait PID was accepted")
	}
	if _, err := parseOptions([]string{"unexpected"}); err == nil {
		t.Fatal("unexpected positional argument was accepted")
	}
}

func TestProductionHasNoMinimumBootstrapBypassFlag(t *testing.T) {
	t.Setenv("KFPS_UPDATER_TEST_MODE", "")
	if _, err := parseOptions([]string{"--skip-self-update"}); err == nil {
		t.Fatal("production accepted the removed minimum-bootstrap bypass")
	}
}

func TestHandoffCarriesResolvedPackageContextAndParentPID(t *testing.T) {
	layout := bootstrap.Layout{InstallRoot: `C:\KFPS Package`, AppRoot: `C:\KFPS Package\KloudysFH6Painter`}
	actual := buildHandoffArguments([]string{
		"--root", `C:\wrong`, `--state-dir=C:\wrong-state`, "--wait-pid", "99",
		"--channel-url", "http://127.0.0.1/channel.json", "--no-pause", "--check",
	}, layout, `C:\State Path`, 1234, true, true)
	expected := []string{
		"--channel-url", "http://127.0.0.1/channel.json", "--check",
		"--root", layout.InstallRoot, "--state-dir", `C:\State Path`, "--wait-pid", "1234", "--no-pause",
	}
	if !reflect.DeepEqual(actual, expected) {
		t.Fatalf("handoff context mismatch:\nactual:   %#v\nexpected: %#v", actual, expected)
	}
}

func TestCheckExitCodeDistinguishesHealthyAndRepairable(t *testing.T) {
	if code := checkExitCode(bootstrap.RunSummary{}); code != 0 {
		t.Fatalf("healthy check returned %d", code)
	}
	for _, summary := range []bootstrap.RunSummary{{FilesPlannedReplaced: 1}, {FilesPlannedRemoved: 1}} {
		if code := checkExitCode(summary); code != 3 {
			t.Fatalf("repairable check returned %d", code)
		}
	}
}

func TestWaitedHandoffPropagatesChildExitWithoutParentWait(t *testing.T) {
	previous := launchHandoff
	t.Cleanup(func() { launchHandoff = previous })
	waited := false
	var arguments []string
	launchHandoff = func(_ bootstrap.HandoffArtifact, actual []string, _ string, _ io.Reader, _, _ io.Writer, wait bool) (int, error) {
		waited = wait
		arguments = append([]string(nil), actual...)
		return 3, nil
	}
	layout := bootstrap.Layout{InstallRoot: `C:\KFPS`, AppRoot: `C:\KFPS\KloudysFH6Painter`}
	exitCode, err := startHandoff(bootstrap.HandoffArtifact{Path: `C:\state\handoff.exe`}, []string{"--check", "--relaunch"}, layout, `C:\state`, 42, true, true)
	if err != nil || exitCode != 3 || !waited {
		t.Fatalf("waited handoff did not propagate exit 3: code=%d waited=%v err=%v", exitCode, waited, err)
	}
	if strings.Contains(strings.Join(arguments, " "), "--wait-pid") {
		t.Fatalf("synchronous check handoff still waits for its parent: %#v", arguments)
	}
}

func TestMutatingHandoffUsesDistinctPendingExitCode(t *testing.T) {
	if handoffPendingExitCode == 0 || handoffPendingExitCode == 1 || handoffPendingExitCode == 2 || handoffPendingExitCode == 3 {
		t.Fatalf("handoff pending code collides with terminal updater exits: %d", handoffPendingExitCode)
	}
}
