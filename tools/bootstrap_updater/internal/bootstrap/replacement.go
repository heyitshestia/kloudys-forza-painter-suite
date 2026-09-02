package bootstrap

// ReplaceFileAtomically replaces destination with a fully written temporary file.
// Source and destination must be on the same volume.
func ReplaceFileAtomically(source, destination string) error {
	return replaceFile(source, destination)
}
