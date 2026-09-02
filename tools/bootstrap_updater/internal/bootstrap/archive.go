package bootstrap

import (
	"archive/zip"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const (
	maximumArchiveFiles = 50000
	maximumArchiveBytes = int64(4 * 1024 * 1024 * 1024)
	maximumManifestSize = int64(32 * 1024 * 1024)
)

type zipInventory struct {
	archive *zip.ReadCloser
	files   map[string]*zip.File
	actual  map[string]string
	total   int64
}

func openZipInventory(path string) (*zipInventory, error) {
	archive, err := zip.OpenReader(path)
	if err != nil {
		return nil, err
	}
	inventory := &zipInventory{
		archive: archive,
		files:   map[string]*zip.File{},
		actual:  map[string]string{},
	}
	directories := map[string]bool{}
	if len(archive.File) > maximumArchiveFiles+1000 {
		archive.Close()
		return nil, fmt.Errorf("archive contains too many entries")
	}
	for _, entry := range archive.File {
		if strings.Contains(entry.Name, "\\") {
			archive.Close()
			return nil, fmt.Errorf("archive path is not canonical: %s", entry.Name)
		}
		name := strings.ReplaceAll(entry.Name, "\\", "/")
		if strings.HasSuffix(name, "/") {
			clean, err := cleanRelativePath(strings.TrimSuffix(name, "/"))
			if err != nil || clean != strings.TrimSuffix(name, "/") {
				archive.Close()
				return nil, fmt.Errorf("unsafe archive directory %q: %w", entry.Name, err)
			}
			key := pathKey(clean)
			if _, exists := inventory.files[key]; exists {
				archive.Close()
				return nil, fmt.Errorf("archive path is both a file and directory: %s", clean)
			}
			directories[key] = true
			continue
		}
		clean, err := cleanRelativePath(name)
		if err != nil || clean != name {
			archive.Close()
			return nil, fmt.Errorf("unsafe archive file %q", entry.Name)
		}
		if entry.FileInfo().Mode()&os.ModeSymlink != 0 {
			archive.Close()
			return nil, fmt.Errorf("archive contains a symbolic link: %s", name)
		}
		if entry.UncompressedSize64 > uint64(maximumArchiveBytes) {
			archive.Close()
			return nil, fmt.Errorf("archive file is too large: %s", name)
		}
		inventory.total += int64(entry.UncompressedSize64)
		if inventory.total > maximumArchiveBytes {
			archive.Close()
			return nil, fmt.Errorf("archive expands beyond the supported limit")
		}
		key := pathKey(clean)
		if directories[key] {
			archive.Close()
			return nil, fmt.Errorf("archive path is both a file and directory: %s", clean)
		}
		for parent := filepath.ToSlash(filepath.Dir(clean)); parent != "."; parent = filepath.ToSlash(filepath.Dir(parent)) {
			if _, exists := inventory.files[pathKey(parent)]; exists {
				archive.Close()
				return nil, fmt.Errorf("archive file is nested below another file: %s", clean)
			}
		}
		if _, exists := inventory.files[key]; exists {
			archive.Close()
			return nil, fmt.Errorf("archive contains duplicate path %s", clean)
		}
		inventory.files[key] = entry
		inventory.actual[key] = clean
	}
	keys := make([]string, 0, len(inventory.files))
	for key := range inventory.files {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		for parent := filepath.ToSlash(filepath.Dir(key)); parent != "."; parent = filepath.ToSlash(filepath.Dir(parent)) {
			if _, exists := inventory.files[pathKey(parent)]; exists {
				archive.Close()
				return nil, fmt.Errorf("archive file is nested below another file: %s", inventory.actual[key])
			}
		}
	}
	return inventory, nil
}

func ValidateComponentArchiveFile(path string, component Component) error {
	records, err := validateFileRecords(component.Files)
	if err != nil {
		return err
	}
	inventory, err := openZipInventory(path)
	if err != nil {
		return err
	}
	defer inventory.Close()
	if len(inventory.files) != len(records) {
		return fmt.Errorf("archive contains %d files; manifest declares %d", len(inventory.files), len(records))
	}
	for key, record := range records {
		entry := inventory.files[key]
		if entry == nil || int64(entry.UncompressedSize64) != record.Size {
			return fmt.Errorf("archive is missing or mis-sizes %s", record.Path)
		}
		reader, err := entry.Open()
		if err != nil {
			return err
		}
		hash := sha256.New()
		written, copyErr := io.Copy(hash, io.LimitReader(reader, record.Size+1))
		closeErr := reader.Close()
		if copyErr != nil {
			return copyErr
		}
		if closeErr != nil {
			return closeErr
		}
		if written != record.Size || hex.EncodeToString(hash.Sum(nil)) != strings.ToLower(record.SHA256) {
			return fmt.Errorf("archive content does not match manifest for %s", record.Path)
		}
	}
	return nil
}

func (inventory *zipInventory) Close() error {
	return inventory.archive.Close()
}

func (inventory *zipInventory) read(name string, maximum int64) ([]byte, error) {
	entry := inventory.files[pathKey(name)]
	if entry == nil {
		return nil, fmt.Errorf("archive is missing %s", name)
	}
	if int64(entry.UncompressedSize64) > maximum {
		return nil, fmt.Errorf("archive entry %s exceeds %d bytes", name, maximum)
	}
	reader, err := entry.Open()
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	payload, err := io.ReadAll(io.LimitReader(reader, maximum+1))
	if err != nil {
		return nil, err
	}
	if int64(len(payload)) > maximum {
		return nil, fmt.Errorf("archive entry %s exceeds %d bytes", name, maximum)
	}
	return payload, nil
}

func (inventory *zipInventory) extract(name, destination string, record FileRecord) error {
	entry := inventory.files[pathKey(name)]
	if entry == nil {
		return fmt.Errorf("archive is missing %s", name)
	}
	if int64(entry.UncompressedSize64) != record.Size {
		return fmt.Errorf("archive size mismatch for %s", name)
	}
	reader, err := entry.Open()
	if err != nil {
		return err
	}
	defer reader.Close()
	if err := ensureNoLinkedPath(destination); err != nil {
		return err
	}
	if err := makeSafeDirectory(filepath.Dir(destination), 0o755); err != nil {
		return err
	}
	temporary := destination + ".partial"
	if err := ensureNoLinkedPath(temporary); err != nil {
		return err
	}
	output, err := os.OpenFile(temporary, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	written, copyErr := io.Copy(output, io.LimitReader(reader, record.Size+1))
	syncErr := output.Sync()
	closeErr := output.Close()
	if copyErr != nil || syncErr != nil || closeErr != nil || written != record.Size {
		_ = os.Remove(temporary)
		if copyErr != nil {
			return copyErr
		}
		if syncErr != nil {
			return syncErr
		}
		if closeErr != nil {
			return closeErr
		}
		return fmt.Errorf("archive extraction size mismatch for %s", name)
	}
	hash, err := sha256File(temporary)
	if err != nil {
		_ = os.Remove(temporary)
		return err
	}
	expected, _ := normalizeSHA256(record.SHA256)
	if hash != expected {
		_ = os.Remove(temporary)
		return fmt.Errorf("archive file hash mismatch for %s", name)
	}
	if err := os.Rename(temporary, destination); err != nil {
		_ = os.Remove(temporary)
		return err
	}
	return nil
}
