package bootstrap

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

type EngineConfig struct {
	BootstrapVersion        string
	ChannelURL              string
	ChannelSignature        string
	TrustedKey              ed25519.PublicKey
	Recovery                RecoveryConfig
	RecoveryArchive         string
	Layout                  Layout
	StateDir                string
	CurrentExecutable       string
	Logger                  *Logger
	AllowLocalSources       bool
	ForceRecovery           bool
	DisableFallback         bool
	AllowSequenceReset      bool
	DryRun                  bool
	FinalizeLegacyMigration bool
}

type EngineResult struct {
	Summary RunSummary
	Handoff HandoffArtifact
}

type Engine struct {
	config            EngineConfig
	downloader        *Downloader
	installationID    string
	runID             string
	stageDir          string
	saveStateOverride func(PreparedUpdate) error
}

func NewEngine(config EngineConfig) (*Engine, error) {
	if err := config.Layout.Validate(); err != nil {
		return nil, err
	}
	if config.Logger == nil {
		return nil, fmt.Errorf("updater logger is required")
	}
	stateDir, err := ValidateUpdaterStateDir(config.StateDir, config.Layout)
	if err != nil {
		return nil, err
	}
	config.StateDir = stateDir
	installationID, err := InstallationIdentity(config.Layout)
	if err != nil {
		return nil, err
	}
	runID, err := newRunID()
	if err != nil {
		return nil, err
	}
	return &Engine{
		config:         config,
		downloader:     NewDownloader(config.Logger, config.AllowLocalSources),
		installationID: installationID,
		runID:          runID,
		stageDir:       filepath.Join(config.StateDir, "runs", runID),
	}, nil
}

