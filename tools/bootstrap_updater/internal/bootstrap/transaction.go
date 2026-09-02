package bootstrap

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

type journalOperation struct {
	Kind        ChangeKind `json:"kind"`
	Destination string     `json:"destination"`
	Backup      string     `json:"backup"`
	Temporary   string     `json:"temporary,omitempty"`
	Existed     bool       `json:"existed"`
	Started     bool       `json:"started"`
	Applied     bool       `json:"applied"`
}

type journalStateTransition struct {
	Path            string `json:"path"`
	PreviousPayload []byte `json:"previous_payload,omitempty"`
	Existed         bool   `json:"existed"`
	Updated         bool   `json:"updated"`
}

type transactionJournal struct {
	Schema      string                  `json:"schema"`
	RunID       string                  `json:"run_id"`
	Status      string                  `json:"status"`
	InstallRoot string                  `json:"install_root"`
	CreatedUTC  string                  `json:"created_utc"`
	Operations  []journalOperation      `json:"operations"`
	State       *journalStateTransition `json:"state,omitempty"`
}

type Transaction struct {
	stateDir    string
	installRoot string
	backupDir   string
	journalPath string
	journal     transactionJournal
	changes     []Change
	logger      *Logger
}

func NewTransaction(stateDir, runID string, layout Layout, changes []Change, logger *Logger) (*Transaction, error) {
	backupDir := filepath.Join(stateDir, "backups", runID)
	transaction := &Transaction{
		stateDir:    stateDir,
		installRoot: layout.InstallRoot,
		backupDir:   backupDir,
		journalPath: filepath.Join(stateDir, "current-transaction.json"),
		journal: transactionJournal{
			Schema:      "kfps.update-transaction.v1",
			RunID:       runID,
			Status:      "preparing",
			InstallRoot: layout.InstallRoot,
			CreatedUTC:  utcNow(),
		},
		changes: changes,
		logger:  logger,
	}
	seen := map[string]bool{}
	for index, change := range changes {
		relative, err := filepath.Rel(layout.InstallRoot, change.Destination)
		if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
			return nil, fmt.Errorf("transaction destination is outside installation root: %s", change.Destination)
		}
		if err := ensureSafeContainedPath(layout.InstallRoot, change.Destination); err != nil {
			return nil, err
		}
		key := pathKey(change.Destination)
		if seen[key] {
			return nil, fmt.Errorf("transaction contains duplicate destination: %s", change.Destination)
		}
		seen[key] = true
		backup := filepath.Join(backupDir, fmt.Sprintf("%06d", index), filepath.Base(change.Destination))
		temporary := filepath.Join(filepath.Dir(change.Destination), fmt.Sprintf(".%s.kfps-update-%s-%06d.tmp", filepath.Base(change.Destination), runID, index))
		if err := ensureSafeContainedPath(stateDir, backup); err != nil {
			return nil, err
		}
		if err := ensureSafeContainedPath(layout.InstallRoot, temporary); err != nil {
			return nil, err
		}
		transaction.journal.Operations = append(transaction.journal.Operations, journalOperation{
			Kind:        change.Kind,
			Destination: change.Destination,
			Backup:      backup,
			Temporary:   temporary,
		})
	}
	if err := ensureSafeContainedPath(stateDir, backupDir); err != nil {
		return nil, err
	}
	if err := makeSafeDirectory(backupDir, 0o700); err != nil {
		return nil, err
	}
	return transaction, nil
}

func (transaction *Transaction) Prepare() error {
	var backupBytes int64
	var backupFiles int
	for index := range transaction.journal.Operations {
		operation := &transaction.journal.Operations[index]
		if err := ensureSafeContainedPath(transaction.installRoot, operation.Destination); err != nil {
			return err
		}
		info, err := os.Stat(operation.Destination)
		if err == nil && info.Mode().IsRegular() {
			operation.Existed = true
			backupBytes += info.Size()
			backupFiles++
		} else if err != nil && !os.IsNotExist(err) {
			return err
		}
	}
	if err := ensureTransactionSpace(transaction.stateDir, backupBytes, transaction.changes, transaction.journal.Operations); err != nil {
		return err
	}
	if backupBytes > 0 {
		transaction.logger.Printf("[BACKUP] Preserving %d existing file(s), %d bytes, for rollback.", backupFiles, backupBytes)
	}
	for index := range transaction.changes {
		operation := &transaction.journal.Operations[index]
		if err := ensureSafeContainedPath(transaction.installRoot, operation.Destination); err != nil {
			return err
		}
		if err := ensureSafeContainedPath(transaction.stateDir, operation.Backup); err != nil {
			return err
		}
		info, err := os.Stat(operation.Destination)
		if err == nil {
			if !info.Mode().IsRegular() {
				return fmt.Errorf("destination is not a regular file: %s", operation.Destination)
			}
			operation.Existed = true
			if err := copyFile(operation.Destination, operation.Backup); err != nil {
				return fmt.Errorf("back up %s: %w", operation.Destination, err)
			}
		} else if !os.IsNotExist(err) {
			return err
		}
	}
	if err := transaction.writeJournal(); err != nil {
		return err
	}
	transaction.logger.Printf("[OK] Rollback backup and transaction journal are ready.")
	return nil
}

