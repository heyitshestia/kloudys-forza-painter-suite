package bootstrap

import "time"

const (
	ChannelSchema   = "kfps.update-channel.v1"
	ManifestSchema  = "kfps.update-manifest.v1"
	SignatureSchema = "kfps.detached-signature.v1"
	ReleaseSchema   = "kfps.release-manifest.v1"
)

type Artifact struct {
	URL    string `json:"url"`
	SHA256 string `json:"sha256"`
	Size   int64  `json:"size"`
}

type UpdaterArtifact struct {
	Version string `json:"version"`
	Artifact
}

type ManifestReference struct {
	Artifact
	SignatureURL string `json:"signature_url"`
}

type Channel struct {
	Schema           string            `json:"schema"`
	Channel          string            `json:"channel"`
	Sequence         uint64            `json:"sequence"`
	PublishedUTC     string            `json:"published_utc"`
	MinimumBootstrap string            `json:"minimum_bootstrap"`
	Updater          UpdaterArtifact   `json:"updater"`
	Manifest         ManifestReference `json:"manifest"`
	Identity         string            `json:"-"`
}

type FileRecord struct {
	Path   string `json:"path"`
	Size   int64  `json:"size"`
	SHA256 string `json:"sha256"`
}

type Component struct {
	Name         string       `json:"name"`
	Target       string       `json:"target"`
	Archive      Artifact     `json:"archive"`
	Files        []FileRecord `json:"files"`
	ExactRoots   []string     `json:"exact_roots,omitempty"`
	RetiredFiles []string     `json:"retired_files,omitempty"`
}

type UpdateManifest struct {
	Schema       string      `json:"schema"`
	Channel      string      `json:"channel"`
	Sequence     uint64      `json:"sequence"`
	Version      string      `json:"version"`
	Commit       string      `json:"commit"`
	PublishedUTC string      `json:"published_utc"`
	Components   []Component `json:"components"`
	Relaunch     string      `json:"relaunch,omitempty"`
	Identity     string      `json:"-"`
}

type DetachedSignature struct {
	Schema    string `json:"schema"`
	Algorithm string `json:"algorithm"`
	KeyID     string `json:"key_id"`
	Signature string `json:"signature"`
}

type ReleaseManifest struct {
	Schema             string       `json:"schema"`
	Version            string       `json:"version"`
	Commit             string       `json:"commit"`
	Kind               string       `json:"kind"`
	SourceTimestampUTC string       `json:"source_timestamp_utc"`
	Files              []FileRecord `json:"files"`
}

type PersistentState struct {
	Schema          string `json:"schema"`
	InstallationID  string `json:"installation_id,omitempty"`
	HighestSequence uint64 `json:"highest_sequence"`
	Version         string `json:"version"`
	Commit          string `json:"commit"`
	ChannelSHA256   string `json:"channel_sha256,omitempty"`
	ManifestSHA256  string `json:"manifest_sha256,omitempty"`
	UpdatedUTC      string `json:"updated_utc"`
}

type RunChange struct {
	Action string `json:"action"`
	Path   string `json:"path"`
	Size   int64  `json:"size,omitempty"`
	SHA256 string `json:"sha256,omitempty"`
}

type RunSummary struct {
	Schema               string      `json:"schema"`
	RunID                string      `json:"run_id"`
	UpdaterVersion       string      `json:"updater_version"`
	Platform             string      `json:"platform"`
	StartedUTC           string      `json:"started_utc"`
	FinishedUTC          string      `json:"finished_utc"`
	Status               string      `json:"status"`
	Phase                string      `json:"phase"`
	Mode                 string      `json:"mode"`
	InstallRoot          string      `json:"install_root"`
	AppRoot              string      `json:"app_root"`
	InstallationID       string      `json:"installation_id"`
	LogPath              string      `json:"log_path"`
	HandoffPath          string      `json:"handoff_path,omitempty"`
	HandoffSHA256        string      `json:"handoff_sha256,omitempty"`
	HandoffSize          int64       `json:"handoff_size,omitempty"`
	HandoffExitCode      *int        `json:"handoff_exit_code,omitempty"`
	FromVersion          string      `json:"from_version"`
	ToVersion            string      `json:"to_version"`
	Sequence             uint64      `json:"sequence"`
	FilesChecked         int         `json:"files_checked"`
	FilesPlannedReplaced int         `json:"files_planned_replaced"`
	FilesPlannedRemoved  int         `json:"files_planned_removed"`
	FilesReplaced        int         `json:"files_replaced"`
	FilesRemoved         int         `json:"files_removed"`
	BytesDownloaded      int64       `json:"bytes_downloaded"`
	Rollback             bool        `json:"rollback"`
	RollbackSuccess      bool        `json:"rollback_success,omitempty"`
	RecoveredCrash       bool        `json:"recovered_interrupted_transaction,omitempty"`
	Success              bool        `json:"success"`
	Error                string      `json:"error,omitempty"`
	Warnings             []string    `json:"warnings,omitempty"`
	Changes              []RunChange `json:"changes,omitempty"`
}

func utcNow() string {
	return time.Now().UTC().Format(time.RFC3339)
}