func (engine *Engine) Run(ctx context.Context) (result EngineResult, runErr error) {
	summary := RunSummary{
		Schema:         "kfps.update-run.v1",
		RunID:          engine.runID,
		UpdaterVersion: engine.config.BootstrapVersion,
		Platform:       runtime.GOOS + "/" + runtime.GOARCH,
		StartedUTC:     utcNow(),
		Status:         "running",
		Phase:          "initialization",
		InstallRoot:    engine.config.Layout.InstallRoot,
		AppRoot:        engine.config.Layout.AppRoot,
		InstallationID: engine.installationID,
		LogPath:        engine.config.Logger.Path,
		FromVersion:    "unknown",
	}
	result.Summary = summary
	defer func() {
		result.Summary.FinishedUTC = utcNow()
		result.Summary.BytesDownloaded = engine.downloader.Bytes
		result.Summary.Success = runErr == nil && result.Handoff.Path == ""
		if runErr != nil {
			result.Summary.Status = "failed"
			result.Summary.Error = runErr.Error()
		} else if result.Handoff.Path != "" {
			result.Summary.Status = "handoff-pending"
			result.Summary.Phase = "self-update-handoff"
			result.Summary.HandoffPath = result.Handoff.Path
			result.Summary.HandoffSHA256 = strings.ToLower(result.Handoff.SHA256)
			result.Summary.HandoffSize = result.Handoff.Size
		} else if engine.config.DryRun {
			result.Summary.Status = "checked"
			result.Summary.Phase = "complete"
		} else {
			result.Summary.Status = "completed"
			result.Summary.Phase = "complete"
		}
		if err := engine.writeSummary(result.Summary); err != nil {
			engine.config.Logger.Printf("Could not write updater summary: %v", err)
		}
	}()

	engine.config.Logger.Printf("[STATE] Checking updater lock, saved state, and interrupted work.")
	result.Summary.Phase = "acquire-lock"
	lock, err := AcquireUpdateLock(engine.config.StateDir, 30*time.Second)
	if err != nil {
		return result, err
	}
	defer lock.Close()
	result.Summary.Phase = "recover-interrupted-transaction"
	recovered, err := RecoverInterruptedTransaction(engine.config.StateDir, engine.config.Layout, engine.config.Logger)
	if err != nil {
		return result, fmt.Errorf("interrupted update recovery failed: %w", err)
	}
	result.Summary.RecoveredCrash = recovered
	result.Summary.FromVersion = installedVersion(engine.config.Layout.AppRoot)
	PruneUpdaterState(engine.config.StateDir, engine.config.Logger)
	result.Summary.Phase = "prepare-staging"
	if err := ensureSafeContainedPath(engine.config.StateDir, engine.stageDir); err != nil {
		return result, err
	}
	if err := makeSafeDirectory(engine.stageDir, 0o700); err != nil {
		return result, err
	}
	defer removeSafeTree(engine.config.StateDir, engine.stageDir)

	var prepared PreparedUpdate
	if engine.config.ForceRecovery {
		result.Summary.Mode = "recovery"
		result.Summary.Phase = "prepare-recovery"
		engine.config.Logger.Printf("[RECOVERY] Checking the pinned recovery package.")
		if err = engine.ensureRecoveryEligible(); err == nil {
			prepared, err = engine.prepareRecovery(ctx)
		}
	} else {
		result.Summary.Mode = "signed-channel"
		result.Summary.Phase = "load-signed-channel"
		engine.config.Logger.Printf("[CHANNEL] Contacting and verifying the signed stable channel.")
		prepared, result.Handoff, err = engine.prepareChannel(ctx, &result.Summary)
		if result.Handoff.Path != "" {
			engine.config.Logger.Printf("A verified bootstrap updater handoff is ready: %s", result.Handoff.Path)
			return result, nil
		}
		if err != nil && !engine.config.DisableFallback && isAvailabilityError(err) {
			if eligibilityErr := engine.ensureRecoveryEligible(); eligibilityErr == nil {
				warning := fmt.Sprintf("Signed channel was unavailable (%v); using the hash-pinned %s recovery baseline.", err, engine.config.Recovery.Version)
				engine.config.Logger.Printf("%s", warning)
				result.Summary.Warnings = append(result.Summary.Warnings, warning)
				result.Summary.Mode = "recovery-fallback"
				result.Summary.Phase = "prepare-recovery-fallback"
				prepared, err = engine.prepareRecovery(ctx)
			} else {
				err = fmt.Errorf("signed channel unavailable and recovery is unsafe: %w", eligibilityErr)
			}
		}
	}
	if err != nil {
		return result, err
	}
	prepared, err = engine.prepareLegacyMigration(prepared)
	if err != nil {
		return result, err
	}
	result.Summary.ToVersion = prepared.Version
	result.Summary.Sequence = prepared.Sequence
	result.Summary.FilesChecked = prepared.FilesChecked
	for _, change := range prepared.Changes {
		relative, relativeErr := filepath.Rel(engine.config.Layout.InstallRoot, change.Destination)
		if relativeErr != nil {
			relative = change.Relative
		}
		record := RunChange{Action: string(change.Kind), Path: filepath.ToSlash(relative)}
		if change.Kind == ReplaceFile {
			result.Summary.FilesPlannedReplaced++
			record.Size = change.Expected.Size
			record.SHA256 = change.Expected.SHA256
		} else if change.Kind == RemoveFile {
			result.Summary.FilesPlannedRemoved++
		}
		result.Summary.Changes = append(result.Summary.Changes, record)
	}
	if engine.config.DryRun {
		engine.config.Logger.Printf("[CHECK] Dry run complete; no installation files were changed.")
		return result, nil
	}
	var transaction *Transaction
	if len(prepared.Changes) > 0 {
		engine.config.Logger.Printf("[APPLY] Installing %d verified file operation(s).", len(prepared.Changes))
		result.Summary.Phase = "back-up-current-files"
		transaction, err = NewTransaction(engine.config.StateDir, engine.runID, engine.config.Layout, prepared.Changes, engine.config.Logger)
		if err != nil {
			return result, err
		}
		if err := transaction.Prepare(); err != nil {
			transaction.AbandonPreparation()
			return result, err
		}
		result.Summary.Phase = "apply-files"
		if err := transaction.Apply(); err != nil {
			result.Summary.Rollback = true
			rollbackErr := transaction.Rollback()
			if rollbackErr != nil {
				return result, fmt.Errorf("update failed: %v; rollback also failed: %w", err, rollbackErr)
			}
			result.Summary.RollbackSuccess = true
			return result, err
		}
		result.Summary.Phase = "verify-installed-files"
		if err := VerifyPreparedUpdateWithLogger(prepared, engine.config.Logger); err != nil {
			result.Summary.Rollback = true
			rollbackErr := transaction.Rollback()
			if rollbackErr != nil {
				return result, fmt.Errorf("verification failed: %v; rollback also failed: %w", err, rollbackErr)
			}
			result.Summary.RollbackSuccess = true
			return result, err
		}
	} else {
		engine.config.Logger.Printf("[OK] This installation already matches the signed release.")
	}
	var previousState stateSnapshot
	if prepared.Sequence > 0 {
		engine.config.Logger.Printf("[STATE] Recording signed release sequence %d.", prepared.Sequence)
		previousState, err = engine.snapshotState()
		if err != nil {
			if transaction != nil {
				return result, engine.rollbackAfterFailure(&result.Summary, transaction, fmt.Errorf("snapshot updater state: %w", err))
			}
			return result, err
		}
		if transaction != nil {
			if err := transaction.PrepareStateTransition(filepath.Join(engine.config.StateDir, "state.json"), previousState.payload, previousState.exists); err != nil {
				return result, engine.rollbackAfterFailure(&result.Summary, transaction, fmt.Errorf("journal updater state: %w", err))
			}
		}
		if err := engine.saveState(prepared); err != nil {
			if transaction != nil {
				return result, engine.rollbackAfterFailure(&result.Summary, transaction, fmt.Errorf("save updater state: %w", err))
			}
			return result, err
		}
		if transaction != nil {
			if err := transaction.MarkStateUpdated(); err != nil {
				return result, engine.rollbackAfterFailure(&result.Summary, transaction, fmt.Errorf("journal saved updater state: %w", err))
			}
		}
	}
	if transaction != nil {
		if err := transaction.Commit(); err != nil {
			failure := engine.rollbackAfterFailure(&result.Summary, transaction, fmt.Errorf("commit update: %w", err))
			return result, failure
		}
		result.Summary.FilesReplaced = result.Summary.FilesPlannedReplaced
		result.Summary.FilesRemoved = result.Summary.FilesPlannedRemoved
	}
	engine.config.Logger.Printf("[OK] KFPS update verified: %s -> %s; %d replaced, %d removed.", result.Summary.FromVersion, prepared.Version, result.Summary.FilesReplaced, result.Summary.FilesRemoved)
	return result, nil
}

