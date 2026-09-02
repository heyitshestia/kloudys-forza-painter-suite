package bootstrap

import (
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

func InstallationIdentity(layout Layout) (string, error) {
	root, err := filepath.Abs(layout.InstallRoot)
	if err != nil {
		return "", err
	}
	root = filepath.Clean(root)
	if resolved, resolveErr := filepath.EvalSymlinks(root); resolveErr == nil {
		root = filepath.Clean(resolved)
	} else if !os.IsNotExist(resolveErr) {
		return "", resolveErr
	}
	normalized := filepath.ToSlash(root)
	if runtime.GOOS == "windows" {
		normalized = strings.ToLower(normalized)
	}
	digest := sha256.Sum256([]byte(normalized))
	return hex.EncodeToString(digest[:]), nil
}
