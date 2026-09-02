//go:build windows

package bootstrap

import "os"

func clearReadOnly(path string) error {
	info, err := os.Stat(path)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	if info.Mode().Perm()&0o200 != 0 {
		return nil
	}
	return os.Chmod(path, info.Mode().Perm()|0o200)
}
