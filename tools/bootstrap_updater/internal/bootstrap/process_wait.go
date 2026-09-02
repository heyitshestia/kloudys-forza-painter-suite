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
	logger.Printf("[WAIT] Waiting for KFPS process %d to close safely.", pid)
	deadline := time.Now().Add(timeout)
	started := time.Now()
	nextUpdate := started.Add(5 * time.Second)
	for processRunning(pid) {
		if time.Now().After(deadline) {
			return fmt.Errorf("KFPS process %d did not close within %s; close it and run the updater again", pid, timeout)
		}
		if time.Now().After(nextUpdate) {
			logger.Printf("[WAIT] KFPS is still closing (%ds elapsed).", int(time.Since(started).Seconds()))
			nextUpdate = nextUpdate.Add(5 * time.Second)
		}
		time.Sleep(200 * time.Millisecond)
	}
	logger.Printf("[OK] KFPS process %d closed safely.", pid)
	return nil
}
