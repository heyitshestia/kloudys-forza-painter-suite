package main

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/heyitshestia/kloudys-forza-painter-suite/tools/bootstrap_updater/internal/bootstrap"
)

type repeatedFlag []string

func (values *repeatedFlag) String() string { return strings.Join(*values, ",") }
func (values *repeatedFlag) Set(value string) error {
	*values = append(*values, value)
	return nil
}

type payloadFile struct {
	Source string
	Path   string
}

type updaterBuildInfo struct {
	Schema   string `json:"schema"`
	Version  string `json:"version"`
	KeyID    string `json:"key_id"`
	Platform string `json:"platform"`
}

func buildPayload(arguments []string) error {
	flags := flag.NewFlagSet("build", flag.ContinueOnError)
	appRootArg := flags.String("app-root", "", "KFPS source checkout")
	pythonRootArg := flags.String("python-root", "", "validated bundled Python runtime")
	updaterArg := flags.String("updater", "", "built KFPS-Updater.exe")
	privateArg := flags.String("private", "", "production private key")
	publicArg := flags.String("public", "", "production public key")
	outputArg := flags.String("output", "", "empty payload output directory")
	baseURLArg := flags.String("base-url", "", "HTTPS payload base URL")
	versionArg := flags.String("version", "", "KFPS version; defaults to VERSION")
	commitArg := flags.String("commit", "", "Git commit; defaults to HEAD")
	bootstrapVersion := flags.String("bootstrap-version", "1.0.1", "bootstrap updater version")
	sequence := flags.Uint64("sequence", 0, "monotonic stable-channel sequence")
	publishedArg := flags.String("published-utc", "", "RFC3339 publication timestamp")
	retired := repeatedFlag{
		"03_update_from_github.bat",
		"update_from_github.bat",
	}
	flags.Var(&retired, "retired-file", "application-relative file to retire; repeatable")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *appRootArg == "" || *pythonRootArg == "" || *updaterArg == "" || *privateArg == "" || *publicArg == "" || *outputArg == "" || *baseURLArg == "" || *sequence == 0 {
		return fmt.Errorf("app root, Python root, updater, keys, output, base URL, and non-zero sequence are required")
	}
	appRoot, err := filepath.Abs(*appRootArg)
	if err != nil {
		return err
	}
	pythonRoot, err := filepath.Abs(*pythonRootArg)
	if err != nil {
		return err
	}
	updaterPath, err := filepath.Abs(*updaterArg)
	if err != nil {
		return err
	}
	output, err := filepath.Abs(*outputArg)
	if err != nil {
		return err
	}
	if !fileIsRegular(filepath.Join(appRoot, "KFPS.exe")) || !fileIsRegular(filepath.Join(pythonRoot, "python.exe")) || !fileIsRegular(updaterPath) {
		return fmt.Errorf("app launcher, Python runtime, or bootstrap updater is missing")
	}
	if err := validatePublicationOutput(output, appRoot, pythonRoot); err != nil {
		return err
	}
	baseURL, err := validateBaseURL(*baseURLArg)
	if err != nil {
		return err
	}
	if err := bootstrap.ValidateReleaseVersion(*bootstrapVersion); err != nil {
		return fmt.Errorf("invalid bootstrap version: %w", err)
	}
	commit := strings.TrimSpace(*commitArg)
	headPayload, err := exec.Command("git", "-C", appRoot, "rev-parse", "HEAD").Output()
	if err != nil {
		return fmt.Errorf("resolve Git commit: %w", err)
	}
	head := strings.TrimSpace(string(headPayload))
	if commit == "" {
		commit = head
	}
	if len(commit) != 40 || !strings.EqualFold(commit, head) {
		return fmt.Errorf("component payloads must identify the current 40-character HEAD commit")
	}
	if err := requireCleanTrackedFiles(appRoot); err != nil {
		return err
	}
	published := strings.TrimSpace(*publishedArg)
	if published == "" {
		published = time.Now().UTC().Format(time.RFC3339)
	} else if _, err := time.Parse(time.RFC3339, published); err != nil {
		return fmt.Errorf("invalid --published-utc: %w", err)
	}

	if err := os.MkdirAll(filepath.Dir(output), 0o755); err != nil {
		return err
	}
	workspace, err := os.MkdirTemp(filepath.Dir(output), ".kfps-publish-work-*")
	if err != nil {
		return err
	}
	defer os.RemoveAll(workspace)
	appSnapshot := filepath.Join(workspace, "application-source")
	pythonSnapshot := filepath.Join(workspace, "python-source")
	updaterSnapshot := filepath.Join(workspace, "updater-source.exe")
	if err := createGitSnapshot(appRoot, commit, appSnapshot); err != nil {
		return err
	}
	if err := copyRuntimeSnapshot(pythonRoot, pythonSnapshot); err != nil {
		return fmt.Errorf("snapshot Python runtime: %w", err)
	}
	if err := copyFileExclusive(updaterPath, updaterSnapshot); err != nil {
		return fmt.Errorf("snapshot bootstrap updater: %w", err)
	}
	versionPayload, err := os.ReadFile(filepath.Join(appSnapshot, "VERSION"))
	if err != nil {
		return err
	}
	version := strings.TrimSpace(string(versionPayload))
	if err := bootstrap.ValidateReleaseVersion(version); err != nil {
		return err
	}
	if requested := strings.TrimSpace(*versionArg); requested != "" && requested != version {
		return fmt.Errorf("--version %s does not match packaged VERSION %s from the immutable snapshot", requested, version)
	}
	if string(versionPayload) != version+"\n" {
		return fmt.Errorf("snapshotted VERSION must contain exactly %s followed by one LF; got %q", version, string(versionPayload))
	}
	privatePayload, err := os.ReadFile(*privateArg)
	if err != nil {
		return err
	}
	privateKey, err := bootstrap.DecodePrivateKey(string(privatePayload))
	if err != nil {
		return err
	}
	publicPayload, err := os.ReadFile(*publicArg)
	if err != nil {
		return err
	}
	publicKey, err := bootstrap.DecodePublicKey(string(publicPayload))
	if err != nil {
		return err
	}
	derivedPublic := privateKey.Public().(ed25519.PublicKey)
	if !bytes.Equal(derivedPublic, publicKey) {
		return fmt.Errorf("private key does not match the production public key")
	}
	requestedOutput := output
	output = filepath.Join(workspace, "payload")
	if err := os.MkdirAll(output, 0o700); err != nil {
		return err
	}
	updaterName := "KFPS-Updater-" + *bootstrapVersion + ".exe"
	updaterOutput := filepath.Join(output, updaterName)
	if err := copyFileExclusive(updaterSnapshot, updaterOutput); err != nil {
		return err
	}
	buildInfo, err := inspectUpdaterBuild(updaterOutput)
	if err != nil {
		return err
	}
	if buildInfo.Version != *bootstrapVersion {
		return fmt.Errorf("updater reports version %s; publication requested %s", buildInfo.Version, *bootstrapVersion)
	}
	if buildInfo.KeyID != bootstrap.KeyID(publicKey) {
		return fmt.Errorf("updater trusts key %s; publication uses %s", buildInfo.KeyID, bootstrap.KeyID(publicKey))
	}
	for _, retiredPath := range retired {
		if err := bootstrap.ValidateComponentFilePath(bootstrap.Component{Name: "application", Target: "app-root"}, retiredPath); err != nil {
			return fmt.Errorf("invalid retired application file: %w", err)
		}
	}

	applicationFiles, err := walkedApplicationFiles(appSnapshot)
	if err != nil {
		return err
	}
	applicationFiles = excludeRetiredApplicationFiles(applicationFiles, retired)
	applicationFiles, err = includeInnerUpdater(applicationFiles, updaterOutput)
	if err != nil {
		return err
	}
	pythonFiles, err := walkedFiles(pythonSnapshot, "python", false)
	if err != nil {
		return err
	}
	launcherFiles := []payloadFile{
		{Source: filepath.Join(appSnapshot, "KFPS.exe"), Path: "KFPS.exe"},
		{Source: updaterOutput, Path: "KFPS-Updater.exe"},
	}

	applicationName := "kfps-" + version + "-application.zip"
	pythonName := "kfps-" + version + "-python-runtime.zip"
	launcherName := "kfps-" + version + "-native-launchers.zip"
	applicationRecords, applicationArtifact, err := writeComponent(filepath.Join(output, applicationName), applicationFiles, baseURL+"/"+applicationName)
	if err != nil {
		return err
	}
	pythonRecords, pythonArtifact, err := writeComponent(filepath.Join(output, pythonName), pythonFiles, baseURL+"/"+pythonName)
	if err != nil {
		return err
	}
	launcherRecords, launcherArtifact, err := writeComponent(filepath.Join(output, launcherName), launcherFiles, baseURL+"/"+launcherName)
	if err != nil {
		return err
	}
	manifest := bootstrap.UpdateManifest{
		Schema: bootstrap.ManifestSchema, Channel: "stable", Sequence: *sequence, Version: version, Commit: strings.ToLower(commit), PublishedUTC: published, Relaunch: "KFPS.exe",
		Components: []bootstrap.Component{
			{Name: "application", Target: "app-root", Archive: applicationArtifact, Files: applicationRecords, RetiredFiles: retired},
			{Name: "python-runtime", Target: "app-root", Archive: pythonArtifact, Files: pythonRecords, ExactRoots: []string{"python"}},
			{Name: "native-launchers", Target: "install-root", Archive: launcherArtifact, Files: launcherRecords},
		},
	}
	for index, component := range manifest.Components {
		componentPath := []string{filepath.Join(output, applicationName), filepath.Join(output, pythonName), filepath.Join(output, launcherName)}[index]
		if err := bootstrap.ValidateComponentArchiveFile(componentPath, component); err != nil {
			return fmt.Errorf("validate published component %s: %w", component.Name, err)
		}
	}
	manifestName := "kfps-update-" + version + ".json"
	if err := verifyGitSourceIdentity(appRoot, commit); err != nil {
		return fmt.Errorf("source changed before signing: %w", err)
	}
	manifestPayload, err := marshalContract(manifest)
	if err != nil {
		return err
	}
	if err := writeExclusive(filepath.Join(output, manifestName), manifestPayload, 0o644); err != nil {
		return err
	}
	manifestSignature, err := bootstrap.SignBytes(manifestPayload, privateKey)
	if err != nil {
		return err
	}
	manifestSignature = append(manifestSignature, '\n')
	if err := writeExclusive(filepath.Join(output, manifestName+".sig"), manifestSignature, 0o644); err != nil {
		return err
	}

	updaterArtifact, err := artifactFor(updaterOutput, baseURL+"/"+updaterName)
	if err != nil {
		return err
	}
	manifestArtifact, err := artifactFor(filepath.Join(output, manifestName), baseURL+"/"+manifestName)
	if err != nil {
		return err
	}
	channel := bootstrap.Channel{
		Schema: bootstrap.ChannelSchema, Channel: "stable", Sequence: *sequence, PublishedUTC: published, MinimumBootstrap: *bootstrapVersion,
		Updater:  bootstrap.UpdaterArtifact{Version: *bootstrapVersion, Artifact: updaterArtifact},
		Manifest: bootstrap.ManifestReference{Artifact: manifestArtifact, SignatureURL: baseURL + "/" + manifestName + ".sig"},
	}
	if err := bootstrap.ValidatePublishedContract(channel, manifest); err != nil {
		return fmt.Errorf("generated update contract is invalid: %w", err)
	}
	channelPayload, err := marshalContract(channel)
	if err != nil {
		return err
	}
	if err := writeExclusive(filepath.Join(output, "channel.json"), channelPayload, 0o644); err != nil {
		return err
	}
	channelSignature, err := bootstrap.SignBytes(channelPayload, privateKey)
	if err != nil {
		return err
	}
	if err := writeExclusive(filepath.Join(output, "channel.json.sig"), append(channelSignature, '\n'), 0o644); err != nil {
		return err
	}
	if err := writeChecksums(output); err != nil {
		return err
	}
	if err := promotePayload(output, requestedOutput); err != nil {
		return fmt.Errorf("publish completed payload: %w", err)
	}
	fmt.Printf("Built signed KFPS %s update sequence %d with key %s\n", version, *sequence, bootstrap.KeyID(publicKey))
	fmt.Printf("Application files: %d\nPython runtime files: %d\nLauncher files: %d\n", len(applicationRecords), len(pythonRecords), len(launcherRecords))
	return nil
}

