package bootstrap

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestAcquireUpdateLockRemovesDeadProcessLock(t *testing.T) {
	state := t.TempDir()
	path := filepath.Join(state, "updater.lock")
	if err := os.WriteFile(path, []byte("pid=2147483647\nstarted=2026-01-01T00:00:00Z\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	started := time.Now()
	lock, err := AcquireUpdateLock(state, 2*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer lock.Close()
	if time.Since(started) > time.Second {
		t.Fatal("dead updater lock was not removed promptly")
	}
}

func TestAcquireUpdateLockRejectsLiveUpdater(t *testing.T) {
	state := t.TempDir()
	first, err := AcquireUpdateLock(state, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer first.Close()
	started := time.Now()
	if _, err := AcquireUpdateLock(state, 30*time.Millisecond); err == nil || !strings.Contains(err.Error(), "already running") {
		t.Fatalf("live updater lock was not enforced: %v", err)
	}
	if time.Since(started) > time.Second {
		t.Fatal("live updater lock timeout was not bounded")
	}
}

func TestAcquireUpdateLockRemovesStaleMalformedLock(t *testing.T) {
	state := t.TempDir()
	path := filepath.Join(state, "updater.lock")
	if err := os.WriteFile(path, []byte("not-a-lock\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	old := time.Now().Add(-2 * time.Minute)
	if err := os.Chtimes(path, old, old); err != nil {
		t.Fatal(err)
	}
	lock, err := AcquireUpdateLock(state, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer lock.Close()
}

func TestWaitForProcessExitIsBounded(t *testing.T) {
	state := t.TempDir()
	logger := testLogger(t, state, "process-wait")
	if err := WaitForProcessExit(2147483647, time.Second, logger); err != nil {
		t.Fatalf("nonexistent process blocked update: %v", err)
	}
	started := time.Now()
	if err := WaitForProcessExit(os.Getpid(), 50*time.Millisecond, logger); err == nil {
		t.Fatal("running process did not trigger the wait timeout")
	}
	if time.Since(started) > time.Second {
		t.Fatal("process wait timeout was not bounded")
	}
}
