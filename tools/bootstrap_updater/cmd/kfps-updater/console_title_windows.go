//go:build windows

package main

import (
	"syscall"
	"unsafe"
)

var setConsoleTitleW = syscall.NewLazyDLL("kernel32.dll").NewProc("SetConsoleTitleW")

func setConsoleTitle(title string) {
	value, err := syscall.UTF16PtrFromString(title)
	if err != nil {
		return
	}
	_, _, _ = setConsoleTitleW.Call(uintptr(unsafe.Pointer(value)))
}
