package bootstrap

import (
	"os"
	"path/filepath"
	"sort"
	"time"
)

func PruneUpdaterState(stateDir string, logger *Logger) {
	for _, name := range []string{"runs", "backups"} {
		path := filepath.Join(stateDir, name)
		if err := removeSafeTree(stateDir, path); err != nil && !os.IsNotExist(err) {
			logger.Printf("Could not remove stale updater %s: %v", name, err)
		}
	}
	pruneFiles(filepath.Join(stateDir, "logs"), 40, 90*24*time.Hour, logger)
	pruneFiles(filepath.Join(stateDir, "reports"), 40, 90*24*time.Hour, logger)
	pruneFiles(filepath.Join(stateDir, "handoff"), 4, 30*24*time.Hour, logger)
}

func pruneFiles(directory string, keep int, maximumAge time.Duration, logger *Logger) {
	if err := ensureNoLinkedPath(directory); err != nil {
		logger.Printf("Skipped unsafe updater history path %s: %v", directory, err)
		return
	}
	entries, err := os.ReadDir(directory)
	if os.IsNotExist(err) {
		return
	}
	if err != nil {
		logger.Printf("Could not inspect updater history %s: %v", directory, err)
		return
	}
	type candidate struct {
		path string
		when time.Time
	}
	files := []candidate{}
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		path := filepath.Join(directory, entry.Name())
		if err := ensureNoLinkedPath(path); err != nil {
			logger.Printf("Skipped unsafe updater history entry %s: %v", path, err)
			continue
		}
		info, err := entry.Info()
		if err == nil {
			files = append(files, candidate{path: path, when: info.ModTime()})
		}
	}
	sort.Slice(files, func(left, right int) bool { return files[left].when.After(files[right].when) })
	cutoff := time.Now().Add(-maximumAge)
	for index, file := range files {
		if index < keep && file.when.After(cutoff) {
			continue
		}
		if err := os.Remove(file.path); err != nil && !os.IsNotExist(err) {
			logger.Printf("Could not remove stale updater history %s: %v", file.path, err)
		}
	}
}