func (transaction *Transaction) AbandonPreparation() {
	if err := removeSafeTree(transaction.stateDir, transaction.backupDir); err != nil && !os.IsNotExist(err) {
		transaction.logger.Printf("Could not remove an incomplete rollback backup: %v", err)
	}
	for _, path := range []string{transaction.journalPath} {
		payload, err := os.ReadFile(path)
		if err == nil {
			var journal transactionJournal
			if decodeStrictJSON(payload, &journal) == nil && journal.RunID != transaction.journal.RunID {
				continue
			}
		}
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			transaction.logger.Printf("Could not remove incomplete transaction state %s: %v", path, err)
		}
	}
}

func (transaction *Transaction) Apply() error {
	transaction.journal.Status = "applying"
	// Every destination has already been backed up. Marking the complete plan as
	// started lets crash recovery safely restore all operations without rewriting
	// a large journal before and after every individual file.
	for index := range transaction.journal.Operations {
		transaction.journal.Operations[index].Started = true
	}
	if err := transaction.writeJournal(); err != nil {
		return err
	}
	total := len(transaction.changes)
	for index, change := range transaction.changes {
		operation := &transaction.journal.Operations[index]
		if err := ensureSafeContainedPath(transaction.installRoot, operation.Destination); err != nil {
			return err
		}
		if err := ensureSafeContainedPath(transaction.installRoot, operation.Temporary); err != nil {
			return err
		}
		var err error
		switch change.Kind {
		case ReplaceFile:
			err = atomicInstallWithTemporary(change.Staged, change.Destination, operation.Temporary)
		case RemoveFile:
			err = removeManagedFile(change.Destination)
			if os.IsNotExist(err) {
				err = nil
			}
		default:
			err = fmt.Errorf("unknown transaction operation %q", change.Kind)
		}
		if err != nil {
			return fmt.Errorf("apply %s to %s: %w", change.Kind, change.Destination, err)
		}
		operation.Applied = true
		completed := index + 1
		if completed%250 == 0 || completed == total {
			transaction.logger.Printf("[APPLY] %d/%d file operation(s) complete.", completed, total)
		}
	}
	return nil
}

func (transaction *Transaction) Commit() error {
	transaction.journal.Status = "committed"
	if err := transaction.writeJournal(); err != nil {
		return err
	}
	if err := os.Remove(transaction.journalPath); err != nil {
		transaction.logger.Printf("Update committed, but its completed transaction journal could not be removed: %v", err)
	}
	if err := removeSafeTree(transaction.stateDir, transaction.backupDir); err != nil {
		transaction.logger.Printf("Update succeeded, but its temporary rollback backup could not be removed: %v", err)
	}
	transaction.cleanupOperationTemporaries()
	return nil
}

func (transaction *Transaction) PrepareStateTransition(path string, previous []byte, existed bool) error {
	if transaction.journal.Status != "applying" {
		return fmt.Errorf("updater state can only join an applying transaction")
	}
	if err := ensureSafeContainedPath(transaction.stateDir, path); err != nil {
		return err
	}
	if !strings.EqualFold(filepath.Clean(path), filepath.Join(transaction.stateDir, "state.json")) {
		return fmt.Errorf("transaction updater state path is invalid")
	}
	if len(previous) > 1024*1024 {
		return fmt.Errorf("previous updater state is too large")
	}
	transaction.journal.State = &journalStateTransition{
		Path: path, PreviousPayload: append([]byte(nil), previous...), Existed: existed,
	}
	return transaction.writeJournal()
}

func (transaction *Transaction) MarkStateUpdated() error {
	if transaction.journal.State == nil {
		return fmt.Errorf("updater state transition was not prepared")
	}
	transaction.journal.State.Updated = true
	return transaction.writeJournal()
}

