package bootstrap

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type RecoveryConfig struct {
	Version        string
	Commit         string
	ManifestSHA256 string
	ManifestSize   int64
	Artifact       Artifact
	ExcludedFiles  []string
}

func recoveryExcludedFiles(layout Layout, expected RecoveryConfig, records map[string]FileRecord) (map[string]bool, error) {
	excluded := map[string]bool{}
	for _, raw := range expected.ExcludedFiles {
		clean, err := cleanRelativePath(raw)
		if err != nil {
			return nil, err
		}
		key := pathKey(clean)
		if excluded[key] {
			return nil, fmt.Errorf("duplicate recovery exclusion path %s", clean)
		}
		if _, declared := records[key]; !declared {
			return nil, fmt.Errorf("recovery exclusion path is not declared by the pinned inventory: %s", clean)
		}
		prefix := "kloudysfh6painter/"
		if !strings.HasPrefix(key, prefix) {
			return nil, fmt.Errorf("recovery retirement path is outside the application root: %s", clean)
		}
		appRelative := filepath.ToSlash(clean[len("KloudysFH6Painter/"):])
		if err := validateComponentPath(Component{Name: "application", Target: "app-root"}, appRelative); err != nil {
			return nil, err
		}
		if _, err := joinContained(layout.InstallRoot, clean); err != nil {
			return nil, err
		}
		excluded[key] = true
	}
	return excluded, nil
}

