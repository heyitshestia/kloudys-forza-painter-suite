package main

import (
	"archive/zip"
	"io"
	"os"
	"path/filepath"
	"testing"
)

func TestGarageSupportRequiredForGarageSnapshot(t *testing.T) {
	root := t.TempDir()
	if err := validateGarageSupport(root, root); err != nil {
		t.Fatal(err)
	}
	writeBuildTestFile(t, filepath.Join(root, "KFPS.UI", "src", "kfps_ui", "garage_reader.py"), "# worker client")
	if err := validateGarageSupport(root, root); err == nil {
		t.Fatal("missing Garage worker accepted")
	}
	writeBuildTestFile(t, filepath.Join(root, "tools", "garage-reader", "reader.py"), "raise SystemExit(3)")
	if err := validateGarageSupport(root, root); err == nil {
		t.Fatal("missing runtime accepted")
	}
}

func TestGarageInstalledComponentRoundtrip(t *testing.T) {
	root := os.Getenv("KFPS_TEST_GARAGE_ROOT")
	pythonRoot := os.Getenv("KFPS_TEST_GARAGE_PYTHON")
	if root == "" || pythonRoot == "" {
		t.Skip("opt-in installed worker qualification")
	}
	if err := validateGarageSupport(root, pythonRoot); err != nil {
		t.Fatal(err)
	}
	files, err := walkedFiles(filepath.Join(root, "tools", "garage-reader"), "tools/garage-reader", true)
	if err != nil {
		t.Fatal(err)
	}
	for _, file := range files {
		if excludedApplicationPath(file.Path) {
			t.Fatalf("required Garage file excluded: %s", file.Path)
		}
	}
	directory := t.TempDir()
	archive := filepath.Join(directory, "component.zip")
	records, _, err := writeComponent(archive, files, "https://example.invalid/component.zip")
	if err != nil {
		t.Fatal(err)
	}
	if len(records) != len(files) {
		t.Fatal("component inventory lost files")
	}
	installed := filepath.Join(directory, "installed")
	writeBuildTestFile(t, filepath.Join(installed, "KFPS.UI", "src", "kfps_ui", "garage_reader.py"), "# worker client")
	bundle, err := zip.OpenReader(archive)
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range bundle.File {
		target := filepath.Join(installed, filepath.FromSlash(entry.Name))
		if err := os.MkdirAll(filepath.Dir(target), 0700); err != nil {
			t.Fatal(err)
		}
		input, err := entry.Open()
		if err != nil {
			t.Fatal(err)
		}
		output, err := os.Create(target)
		if err != nil {
			input.Close()
			t.Fatal(err)
		}
		_, err = io.Copy(output, input)
		output.Close()
		input.Close()
		if err != nil {
			t.Fatal(err)
		}
	}
	bundle.Close()
	if err := validateGarageSupport(installed, pythonRoot); err != nil {
		t.Fatal(err)
	}
	resource := filepath.Join(installed, "tools", "garage-reader", "support", "profile-support.dll")
	original, err := os.ReadFile(resource)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(resource); err != nil {
		t.Fatal(err)
	}
	if err := validateGarageSupport(installed, pythonRoot); err == nil {
		t.Fatal("missing support accepted")
	}
	if err := os.WriteFile(resource, original, 0600); err != nil {
		t.Fatal(err)
	}
	if err := validateGarageSupport(installed, pythonRoot); err != nil {
		t.Fatal(err)
	}
}
