package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/heyitshestia/kloudys-forza-painter-suite/tools/bootstrap_updater/internal/bootstrap"
)

// The baseline is generated inside the immutable snapshot and is covered by the
// signed application component. Existing exact runtime-root repair owns delivery.
func writeEditorBaseline(root, pythonRoot string) error {
	if _, err := os.Stat(filepath.Join(root, "KFPS.Editor", "manifest.json")); os.IsNotExist(err) {
		return nil // Historical non-editor fixtures/releases retain their format.
	} else if err != nil {
		return err
	}
	tool := filepath.Join(root, "tools", "editor_baseline.py")
	if !fileIsRegular(tool) {
		return fmt.Errorf("editor baseline builder is missing")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	command := exec.CommandContext(ctx, filepath.Join(pythonRoot, "python.exe"), "-I", "-B", tool, "--app-root", root, "--python-root", pythonRoot)
	output, err := command.CombinedOutput()
	if err != nil {
		return fmt.Errorf("editor baseline validation failed: %w: %.2000s", err, output)
	}
	if !fileIsRegular(filepath.Join(root, "KFPS.Editor", "baseline.json")) {
		return fmt.Errorf("editor baseline was not produced")
	}
	return nil
}

// Read from the same immutable Git snapshot as the application payload. Retire
// exact old program paths only; never infer a recursive directory deletion.
func editorRetiredFiles(root string) ([]string, error) {
	if _, err := os.Stat(filepath.Join(root, "KFPS.Editor", "manifest.json")); os.IsNotExist(err) {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	path := filepath.Join(root, "KFPS.Editor", "retired-files.json")
	info, err := os.Stat(path)
	if err != nil || info == nil || info.Size() > 1024*1024 {
		return nil, fmt.Errorf("missing or oversized editor retirement inventory")
	}
	payload, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var index struct {
		Schema string   `json:"schema"`
		Files  []string `json:"files"`
	}
	if err := json.Unmarshal(payload, &index); err != nil {
		return nil, err
	}
	if index.Schema != "kfps-editor-retired-files/1" || len(index.Files) > 4096 {
		return nil, fmt.Errorf("invalid editor retirement inventory")
	}
	seen := map[string]bool{}
	for _, name := range index.Files {
		if err := bootstrap.ValidateComponentFilePath(bootstrap.Component{Name: "application", Target: "app-root"}, name); err != nil {
			return nil, err
		}
		key := strings.ToLower(name)
		if seen[key] || !(strings.HasPrefix(name, "tools/fabric-editor/") || name == "tools/editor_manifest.json") {
			return nil, fmt.Errorf("invalid or duplicate retired editor path: %s", name)
		}
		seen[key] = true
		if _, err := os.Stat(filepath.Join(root, filepath.FromSlash(name))); !os.IsNotExist(err) {
			return nil, fmt.Errorf("retired editor path still exists or cannot be checked: %s", name)
		}
	}
	return index.Files, nil
}