func excludeRetiredApplicationFiles(files []payloadFile, retired []string) []payloadFile {
	retiredPaths := map[string]bool{}
	for _, relative := range retired {
		retiredPaths[strings.ToLower(filepath.ToSlash(filepath.Clean(relative)))] = true
	}
	filtered := make([]payloadFile, 0, len(files))
	for _, file := range files {
		if retiredPaths[strings.ToLower(filepath.ToSlash(filepath.Clean(file.Path)))] {
			continue
		}
		filtered = append(filtered, file)
	}
	return filtered
}

func inspectUpdaterBuild(path string) (updaterBuildInfo, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, path, "--build-info")
	payload, err := command.Output()
	if err != nil {
		if ctx.Err() != nil {
			return updaterBuildInfo{}, fmt.Errorf("bootstrap updater build-info timed out")
		}
		return updaterBuildInfo{}, fmt.Errorf("execute bootstrap updater build-info: %w", err)
	}
	var info updaterBuildInfo
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&info); err != nil {
		return updaterBuildInfo{}, fmt.Errorf("decode bootstrap updater build-info: %w", err)
	}
	if decoder.Decode(&struct{}{}) != io.EOF {
		return updaterBuildInfo{}, fmt.Errorf("bootstrap updater build-info contains trailing data")
	}
	if info.Schema != "kfps.bootstrap-build.v1" || info.Version == "" || info.KeyID == "" || info.Platform == "" {
		return updaterBuildInfo{}, fmt.Errorf("bootstrap updater returned incomplete build identity")
	}
	if info.Platform != "windows/amd64" {
		return updaterBuildInfo{}, fmt.Errorf("bootstrap updater targets %s; expected windows/amd64", info.Platform)
	}
	return info, nil
}

