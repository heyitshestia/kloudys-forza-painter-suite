package bootstrap

import (
	"fmt"
	"os"
	"path/filepath"
)

type volumeSpaceRequirement struct {
	path    string
	backup  int64
	maximum int64
}

func ensureTransactionSpace(stateDir string, backupBytes int64, changes []Change, operations []journalOperation) error {
	requirements := map[string]*volumeSpaceRequirement{}
	stateKey, err := storageVolumeKey(stateDir)
	if err != nil {
		return err
	}
	requirements[stateKey] = &volumeSpaceRequirement{path: stateDir, backup: backupBytes}
	for index, change := range changes {
		key, err := storageVolumeKey(change.Destination)
		if err != nil {
			return err
		}
		requirement := requirements[key]
		if requirement == nil {
			requirement = &volumeSpaceRequirement{path: filepath.Dir(change.Destination)}
			requirements[key] = requirement
		}
		needed := change.Expected.Size
		if index < len(operations) && operations[index].Existed {
			if info, statErr := os.Stat(operations[index].Destination); statErr == nil && info.Size() > needed {
				needed = info.Size()
			}
		}
		if needed > requirement.maximum {
			requirement.maximum = needed
		}
	}
	for _, requirement := range requirements {
		required := requirement.backup + requirement.maximum
		if required == 0 {
			continue
		}
		required += 64 * 1024 * 1024
		available, err := availableSpace(requirement.path)
		if err != nil {
			return err
		}
		if available < uint64(required) {
			return fmt.Errorf("not enough free space for a rollback-safe update on %s: need %d bytes, have %d", requirement.path, required, available)
		}
	}
	return nil
}
