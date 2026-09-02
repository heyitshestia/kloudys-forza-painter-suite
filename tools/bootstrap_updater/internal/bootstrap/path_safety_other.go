//go:build !windows

package bootstrap

import "os"

func pathObjectIsLinked(_ string, info os.FileInfo) (bool, error) {
	return info.Mode()&os.ModeSymlink != 0, nil
}
