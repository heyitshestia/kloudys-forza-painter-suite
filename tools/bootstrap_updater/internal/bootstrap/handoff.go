package bootstrap

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
)

type HandoffArtifact struct {
	Path string
	Artifact
}

type openedExecutable struct {
	file        *os.File
	commandPath string
	revalidate  func() error
}

func (opened *openedExecutable) close() error {
	if opened == nil || opened.file == nil {
		return nil
	}
	err := opened.file.Close()
	opened.file = nil
	return err
}

func verifyOpenedExecutable(opened *openedExecutable, expected Artifact) error {
	if opened == nil || opened.file == nil {
		return fmt.Errorf("verified executable handle is unavailable")
	}
	expectedHash, err := normalizeSHA256(expected.SHA256)
	if err != nil {
		return err
	}
	if expected.Size <= 0 {
		return fmt.Errorf("verified executable size is invalid")
	}
	info, err := opened.file.Stat()
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() || info.Size() != expected.Size {
		return fmt.Errorf("verified executable type or size does not match the signed artifact")
	}
	if _, err := opened.file.Seek(0, 0); err != nil {
		return err
	}
	hash := sha256.New()
	if _, err := io.Copy(hash, opened.file); err != nil {
		return err
	}
	actualHash := hex.EncodeToString(hash.Sum(nil))
	if !strings.EqualFold(actualHash, expectedHash) {
		return fmt.Errorf("verified executable SHA-256 does not match the signed artifact")
	}
	if opened.revalidate != nil {
		if err := opened.revalidate(); err != nil {
			return err
		}
	}
	return nil
}

// LaunchVerifiedExecutable keeps a no-follow, authenticated file handle open
// until process creation has opened the image. A waited child returns its exact
// exit code; an asynchronous launch returns -1 after process creation succeeds.
func LaunchVerifiedExecutable(handoff HandoffArtifact, arguments []string, directory string, stdin io.Reader, stdout, stderr io.Writer, wait bool) (int, error) {
	opened, err := openVerifiedExecutable(handoff.Path)
	if err != nil {
		return -1, err
	}
	defer opened.close()
	if err := verifyOpenedExecutable(opened, handoff.Artifact); err != nil {
		return -1, err
	}
	command := exec.Command(opened.commandPath, arguments...)
	command.Dir = directory
	command.Stdin = stdin
	command.Stdout = stdout
	command.Stderr = stderr
	if err := command.Start(); err != nil {
		return -1, err
	}
	_ = opened.close()
	if !wait {
		return -1, nil
	}
	if err := command.Wait(); err != nil {
		var exitError *exec.ExitError
		if !errors.As(err, &exitError) {
			return -1, err
		}
		return exitError.ExitCode(), nil
	}
	return 0, nil
}