func includeInnerUpdater(files []payloadFile, updaterPath string) ([]payloadFile, error) {
	found := false
	updaterHash, err := fileSHA256(updaterPath)
	if err != nil {
		return nil, err
	}
	for index := range files {
		if !strings.EqualFold(filepath.ToSlash(files[index].Path), "KFPS-Updater.exe") {
			continue
		}
		trackedHash, err := fileSHA256(files[index].Source)
		if err != nil {
			return nil, err
		}
		if trackedHash != updaterHash {
			return nil, fmt.Errorf("tracked KFPS-Updater.exe differs from the supplied bootstrap updater")
		}
		files[index].Source = updaterPath
		found = true
	}
	if !found {
		files = append(files, payloadFile{Source: updaterPath, Path: "KFPS-Updater.exe"})
	}
	sort.Slice(files, func(left, right int) bool { return files[left].Path < files[right].Path })
	return files, nil
}

func requireCleanTrackedFiles(root string) error {
	for _, arguments := range [][]string{{"diff", "--quiet"}, {"diff", "--cached", "--quiet"}} {
		command := exec.Command("git", append([]string{"-C", root}, arguments...)...)
		if err := command.Run(); err != nil {
			return fmt.Errorf("refusing to publish from modified tracked files; commit and verify the release source first")
		}
	}
	return nil
}

