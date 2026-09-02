//go:build !windows

package bootstrap

import (
	"fmt"
	"os"
	"path/filepath"
	"syscall"
)

func openVerifiedExecutable(path string) (*openedExecutable, error) {
	if err := ensureNoLinkedPath(path); err != nil {
		return nil, err
	}
	descriptor, err := syscall.Open(path, syscall.O_RDONLY|syscall.O_CLOEXEC|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return nil, err
	}
	file := os.NewFile(uintptr(descriptor), path)
	var initial syscall.Stat_t
	if err := syscall.Fstat(descriptor, &initial); err != nil {
		file.Close()
		return nil, err
	}
	if initial.Mode&syscall.S_IFMT != syscall.S_IFREG || initial.Nlink != 1 {
		file.Close()
		return nil, fmt.Errorf("handoff executable must be a single-link regular file")
	}
	commandPath := fmt.Sprintf("/proc/self/fd/%d", descriptor)
	if _, err := os.Stat(commandPath); err != nil {
		commandPath = fmt.Sprintf("/dev/fd/%d", descriptor)
		if _, err := os.Stat(commandPath); err != nil {
			file.Close()
			return nil, fmt.Errorf("this platform cannot execute a handoff through its verified file descriptor")
		}
	}
	return &openedExecutable{
		file: file, commandPath: filepath.Clean(commandPath),
		revalidate: func() error {
			var current syscall.Stat_t
			if err := syscall.Fstat(descriptor, &current); err != nil {
				return err
			}
			if current.Dev != initial.Dev || current.Ino != initial.Ino || current.Nlink != 1 || current.Mode&syscall.S_IFMT != syscall.S_IFREG {
				return fmt.Errorf("handoff executable identity changed before launch")
			}
			return nil
		},
	}, nil
}
