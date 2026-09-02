//go:build !windows

package bootstrap

import (
	"os"
)

func replaceFile(source, destination string) error {
	return os.Rename(source, destination)
}