func excludedApplicationPath(relative string) bool {
	key := strings.ToLower(filepath.ToSlash(relative))
	if strings.HasSuffix(key, ".kfpskey") {
		return true
	}
	for _, prefix := range []string{"runtime/", "imgs/", "webui-data/", "python/", "node_modules/", ".wrangler/", ".venv/", "dist/", "build/"} {
		if strings.HasPrefix(key, prefix) {
			return true
		}
	}
	return key == ".dev.vars" || strings.HasPrefix(key, ".dev.vars.")
}

func walkedFiles(root, archivePrefix string, excludeCaches bool) ([]payloadFile, error) {
	files := []payloadFile{}
	err := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			if excludeCaches && strings.EqualFold(entry.Name(), "__pycache__") {
				return filepath.SkipDir
			}
			return nil
		}
		if !entry.Type().IsRegular() {
			return fmt.Errorf("component source contains a non-regular file: %s", path)
		}
		if excludeCaches && strings.HasSuffix(strings.ToLower(entry.Name()), ".pyc") {
			return nil
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		files = append(files, payloadFile{Source: path, Path: filepath.ToSlash(filepath.Join(archivePrefix, relative))})
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Slice(files, func(left, right int) bool { return files[left].Path < files[right].Path })
	return files, nil
}

