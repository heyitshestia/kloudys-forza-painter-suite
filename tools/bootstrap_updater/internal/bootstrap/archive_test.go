package bootstrap

import (
	"archive/zip"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestZipInventoryRejectsTraversalDuplicatesAndLinks(t *testing.T) {
	tests := []struct {
		name    string
		entries []zipTestEntry
	}{
		{name: "traversal", entries: []zipTestEntry{{name: "../escape.txt"}}},
		{name: "case-insensitive duplicate", entries: []zipTestEntry{{name: "safe/File.txt"}, {name: "safe/file.txt"}}},
		{name: "symbolic link", entries: []zipTestEntry{{name: "safe/link", mode: os.ModeSymlink | 0o777}}},
		{name: "noncanonical separator", entries: []zipTestEntry{{name: `safe\file.txt`}}},
		{name: "file parent collision", entries: []zipTestEntry{{name: "safe"}, {name: "safe/file.txt"}}},
		{name: "file child collision", entries: []zipTestEntry{{name: "safe/file.txt"}, {name: "safe"}}},
		{name: "file directory collision", entries: []zipTestEntry{{name: "safe/"}, {name: "safe"}}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "unsafe.zip")
			writeRawZip(t, path, test.entries)
			if inventory, err := openZipInventory(path); err == nil {
				inventory.Close()
				t.Fatal("unsafe ZIP inventory was accepted")
			}
		})
	}
}

type zipTestEntry struct {
	name string
	mode os.FileMode
}

func writeRawZip(t *testing.T, path string, entries []zipTestEntry) {
	t.Helper()
	output, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	archive := zip.NewWriter(output)
	for _, entry := range entries {
		header := &zip.FileHeader{Name: entry.name, Method: zip.Store}
		if entry.mode != 0 {
			header.SetMode(entry.mode)
		}
		writer, err := archive.CreateHeader(header)
		if err != nil {
			t.Fatal(err)
		}
		if !strings.HasSuffix(entry.name, "/") {
			if _, err := writer.Write([]byte("data")); err != nil {
				t.Fatal(err)
			}
		}
	}
	if err := archive.Close(); err != nil {
		t.Fatal(err)
	}
	if err := output.Close(); err != nil {
		t.Fatal(err)
	}
}