type stateSnapshot struct {
	payload []byte
	exists  bool
}

func (engine *Engine) snapshotState() (stateSnapshot, error) {
	path := filepath.Join(engine.config.StateDir, "state.json")
	payload, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return stateSnapshot{}, nil
	}
	if err != nil {
		return stateSnapshot{}, err
	}
	return stateSnapshot{payload: payload, exists: true}, nil
}

func (engine *Engine) rollbackAfterFailure(summary *RunSummary, transaction *Transaction, cause error) error {
	summary.Rollback = true
	rollbackErr := transaction.Rollback()
	if rollbackErr != nil {
		return fmt.Errorf("%v; rollback also failed: %w", cause, rollbackErr)
	}
	summary.RollbackSuccess = true
	return cause
}

func (engine *Engine) prepareRecovery(ctx context.Context) (PreparedUpdate, error) {
	if strings.EqualFold(engine.config.Layout.InstallRoot, engine.config.Layout.AppRoot) {
		return PreparedUpdate{}, fmt.Errorf("the embedded release recovery is only valid for packaged KFPS layouts")
	}
	if healthy, ok, err := engine.recoveryHealth(); err != nil {
		return PreparedUpdate{}, err
	} else if ok {
		engine.config.Logger.Printf("The hash-pinned %s recovery baseline is already complete.", engine.config.Recovery.Version)
		return healthy, nil
	}
	archivePath := engine.config.RecoveryArchive
	if archivePath == "" {
		archivePath = filepath.Join(engine.stageDir, "downloads", "recovery.zip")
		engine.config.Logger.Printf("Downloading the hash-pinned %s recovery baseline.", engine.config.Recovery.Version)
		if err := engine.downloader.DownloadArtifact(ctx, engine.config.Recovery.Artifact, archivePath); err != nil {
			return PreparedUpdate{}, err
		}
	} else {
		hash, err := sha256File(archivePath)
		if err != nil {
			return PreparedUpdate{}, err
		}
		info, err := os.Stat(archivePath)
		if err != nil || info.Size() != engine.config.Recovery.Artifact.Size || !strings.EqualFold(hash, engine.config.Recovery.Artifact.SHA256) {
			return PreparedUpdate{}, fmt.Errorf("local recovery archive does not match the pinned size and SHA-256")
		}
	}
	return PrepareRecoveryBundle(archivePath, filepath.Join(engine.stageDir, "recovery"), engine.config.Layout, engine.config.Recovery, engine.config.Logger)
}

