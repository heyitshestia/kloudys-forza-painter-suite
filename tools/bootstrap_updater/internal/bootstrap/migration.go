package bootstrap

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const legacyBootstrapShim = "@echo off\r\n" +
	"setlocal EnableExtensions EnableDelayedExpansion\r\n" +
	"set \"SCRIPT_DIR=%~dp0\"\r\n" +
	"if exist \"%SCRIPT_DIR%..\\KFPS-Updater.exe\" (\r\n" +
	"    \"%SCRIPT_DIR%..\\KFPS-Updater.exe\" --root \"%SCRIPT_DIR%..\" --relaunch %*\r\n" +
	"    if not errorlevel 1 exit /b 0\r\n" +
	"    set \"OUTER_ERROR=!ERRORLEVEL!\"\r\n" +
	"    if !OUTER_ERROR! EQU 5 goto try_inner\r\n" +
	"    if !OUTER_ERROR! EQU 193 goto try_inner\r\n" +
	"    if !OUTER_ERROR! EQU 216 goto try_inner\r\n" +
	"    if !OUTER_ERROR! EQU 9009 goto try_inner\r\n" +
	"    exit /b !OUTER_ERROR!\r\n" +
	")\r\n" +
	":try_inner\r\n" +
	"if exist \"%SCRIPT_DIR%KFPS-Updater.exe\" (\r\n" +
	"    echo Outer bootstrap updater could not start; using the independently repairable inner copy.\r\n" +
	"    \"%SCRIPT_DIR%KFPS-Updater.exe\" --root \"%SCRIPT_DIR%..\" --relaunch %*\r\n" +
	"    exit /b !ERRORLEVEL!\r\n" +
	")\r\n" +
	"echo KFPS-Updater.exe is missing. Download the current KFPS updater.\r\n" +
	"exit /b 1\r\n"

var legacyUpdaterAppFiles = []string{
	"03_update_from_github.bat",
	"update_from_github.bat",
}

func (engine *Engine) prepareLegacyMigration(prepared PreparedUpdate) (PreparedUpdate, error) {
	if !engine.config.FinalizeLegacyMigration || strings.EqualFold(engine.config.Layout.InstallRoot, engine.config.Layout.AppRoot) {
		return prepared, nil
	}
	if !fileExists(engine.config.CurrentExecutable) {
		return PreparedUpdate{}, fmt.Errorf("running bootstrap updater is unavailable for installation migration")
	}

	currentInfo, err := os.Stat(engine.config.CurrentExecutable)
	if err != nil {
		return PreparedUpdate{}, err
	}
	currentHash, err := sha256File(engine.config.CurrentExecutable)
	if err != nil {
		return PreparedUpdate{}, err
	}
	currentRecord := FileRecord{Path: "KFPS-Updater.exe", Size: currentInfo.Size(), SHA256: currentHash}

	legacyDestinations := map[string]bool{}
	for _, relative := range legacyUpdaterAppFiles {
		destination, err := joinContained(engine.config.Layout.AppRoot, relative)
		if err != nil {
			return PreparedUpdate{}, err
		}
		legacyDestinations[pathKey(destination)] = true
	}
	filtered := make([]Change, 0, len(prepared.Changes)+4)
	plannedDestinations := map[string]Change{}
	for _, change := range prepared.Changes {
		key := pathKey(change.Destination)
		if legacyDestinations[key] {
			if change.Kind == RemoveFile {
				plannedDestinations[key] = change
				filtered = append(filtered, change)
			}
			continue
		}
		plannedDestinations[key] = change
		filtered = append(filtered, change)
	}

	primaryBatch := filepath.Join(engine.config.Layout.AppRoot, legacyUpdaterAppFiles[0])
	if prepared.Sequence == 0 {
		shimRecord := FileRecord{Path: legacyUpdaterAppFiles[0], Size: int64(len(legacyBootstrapShim)), SHA256: sha256Bytes([]byte(legacyBootstrapShim))}
		filtered, plannedDestinations, err = engine.planMigrationReplacement(filtered, plannedDestinations, primaryBatch, shimRecord, []byte(legacyBootstrapShim), "legacy-bootstrap-shim")
		if err != nil {
			return PreparedUpdate{}, err
		}
	} else {
		filtered, plannedDestinations, err = planMigrationRemoval(filtered, plannedDestinations, primaryBatch, legacyUpdaterAppFiles[0])
		if err != nil {
			return PreparedUpdate{}, err
		}
	}

	wrapperBatch := filepath.Join(engine.config.Layout.AppRoot, legacyUpdaterAppFiles[1])
	filtered, plannedDestinations, err = planMigrationRemoval(filtered, plannedDestinations, wrapperBatch, legacyUpdaterAppFiles[1])
	if err != nil {
		return PreparedUpdate{}, err
	}

	for _, destination := range []string{
		filepath.Join(engine.config.Layout.AppRoot, "KFPS-Updater.exe"),
		filepath.Join(engine.config.Layout.InstallRoot, "KFPS-Updater.exe"),
	} {
		key := pathKey(destination)
		if existing, planned := plannedDestinations[key]; planned {
			if existing.Kind != ReplaceFile || !strings.EqualFold(existing.Expected.SHA256, currentRecord.SHA256) || existing.Expected.Size != currentRecord.Size {
				return PreparedUpdate{}, fmt.Errorf("update plan conflicts with the running bootstrap at %s", destination)
			}
			continue
		}
		prepared.FilesChecked++
		needsRepair, err := fileNeedsRepair(destination, currentRecord)
		if err != nil {
			return PreparedUpdate{}, err
		}
		if !needsRepair {
			continue
		}
		payload, err := os.ReadFile(engine.config.CurrentExecutable)
		if err != nil {
			return PreparedUpdate{}, err
		}
		stageName := "app-root-updater"
		if strings.EqualFold(filepath.Dir(destination), engine.config.Layout.InstallRoot) {
			stageName = "install-root-updater"
		}
		filtered, plannedDestinations, err = engine.planMigrationReplacement(filtered, plannedDestinations, destination, currentRecord, payload, stageName)
		if err != nil {
			return PreparedUpdate{}, err
		}
	}

	prepared.Changes = filtered
	sortChanges(prepared.Changes, engine.config.Layout.InstallRoot)
	return prepared, nil
}

