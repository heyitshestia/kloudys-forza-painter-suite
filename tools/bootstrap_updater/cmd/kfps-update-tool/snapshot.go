package main

import (
	"archive/zip"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
)

func validatePublicationOutput(output string, sourceRoots ...string) error {
	canonicalOutput, err := canonicalProspectivePath(output)
	if err != nil {
		return err
	}
	if canonicalOutput == filepath.VolumeName(canonicalOutput)+string(filepath.Separator) {
		return fmt.Errorf("refusing to publish to a filesystem root")
	}
	for _, source := range sourceRoots {
		canonicalSource, err := canonicalProspectivePath(source)
		if err != nil {
			return err
		}
		if pathsOverlap(canonicalOutput, canonicalSource) {
			return fmt.Errorf("payload output must be disjoint from source root %s", source)
		}
	}
	info, err := os.Lstat(output)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return fmt.Errorf("payload output must be an absent or empty regular directory: %s", output)
	}
	entries, err := os.ReadDir(output)
	if err != nil {
		return err
	}
	if len(entries) != 0 {
		return fmt.Errorf("payload output directory is not empty: %s", output)
	}
	return nil
}

func canonicalProspectivePath(value string) (string, error) {
	absolute, err := filepath.Abs(value)
	if err != nil {
		return "", err
	}
	absolute = filepath.Clean(absolute)
	current := absolute
	missing := []string{}
	for {
		if _, err := os.Lstat(current); err == nil {
			break
		} else if !os.IsNotExist(err) {
			return "", err
		}
		parent := filepath.Dir(current)
		if parent == current {
			break
		}
		missing = append(missing, filepath.Base(current))
		current = parent
	}
	resolved, err := filepath.EvalSymlinks(current)
	if err != nil {
		return "", err
	}
	for index := len(missing) - 1; index >= 0; index-- {
		resolved = filepath.Join(resolved, missing[index])
	}
	return filepath.Clean(resolved), nil
}

func pathsOverlap(left, right string) bool {
	return pathContains(left, right) || pathContains(right, left)
}

func pathContains(root, target string) bool {
	if runtime.GOOS == "windows" {
		root = strings.ToLower(root)
		target = strings.ToLower(target)
	}
	relative, err := filepath.Rel(root, target)
	return err == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator))
}

func createGitSnapshot(repository, commit, destination string) error {
	if err := os.MkdirAll(filepath.Dir(destination), 0o700); err != nil {
		return err
	}
	archivePath := destination + ".zip"
	command := exec.Command("git", "-C", repository, "archive", "--format=zip", "--output", archivePath, commit)
	if output, err := command.CombinedOutput(); err != nil {
		return fmt.Errorf("create immutable Git snapshot: %w: %s", err, strings.TrimSpace(string(output)))
	}
	defer os.Remove(archivePath)
	return extractSnapshotArchive(archivePath, destination)
}

func extractSnapshotArchive(archivePath, destination string) error {
	archive, err := zip.OpenReader(archivePath)
	if err != nil {
		return err
	}
	defer archive.Close()
	if len(archive.File) == 0 || len(archive.File) > 200000 {
		return fmt.Errorf("Git snapshot contains %d entries", len(archive.File))
	}
	if err := os.MkdirAll(destination, 0o700); err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, entry := range archive.File {
		relative, err := cleanSnapshotPath(entry.Name)
		if err != nil {
			return err
		}
		key := strings.ToLower(relative)
		if seen[key] {
			return fmt.Errorf("Git snapshot contains duplicate path %s", relative)
		}
		seen[key] = true
		target := filepath.Join(destination, filepath.FromSlash(relative))
		if !pathContains(destination, target) {
			return fmt.Errorf("Git snapshot path escapes its destination: %s", relative)
		}
		if entry.FileInfo().IsDir() {
			if err := os.MkdirAll(target, 0o700); err != nil {
				return err
			}
			continue
		}
		if !entry.Mode().IsRegular() {
			return fmt.Errorf("Git snapshot contains a non-regular entry: %s", relative)
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o700); err != nil {
			return err
		}
		input, err := entry.Open()
		if err != nil {
			return err
		}
		output, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
		if err != nil {
			input.Close()
			return err
		}
		_, copyErr := io.Copy(output, input)
		inputErr := input.Close()
		syncErr := output.Sync()
		outputErr := output.Close()
		for _, candidate := range []error{copyErr, inputErr, syncErr, outputErr} {
			if candidate != nil {
				return candidate
			}
		}
	}
	return nil
}

func cleanSnapshotPath(value string) (string, error) {
	if value == "" || strings.Contains(value, "\\") || strings.Contains(value, ":") || strings.HasPrefix(value, "/") {
		return "", fmt.Errorf("Git snapshot contains unsafe path %q", value)
	}
	clean := filepath.ToSlash(filepath.Clean(filepath.FromSlash(value)))
	clean = strings.TrimSuffix(clean, "/")
	if clean == "" || clean == "." || clean == ".." || strings.HasPrefix(clean, "../") {
		return "", fmt.Errorf("Git snapshot contains unsafe path %q", value)
	}
	return clean, nil
}

func copyRuntimeSnapshot(source, destination string) error {
	files, err := walkedFiles(source, "", true)
	if err != nil {
		return err
	}
	for _, file := range files {
		target := filepath.Join(destination, filepath.FromSlash(file.Path))
		if err := os.MkdirAll(filepath.Dir(target), 0o700); err != nil {
			return err
		}
		if err := copyFileExclusive(file.Source, target); err != nil {
			return err
		}
	}
	return nil
}

func walkedApplicationFiles(root string) ([]payloadFile, error) {
	files := []payloadFile{}
	err := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			if path != root {
				relative, err := filepath.Rel(root, path)
				if err != nil {
					return err
				}
				if excludedApplicationPath(filepath.ToSlash(relative) + "/") {
					return filepath.SkipDir
				}
			}
			return nil
		}
		if !entry.Type().IsRegular() {
			return fmt.Errorf("application snapshot contains a non-regular file: %s", path)
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		if excludedApplicationPath(relative) {
			return nil
		}
		files = append(files, payloadFile{Source: path, Path: relative})
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Slice(files, func(left, right int) bool { return files[left].Path < files[right].Path })
	return files, nil
}

func verifyGitSourceIdentity(repository, commit string) error {
	payload, err := exec.Command("git", "-C", repository, "rev-parse", "HEAD").Output()
	if err != nil {
		return fmt.Errorf("recheck Git commit: %w", err)
	}
	if !strings.EqualFold(strings.TrimSpace(string(payload)), commit) {
		return fmt.Errorf("source HEAD changed while publishing")
	}
	return requireCleanTrackedFiles(repository)
}

func promotePayload(staged, output string) error {
	if err := validatePublicationOutput(output); err != nil {
		return err
	}
	if info, err := os.Lstat(output); err == nil {
		if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("payload output changed before promotion")
		}
		if err := os.Remove(output); err != nil {
			return err
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	return os.Rename(staged, output)
}
