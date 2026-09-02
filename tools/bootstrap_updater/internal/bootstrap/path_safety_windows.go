//go:build windows

package bootstrap

import (
	"os"
	"syscall"
)

const fileAttributeReparsePoint = 0x400

func pathObjectIsLinked(path string, info os.FileInfo) (bool, error) {
	if info.Mode()&os.ModeSymlink != 0 {
		return true, nil
	}
	extended, err := extendedWindowsPath(path)
	if err != nil {
		return false, err
	}
	pointer, err := syscall.UTF16PtrFromString(extended)
	if err != nil {
		return false, err
	}
	attributes, err := syscall.GetFileAttributes(pointer)
	if err != nil {
		return false, err
	}
	return attributes&fileAttributeReparsePoint != 0, nil
}