func RecoveryAlreadyHealthy(layout Layout, expected RecoveryConfig, logger *Logger) (PreparedUpdate, bool, error) {
	manifestPath := filepath.Join(layout.InstallRoot, "RELEASE-MANIFEST.json")
	info, err := os.Stat(manifestPath)
	if os.IsNotExist(err) || err == nil && info.Size() != expected.ManifestSize {
		return PreparedUpdate{}, false, nil
	}
	if err != nil {
		return PreparedUpdate{}, false, err
	}
	hash, err := sha256File(manifestPath)
	if err != nil || !strings.EqualFold(hash, expected.ManifestSHA256) {
		return PreparedUpdate{}, false, err
	}
	payload, err := os.ReadFile(manifestPath)
	if err != nil {
		return PreparedUpdate{}, false, err
	}
	var manifest ReleaseManifest
	if err := decodeStrictJSON(payload, &manifest); err != nil {
		return PreparedUpdate{}, false, nil
	}
	if manifest.Schema != ReleaseSchema || manifest.Version != expected.Version || !strings.EqualFold(manifest.Commit, expected.Commit) {
		return PreparedUpdate{}, false, nil
	}
	records, err := validateFileRecords(manifest.Files)
	if err != nil {
		return PreparedUpdate{}, false, nil
	}
	excluded, err := recoveryExcludedFiles(layout, expected, records)
	if err != nil {
		return PreparedUpdate{}, false, err
	}
	expectedPython := map[string]bool{}
	filesChecked := 0
	for _, record := range records {
		if generatedPythonCachePath(record.Path) {
			continue
		}
		if excluded[pathKey(record.Path)] {
			filesChecked++
			continue
		}
		destination, err := joinContained(layout.InstallRoot, record.Path)
		if err != nil {
			return PreparedUpdate{}, false, err
		}
		if strings.HasPrefix(pathKey(record.Path), "kloudysfh6painter/python/") {
			expectedPython[pathKey(record.Path)] = true
		}
		filesChecked++
		if logger != nil && filesChecked%1000 == 0 {
			logger.Printf("Recovery health check: %d program files verified.", filesChecked)
		}
		needsRepair, err := fileNeedsRepair(destination, record)
		if err != nil || needsRepair {
			return PreparedUpdate{}, false, err
		}
	}
	pythonRoot := filepath.Join(layout.AppRoot, "python")
	healthy := true
	err = filepath.WalkDir(pythonRoot, func(path string, entry os.DirEntry, walkErr error) error {
		if os.IsNotExist(walkErr) {
			return nil
		}
		if walkErr != nil {
			return walkErr
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
		relative, err := filepath.Rel(layout.InstallRoot, path)
		if err != nil {
			return err
		}
		if !expectedPython[pathKey(filepath.ToSlash(relative))] {
			healthy = false
		}
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return PreparedUpdate{}, false, err
	}
	return PreparedUpdate{Version: manifest.Version, Commit: manifest.Commit, FilesChecked: filesChecked}, healthy, nil
}

func PrepareRecoveryBundle(archivePath, stagingRoot string, layout Layout, expected RecoveryConfig, logger *Logger) (PreparedUpdate, error) {
	inventory, err := openZipInventory(archivePath)
	if err != nil {
		return PreparedUpdate{}, err
	}
	defer inventory.Close()

	manifestName := ""
	for _, actual := range inventory.actual {
		if strings.HasSuffix(pathKey(actual), "/release-manifest.json") {
			if manifestName != "" {
				return PreparedUpdate{}, fmt.Errorf("recovery archive contains more than one release manifest")
			}
			manifestName = actual
		}
	}
	if manifestName == "" {
		return PreparedUpdate{}, fmt.Errorf("recovery archive does not contain RELEASE-MANIFEST.json")
	}
	prefix := strings.TrimSuffix(manifestName, "RELEASE-MANIFEST.json")
	if strings.Count(strings.TrimSuffix(prefix, "/"), "/") != 0 {
		return PreparedUpdate{}, fmt.Errorf("release manifest is not at the archive package root")
	}
	payload, err := inventory.read(manifestName, maximumManifestSize)
	if err != nil {
		return PreparedUpdate{}, err
	}
	var manifest ReleaseManifest
	if err := decodeStrictJSON(payload, &manifest); err != nil {
		return PreparedUpdate{}, fmt.Errorf("decode release manifest: %w", err)
	}
	if manifest.Schema != ReleaseSchema || manifest.Kind != "recommended" {
		return PreparedUpdate{}, fmt.Errorf("recovery archive has an unsupported release contract")
	}
	if manifest.Version != expected.Version || !strings.EqualFold(manifest.Commit, expected.Commit) {
		return PreparedUpdate{}, fmt.Errorf("recovery archive identifies %s/%s; expected %s/%s", manifest.Version, manifest.Commit, expected.Version, expected.Commit)
	}
	records, err := validateFileRecords(manifest.Files)
	if err != nil {
		return PreparedUpdate{}, err
	}
	excluded, err := recoveryExcludedFiles(layout, expected, records)
	if err != nil {
		return PreparedUpdate{}, err
	}
	if len(inventory.files) != len(records)+1 {
		return PreparedUpdate{}, fmt.Errorf("recovery archive inventory differs from its signed-in-binary release inventory")
	}
	changes := []Change{}
	manifestRecord := FileRecord{Path: "RELEASE-MANIFEST.json", Size: int64(len(payload)), SHA256: sha256Bytes(payload)}
	if manifestRecord.Size != expected.ManifestSize || !strings.EqualFold(manifestRecord.SHA256, expected.ManifestSHA256) {
		return PreparedUpdate{}, fmt.Errorf("recovery release manifest does not match the hash pinned into this updater")
	}
	manifestDestination := filepath.Join(layout.InstallRoot, "RELEASE-MANIFEST.json")
	manifestNeedsRepair, err := fileNeedsRepair(manifestDestination, manifestRecord)
	if err != nil {
		return PreparedUpdate{}, err
	}
	if manifestNeedsRepair {
		manifestStaged := filepath.Join(stagingRoot, "RELEASE-MANIFEST.json")
		if err := ensureNoLinkedPath(manifestStaged); err != nil {
			return PreparedUpdate{}, err
		}
		if err := makeSafeDirectory(filepath.Dir(manifestStaged), 0o755); err != nil {
			return PreparedUpdate{}, err
		}
		if err := os.WriteFile(manifestStaged, payload, 0o600); err != nil {
			return PreparedUpdate{}, err
		}
		changes = append(changes, Change{Kind: ReplaceFile, Relative: manifestRecord.Path, Destination: manifestDestination, Staged: manifestStaged, Expected: manifestRecord})
	}
	expectedPython := map[string]bool{}
	filesChecked := 0
	for _, record := range records {
		archiveName := prefix + record.Path
		entry := inventory.files[pathKey(archiveName)]
		if entry == nil || int64(entry.UncompressedSize64) != record.Size {
			return PreparedUpdate{}, fmt.Errorf("recovery archive is missing or mis-sizes %s", record.Path)
		}
		if record.Path != "KFPS.exe" && !strings.HasPrefix(pathKey(record.Path), "kloudysfh6painter/") {
			return PreparedUpdate{}, fmt.Errorf("recovery manifest path is outside the KFPS layout: %s", record.Path)
		}
		if strings.HasSuffix(pathKey(record.Path), ".kfpskey") {
			return PreparedUpdate{}, fmt.Errorf("recovery manifest attempted to manage a supporter key")
		}
		if generatedPythonCachePath(record.Path) {
			continue
		}
		filesChecked++
		if excluded[pathKey(record.Path)] {
			continue
		}
		appRelative := strings.TrimPrefix(filepath.ToSlash(record.Path), "KloudysFH6Painter/")
		if record.Path != "KFPS.exe" && protectedAppPath(appRelative) {
			return PreparedUpdate{}, fmt.Errorf("recovery manifest attempted to manage protected path %s", record.Path)
		}
		destination, err := joinContained(layout.InstallRoot, record.Path)
		if err != nil {
			return PreparedUpdate{}, err
		}
		if strings.HasPrefix(pathKey(record.Path), "kloudysfh6painter/python/") {
			expectedPython[pathKey(record.Path)] = true
		}
		if filesChecked%1000 == 0 {
			logger.Printf("Recovery inventory: %d program files checked.", filesChecked)
		}
		needsRepair, err := fileNeedsRepair(destination, record)
		if err != nil {
			return PreparedUpdate{}, err
		}
		if !needsRepair {
			continue
		}
		staged, err := joinContained(stagingRoot, record.Path)
		if err != nil {
			return PreparedUpdate{}, err
		}
		if err := inventory.extract(archiveName, staged, record); err != nil {
			return PreparedUpdate{}, err
		}
		changes = append(changes, Change{Kind: ReplaceFile, Relative: record.Path, Destination: destination, Staged: staged, Expected: record})
	}

	pythonRoot := filepath.Join(layout.AppRoot, "python")
	err = filepath.WalkDir(pythonRoot, func(path string, entry os.DirEntry, walkErr error) error {
		if os.IsNotExist(walkErr) {
			return nil
		}
		if walkErr != nil {
			return walkErr
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
		relative, err := filepath.Rel(layout.InstallRoot, path)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		if !expectedPython[pathKey(relative)] {
			changes = append(changes, Change{Kind: RemoveFile, Relative: relative, Destination: path})
		}
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return PreparedUpdate{}, err
	}
	sortChanges(changes, layout.InstallRoot)
	logger.Printf("Recovery inventory checked %d program files and planned %d repair operation(s).", filesChecked, len(changes))
	return PreparedUpdate{
		Version:      manifest.Version,
		Commit:       manifest.Commit,
		Changes:      changes,
		FilesChecked: filesChecked,
	}, nil
}
