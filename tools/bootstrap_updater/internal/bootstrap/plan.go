package bootstrap

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type ChangeKind string

const (
	ReplaceFile ChangeKind = "replace"
	RemoveFile  ChangeKind = "remove"
)

type Change struct {
	Kind        ChangeKind
	Relative    string
	Destination string
	Staged      string
	Expected    FileRecord
}

type PreparedUpdate struct {
	Version        string
	Commit         string
	Sequence       uint64
	ChannelSHA256  string
	ManifestSHA256 string
	Relaunch       string
	Changes        []Change
	FilesChecked   int
}

func fileNeedsRepair(path string, record FileRecord) (bool, error) {
	info, err := os.Stat(path)
	if os.IsNotExist(err) {
		return true, nil
	}
	if err != nil {
		return false, err
	}
	if !info.Mode().IsRegular() {
		return false, fmt.Errorf("expected file path is not a regular file and requires manual remediation: %s", path)
	}
	if info.Size() != record.Size {
		return true, nil
	}
	hash, err := sha256File(path)
	if err != nil {
		return false, err
	}
	expected, _ := normalizeSHA256(record.SHA256)
	return hash != expected, nil
}

func validateFileRecords(records []FileRecord) (map[string]FileRecord, error) {
	if len(records) == 0 || len(records) > maximumArchiveFiles {
		return nil, fmt.Errorf("file inventory contains %d records", len(records))
	}
	result := make(map[string]FileRecord, len(records))
	for _, record := range records {
		clean, err := cleanRelativePath(record.Path)
		if err != nil {
			return nil, err
		}
		if record.Size < 0 || record.Size > maximumArchiveBytes {
			return nil, fmt.Errorf("invalid size for %s", clean)
		}
		hash, err := normalizeSHA256(record.SHA256)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", clean, err)
		}
		record.Path = clean
		record.SHA256 = hash
		key := pathKey(clean)
		if _, exists := result[key]; exists {
			return nil, fmt.Errorf("duplicate inventory path %s", clean)
		}
		result[key] = record
	}
	return result, nil
}

func protectedAppPath(relative string) bool {
	key := pathKey(relative)
	if strings.HasSuffix(key, ".kfpskey") || key == ".git" || strings.HasPrefix(key, ".git/") {
		return true
	}
	for _, root := range []string{"runtime", "imgs", "webui-data", "node_modules", ".wrangler", ".venv"} {
		if key == root || strings.HasPrefix(key, root+"/") {
			return true
		}
	}
	return key == ".dev.vars" || strings.HasPrefix(key, ".dev.vars.")
}

func validateComponentPath(component Component, relative string) error {
	clean, err := cleanRelativePath(relative)
	if err != nil {
		return err
	}
	if component.Target == "install-root" {
		if !strings.EqualFold(clean, "KFPS.exe") && !strings.EqualFold(clean, "KFPS-Updater.exe") {
			return fmt.Errorf("install-root component %q may only manage KFPS.exe and KFPS-Updater.exe", component.Name)
		}
		return nil
	}
	if component.Target != "app-root" {
		return fmt.Errorf("unsupported target %q", component.Target)
	}
	if protectedAppPath(clean) {
		return fmt.Errorf("component %q attempted to manage protected path %s", component.Name, clean)
	}
	if strings.HasPrefix(pathKey(clean), "python/") && component.Name != "python-runtime" {
		return fmt.Errorf("only the python-runtime component may manage python/")
	}
	if component.Name == "python-runtime" && !strings.HasPrefix(pathKey(clean), "python/") {
		return fmt.Errorf("python-runtime path is outside python/: %s", clean)
	}
	return nil
}

func collectExactRootRemovals(root string, component Component, records map[string]FileRecord, existing map[string]bool) ([]Change, error) {
	changes := []Change{}
	for _, rawRoot := range component.ExactRoots {
		cleanRoot, err := cleanRelativePath(rawRoot)
		if err != nil {
			return nil, err
		}
		if component.Name != "python-runtime" || pathKey(cleanRoot) != "python" {
			return nil, fmt.Errorf("unsupported exact root %q for component %q", cleanRoot, component.Name)
		}
		absoluteRoot, err := joinContained(root, cleanRoot)
		if err != nil {
			return nil, err
		}
		err = filepath.WalkDir(absoluteRoot, func(path string, entry os.DirEntry, walkErr error) error {
			if os.IsNotExist(walkErr) {
				return nil
			}
			if walkErr != nil {
				return walkErr
			}
			info, err := entry.Info()
			if err != nil {
				return err
			}
			linked, err := pathObjectIsLinked(path, info)
			if err != nil {
				return err
			}
			if linked {
				return fmt.Errorf("refusing linked or reparse-point path in exact root: %s", path)
			}
			if entry.IsDir() {
				if generatedPythonCachePath(path) {
					return filepath.SkipDir
				}
				return nil
			}
			if generatedPythonCachePath(path) {
				return nil
			}
			relative, err := filepath.Rel(root, path)
			if err != nil {
				return err
			}
			relative = filepath.ToSlash(relative)
			key := pathKey(relative)
			if _, expected := records[key]; expected {
				return nil
			}
			if existing[key] {
				return nil
			}
			existing[key] = true
			changes = append(changes, Change{Kind: RemoveFile, Relative: relative, Destination: path})
			return nil
		})
		if err != nil && !os.IsNotExist(err) {
			return nil, err
		}
	}
	return changes, nil
}

func generatedPythonCachePath(path string) bool {
	key := pathKey(path)
	return strings.HasSuffix(key, ".pyc") || strings.Contains(key, "/__pycache__/") || strings.HasSuffix(key, "/__pycache__")
}

func sortChanges(changes []Change, installRoot string) {
	outerLauncher := pathKey(filepath.Join(installRoot, "KFPS.exe"))
	outerUpdater := pathKey(filepath.Join(installRoot, "KFPS-Updater.exe"))
	priority := func(change Change) int {
		switch pathKey(change.Destination) {
		case outerLauncher:
			return 2
		case outerUpdater:
			return 3
		default:
			if strings.EqualFold(filepath.Base(change.Destination), "KFPS.exe") {
				return 1
			}
			return 0
		}
	}
	sort.SliceStable(changes, func(left, right int) bool {
		leftPriority := priority(changes[left])
		rightPriority := priority(changes[right])
		if leftPriority != rightPriority {
			return leftPriority < rightPriority
		}
		return pathKey(changes[left].Destination) < pathKey(changes[right].Destination)
	})
}