func (engine *Engine) recoveryHealth() (PreparedUpdate, bool, error) {
	return RecoveryAlreadyHealthy(engine.config.Layout, engine.config.Recovery, engine.config.Logger)
}

func (engine *Engine) prepareChannel(ctx context.Context, summary *RunSummary) (PreparedUpdate, HandoffArtifact, error) {
	if len(engine.config.TrustedKey) != ed25519.PublicKeySize {
		return PreparedUpdate{}, HandoffArtifact{}, fmt.Errorf("the updater was not built with a valid production trust key")
	}
	summary.Phase = "verify-signed-channel"
	channel, err := LoadChannel(ctx, engine.downloader, engine.config.ChannelURL, engine.config.ChannelSignature, engine.config.TrustedKey)
	if err != nil {
		return PreparedUpdate{}, HandoffArtifact{}, err
	}
	engine.config.Logger.Printf("[OK] Signed stable channel verified (sequence %d).", channel.Sequence)
	engine.config.Logger.Printf("[TRUST] Checking accepted state and the bootstrap updater binary.")
	summary.Phase = "validate-accepted-state"
	state, err := engine.loadState()
	if err != nil {
		return PreparedUpdate{}, HandoffArtifact{}, err
	}
	if state.HighestSequence > channel.Sequence && !engine.config.AllowSequenceReset {
		return PreparedUpdate{}, HandoffArtifact{}, fmt.Errorf("refusing signed-channel rollback from sequence %d to %d", state.HighestSequence, channel.Sequence)
	}
	var manifest UpdateManifest
	manifestLoaded := false
	if state.HighestSequence == channel.Sequence && state.HighestSequence > 0 && !engine.config.AllowSequenceReset {
		if state.ChannelSHA256 != "" && !strings.EqualFold(state.ChannelSHA256, channel.Identity) {
			return PreparedUpdate{}, HandoffArtifact{}, fmt.Errorf("signed sequence %d was republished with different content (channel identity)", channel.Sequence)
		}
		if state.ManifestSHA256 != "" && !strings.EqualFold(state.ManifestSHA256, channel.Manifest.SHA256) {
			return PreparedUpdate{}, HandoffArtifact{}, fmt.Errorf("signed sequence %d was republished with different content (manifest identity)", channel.Sequence)
		}
		if state.ChannelSHA256 == "" || state.ManifestSHA256 == "" {
			engine.config.Logger.Printf("[MANIFEST] Downloading and verifying the signed release manifest.")
			summary.Phase = "verify-update-manifest"
			manifest, err = LoadUpdateManifest(ctx, engine.downloader, channel.Manifest, engine.config.TrustedKey, channel)
			if err != nil {
				return PreparedUpdate{}, HandoffArtifact{}, err
			}
			manifestLoaded = true
			if state.Version != manifest.Version || state.Commit == "" || !strings.EqualFold(state.Commit, manifest.Commit) {
				return PreparedUpdate{}, HandoffArtifact{}, fmt.Errorf("signed sequence %d lacks a matching persistent release identity", channel.Sequence)
			}
		}
	}
	summary.Phase = "verify-bootstrap-updater"
	handoff, err := engine.prepareSelfUpdate(ctx, channel)
	if err != nil || handoff.Path != "" {
		return PreparedUpdate{}, handoff, err
	}
	engine.config.Logger.Printf("[OK] Bootstrap updater %s passed its signed identity check.", engine.config.BootstrapVersion)
	minimumComparison, err := compareVersions(engine.config.BootstrapVersion, channel.MinimumBootstrap)
	if err != nil || minimumComparison < 0 {
		return PreparedUpdate{}, HandoffArtifact{}, fmt.Errorf("running bootstrap %s does not satisfy signed minimum %s", engine.config.BootstrapVersion, channel.MinimumBootstrap)
	}
	if !manifestLoaded {
		engine.config.Logger.Printf("[MANIFEST] Downloading and verifying the signed release manifest.")
		summary.Phase = "verify-update-manifest"
		manifest, err = LoadUpdateManifest(ctx, engine.downloader, channel.Manifest, engine.config.TrustedKey, channel)
		if err != nil {
			return PreparedUpdate{}, HandoffArtifact{}, err
		}
	}
	engine.config.Logger.Printf("[OK] Signed KFPS %s manifest verified (%d components).", manifest.Version, len(manifest.Components))
	if state.HighestSequence == channel.Sequence && state.HighestSequence > 0 && !engine.config.AllowSequenceReset {
		if state.ChannelSHA256 != "" || state.ManifestSHA256 != "" {
			if !strings.EqualFold(state.ChannelSHA256, channel.Identity) || !strings.EqualFold(state.ManifestSHA256, manifest.Identity) {
				return PreparedUpdate{}, HandoffArtifact{}, fmt.Errorf("signed sequence %d was republished with different content", channel.Sequence)
			}
		} else if state.Version != manifest.Version || state.Commit == "" || !strings.EqualFold(state.Commit, manifest.Commit) {
			return PreparedUpdate{}, HandoffArtifact{}, fmt.Errorf("signed sequence %d lacks a matching persistent release identity", channel.Sequence)
		}
	}
	summary.Phase = "inspect-installation"
	prepared, err := PrepareComponentUpdate(ctx, engine.downloader, manifest, filepath.Join(engine.stageDir, "signed"), engine.config.Layout, engine.config.Logger)
	prepared.ChannelSHA256 = channel.Identity
	return prepared, HandoffArtifact{}, err
}

