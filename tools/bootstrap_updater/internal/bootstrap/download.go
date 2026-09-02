package bootstrap

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type Downloader struct {
	Client     *http.Client
	Logger     *Logger
	AllowLocal bool
	Bytes      int64
}

func NewDownloader(logger *Logger, allowLocal bool) *Downloader {
	client := &http.Client{
		Transport: &http.Transport{
			Proxy:                 http.ProxyFromEnvironment,
			DialContext:           (&net.Dialer{Timeout: 30 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
			TLSHandshakeTimeout:   30 * time.Second,
			ResponseHeaderTimeout: 60 * time.Second,
			ExpectContinueTimeout: time.Second,
			IdleConnTimeout:       90 * time.Second,
		},
		CheckRedirect: func(request *http.Request, via []*http.Request) error {
			if len(via) >= 6 {
				return policyFailure(fmt.Errorf("too many redirects"))
			}
			if request.URL.Scheme != "https" && !(allowLocal && request.URL.Scheme == "http" && isLoopbackHost(request.URL.Hostname())) {
				return policyFailure(fmt.Errorf("refusing redirect to %s", request.URL.Redacted()))
			}
			return nil
		},
	}
	return &Downloader{Client: client, Logger: logger, AllowLocal: allowLocal}
}

func (downloader *Downloader) Read(ctx context.Context, location string, maximum int64) ([]byte, error) {
	if maximum <= 0 {
		return nil, fmt.Errorf("invalid download limit")
	}
	parsed, err := url.Parse(location)
	if err != nil {
		return nil, err
	}
	if parsed.Scheme == "file" {
		if !downloader.AllowLocal {
			return nil, fmt.Errorf("local update sources are disabled")
		}
		path, err := fileURLPath(parsed)
		if err != nil {
			return nil, err
		}
		payload, err := os.ReadFile(path)
		if err != nil {
			return nil, unavailable(err)
		}
		if int64(len(payload)) > maximum {
			return nil, fmt.Errorf("local payload exceeds %d bytes", maximum)
		}
		downloader.Bytes += int64(len(payload))
		return payload, nil
	}
	if parsed.Scheme != "https" && !(downloader.AllowLocal && parsed.Scheme == "http" && isLoopbackHost(parsed.Hostname())) {
		return nil, fmt.Errorf("refusing non-HTTPS update source %s", parsed.Redacted())
	}
	var lastError error
	for attempt := 1; attempt <= 3; attempt++ {
		attemptContext, cancelAttempt := context.WithCancel(ctx)
		idleTimer := time.AfterFunc(2*time.Minute, cancelAttempt)
		request, err := http.NewRequestWithContext(attemptContext, http.MethodGet, location, nil)
		if err != nil {
			idleTimer.Stop()
			cancelAttempt()
			return nil, err
		}
		request.Header.Set("User-Agent", "KFPS-Bootstrap-Updater")
		request.Header.Set("Accept", "application/octet-stream, application/json")
		response, err := downloader.Client.Do(request)
		if err != nil {
			if !isPolicyError(err) {
				err = unavailable(err)
			}
		}
		if err == nil {
			if response.StatusCode != http.StatusOK {
				err = unavailable(fmt.Errorf("HTTP %d from %s", response.StatusCode, parsed.Redacted()))
			} else if response.ContentLength > maximum {
				err = fmt.Errorf("download declares %d bytes; limit is %d", response.ContentLength, maximum)
			} else {
				reader := activityReader{reader: availabilityReader{reader: response.Body}, activity: func() { idleTimer.Reset(2 * time.Minute) }}
				payload, readErr := io.ReadAll(io.LimitReader(reader, maximum+1))
				if readErr != nil {
					err = readErr
				} else if int64(len(payload)) > maximum {
					err = fmt.Errorf("download exceeds %d bytes", maximum)
				} else {
					response.Body.Close()
					downloader.Bytes += int64(len(payload))
					return payload, nil
				}
			}
			response.Body.Close()
		}
		idleTimer.Stop()
		cancelAttempt()
		if err != nil {
			lastError = err
			if !isAvailabilityError(err) {
				return nil, err
			}
		}
		if attempt < 3 {
			downloader.Logger.Printf("Download attempt %d failed: %v", attempt, lastError)
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(time.Duration(attempt) * time.Second):
			}
		}
	}
	return nil, lastError
}

func (downloader *Downloader) DownloadArtifact(ctx context.Context, artifact Artifact, destination string) error {
	if err := validateArtifact("artifact", artifact); err != nil {
		return err
	}
	if err := ensureNoLinkedPath(destination); err != nil {
		return err
	}
	if err := ensureNoLinkedPath(destination + ".partial"); err != nil {
		return err
	}
	if err := makeSafeDirectory(filepath.Dir(destination), 0o755); err != nil {
		return err
	}
	parsed, err := url.Parse(artifact.URL)
	if err != nil {
		return err
	}
	if parsed.Scheme == "file" {
		if !downloader.AllowLocal {
			return fmt.Errorf("local update sources are disabled")
		}
		path, err := fileURLPath(parsed)
		if err != nil {
			return err
		}
		input, err := os.Open(path)
		if err != nil {
			return unavailable(err)
		}
		defer input.Close()
		_ = os.Remove(destination + ".partial")
		written, err := downloader.writeVerifiedArtifact(input, artifact, destination, 0)
		downloader.Bytes += written
		return err
	}
	if parsed.Scheme != "https" && !(downloader.AllowLocal && parsed.Scheme == "http" && isLoopbackHost(parsed.Hostname())) {
		return fmt.Errorf("refusing non-HTTPS update source %s", parsed.Redacted())
	}
	var lastError error
	for attempt := 1; attempt <= 3; attempt++ {
		offset := validPartialSize(destination+".partial", artifact.Size)
		attemptContext, cancelAttempt := context.WithCancel(ctx)
		idleTimer := time.AfterFunc(2*time.Minute, cancelAttempt)
		request, err := http.NewRequestWithContext(attemptContext, http.MethodGet, artifact.URL, nil)
		if err != nil {
			idleTimer.Stop()
			cancelAttempt()
			return err
		}
		request.Header.Set("User-Agent", "KFPS-Bootstrap-Updater")
		if offset > 0 {
			request.Header.Set("Range", fmt.Sprintf("bytes=%d-", offset))
		}
		response, err := downloader.Client.Do(request)
		if err != nil {
			if !isPolicyError(err) {
				err = unavailable(err)
			}
		}
		if err == nil {
			if response.StatusCode != http.StatusOK && response.StatusCode != http.StatusPartialContent {
				err = unavailable(fmt.Errorf("HTTP %d from %s", response.StatusCode, parsed.Redacted()))
			} else {
				if response.StatusCode == http.StatusOK {
					offset = 0
					_ = os.Remove(destination + ".partial")
				} else if rangeErr := validateContentRange(response.Header.Get("Content-Range"), offset, artifact.Size); rangeErr != nil {
					err = rangeErr
				}
				expectedResponse := artifact.Size - offset
				if err == nil && response.ContentLength >= 0 && response.ContentLength != expectedResponse {
					err = fmt.Errorf("server reports %d bytes; expected %d", response.ContentLength, expectedResponse)
				} else if err == nil {
					reader := activityReader{reader: availabilityReader{reader: response.Body}, activity: func() { idleTimer.Reset(2 * time.Minute) }}
					progress := newDownloadProgress(reader, artifact.Size, downloader.Logger)
					progress.read = offset
					written, writeErr := downloader.writeVerifiedArtifact(progress, artifact, destination, offset)
					downloader.Bytes += written
					err = writeErr
				}
			}
			response.Body.Close()
		}
		idleTimer.Stop()
		cancelAttempt()
		if err == nil {
			return nil
		}
		lastError = err
		if !isAvailabilityError(err) {
			_ = os.Remove(destination + ".partial")
			return err
		}
		if attempt < 3 {
			downloader.Logger.Printf("Artifact download attempt %d failed: %v", attempt, err)
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(time.Duration(attempt) * time.Second):
			}
		}
	}
	return lastError
}