func (transaction *Transaction) Rollback() error {
	transaction.logger.Printf("Rolling back %d planned file operation(s).", len(transaction.journal.Operations))
	var failures []string
	for index := len(transaction.journal.Operations) - 1; index >= 0; index-- {
		operation := &transaction.journal.Operations[index]
		if !operation.Started {
			continue
		}
		if operation.Existed {
			_ = os.Remove(operation.Temporary)
			if err := atomicInstallWithTemporary(operation.Backup, operation.Destination, operation.Temporary); err != nil {
				failures = append(failures, err.Error())
			}
		} else if err := removeManagedFile(operation.Destination); err != nil && !os.IsNotExist(err) {
			failures = append(failures, err.Error())
		}
		_ = os.Remove(operation.Temporary)
	}
	if transaction.journal.State != nil {
		if err := transaction.restorePreviousState(); err != nil {
			failures = append(failures, err.Error())
		}
	}
	transaction.journal.Status = "rolled-back"
	_ = transaction.writeJournal()
	if len(failures) > 0 {
		return fmt.Errorf("rollback failed: %s", strings.Join(failures, "; "))
	}
	_ = os.Remove(transaction.journalPath)
	if err := removeSafeTree(transaction.stateDir, transaction.backupDir); err != nil {
		transaction.logger.Printf("Rollback succeeded, but its temporary backup could not be removed: %v", err)
	}
	transaction.cleanupOperationTemporaries()
	return nil
}

func (transaction *Transaction) restorePreviousState() error {
	state := transaction.journal.State
	if state == nil {
		return nil
	}
	if err := ensureSafeContainedPath(transaction.stateDir, state.Path); err != nil {
		return err
	}
	if state.Existed {
		return writeAtomic(state.Path, state.PreviousPayload, 0o600)
	}
	if err := os.Remove(state.Path); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

func (transaction *Transaction) cleanupOperationTemporaries() {
	for _, operation := range transaction.journal.Operations {
		if operation.Temporary == "" {
			continue
		}
		if err := ensureSafeContainedPath(transaction.installRoot, operation.Temporary); err == nil {
			_ = os.Remove(operation.Temporary)
		}
	}
}

func RecoverInterruptedTransaction(stateDir string, layout Layout, logger *Logger) (bool, error) {
	path := filepath.Join(stateDir, "current-transaction.json")
	payload, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	var journal transactionJournal
	if err := decodeStrictJSON(payload, &journal); err != nil {
		return false, fmt.Errorf("cannot decode interrupted transaction journal: %w", err)
	}
	if err := validateInterruptedJournal(journal, stateDir, layout); err != nil {
		return false, err
	}
	if journal.Status == "committed" || journal.Status == "rolled-back" {
		transaction := &Transaction{stateDir: stateDir, installRoot: layout.InstallRoot, journal: journal, logger: logger}
		transaction.cleanupOperationTemporaries()
		if err := os.Remove(path); err != nil {
			return false, err
		}
		_ = removeSafeTree(stateDir, filepath.Join(stateDir, "backups", journal.RunID))
		return true, nil
	}
	logger.Printf("Recovering interrupted updater transaction %s.", journal.RunID)
	transaction := &Transaction{stateDir: stateDir, installRoot: layout.InstallRoot, backupDir: filepath.Join(stateDir, "backups", journal.RunID), journalPath: path, journal: journal, logger: logger}
	if err := transaction.Rollback(); err != nil {
		return false, err
	}
	return true, nil
}

func validateInterruptedJournal(journal transactionJournal, stateDir string, layout Layout) error {
	if journal.Schema != "kfps.update-transaction.v1" {
		return fmt.Errorf("unknown interrupted transaction schema")
	}
	if journal.RunID == "" || safeName(journal.RunID) != journal.RunID {
		return fmt.Errorf("interrupted transaction has an invalid run id")
	}
	switch journal.Status {
	case "preparing", "applying", "committed", "rolled-back":
	default:
		return fmt.Errorf("interrupted transaction has an invalid status")
	}
	expectedInstall, err := filepath.Abs(layout.InstallRoot)
	if err != nil {
		return err
	}
	journalInstall, err := filepath.Abs(journal.InstallRoot)
	if err != nil || !strings.EqualFold(filepath.Clean(journalInstall), filepath.Clean(expectedInstall)) {
		return fmt.Errorf("interrupted transaction belongs to a different installation")
	}
	if len(journal.Operations) > maximumArchiveFiles {
		return fmt.Errorf("interrupted transaction contains too many operations")
	}
	expectedBackupRoot, err := filepath.Abs(filepath.Join(stateDir, "backups", journal.RunID))
	if err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, operation := range journal.Operations {
		if operation.Kind != ReplaceFile && operation.Kind != RemoveFile {
			return fmt.Errorf("interrupted transaction contains an invalid operation")
		}
		destination, err := filepath.Abs(operation.Destination)
		if err != nil || !pathIsContained(expectedInstall, destination) {
			return fmt.Errorf("interrupted transaction destination is outside the installation")
		}
		if seen[pathKey(destination)] {
			return fmt.Errorf("interrupted transaction contains duplicate destinations")
		}
		seen[pathKey(destination)] = true
		backup, err := filepath.Abs(operation.Backup)
		if err != nil || !pathIsContained(expectedBackupRoot, backup) {
			return fmt.Errorf("interrupted transaction backup is outside its run directory")
		}
		if journal.Status != "committed" && journal.Status != "rolled-back" && operation.Started && operation.Existed && !fileExists(backup) {
			return fmt.Errorf("interrupted transaction rollback backup is missing")
		}
		if operation.Temporary == "" && journal.Status != "committed" && journal.Status != "rolled-back" {
			return fmt.Errorf("interrupted transaction operation has no temporary path")
		}
		if operation.Temporary != "" {
			temporary, err := filepath.Abs(operation.Temporary)
			if err != nil || !pathIsContained(expectedInstall, temporary) || !strings.EqualFold(filepath.Dir(temporary), filepath.Dir(destination)) {
				return fmt.Errorf("interrupted transaction temporary path is invalid")
			}
		}
	}
	if journal.State != nil {
		expectedState := filepath.Join(stateDir, "state.json")
		statePath, err := filepath.Abs(journal.State.Path)
		if err != nil || !strings.EqualFold(filepath.Clean(statePath), filepath.Clean(expectedState)) {
			return fmt.Errorf("interrupted transaction updater state path is invalid")
		}
		if len(journal.State.PreviousPayload) > 1024*1024 {
			return fmt.Errorf("interrupted transaction previous updater state is too large")
		}
	}
	return nil
}

func pathIsContained(root, target string) bool {
	relative, err := filepath.Rel(root, target)
	return err == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator))
}

