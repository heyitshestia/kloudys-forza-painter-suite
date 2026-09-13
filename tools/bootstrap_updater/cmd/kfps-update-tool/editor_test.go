package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestEditorBaselineRequiredForModernSnapshot(t *testing.T) {
	root := t.TempDir()
	if err := writeEditorBaseline(root, root); err != nil { t.Fatal(err) }
	writeBuildTestFile(t, filepath.Join(root, "KFPS.Editor", "manifest.json"), "{}")
	if err := writeEditorBaseline(root, root); err == nil { t.Fatal("missing baseline generator accepted") }
	writeBuildTestFile(t, filepath.Join(root, "tools", "editor_baseline.py"), "raise RuntimeError('broken')")
	if err := writeEditorBaseline(root, filepath.Join(root, "missing")); err == nil { t.Fatal("missing runtime accepted") }
}

func TestEditorRetirementInventory(t *testing.T) {
	root := t.TempDir()
	if files, err := editorRetiredFiles(root); err != nil || len(files) != 0 {
		t.Fatalf("legacy snapshot changed: %v %v", files, err)
	}
	writeBuildTestFile(t, filepath.Join(root, "KFPS.Editor", "manifest.json"), "{}")
	if _, err := editorRetiredFiles(root); err == nil {
		t.Fatal("new package without retirement inventory was accepted")
	}
	for _, fixture := range []struct {
		name  string
		files []string
		valid bool
	}{
		{"exact program file", []string{"tools/fabric-editor/editor.js"}, true},
		{"profile", []string{"runtime/fabric-editor/preferences.json"}, false},
		{"traversal", []string{"tools/fabric-editor/../../runtime/user.json"}, false},
		{"duplicate", []string{"tools/fabric-editor/editor.js", "tools/fabric-editor/EDITOR.js"}, false},
		{"new package", []string{"KFPS.Editor/web/editor.js"}, false},
	} {
		t.Run(fixture.name, func(t *testing.T) {
			data, _ := json.Marshal(map[string]any{"schema": "kfps-editor-retired-files/1", "files": fixture.files})
			if err := os.WriteFile(filepath.Join(root, "KFPS.Editor", "retired-files.json"), data, 0600); err != nil {
				t.Fatal(err)
			}
			_, err := editorRetiredFiles(root)
			if (err == nil) != fixture.valid {
				t.Fatalf("valid=%v, got %v", fixture.valid, err)
			}
		})
	}
	writeBuildTestFile(t, filepath.Join(root, "KFPS.Editor", "retired-files.json"), `{"schema":"kfps-editor-retired-files/1","files":["tools/fabric-editor/start_fabric_editor.py"]}`)
	writeBuildTestFile(t, filepath.Join(root, "tools", "fabric-editor", "start_fabric_editor.py"), "compatibility adapter")
	if _, err := editorRetiredFiles(root); err == nil {
		t.Fatal("live compatibility adapter could be retired")
	}
}