func validateContentRange(value string, offset, total int64) error {
	if offset <= 0 {
		return fmt.Errorf("server returned partial content without a resumable local artifact")
	}
	fields := strings.Fields(value)
	if len(fields) != 2 || fields[0] != "bytes" {
		return fmt.Errorf("server returned an invalid Content-Range %q", value)
	}
	parts := strings.Split(fields[1], "/")
	if len(parts) != 2 {
		return fmt.Errorf("server returned an invalid Content-Range %q", value)
	}
	limits := strings.Split(parts[0], "-")
	if len(limits) != 2 {
		return fmt.Errorf("server returned an invalid Content-Range %q", value)
	}
	start, startErr := strconv.ParseInt(limits[0], 10, 64)
	end, endErr := strconv.ParseInt(limits[1], 10, 64)
	declaredTotal, totalErr := strconv.ParseInt(parts[1], 10, 64)
	if startErr != nil || endErr != nil || totalErr != nil || start != offset || end != total-1 || declaredTotal != total {
		return fmt.Errorf("server returned Content-Range %q; expected bytes %d-%d/%d", value, offset, total-1, total)
	}
	return nil
}

type downloadProgress struct {
	reader      io.Reader
	total       int64
	read        int64
	nextPercent int64
	logger      *Logger
}

