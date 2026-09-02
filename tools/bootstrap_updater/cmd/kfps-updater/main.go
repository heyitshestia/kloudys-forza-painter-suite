package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/heyitshestia/kloudys-forza-painter-suite/tools/bootstrap_updater/internal/bootstrap"
)

var (
	version          = "dev"
	trustedPublicKey = ""
	testFeatures     = "disabled"
	launchHandoff    = bootstrap.LaunchVerifiedExecutable
)

const (
	defaultChannelURL      = "https://raw.githubusercontent.com/heyitshestia/kloudys-forza-painter-suite/main/updates/stable/channel.json"
	recoveryVersion        = "3.1.54"
	recoveryCommit         = "87dd1de0dc9104f423a8042d9be304f86f87ad15"
	recoveryURL            = "https://github.com/heyitshestia/kloudys-forza-painter-suite/releases/download/v3.1.54/KFPS-3.1.54-bundled.zip"
	recoverySHA256         = "551f4052ee8f6707d7c7e24fb7b42ed74be9bfac45e3cfdd7281ca773e1ad0ec"
	recoverySize           = int64(422238121)
	recoveryManifest       = "3929f83aa0794909dfe1854d97885a10db9d6d0badfe0f10d3b55a176044a4c6"
	recoveryManSize        = int64(2286851)
	handoffPendingExitCode = 4
)