func (transaction *Transaction) writeJournal() error {
	payload, err := json.MarshalIndent(transaction.journal, "", "  ")
	if err != nil {
		return err
	}
	if err := ensureSafeContainedPath(transaction.stateDir, transaction.journalPath); err != nil {
		return err
	}
	return writeAtomic(transaction.journalPath, append(payload, '\n'), 0o600)
}

func writeAtomic(path string, payload []byte, mode os.FileMode) error {
	if err := ensureNoLinkedPath(path); err != nil {
		return err
	}
	if err := makeSafeDirectory(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	file, err := os.CreateTemp(filepath.Dir(path), "."+filepath.Base(path)+".kfps-state-*.tmp")
	if err != nil {
		return err
	}
	temporary := file.Name()
	if err := file.Chmod(mode); err != nil {
		file.Close()
		_ = os.Remove(temporary)
		return err
	}
	if _, err = file.Write(payload); err == nil {
		err = file.Sync()
	}
	if closeErr := file.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		_ = os.Remove(temporary)
		return err
	}
	if err := ensureNoLinkedPath(path); err != nil {
		_ = os.Remove(temporary)
		return err
	}
	if err := replaceFile(temporary, path); err != nil {
		_ = os.Remove(temporary)
		return err
	}
	return nil
}

func copyFile(source, destination string) error {
	input, err := os.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()
	if err := makeSafeDirectory(filepath.Dir(destination), 0o700); err != nil {
		return err
	}
	output, err := os.OpenFile(destination, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
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

func atomicInstallWithTemporary(source, destination, temporary string) error {
	if err := makeSafeDirectory(filepath.Dir(destination), 0o755); err != nil {
		return err
	}
	if err := copyFileExclusive(source, temporary); err != nil {
		return err
	}
	if err := clearReadOnly(destination); err != nil {
		_ = os.Remove(temporary)
		return err
	}
	if err := replaceFile(temporary, destination); err != nil {
		_ = os.Remove(temporary)
		return err
	}
	return nil
}

func copyFileExclusive(source, destination string) error {
	input, err := os.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()
	if err := makeSafeDirectory(filepath.Dir(destination), 0o700); err != nil {
		return err
	}
	output, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
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

func removeManagedFile(path string) error {
	if err := clearReadOnly(path); err != nil {
		return err
	}
	return os.Remove(path)
}
