package bootstrap

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type Layout struct {
	InstallRoot string
	AppRoot     string
}

func ResolveLayout(explicitRoot, executablePath, workingDirectory string) (Layout, error) {
	if strings.TrimSpace(explicitRoot) != "" {
		absolute, err := filepath.Abs(explicitRoot)
		if err != nil {
			return Layout{}, err
		}
		absolute = filepath.Clean(absolute)
		if layout, ok := recognizeLayout(absolute, true); ok {
			return layout, nil
		}
		return Layout{}, fmt.Errorf("the explicit KFPS root is not a recognized installation: %s", absolute)
	}
	type candidate struct {
		path               string
		allowBrokenPackage bool
	}
	candidates := make([]candidate, 0, 2)
	if strings.TrimSpace(executablePath) != "" {
		candidates = append(candidates, candidate{path: filepath.Dir(executablePath), allowBrokenPackage: true})
	}
	if strings.TrimSpace(workingDirectory) != "" {
		candidates = append(candidates, candidate{path: workingDirectory})
	}
	seen := map[string]bool{}
	for _, source := range candidates {
		absolute, err := filepath.Abs(source.path)
		if err != nil {
			continue
		}
		absolute = filepath.Clean(absolute)
		key := strings.ToLower(absolute)
		if seen[key] {
			continue
		}
		seen[key] = true
		if layout, ok := recognizeLayout(absolute, false); ok {
			if err := layout.Validate(); err == nil {
				return layout, nil
			}
		}
		if source.allowBrokenPackage && (fileExists(filepath.Join(absolute, "KFPS.exe")) || fileExists(filepath.Join(absolute, "RELEASE-MANIFEST.json"))) {
			layout := Layout{InstallRoot: absolute, AppRoot: filepath.Join(absolute, "KloudysFH6Painter")}
			if err := layout.Validate(); err == nil {
				return layout, nil
			}
		}
	}
	return Layout{}, fmt.Errorf("could not locate a KFPS installation; place KFPS-Updater.exe beside KFPS.exe or pass --root")
}

func recognizeLayout(candidate string, explicit bool) (Layout, bool) {
	child := filepath.Join(candidate, "KloudysFH6Painter")
	if isDirectory(child) {
		return Layout{InstallRoot: candidate, AppRoot: child}, true
	}
	if strings.EqualFold(filepath.Base(candidate), "KloudysFH6Painter") && isDirectory(candidate) {
		return Layout{InstallRoot: filepath.Dir(candidate), AppRoot: candidate}, true
	}
	// Early source-style releases kept VERSION beside app.py at the package root.
	// A dropped-in bootstrap marker makes that directory an incomplete outer
	// package, not a modern direct-source layout.
	if explicit && !isDirectory(filepath.Join(candidate, "KFPS.UI")) &&
		(fileExists(filepath.Join(candidate, "KFPS.exe")) ||
			fileExists(filepath.Join(candidate, "KFPS-Updater.exe")) ||
			fileExists(filepath.Join(candidate, "RELEASE-MANIFEST.json"))) {
		return Layout{InstallRoot: candidate, AppRoot: child}, true
	}
	if fileExists(filepath.Join(candidate, "VERSION")) || isDirectory(filepath.Join(candidate, "KFPS.UI")) {
		if explicit && !strings.EqualFold(filepath.Base(candidate), "KloudysFH6Painter") {
			return Layout{InstallRoot: candidate, AppRoot: candidate}, true
		}
		return Layout{InstallRoot: filepath.Dir(candidate), AppRoot: candidate}, true
	}
	if explicit && (fileExists(filepath.Join(candidate, "KFPS.exe")) || fileExists(filepath.Join(candidate, "KFPS-Updater.exe")) || fileExists(filepath.Join(candidate, "RELEASE-MANIFEST.json"))) {
		return Layout{InstallRoot: candidate, AppRoot: child}, true
	}
	return Layout{}, false
}

func (layout Layout) Validate() error {
	install, err := filepath.Abs(layout.InstallRoot)
	if err != nil {
		return err
	}
	app, err := filepath.Abs(layout.AppRoot)
	if err != nil {
		return err
	}
	if filepath.Clean(install) == filepath.VolumeName(install)+string(filepath.Separator) {
		return fmt.Errorf("refusing to use a drive root as the KFPS installation")
	}
	rel, err := filepath.Rel(install, app)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return fmt.Errorf("application root is outside the installation root")
	}
	if err := ensureNoLinkedPath(install); err != nil {
		return fmt.Errorf("installation root is unsafe: %w", err)
	}
	if err := ensureSafeContainedPath(install, app); err != nil {
		return fmt.Errorf("application root is unsafe: %w", err)
	}
	if strings.EqualFold(install, app) {
		if !fileExists(filepath.Join(app, "VERSION")) || !isDirectory(filepath.Join(app, "KFPS.UI")) {
			return fmt.Errorf("direct source layout is missing VERSION or KFPS.UI")
		}
		return nil
	}
	if !strings.EqualFold(filepath.Base(app), "KloudysFH6Painter") {
		return fmt.Errorf("application root must be named KloudysFH6Painter")
	}
	return nil
}

func (layout Layout) TargetRoot(target string) (string, error) {
	switch target {
	case "install-root":
		return layout.InstallRoot, nil
	case "app-root":
		return layout.AppRoot, nil
	default:
		return "", fmt.Errorf("unsupported component target %q", target)
	}
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}

func isDirectory(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}
