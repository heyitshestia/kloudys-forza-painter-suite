//go:build !windows

package bootstrap

func clearReadOnly(path string) error {
	return nil
}
