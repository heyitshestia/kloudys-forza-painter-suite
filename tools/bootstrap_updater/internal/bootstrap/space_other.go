//go:build !windows

package bootstrap

func availableSpace(_ string) (uint64, error)   { return ^uint64(0), nil }
func storageVolumeKey(_ string) (string, error) { return "default", nil }
