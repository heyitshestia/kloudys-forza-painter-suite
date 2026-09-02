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

var getFinalPathNameByHandle = syscall.NewLazyDLL("kernel32.dll").NewProc("GetFinalPathNameByHandleW")

func openVerifiedExecutable(path string) (*openedExecutable, error) {
	if err := ensureNoLinkedPath(path); err != nil {
		return nil, err
	}
	extended, err := extendedWindowsPath(path)
	if err != nil {
		return nil, err
	}
	pointer, err := syscall.UTF16PtrFromString(extended)
	if err != nil {
		return nil, err
	}
	handle, err := syscall.CreateFile(
		pointer,
		syscall.GENERIC_READ,
		syscall.FILE_SHARE_READ,
		nil,
		syscall.OPEN_EXISTING,
		syscall.FILE_ATTRIBUTE_NORMAL|syscall.FILE_FLAG_OPEN_REPARSE_POINT,
		0,
	)
	if err != nil {
		return nil, err
	}
	file := os.NewFile(uintptr(handle), path)
	var initial syscall.ByHandleFileInformation
	if err := syscall.GetFileInformationByHandle(handle, &initial); err != nil {
		file.Close()
		return nil, err
	}
	if initial.FileAttributes&(syscall.FILE_ATTRIBUTE_REPARSE_POINT|syscall.FILE_ATTRIBUTE_DIRECTORY) != 0 || initial.NumberOfLinks != 1 {
		file.Close()
		return nil, fmt.Errorf("handoff executable must be a non-reparse, single-link regular file")
	}
	finalPath, err := finalWindowsHandlePath(handle)
	if err != nil {
		file.Close()
		return nil, err
	}
	if !strings.EqualFold(filepath.Clean(finalPath), filepath.Clean(extended)) {
		file.Close()
		return nil, fmt.Errorf("handoff executable handle resolved to a different path")
	}
	return &openedExecutable{
		file: file, commandPath: path,
		revalidate: func() error {
			var current syscall.ByHandleFileInformation
			if err := syscall.GetFileInformationByHandle(handle, &current); err != nil {
				return err
			}
			if current.VolumeSerialNumber != initial.VolumeSerialNumber || current.FileIndexHigh != initial.FileIndexHigh || current.FileIndexLow != initial.FileIndexLow || current.NumberOfLinks != 1 || current.FileAttributes&(syscall.FILE_ATTRIBUTE_REPARSE_POINT|syscall.FILE_ATTRIBUTE_DIRECTORY) != 0 {
				return fmt.Errorf("handoff executable identity changed before launch")
			}
			resolved, err := finalWindowsHandlePath(handle)
			if err != nil {
				return err
			}
			if !strings.EqualFold(filepath.Clean(resolved), filepath.Clean(extended)) {
				return fmt.Errorf("handoff executable path changed before launch")
			}
			return nil
		},
	}, nil
}

func finalWindowsHandlePath(handle syscall.Handle) (string, error) {
	buffer := make([]uint16, syscall.MAX_LONG_PATH)
	length, _, callErr := getFinalPathNameByHandle.Call(
		uintptr(handle),
		uintptr(unsafe.Pointer(&buffer[0])),
		uintptr(len(buffer)),
		0,
	)
	if length == 0 {
		return "", fmt.Errorf("GetFinalPathNameByHandleW failed: %w", callErr)
	}
	if length >= uintptr(len(buffer)) {
		return "", fmt.Errorf("handoff executable final path is too long")
	}
	return syscall.UTF16ToString(buffer[:length]), nil
}