func newDownloadProgress(reader io.Reader, total int64, logger *Logger) *downloadProgress {
	return &downloadProgress{reader: reader, total: total, nextPercent: 10, logger: logger}
}

func (progress *downloadProgress) Read(buffer []byte) (int, error) {
	count, err := progress.reader.Read(buffer)
	progress.read += int64(count)
	if progress.total > 0 {
		percent := progress.read * 100 / progress.total
		if percent >= progress.nextPercent {
			progress.logger.Printf("Download progress: %d%% (%d/%d bytes).", percent, progress.read, progress.total)
			progress.nextPercent = (percent/10 + 1) * 10
		}
	}
	return count, err
}

func (downloader *Downloader) writeVerifiedArtifact(reader io.Reader, artifact Artifact, destination string, offset int64) (int64, error) {
	temporary := destination + ".partial"
	if err := ensureNoLinkedPath(temporary); err != nil {
		return 0, err
	}
	hash := sha256.New()
	if offset > 0 {
		existing, err := os.Open(temporary)
		if err != nil {
			return 0, err
		}
		count, hashErr := io.Copy(hash, io.LimitReader(existing, offset+1))
		closeErr := existing.Close()
		if hashErr != nil || closeErr != nil || count != offset {
			_ = os.Remove(temporary)
			if hashErr != nil {
				return 0, hashErr
			}
			if closeErr != nil {
				return 0, closeErr
			}
			return 0, fmt.Errorf("partial artifact size changed")
		}
	}
	flags := os.O_CREATE | os.O_WRONLY
	if offset == 0 {
		flags |= os.O_TRUNC
	} else {
		flags |= os.O_APPEND
	}
	output, err := os.OpenFile(temporary, flags, 0o600)
	if err != nil {
		return 0, err
	}
	remaining := artifact.Size - offset
	written, copyErr := io.Copy(io.MultiWriter(output, hash), io.LimitReader(reader, remaining+1))
	syncErr := output.Sync()
	closeErr := output.Close()
	if copyErr != nil || syncErr != nil || closeErr != nil || written != remaining {
		if !isAvailabilityError(copyErr) && copyErr == nil && written != remaining {
			copyErr = unavailable(fmt.Errorf("download ended after %d of %d remaining bytes", written, remaining))
		}
		if !isAvailabilityError(copyErr) {
			_ = os.Remove(temporary)
		}
		if copyErr != nil {
			return written, copyErr
		}
		if syncErr != nil {
			return written, syncErr
		}
		if closeErr != nil {
			return written, closeErr
		}
		return written, fmt.Errorf("downloaded artifact has %d bytes; expected %d", offset+written, artifact.Size)
	}
	expected, _ := normalizeSHA256(artifact.SHA256)
	actual := hex.EncodeToString(hash.Sum(nil))
	if actual != expected {
		_ = os.Remove(temporary)
		return written, fmt.Errorf("downloaded artifact SHA-256 is %s; expected %s", actual, expected)
	}
	if err := replaceFile(temporary, destination); err != nil {
		_ = os.Remove(temporary)
		return written, err
	}
	return written, nil
}

type activityReader struct {
	reader   io.Reader
	activity func()
}

func (reader activityReader) Read(buffer []byte) (int, error) {
	count, err := reader.reader.Read(buffer)
	if count > 0 && reader.activity != nil {
		reader.activity()
	}
	return count, err
}

func validPartialSize(path string, maximum int64) int64 {
	info, err := os.Stat(path)
	if err != nil || !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() >= maximum {
		if err == nil && (info.Size() <= 0 || info.Size() > maximum) {
			_ = os.Remove(path)
		}
		return 0
	}
	return info.Size()
}

func fileURLPath(parsed *url.URL) (string, error) {
	path, err := url.PathUnescape(parsed.Path)
	if err != nil {
		return "", err
	}
	if parsed.Host != "" {
		path = "//" + parsed.Host + path
	}
	if len(path) >= 3 && path[0] == '/' && path[2] == ':' {
		path = path[1:]
	}
	return filepath.FromSlash(path), nil
}

func sha256Bytes(payload []byte) string {
	hash := sha256.Sum256(payload)
	return hex.EncodeToString(hash[:])
}

func isLoopbackHost(host string) bool {
	host = strings.ToLower(strings.TrimSpace(host))
	return host == "localhost" || host == "127.0.0.1" || host == "::1"
}