func (engine *Engine) planMigrationReplacement(changes []Change, planned map[string]Change, destination string, record FileRecord, payload []byte, stageName string) ([]Change, map[string]Change, error) {
	key := pathKey(destination)
	if existing, exists := planned[key]; exists {
		if existing.Kind != ReplaceFile || !strings.EqualFold(existing.Expected.SHA256, record.SHA256) || existing.Expected.Size != record.Size {
			return nil, nil, fmt.Errorf("update plan conflicts with migration replacement at %s", destination)
		}
		return changes, planned, nil
	}
	needsRepair, err := fileNeedsRepair(destination, record)
	if err != nil {
		return nil, nil, err
	}
	if !needsRepair {
		return changes, planned, nil
	}
	staged := filepath.Join(engine.stageDir, "bootstrap-migration", stageName, filepath.Base(destination))
	if err := makeSafeDirectory(filepath.Dir(staged), 0o700); err != nil {
		return nil, nil, err
	}
	if err := os.WriteFile(staged, payload, 0o600); err != nil {
		return nil, nil, err
	}
	stagedHash, err := sha256File(staged)
	if err != nil || !strings.EqualFold(stagedHash, record.SHA256) {
		return nil, nil, fmt.Errorf("staged migration replacement did not verify")
	}
	change := Change{Kind: ReplaceFile, Relative: record.Path, Destination: destination, Staged: staged, Expected: record}
	planned[key] = change
	return append(changes, change), planned, nil
}

func planMigrationRemoval(changes []Change, planned map[string]Change, destination, relative string) ([]Change, map[string]Change, error) {
	key := pathKey(destination)
	if existing, exists := planned[key]; exists {
		if existing.Kind != RemoveFile {
			return nil, nil, fmt.Errorf("update plan conflicts with migration removal at %s", destination)
		}
		return changes, planned, nil
	}
	info, err := os.Lstat(destination)
	if os.IsNotExist(err) {
		return changes, planned, nil
	}
	if err != nil {
		return nil, nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, nil, fmt.Errorf("legacy updater path requires manual remediation because it is not a regular file: %s", destination)
	}
	change := Change{Kind: RemoveFile, Relative: relative, Destination: destination}
	planned[key] = change
	return append(changes, change), planned, nil
}
