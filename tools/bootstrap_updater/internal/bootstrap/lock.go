package bootstrap

import (
	"fmt"
	"os"
	"path/filepath"
	"time"
)

type UpdateLock struct {
	path  string
	file  *os.File
	token string
}

func AcquireUpdateLock(stateDir string, wait time.Duration) (*UpdateLock, error) {
	if err := makeSafeDirectory(stateDir, 0o700); err != nil {
		return nil, err
	}
	if err := ensureSafeContainedPath(stateDir, stateDir); err != nil {
		return nil, err
	}
	path := filepath.Join(stateDir, "updater.lock")
	if err := ensureSafeContainedPath(stateDir, path); err != nil {
		return nil, err
	}
	deadline := time.Now().Add(wait)
	for {
		file, acquired, err := tryAcquirePlatformLock(path)
		if err != nil {
			return nil, err
		}
		if acquired {
			token, tokenErr := newRunID()
			if tokenErr != nil {
				file.Close()
				return nil, tokenErr
			}
			if err := file.Truncate(0); err != nil {
				file.Close()
				return nil, err
			}
			if _, err := file.Seek(0, 0); err != nil {
				file.Close()
				return nil, err
			}
			if _, err := fmt.Fprintf(file, "pid=%d\nstarted=%s\ntoken=%s\n", os.Getpid(), utcNow(), token); err != nil {
				file.Close()
				return nil, err
			}
			if err := file.Sync(); err != nil {
				file.Close()
				return nil, err
			}
			return &UpdateLock{path: path, file: file, token: token}, nil
		}
		if time.Now().After(deadline) {
			return nil, fmt.Errorf("another KFPS updater is already running")
		}
		time.Sleep(250 * time.Millisecond)
	}
}

func (lock *UpdateLock) Close() error {
	if lock == nil || lock.file == nil {
		return nil
	}
	err := lock.file.Close()
	lock.file = nil
	return err
}
