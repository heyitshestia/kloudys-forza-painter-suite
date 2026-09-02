package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAuditV2PublisherRejectsOutputInsidePythonRoot(t *testing.T) {
	root := t.TempDir()
	app := filepath.Join(root, "app")
	python := filepath.Join(root, "python")
	updater := filepath.Join(root, "KFPS-Updater.exe")
	writeBuildTestFile(t, filepath.Join(app, "KFPS.exe"), "launcher")
	writeBuildTestFile(t, filepath.Join(app, "VERSION"), "1.0.0\n")
	writeBuildTestFile(t, filepath.Join(python, "python.exe"), "python")
	writeBuildTestFile(t, updater, "updater")
	err := buildPayload([]string{
		"--app-root", app, "--python-root", python, "--updater", updater,
		"--private", filepath.Join(root, "missing.private"), "--public", filepath.Join(root, "missing.public"),
		"--output", filepath.Join(python, "payload"), "--base-url", "https://updates.example.invalid/stable", "--sequence", "1",
	})
	if err == nil || !strings.Contains(err.Error(), "disjoint") {
		t.Fatalf("publisher output inside Python source was accepted: %v", err)
	}
	if _, statErr := os.Stat(filepath.Join(python, "payload")); !os.IsNotExist(statErr) {
		t.Fatalf("rejected overlapping output was created: %v", statErr)
	}
}

func TestAuditV2GitSnapshotIsBoundToCommitBytes(t *testing.T) {
	repository := filepath.Join(t.TempDir(), "repository")
	writeBuildTestFile(t, filepath.Join(repository, "VERSION"), "1.0.0\n")
	writeBuildTestFile(t, filepath.Join(repository, "KFPS.exe"), "launcher")
	runGit(t, repository, "init", "-b", "main")
	runGit(t, repository, "config", "user.name", "KFPS Test")
	runGit(t, repository, "config", "user.email", "test@example.invalid")
	runGit(t, repository, "config", "core.autocrlf", "false")
	runGit(t, repository, "add", ".")
	runGit(t, repository, "commit", "-m", "fixture")
	commit := strings.TrimSpace(runGit(t, repository, "rev-parse", "HEAD"))
	snapshot := filepath.Join(t.TempDir(), "snapshot")
	if err := createGitSnapshot(repository, commit, snapshot); err != nil {
		t.Fatal(err)
	}
	writeBuildTestFile(t, filepath.Join(repository, "VERSION"), "9.9.9\n")
	payload, err := os.ReadFile(filepath.Join(snapshot, "VERSION"))
	if err != nil || string(payload) != "1.0.0\n" {
		t.Fatalf("snapshot changed with working tree: %q %v", payload, err)
	}
	if err := verifyGitSourceIdentity(repository, commit); err == nil || !strings.Contains(err.Error(), "modified tracked files") {
		t.Fatalf("post-snapshot source mutation was not diagnosed: %v", err)
	}
}