func (engine *Engine) prepareSelfUpdate(ctx context.Context, channel Channel) (HandoffArtifact, error) {
	minimumComparison, err := compareVersions(engine.config.BootstrapVersion, channel.MinimumBootstrap)
	if err != nil {
		return HandoffArtifact{}, err
	}
	versionComparison, err := compareVersions(engine.config.BootstrapVersion, channel.Updater.Version)
	if err != nil {
		return HandoffArtifact{}, err
	}
	currentHash := ""
	if engine.config.CurrentExecutable != "" {
		currentHash, _ = sha256File(engine.config.CurrentExecutable)
	}
	expectedHash := strings.ToLower(channel.Updater.SHA256)
	if minimumComparison >= 0 && versionComparison > 0 {
		return HandoffArtifact{}, nil
	}
	if minimumComparison >= 0 && versionComparison == 0 && currentHash == expectedHash {
		return HandoffArtifact{}, nil
	}
	handoffDir := filepath.Join(engine.config.StateDir, "handoff", engine.runID)
	if err := makeSafeDirectory(handoffDir, 0o700); err != nil {
		return HandoffArtifact{}, err
	}
	path := filepath.Join(handoffDir, "KFPS-Updater-"+safeName(channel.Updater.Version)+".exe")
	if err := engine.downloader.DownloadArtifact(ctx, channel.Updater.Artifact, path); err != nil {
		return HandoffArtifact{}, err
	}
	return HandoffArtifact{Path: path, Artifact: channel.Updater.Artifact}, nil
}