type options struct {
	root               string
	channelURL         string
	channelSignature   string
	recoveryArchive    string
	stateDir           string
	forceRecovery      bool
	disableFallback    bool
	dryRun             bool
	relaunch           bool
	noPause            bool
	allowSequenceReset bool
	waitPID            int
	showVersion        bool
	showBuildInfo      bool
}

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(arguments []string) int {
	parsed, err := parseOptions(arguments)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Updater options are invalid:", err)
		return 2
	}
	if parsed.showVersion {
		fmt.Println("KFPS Bootstrap Updater", version)
		return 0
	}
	if parsed.showBuildInfo {
		keyID := ""
		if key, keyErr := bootstrap.DecodePublicKey(trustedPublicKey); keyErr == nil {
			keyID = bootstrap.KeyID(key)
		}
		_ = json.NewEncoder(os.Stdout).Encode(map[string]string{
			"schema": "kfps.bootstrap-build.v1", "version": version,
			"key_id": keyID, "platform": runtime.GOOS + "/" + runtime.GOARCH,
		})
		return 0
	}
	executable, err := os.Executable()
	if err != nil {
		fmt.Fprintln(os.Stderr, "Could not identify updater executable:", err)
		return 2
	}
	workingDirectory, _ := os.Getwd()
	layout, err := bootstrap.ResolveLayout(parsed.root, executable, workingDirectory)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		pause(parsed.noPause)
		return 2
	}
	if parsed.stateDir == "" {
		parsed.stateDir, err = bootstrap.DefaultStateDir(layout)
		if err != nil {
			fmt.Fprintln(os.Stderr, "Could not locate updater state directory:", err)
			return 2
		}
	}
	parsed.stateDir, err = bootstrap.ValidateUpdaterStateDir(parsed.stateDir, layout)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Updater state directory is unsafe:", err)
		return 2
	}
	logID := time.Now().UTC().Format("20060102-150405") + fmt.Sprintf("-%d", os.Getpid())
	logger, err := bootstrap.NewLogger(filepath.Join(parsed.stateDir, "logs"), logID, os.Stdout)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Could not create updater log:", err)
		return 2
	}
	defer logger.Close()
	logger.Printf("KFPS Bootstrap Updater %s", version)
	logger.Printf("Install root: %s", layout.InstallRoot)
	logger.Printf("Application root: %s", layout.AppRoot)
	logger.Printf("Log file: %s", logger.Path)
	if err := bootstrap.WaitForProcessExit(parsed.waitPID, 60*time.Second, logger); err != nil {
		logger.Printf("Update stopped: %v", err)
		pause(parsed.noPause)
		return 1
	}

	publicKey, keyErr := bootstrap.DecodePublicKey(trustedPublicKey)
	if keyErr != nil {
		logger.Printf("Signed channel trust key is unavailable: %v", keyErr)
		publicKey = nil
	}
	engine, err := bootstrap.NewEngine(bootstrap.EngineConfig{
		BootstrapVersion:        version,
		ChannelURL:              parsed.channelURL,
		ChannelSignature:        parsed.channelSignature,
		TrustedKey:              publicKey,
		RecoveryArchive:         parsed.recoveryArchive,
		Layout:                  layout,
		StateDir:                parsed.stateDir,
		CurrentExecutable:       executable,
		Logger:                  logger,
		AllowLocalSources:       testMode(),
		ForceRecovery:           parsed.forceRecovery,
		DisableFallback:         parsed.disableFallback,
		AllowSequenceReset:      parsed.allowSequenceReset,
		DryRun:                  parsed.dryRun,
		FinalizeLegacyMigration: true,
		Recovery: bootstrap.RecoveryConfig{
			Version:        recoveryVersion,
			Commit:         recoveryCommit,
			ManifestSHA256: recoveryManifest,
			ManifestSize:   recoveryManSize,
			ExcludedFiles: []string{
				"KloudysFH6Painter/03_update_from_github.bat",
				"KloudysFH6Painter/update_from_github.bat",
			},
			Artifact: bootstrap.Artifact{
				URL:    recoveryURL,
				SHA256: recoverySHA256,
				Size:   recoverySize,
			},
		},
	})
	if err != nil {
		logger.Printf("Updater initialization failed: %v", err)
		pause(parsed.noPause)
		return 2
	}
	result, err := engine.Run(context.Background())
	if err != nil {
		logger.Printf("Update failed: %v", err)
		logger.Printf("No unverified update was accepted. See the log and JSON report for details.")
		pause(parsed.noPause)
		return 1
	}
	if bootstrap.IsHandoff(result) {
		waitForResult := parsed.dryRun
		exitCode, err := startHandoff(result.Handoff, arguments, layout, parsed.stateDir, os.Getpid(), testMode(), waitForResult)
		if err != nil {
			logger.Printf("Verified updater handoff could not start: %v", err)
			if reportErr := engine.RecordHandoffFailure(result.Summary, err); reportErr != nil {
				logger.Printf("Could not update the handoff failure report: %v", reportErr)
			}
			pause(parsed.noPause)
			return 1
		}
		if waitForResult {
			if reportErr := engine.RecordHandoffExit(result.Summary, exitCode); reportErr != nil {
				logger.Printf("Could not record the verified child result: %v", reportErr)
			}
			logger.Printf("Verified updater check completed with exit code %d.", exitCode)
			return exitCode
		}
		logger.Printf("Verified updater handoff started and remains pending: %s.", result.Handoff.Path)
		return handoffPendingExitCode
	}
	if parsed.dryRun {
		logger.Printf("Check complete: %d replacement(s) and %d removal(s) would be required.", result.Summary.FilesPlannedReplaced, result.Summary.FilesPlannedRemoved)
		if checkExitCode(result.Summary) != 0 {
			pause(parsed.noPause)
			return checkExitCode(result.Summary)
		}
	} else {
		logger.Printf("Update complete. Installed version: %s", result.Summary.ToVersion)
	}
	if parsed.relaunch && !parsed.dryRun {
		launcher := filepath.Join(layout.InstallRoot, "KFPS.exe")
		command := exec.Command(launcher)
		command.Dir = layout.InstallRoot
		if err := command.Start(); err != nil {
			logger.Printf("Update succeeded, but KFPS could not be relaunched: %v", err)
		}
	}
	pause(parsed.noPause)
	return 0
}

func checkExitCode(summary bootstrap.RunSummary) int {
	if summary.FilesPlannedReplaced > 0 || summary.FilesPlannedRemoved > 0 {
		return 3
	}
	return 0
}

