package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

func validateGarageSupport(root, pythonRoot string) error {
	if _, err := os.Stat(filepath.Join(root, "KFPS.UI", "src", "kfps_ui", "garage_reader.py")); os.IsNotExist(err) {
		return nil
	} else if err != nil {
		return err
	}
	worker := filepath.Join(root, "tools", "garage-reader", "reader.py")
	if !fileIsRegular(worker) {
		return fmt.Errorf("Garage support is missing from the application snapshot")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	for _, name := range []string{"reader.py", "catalogue.py"} {
		command := exec.CommandContext(ctx, filepath.Join(pythonRoot, "python.exe"), "-I", "-B", filepath.Join(filepath.Dir(worker), name), "--check")
		output, err := command.Output()
		if err != nil {
			return fmt.Errorf("Garage support failed its installed check: %w", err)
		}
		var result struct {
			Ready bool `json:"ready"`
		}
		if err := json.Unmarshal(output, &result); err != nil || !result.Ready {
			return fmt.Errorf("Garage support did not confirm readiness")
		}
	}
	return nil
}
