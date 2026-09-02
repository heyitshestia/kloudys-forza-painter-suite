//go:build !windows

package bootstrap

import (
	"errors"
	"os"
	"syscall"
)

func tryAcquirePlatformLock(path string) (*os.File, bool, error) {
	descriptor, err := syscall.Open(path, syscall.O_CREAT|syscall.O_RDWR|syscall.O_CLOEXEC|syscall.O_NOFOLLOW, 0o600)
	if err != nil {
		return nil, false, err
	}
	file := os.NewFile(uintptr(descriptor), path)
	var status syscall.Stat_t
	if err := syscall.Fstat(descriptor, &status); err != nil {
		file.Close()
		return nil, false, err
	}
	if status.Mode&syscall.S_IFMT != syscall.S_IFREG || status.Nlink != 1 {
		file.Close()
		return nil, false, errors.New("updater lock must be a single-link regular file")
	}
	if err := syscall.Flock(int(file.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		file.Close()
		if errors.Is(err, syscall.EWOULDBLOCK) || errors.Is(err, syscall.EAGAIN) {
			return nil, false, nil
		}
		return nil, false, err
	}
	return file, true, nil
}
