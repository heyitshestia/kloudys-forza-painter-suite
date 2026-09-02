package bootstrap

import (
	"fmt"
	"time"
)

func WaitForProcessExit(pid int, timeout time.Duration, logger *Logger) error {
	if pid <= 0 {
		return nil
	}
	if !processRunning(pid) {
		return nil
	}
	logger.Printf("Waiting for KFPS process %d to close before updating.", pid)
	deadline := time.Now().Add(timeout)
	for processRunning(pid) {
		if time.Now().After(deadline) {
			return fmt.Errorf("KFPS process %d did not close within %s; close it and run the updater again", pid, timeout)
		}
		time.Sleep(200 * time.Millisecond)
	}
	logger.Printf("KFPS process %d closed; continuing safely.", pid)
	return nil
}
