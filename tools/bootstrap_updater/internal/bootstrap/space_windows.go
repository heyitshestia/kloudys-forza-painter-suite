//go:build windows

package bootstrap

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

var getDiskFreeSpaceEx = syscall.NewLazyDLL("kernel32.dll").NewProc("GetDiskFreeSpaceExW")

func availableSpace(path string) (uint64, error) {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return 0, err
	}
	for {
		if info, statErr := os.Stat(absolute); statErr == nil && info.IsDir() {
			break
		}
		parent := filepath.Dir(absolute)
		if parent == absolute {
			break
		}
		absolute = parent
	}
	absolute, err = extendedWindowsPath(absolute)
	if err != nil {
		return 0, err
	}
	pointer, err := syscall.UTF16PtrFromString(absolute)
	if err != nil {
		return 0, err
	}
	var available uint64
	result, _, callErr := getDiskFreeSpaceEx.Call(
		uintptr(unsafe.Pointer(pointer)),
		uintptr(unsafe.Pointer(&available)),
		0,
		0,
	)
	if result == 0 {
		return 0, fmt.Errorf("could not determine free space for update transaction: %w", callErr)
	}
	return available, nil
}

func storageVolumeKey(path string) (string, error) {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return "", err
	}
	return strings.ToLower(filepath.VolumeName(absolute)), nil
}
