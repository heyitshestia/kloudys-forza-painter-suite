//go:build windows

package bootstrap

import (
	"errors"
	"os"
	"syscall"
)

const (
	errorSharingViolation syscall.Errno = 32
	errorLockViolation    syscall.Errno = 33
)

func tryAcquirePlatformLock(path string) (*os.File, bool, error) {
	extended, err := extendedWindowsPath(path)
	if err != nil {
		return nil, false, err
	}
	pointer, err := syscall.UTF16PtrFromString(extended)
	if err != nil {
		return nil, false, err
	}
	handle, err := syscall.CreateFile(
		pointer,
		syscall.GENERIC_READ|syscall.GENERIC_WRITE,
		0,
		nil,
		syscall.OPEN_ALWAYS,
		syscall.FILE_ATTRIBUTE_NORMAL|syscall.FILE_FLAG_OPEN_REPARSE_POINT,
		0,
	)
	if err != nil {
		if errors.Is(err, errorSharingViolation) || errors.Is(err, errorLockViolation) {
			return nil, false, nil
		}
		return nil, false, err
	}
	var information syscall.ByHandleFileInformation
	if err := syscall.GetFileInformationByHandle(handle, &information); err != nil {
		syscall.CloseHandle(handle)
		return nil, false, err
	}
	if information.FileAttributes&(syscall.FILE_ATTRIBUTE_REPARSE_POINT|syscall.FILE_ATTRIBUTE_DIRECTORY) != 0 || information.NumberOfLinks != 1 {
		syscall.CloseHandle(handle)
		return nil, false, errors.New("updater lock must be a non-reparse, single-link regular file")
	}
	return os.NewFile(uintptr(handle), path), true, nil
}