func (engine *Engine) ensureRecoveryEligible() error {
	type evidenceRecord struct {
		version string
		commit  string
	}
	evidence := map[string]evidenceRecord{}
	if installed := installedVersion(engine.config.Layout.AppRoot); installed != "unknown" && installed != "" {
		evidence["installed VERSION"] = evidenceRecord{version: installed}
	}
	state, err := engine.loadState()
	if err != nil {
		return fmt.Errorf("cannot validate persistent updater state before recovery: %w", err)
	}
	if state.HighestSequence > 0 {
		if state.Version == "" {
			return fmt.Errorf("persistent updater state has no accepted version")
		}
		evidence["persistent updater state"] = evidenceRecord{version: state.Version, commit: state.Commit}
	}
	if release, err := installedReleaseIdentity(engine.config.Layout.InstallRoot); err != nil {
		return err
	} else if release.version != "" {
		evidence["installed release manifest"] = evidenceRecord{version: release.version, commit: release.commit}
	}
	for source, value := range evidence {
		comparison, err := compareVersions(value.version, engine.config.Recovery.Version)
		if err != nil {
			return fmt.Errorf("%s has invalid version %q", source, value.version)
		}
		if comparison > 0 {
			return fmt.Errorf("%s identifies newer KFPS %s; refusing recovery downgrade to %s", source, value.version, engine.config.Recovery.Version)
		}
		if comparison == 0 && value.commit != "" && engine.config.Recovery.Commit != "" && !strings.EqualFold(value.commit, engine.config.Recovery.Commit) {
			return fmt.Errorf("%s identifies KFPS %s commit %s; refusing same-version recovery to different commit %s", source, value.version, value.commit, engine.config.Recovery.Commit)
		}
	}
	return nil
}

func (engine *Engine) loadState() (PersistentState, error) {
	path := filepath.Join(engine.config.StateDir, "state.json")
	payload, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return PersistentState{Schema: "kfps.update-state.v1"}, nil
	}
	if err != nil {
		return PersistentState{}, err
	}
	var state PersistentState
	if err := decodeStrictJSON(payload, &state); err != nil {
		return PersistentState{}, err
	}
	if state.Schema != "kfps.update-state.v1" {
		return PersistentState{}, fmt.Errorf("unsupported updater state schema")
	}
	if state.InstallationID != "" && !strings.EqualFold(state.InstallationID, engine.installationID) {
		return PersistentState{}, fmt.Errorf("updater state belongs to a different KFPS installation")
	}
	if state.HighestSequence > 0 {
		if err := ValidateVersion(state.Version); err != nil {
			return PersistentState{}, fmt.Errorf("updater state version is invalid: %w", err)
		}
	}
	for name, value := range map[string]string{"channel": state.ChannelSHA256, "manifest": state.ManifestSHA256} {
		if value == "" {
			continue
		}
		normalized, err := normalizeSHA256(value)
		if err != nil {
			return PersistentState{}, fmt.Errorf("updater state %s identity is invalid: %w", name, err)
		}
		if name == "channel" {
			state.ChannelSHA256 = normalized
		} else {
			state.ManifestSHA256 = normalized
		}
	}
	return state, nil
}

func (engine *Engine) saveState(prepared PreparedUpdate) error {
	if engine.saveStateOverride != nil {
		return engine.saveStateOverride(prepared)
	}
	state := PersistentState{
		Schema:          "kfps.update-state.v1",
		InstallationID:  engine.installationID,
		HighestSequence: prepared.Sequence,
		Version:         prepared.Version,
		Commit:          prepared.Commit,
		ChannelSHA256:   prepared.ChannelSHA256,
		ManifestSHA256:  prepared.ManifestSHA256,
		UpdatedUTC:      utcNow(),
	}
	payload, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return err
	}
	return writeAtomic(filepath.Join(engine.config.StateDir, "state.json"), append(payload, '\n'), 0o600)
}