func parseOptions(arguments []string) (options, error) {
	parsed := options{}
	flags := flag.NewFlagSet("KFPS-Updater", flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	flags.StringVar(&parsed.root, "root", "", "KFPS installation root")
	flags.StringVar(&parsed.channelURL, "channel-url", defaultChannelURL, "signed update channel URL")
	flags.StringVar(&parsed.channelSignature, "channel-signature-url", defaultChannelURL+".sig", "detached channel signature URL")
	flags.StringVar(&parsed.recoveryArchive, "recovery-archive", "", "local hash-pinned v3.1.54 recovery ZIP")
	flags.StringVar(&parsed.stateDir, "state-dir", "", "updater state directory (test mode only)")
	flags.BoolVar(&parsed.forceRecovery, "recover", false, "repair to the embedded hash-pinned recovery baseline")
	flags.BoolVar(&parsed.disableFallback, "no-recovery-fallback", false, "do not use the embedded recovery baseline when the signed channel is unavailable")
	flags.BoolVar(&parsed.dryRun, "check", false, "verify and report without changing installation files")
	flags.BoolVar(&parsed.relaunch, "relaunch", false, "relaunch KFPS after a successful update")
	flags.BoolVar(&parsed.noPause, "no-pause", false, "do not wait for input before exiting")
	flags.BoolVar(&parsed.allowSequenceReset, "allow-sequence-reset", false, "test-only signed channel rollback override")
	flags.IntVar(&parsed.waitPID, "wait-pid", 0, "wait for the launching KFPS process to close")
	flags.BoolVar(&parsed.showVersion, "version", false, "print updater version")
	flags.BoolVar(&parsed.showBuildInfo, "build-info", false, "print machine-readable updater build identity")
	if err := flags.Parse(arguments); err != nil {
		return options{}, err
	}
	if flags.NArg() != 0 {
		return options{}, fmt.Errorf("unexpected argument %q", flags.Arg(0))
	}
	if parsed.waitPID < 0 {
		return options{}, fmt.Errorf("wait PID cannot be negative")
	}
	if !testMode() {
		if parsed.channelURL != defaultChannelURL || parsed.channelSignature != defaultChannelURL+".sig" || parsed.stateDir != "" || parsed.allowSequenceReset {
			return options{}, fmt.Errorf("custom channel, state, and rollback options require a test-enabled updater and KFPS_UPDATER_TEST_MODE=1")
		}
	}
	return parsed, nil
}

func startHandoff(handoff bootstrap.HandoffArtifact, original []string, layout bootstrap.Layout, stateDir string, parentPID int, includeStateDir, waitForResult bool) (int, error) {
	arguments := buildHandoffArguments(original, layout, stateDir, parentPID, includeStateDir, !waitForResult)
	return launchHandoff(handoff, arguments, layout.InstallRoot, os.Stdin, os.Stdout, os.Stderr, waitForResult)
}

func buildHandoffArguments(original []string, layout bootstrap.Layout, stateDir string, parentPID int, includeStateDir, waitForParent bool) []string {
	arguments := make([]string, 0, len(original)+8)
	for index := 0; index < len(original); index++ {
		argument := original[index]
		name := strings.SplitN(argument, "=", 2)[0]
		switch name {
		case "--root", "--state-dir", "--wait-pid":
			if argument == name && index+1 < len(original) {
				index++
			}
			continue
		case "--no-pause":
			continue
		}
		arguments = append(arguments, argument)
	}
	arguments = append(arguments, "--root", layout.InstallRoot)
	if includeStateDir {
		arguments = append(arguments, "--state-dir", stateDir)
	}
	if waitForParent {
		arguments = append(arguments, "--wait-pid", strconv.Itoa(parentPID))
	}
	arguments = append(arguments, "--no-pause")
	return arguments
}

func pause(disabled bool) {
	if disabled || strings.EqualFold(os.Getenv("KFPS_UPDATER_NO_PAUSE"), "1") {
		return
	}
	fmt.Print("Press Enter to close...")
	_, _ = fmt.Scanln()
}

func testMode() bool {
	return strings.EqualFold(testFeatures, "enabled") && os.Getenv("KFPS_UPDATER_TEST_MODE") == "1"
}
