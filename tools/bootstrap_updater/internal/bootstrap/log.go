package bootstrap

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type Logger struct {
	mu   sync.Mutex
	file *os.File
	out  io.Writer
	Path string
}

func NewLogger(directory, runID string, output io.Writer) (*Logger, error) {
	if err := makeSafeDirectory(directory, 0o755); err != nil {
		return nil, err
	}
	path := filepath.Join(directory, "update-"+runID+".log")
	if err := ensureNoLinkedPath(path); err != nil {
		return nil, err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_EXCL, 0o600)
	if err != nil {
		return nil, err
	}
	if output == nil {
		output = io.Discard
	}
	return &Logger{file: file, out: output, Path: path}, nil
}

func (logger *Logger) Close() error {
	logger.mu.Lock()
	defer logger.mu.Unlock()
	if logger.file == nil {
		return nil
	}
	err := logger.file.Close()
	logger.file = nil
	return err
}

func (logger *Logger) Printf(format string, arguments ...any) {
	logger.mu.Lock()
	defer logger.mu.Unlock()
	line := fmt.Sprintf(format, arguments...)
	prefix := time.Now().UTC().Format("2006-01-02T15:04:05.000Z") + " "
	fmt.Fprintln(logger.out, line)
	if logger.file != nil {
		fmt.Fprintln(logger.file, prefix+line)
		_ = logger.file.Sync()
	}
}