func (engine *Engine) writeSummary(summary RunSummary) error {
	payload, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	payload = append(payload, '\n')
	stateReport := filepath.Join(engine.config.StateDir, "reports", "update-"+engine.runID+".json")
	if err := ensureSafeContainedPath(engine.config.StateDir, stateReport); err != nil {
		return err
	}
	if err := writeAtomic(stateReport, payload, 0o600); err != nil {
		return err
	}
	pruneFiles(filepath.Dir(stateReport), 40, 90*24*time.Hour, engine.config.Logger)
	if isDirectory(engine.config.Layout.AppRoot) {
		appReport := filepath.Join(engine.config.Layout.AppRoot, "runtime", "update-reports", "update-"+engine.runID+".json")
		if err := ensureSafeContainedPath(engine.config.Layout.AppRoot, appReport); err != nil {
			engine.config.Logger.Printf("Skipped application report copy because its path is unsafe: %v", err)
			return nil
		}
		if err := writeAtomic(appReport, payload, 0o600); err != nil {
			return err
		}
		pruneFiles(filepath.Dir(appReport), 40, 90*24*time.Hour, engine.config.Logger)
	}
	return nil
}

func (engine *Engine) RecordHandoffFailure(summary RunSummary, cause error) error {
	summary.FinishedUTC = utcNow()
	summary.Status = "failed"
	summary.Phase = "self-update-handoff"
	summary.Success = false
	summary.Error = cause.Error()
	return engine.writeSummary(summary)
}

func (engine *Engine) RecordHandoffExit(summary RunSummary, exitCode int) error {
	summary.FinishedUTC = utcNow()
	summary.HandoffExitCode = &exitCode
	summary.Phase = "complete"
	summary.Success = exitCode == 0 || exitCode == 3
	if summary.Success {
		summary.Status = "handoff-complete"
		summary.Error = ""
	} else {
		summary.Status = "failed"
		summary.Error = fmt.Sprintf("verified updater child exited with code %d", exitCode)
	}
	return engine.writeSummary(summary)
}

func DefaultStateDir(layout Layout) (string, error) {
	local := strings.TrimSpace(os.Getenv("LOCALAPPDATA"))
	if local == "" {
		var err error
		local, err = os.UserCacheDir()
		if err != nil {
			return "", err
		}
	}
	identity, err := InstallationIdentity(layout)
	if err != nil {
		return "", err
	}
	return filepath.Join(local, "KloudysFH6Painter", "updater", "installations", identity), nil
}

type installedIdentity struct {
	version string
	commit  string
}

func installedReleaseIdentity(installRoot string) (installedIdentity, error) {
	payload, err := os.ReadFile(filepath.Join(installRoot, "RELEASE-MANIFEST.json"))
	if os.IsNotExist(err) {
		return installedIdentity{}, nil
	}
	if err != nil {
		return installedIdentity{}, err
	}
	var manifest ReleaseManifest
	if err := decodeStrictJSON(payload, &manifest); err != nil {
		return installedIdentity{}, nil
	}
	if manifest.Schema != ReleaseSchema || ValidateVersion(manifest.Version) != nil || !gitCommitPattern.MatchString(manifest.Commit) {
		return installedIdentity{}, nil
	}
	return installedIdentity{version: manifest.Version, commit: strings.ToLower(manifest.Commit)}, nil
}

func installedVersion(appRoot string) string {
	payload, err := os.ReadFile(filepath.Join(appRoot, "VERSION"))
	if err != nil {
		return "unknown"
	}
	value := strings.TrimSpace(string(payload))
	if _, err := parseVersion(value); err != nil {
		return "unknown"
	}
	return value
}

func newRunID() (string, error) {
	random := make([]byte, 5)
	if _, err := rand.Read(random); err != nil {
		return "", err
	}
	return time.Now().UTC().Format("20060102-150405") + "-" + hex.EncodeToString(random), nil
}

func IsHandoff(result EngineResult) bool {
	return result.Handoff.Path != ""
}
