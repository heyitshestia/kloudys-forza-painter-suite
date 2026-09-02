package bootstrap

import (
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestTransactionRollsBackEarlierReplacement(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	if err := os.MkdirAll(app, 0o755); err != nil {
		t.Fatal(err)
	}
	first := filepath.Join(app, "first.txt")
	second := filepath.Join(app, "second.txt")
	staged := filepath.Join(t.TempDir(), "first.txt")
	if err := os.WriteFile(first, []byte("old-first"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(second, []byte("old-second"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(staged, []byte("new-first"), 0o644); err != nil {
		t.Fatal(err)
	}
	logger, err := NewLogger(filepath.Join(state, "logs"), "transaction", io.Discard)
	if err != nil {
		t.Fatal(err)
	}
	defer logger.Close()
	changes := []Change{
		{Kind: ReplaceFile, Destination: first, Staged: staged},
		{Kind: ReplaceFile, Destination: second, Staged: filepath.Join(t.TempDir(), "missing")},
	}
	transaction, err := NewTransaction(state, "rollback", Layout{InstallRoot: install, AppRoot: app}, changes, logger)
	if err != nil {
		t.Fatal(err)
	}
	if err := transaction.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := transaction.Apply(); err == nil {
		t.Fatal("transaction unexpectedly succeeded")
	}
	payload, err := os.ReadFile(filepath.Join(state, "current-transaction.json"))
	if err != nil {
		t.Fatal(err)
	}
	var journal transactionJournal
	if err := json.Unmarshal(payload, &journal); err != nil {
		t.Fatal(err)
	}
	for index, operation := range journal.Operations {
		if !operation.Started {
			t.Fatalf("operation %d was not crash-recoverable", index)
		}
	}
	if err := transaction.Rollback(); err != nil {
		t.Fatal(err)
	}
	assertFileContent(t, first, "old-first")
	assertFileContent(t, second, "old-second")
}

func TestInterruptedTransactionIsValidatedAndRecovered(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	destination := filepath.Join(app, "program.txt")
	staged := filepath.Join(t.TempDir(), "program.txt")
	writeTestFile(t, destination, "old")
	writeTestFile(t, staged, "new")
	logger := testLogger(t, state, "interrupted")
	transaction, err := NewTransaction(state, "interrupted-run", Layout{InstallRoot: install, AppRoot: app}, []Change{{Kind: ReplaceFile, Destination: destination, Staged: staged}}, logger)
	if err != nil {
		t.Fatal(err)
	}
	if err := transaction.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := transaction.Apply(); err != nil {
		t.Fatal(err)
	}
	assertFileContent(t, destination, "new")
	recovered, err := RecoverInterruptedTransaction(state, Layout{InstallRoot: install, AppRoot: app}, logger)
	if err != nil || !recovered {
		t.Fatalf("interrupted transaction was not recovered: recovered=%v err=%v", recovered, err)
	}
	assertFileContent(t, destination, "old")
	if fileExists(filepath.Join(state, "current-transaction.json")) || isDirectory(filepath.Join(state, "backups", "interrupted-run")) {
		t.Fatal("interrupted transaction state was not cleaned")
	}
}

func TestInterruptedTransactionRejectsOutsideDestination(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	outside := filepath.Join(t.TempDir(), "outside.txt")
	writeTestFile(t, outside, "do-not-touch")
	journal := transactionJournal{
		Schema: "kfps.update-transaction.v1", RunID: "malicious-run", Status: "applying", InstallRoot: install,
		Operations: []journalOperation{{Kind: RemoveFile, Destination: outside, Backup: filepath.Join(state, "backups", "malicious-run", "000000", "outside.txt"), Started: true}},
	}
	payload, _ := json.Marshal(journal)
	if err := writeAtomic(filepath.Join(state, "current-transaction.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	logger := testLogger(t, state, "malicious")
	if _, err := RecoverInterruptedTransaction(state, Layout{InstallRoot: install, AppRoot: app}, logger); err == nil {
		t.Fatal("unsafe interrupted journal was accepted")
	}
	assertFileContent(t, outside, "do-not-touch")
}

func TestCommittedInterruptedTransactionCleansWithoutRollbackBackup(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	destination := filepath.Join(app, "program.txt")
	writeTestFile(t, destination, "new")
	journal := transactionJournal{
		Schema: "kfps.update-transaction.v1", RunID: "committed-run", Status: "committed", InstallRoot: install,
		Operations: []journalOperation{{Kind: ReplaceFile, Destination: destination, Backup: filepath.Join(state, "backups", "committed-run", "000000", "program.txt"), Existed: true, Started: true, Applied: true}},
	}
	payload, _ := json.Marshal(journal)
	if err := writeAtomic(filepath.Join(state, "current-transaction.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	recovered, err := RecoverInterruptedTransaction(state, Layout{InstallRoot: install, AppRoot: app}, testLogger(t, state, "committed-cleanup"))
	if err != nil || !recovered {
		t.Fatalf("committed journal was not cleaned: recovered=%v err=%v", recovered, err)
	}
	assertFileContent(t, destination, "new")
	if fileExists(filepath.Join(state, "current-transaction.json")) {
		t.Fatal("committed journal remained after recovery")
	}
}

func TestTransactionReplacesAndRollsBackReadOnlyFile(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	destination := filepath.Join(app, "readonly.txt")
	staged := filepath.Join(t.TempDir(), "readonly.txt")
	writeTestFile(t, destination, "old")
	writeTestFile(t, staged, "new")
	if err := os.Chmod(destination, 0o444); err != nil {
		t.Fatal(err)
	}
	transaction, err := NewTransaction(state, "readonly-run", Layout{InstallRoot: install, AppRoot: app}, []Change{{Kind: ReplaceFile, Destination: destination, Staged: staged}}, testLogger(t, state, "readonly"))
	if err != nil {
		t.Fatal(err)
	}
	if err := transaction.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := transaction.Apply(); err != nil {
		t.Fatal(err)
	}
	assertFileContent(t, destination, "new")
	if err := transaction.Rollback(); err != nil {
		t.Fatal(err)
	}
	assertFileContent(t, destination, "old")
}

func TestTransactionSupportsLongUnicodePackagePath(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows long-path transaction test")
	}
	install := filepath.Join(t.TempDir(), "KFPS ü package with spaces", strings.Repeat("a", 70), strings.Repeat("b", 70), strings.Repeat("c", 70))
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	destination := filepath.Join(app, "KFPS.UI", "long-path-program.txt")
	staged := filepath.Join(t.TempDir(), "staged.txt")
	writeTestFile(t, destination, "old")
	writeTestFile(t, staged, "new")
	if len(destination) <= 260 {
		t.Fatalf("test path is not long enough: %d", len(destination))
	}
	transaction, err := NewTransaction(state, "long-path-run", Layout{InstallRoot: install, AppRoot: app}, []Change{{Kind: ReplaceFile, Destination: destination, Staged: staged}}, testLogger(t, state, "long-path"))
	if err != nil {
		t.Fatal(err)
	}
	if err := transaction.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := transaction.Apply(); err != nil {
		t.Fatal(err)
	}
	if err := transaction.Commit(); err != nil {
		t.Fatal(err)
	}
	assertFileContent(t, destination, "new")
}

func TestAbandonPreparationRemovesPartialRollbackState(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	state := filepath.Join(t.TempDir(), "state")
	destination := filepath.Join(app, "program.txt")
	staged := filepath.Join(t.TempDir(), "program.txt")
	writeTestFile(t, destination, "old")
	writeTestFile(t, staged, "new")
	transaction, err := NewTransaction(state, "prepare-failure", Layout{InstallRoot: install, AppRoot: app}, []Change{{Kind: ReplaceFile, Destination: destination, Staged: staged}}, testLogger(t, state, "prepare-failure"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(transaction.journal.Operations[0].Backup, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := transaction.Prepare(); err == nil {
		t.Fatal("forced transaction preparation failure did not fail")
	}
	transaction.AbandonPreparation()
	if isDirectory(transaction.backupDir) || fileExists(transaction.journalPath) {
		t.Fatal("failed preparation left rollback state behind")
	}
	assertFileContent(t, destination, "old")
}

func TestChangeOrderingLeavesOuterLaunchersLast(t *testing.T) {
	install := t.TempDir()
	app := filepath.Join(install, "KloudysFH6Painter")
	changes := []Change{
		{Destination: filepath.Join(install, "KFPS-Updater.exe")},
		{Destination: filepath.Join(app, "KFPS.exe")},
		{Destination: filepath.Join(app, "VERSION")},
		{Destination: filepath.Join(install, "KFPS.exe")},
	}
	sortChanges(changes, install)
	want := []string{filepath.Join(app, "VERSION"), filepath.Join(app, "KFPS.exe"), filepath.Join(install, "KFPS.exe"), filepath.Join(install, "KFPS-Updater.exe")}
	for index := range want {
		if changes[index].Destination != want[index] {
			t.Fatalf("unexpected change order at %d: %s", index, changes[index].Destination)
		}
	}
}

func assertFileContent(t *testing.T, path, expected string) {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(payload) != expected {
		t.Fatalf("%s contains %q; expected %q", path, payload, expected)
	}
}