func writeComponent(path string, files []payloadFile, remoteURL string) ([]bootstrap.FileRecord, bootstrap.Artifact, error) {
	if len(files) == 0 {
		return nil, bootstrap.Artifact{}, fmt.Errorf("component %s has no files", filepath.Base(path))
	}
	output, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
	if err != nil {
		return nil, bootstrap.Artifact{}, err
	}
	archive := zip.NewWriter(output)
	records := make([]bootstrap.FileRecord, 0, len(files))
	for _, file := range files {
		input, err := os.Open(file.Source)
		if err != nil {
			archive.Close()
			output.Close()
			return nil, bootstrap.Artifact{}, err
		}
		info, err := input.Stat()
		if err != nil || !info.Mode().IsRegular() {
			input.Close()
			archive.Close()
			output.Close()
			if err != nil {
				return nil, bootstrap.Artifact{}, err
			}
			return nil, bootstrap.Artifact{}, fmt.Errorf("component source is not a regular file: %s", file.Source)
		}
		header := &zip.FileHeader{Name: filepath.ToSlash(file.Path), Method: zip.Deflate}
		header.SetMode(0o644)
		header.SetModTime(time.Date(1980, 1, 1, 0, 0, 0, 0, time.UTC))
		writer, err := archive.CreateHeader(header)
		if err != nil {
			input.Close()
			archive.Close()
			output.Close()
			return nil, bootstrap.Artifact{}, err
		}
		hash := sha256.New()
		written, copyErr := io.Copy(io.MultiWriter(writer, hash), input)
		closeErr := input.Close()
		if copyErr != nil || closeErr != nil || written != info.Size() {
			archive.Close()
			output.Close()
			if copyErr != nil {
				return nil, bootstrap.Artifact{}, copyErr
			}
			if closeErr != nil {
				return nil, bootstrap.Artifact{}, closeErr
			}
			return nil, bootstrap.Artifact{}, fmt.Errorf("component source size changed while packaging: %s", file.Source)
		}
		records = append(records, bootstrap.FileRecord{
			Path: filepath.ToSlash(file.Path), Size: written, SHA256: hex.EncodeToString(hash.Sum(nil)),
		})
	}
	if err := archive.Close(); err != nil {
		output.Close()
		return nil, bootstrap.Artifact{}, err
	}
	if err := output.Sync(); err != nil {
		output.Close()
		return nil, bootstrap.Artifact{}, err
	}
	if err := output.Close(); err != nil {
		return nil, bootstrap.Artifact{}, err
	}
	artifact, err := artifactFor(path, remoteURL)
	return records, artifact, err
}

func artifactFor(path, remoteURL string) (bootstrap.Artifact, error) {
	info, err := os.Stat(path)
	if err != nil {
		return bootstrap.Artifact{}, err
	}
	hash, err := fileSHA256(path)
	if err != nil {
		return bootstrap.Artifact{}, err
	}
	return bootstrap.Artifact{URL: remoteURL, Size: info.Size(), SHA256: hash}, nil
}

func marshalContract(value any) ([]byte, error) {
	payload, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(payload, '\n'), nil
}

func validateBaseURL(value string) (string, error) {
	value = strings.TrimRight(strings.TrimSpace(value), "/")
	parsed, err := url.Parse(value)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", fmt.Errorf("base URL must be an HTTPS directory URL")
	}
	return value, nil
}

func copyFileExclusive(source, destination string) error {
	input, err := os.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()
	mode := os.FileMode(0o644)
	if info, statErr := input.Stat(); statErr != nil {
		return statErr
	} else if info.Mode()&0o111 != 0 {
		mode = 0o755
	}
	output, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, mode)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(output, input)
	syncErr := output.Sync()
	closeErr := output.Close()
	if copyErr != nil {
		return copyErr
	}
	if syncErr != nil {
		return syncErr
	}
	return closeErr
}

func writeChecksums(directory string) error {
	entries, err := os.ReadDir(directory)
	if err != nil {
		return err
	}
	lines := []string{}
	for _, entry := range entries {
		if entry.IsDir() || entry.Name() == "SHA256SUMS.txt" {
			continue
		}
		hash, err := fileSHA256(filepath.Join(directory, entry.Name()))
		if err != nil {
			return err
		}
		lines = append(lines, hash+"  "+entry.Name())
	}
	sort.Strings(lines)
	return writeExclusive(filepath.Join(directory, "SHA256SUMS.txt"), []byte(strings.Join(lines, "\n")+"\n"), 0o644)
}

func fileSHA256(path string) (string, error) {
	input, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer input.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, input); err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func writeExclusive(path string, payload []byte, mode os.FileMode) error {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, mode)
	if err != nil {
		return err
	}
	if _, err := file.Write(payload); err != nil {
		file.Close()
		return err
	}
	if err := file.Sync(); err != nil {
		file.Close()
		return err
	}
	return file.Close()
}

func fileIsRegular(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}
