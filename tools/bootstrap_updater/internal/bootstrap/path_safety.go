package bootstrap

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func ensureNoLinkedPath(path string) error {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return err
	}
	absolute = filepath.Clean(absolute)
	for current := absolute; ; current = filepath.Dir(current) {
		info, statErr := os.Lstat(current)
		if statErr == nil {
			linked, linkErr := pathObjectIsLinked(current, info)
			if linkErr != nil {
				return linkErr
			}
			if linked {
				return fmt.Errorf("refusing linked or reparse-point path: %s", current)
			}
		} else if !os.IsNotExist(statErr) {
			return statErr
		}
		parent := filepath.Dir(current)
		if strings.EqualFold(parent, current) {
			break
		}
	}
	return nil
}

func ensureSafeContainedPath(root, target string) error {
	rootAbs, err := filepath.Abs(root)
	if err != nil {
		return err
	}
	targetAbs, err := filepath.Abs(target)
	if err != nil {
		return err
	}
	rootAbs = filepath.Clean(rootAbs)
	targetAbs = filepath.Clean(targetAbs)
	if !pathIsContained(rootAbs, targetAbs) {
		return fmt.Errorf("path is outside its trusted root: %s", target)
	}
	if err := ensureNoLinkedPath(rootAbs); err != nil {
		return err
	}
	for current := targetAbs; !strings.EqualFold(current, rootAbs); current = filepath.Dir(current) {
		info, statErr := os.Lstat(current)
		if statErr == nil {
			linked, linkErr := pathObjectIsLinked(current, info)
			if linkErr != nil {
				return linkErr
			}
			if linked {
				return fmt.Errorf("refusing linked or reparse-point path: %s", current)
			}
		} else if !os.IsNotExist(statErr) {
			return statErr
		}
		parent := filepath.Dir(current)
		if strings.EqualFold(parent, current) {
			return fmt.Errorf("path traversal did not reach its trusted root: %s", target)
		}
	}
	return nil
}

func makeSafeDirectory(path string, mode os.FileMode) error {
	if err := ensureNoLinkedPath(path); err != nil {
		return err
	}
	if err := os.MkdirAll(path, mode); err != nil {
		return err
	}
	return ensureNoLinkedPath(path)
}

func removeSafeTree(root, target string) error {
	if err := ensureSafeContainedPath(root, target); err != nil {
		return err
	}
	return os.RemoveAll(target)
}
