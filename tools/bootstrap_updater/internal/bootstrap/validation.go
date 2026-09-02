package bootstrap

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

var sha256Pattern = regexp.MustCompile(`^[0-9a-fA-F]{64}$`)
var gitCommitPattern = regexp.MustCompile(`^[0-9a-fA-F]{40}$`)
var releaseVersionPattern = regexp.MustCompile(`^[0-9]+\.[0-9]+(?:\.[0-9]+){0,2}$`)

var windowsReservedNames = map[string]bool{
	"CON": true, "PRN": true, "AUX": true, "NUL": true,
	"COM1": true, "COM2": true, "COM3": true, "COM4": true, "COM5": true, "COM6": true, "COM7": true, "COM8": true, "COM9": true,
	"LPT1": true, "LPT2": true, "LPT3": true, "LPT4": true, "LPT5": true, "LPT6": true, "LPT7": true, "LPT8": true, "LPT9": true,
}

func decodeStrictJSON(payload []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if decoder.Decode(&struct{}{}) != io.EOF {
		return fmt.Errorf("JSON contains trailing data")
	}
	return nil
}

func normalizeSHA256(value string) (string, error) {
	value = strings.ToLower(strings.TrimSpace(value))
	if !sha256Pattern.MatchString(value) {
		return "", fmt.Errorf("invalid SHA-256 value %q", value)
	}
	return value, nil
}

func sha256File(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func validateArtifact(name string, artifact Artifact) error {
	if strings.TrimSpace(artifact.URL) == "" {
		return fmt.Errorf("%s URL is empty", name)
	}
	if _, err := normalizeSHA256(artifact.SHA256); err != nil {
		return fmt.Errorf("%s: %w", name, err)
	}
	if artifact.Size <= 0 || artifact.Size > 4*1024*1024*1024 {
		return fmt.Errorf("%s size %d is outside the supported range", name, artifact.Size)
	}
	return nil
}

func cleanRelativePath(value string) (string, error) {
	if value != strings.TrimSpace(value) {
		return "", fmt.Errorf("unsafe relative path %q", value)
	}
	if value == "" || strings.Contains(value, "\\") || strings.HasPrefix(value, "/") || strings.Contains(value, ":") {
		return "", fmt.Errorf("unsafe relative path %q", value)
	}
	cleaned := filepath.ToSlash(filepath.Clean(filepath.FromSlash(value)))
	if cleaned != value || cleaned == "." || cleaned == ".." || strings.HasPrefix(cleaned, "../") {
		return "", fmt.Errorf("unsafe relative path %q", value)
	}
	for _, part := range strings.Split(cleaned, "/") {
		if part == "" || part == "." || part == ".." {
			return "", fmt.Errorf("unsafe relative path %q", value)
		}
		if strings.ContainsAny(part, "<>\"|?*") || strings.HasSuffix(part, ".") || strings.HasSuffix(part, " ") {
			return "", fmt.Errorf("path is not portable to Windows %q", value)
		}
		for _, character := range part {
			if character < 32 {
				return "", fmt.Errorf("path contains a control character %q", value)
			}
		}
		base := strings.ToUpper(strings.SplitN(part, ".", 2)[0])
		if windowsReservedNames[base] {
			return "", fmt.Errorf("path uses a reserved Windows name %q", value)
		}
	}
	return cleaned, nil
}

func ValidateUpdaterStateDir(value string, layout Layout) (string, error) {
	if strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("updater state directory is required")
	}
	state, err := filepath.Abs(value)
	if err != nil {
		return "", err
	}
	state = filepath.Clean(state)
	if state == filepath.VolumeName(state)+string(filepath.Separator) {
		return "", fmt.Errorf("refusing to use a drive root as updater state")
	}
	if info, statErr := os.Stat(state); statErr == nil && !info.IsDir() {
		return "", fmt.Errorf("updater state path is not a directory")
	} else if statErr != nil && !os.IsNotExist(statErr) {
		return "", statErr
	}
	install, err := filepath.Abs(layout.InstallRoot)
	if err != nil {
		return "", err
	}
	app, err := filepath.Abs(layout.AppRoot)
	if err != nil {
		return "", err
	}
	if pathIsContained(install, state) || pathIsContained(state, install) || pathIsContained(app, state) || pathIsContained(state, app) {
		return "", fmt.Errorf("updater state directory must be separate from the KFPS installation")
	}
	if err := ensureNoLinkedPath(state); err != nil {
		return "", fmt.Errorf("updater state directory is unsafe: %w", err)
	}
	return state, nil
}

func ValidateComponentFilePath(component Component, relative string) error {
	return validateComponentPath(component, relative)
}

func pathKey(value string) string {
	return strings.ToLower(filepath.ToSlash(value))
}

func joinContained(root, relative string) (string, error) {
	clean, err := cleanRelativePath(relative)
	if err != nil {
		return "", err
	}
	rootAbs, err := filepath.Abs(root)
	if err != nil {
		return "", err
	}
	target, err := filepath.Abs(filepath.Join(rootAbs, filepath.FromSlash(clean)))
	if err != nil {
		return "", err
	}
	rel, err := filepath.Rel(rootAbs, target)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("path %q escapes target root", relative)
	}
	if err := ensureSafeContainedPath(rootAbs, target); err != nil {
		return "", err
	}
	return target, nil
}

func parseVersion(value string) ([]int, error) {
	value = strings.TrimSpace(strings.TrimPrefix(value, "v"))
	if value == "dev" {
		return []int{0}, nil
	}
	parts := strings.Split(value, ".")
	if len(parts) < 2 || len(parts) > 4 {
		return nil, fmt.Errorf("invalid version %q", value)
	}
	parsed := make([]int, len(parts))
	for index, part := range parts {
		number, err := strconv.Atoi(part)
		if err != nil || number < 0 {
			return nil, fmt.Errorf("invalid version %q", value)
		}
		parsed[index] = number
	}
	return parsed, nil
}

func compareVersions(left, right string) (int, error) {
	a, err := parseVersion(left)
	if err != nil {
		return 0, err
	}
	b, err := parseVersion(right)
	if err != nil {
		return 0, err
	}
	length := len(a)
	if len(b) > length {
		length = len(b)
	}
	for index := 0; index < length; index++ {
		av, bv := 0, 0
		if index < len(a) {
			av = a[index]
		}
		if index < len(b) {
			bv = b[index]
		}
		if av < bv {
			return -1, nil
		}
		if av > bv {
			return 1, nil
		}
	}
	return 0, nil
}

func ValidateVersion(value string) error {
	_, err := parseVersion(value)
	return err
}

func ValidateReleaseVersion(value string) error {
	if value != strings.TrimSpace(value) || !releaseVersionPattern.MatchString(value) {
		return fmt.Errorf("invalid release version %q", value)
	}
	return ValidateVersion(value)
}
