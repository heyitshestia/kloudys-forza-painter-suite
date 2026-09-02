package bootstrap

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
)

func TestDownloaderRejectsUntrustedSchemesAndLocalFiles(t *testing.T) {
	state := t.TempDir()
	downloader := NewDownloader(testLogger(t, state, "source-policy"), false)
	for _, location := range []string{"http://example.invalid/update.json", "file:///C:/tmp/update.json", "ftp://example.invalid/update.json"} {
		if _, err := downloader.Read(context.Background(), location, 1024); err == nil {
			t.Fatalf("untrusted update source accepted: %s", location)
		}
	}
}

func TestDownloaderAllowsOnlySecureRedirects(t *testing.T) {
	downloader := NewDownloader(testLogger(t, t.TempDir(), "redirect-policy"), false)
	insecure, _ := url.Parse("http://example.invalid/update")
	if err := downloader.Client.CheckRedirect(&http.Request{URL: insecure}, nil); err == nil || !strings.Contains(err.Error(), "refusing redirect") {
		t.Fatalf("insecure redirect was accepted: %v", err)
	}
	secure, _ := url.Parse("https://example.invalid/update")
	if err := downloader.Client.CheckRedirect(&http.Request{URL: secure}, nil); err != nil {
		t.Fatalf("secure redirect was rejected: %v", err)
	}
}

func TestDownloaderRetriesTransientArtifactFailure(t *testing.T) {
	payload := []byte("verified artifact")
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if requests.Add(1) < 3 {
			http.Error(writer, "temporary", http.StatusServiceUnavailable)
			return
		}
		writer.Header().Set("Content-Length", fmt.Sprint(len(payload)))
		_, _ = writer.Write(payload)
	}))
	defer server.Close()
	destination := filepath.Join(t.TempDir(), "artifact.bin")
	downloader := NewDownloader(testLogger(t, t.TempDir(), "retry"), true)
	if err := downloader.DownloadArtifact(context.Background(), Artifact{URL: server.URL, Size: int64(len(payload)), SHA256: sha256Bytes(payload)}, destination); err != nil {
		t.Fatal(err)
	}
	if requests.Load() != 3 {
		t.Fatalf("expected three attempts, got %d", requests.Load())
	}
	assertFileContent(t, destination, string(payload))
}

func TestDownloaderRemovesPartialFileAfterHashFailure(t *testing.T) {
	source := filepath.Join(t.TempDir(), "source.bin")
	writeTestFile(t, source, "tampered")
	destination := filepath.Join(t.TempDir(), "artifact.bin")
	downloader := NewDownloader(testLogger(t, t.TempDir(), "bad-hash"), true)
	location := (&url.URL{Scheme: "file", Path: "/" + filepath.ToSlash(source)}).String()
	err := downloader.DownloadArtifact(context.Background(), Artifact{URL: location, Size: int64(len("tampered")), SHA256: strings.Repeat("0", 64)}, destination)
	if err == nil || !strings.Contains(err.Error(), "SHA-256") {
		t.Fatalf("bad artifact hash was not rejected: %v", err)
	}
	for _, path := range []string{destination, destination + ".partial"} {
		if _, statErr := os.Stat(path); !os.IsNotExist(statErr) {
			t.Fatalf("failed artifact left a file behind: %s", path)
		}
	}
}

func TestDownloaderResumesInterruptedArtifact(t *testing.T) {
	payload := []byte(strings.Repeat("resume-this-artifact-", 4096))
	cut := int64(len(payload) / 3)
	var requests atomic.Int32
	var rangesMu sync.Mutex
	var ranges []string
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		rangesMu.Lock()
		ranges = append(ranges, request.Header.Get("Range"))
		rangesMu.Unlock()
		if requests.Add(1) == 1 {
			writer.Header().Set("Content-Length", fmt.Sprint(len(payload)))
			writer.WriteHeader(http.StatusOK)
			_, _ = writer.Write(payload[:cut])
			return
		}
		writer.Header().Set("Content-Length", fmt.Sprint(int64(len(payload))-cut))
		writer.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", cut, len(payload)-1, len(payload)))
		writer.WriteHeader(http.StatusPartialContent)
		_, _ = writer.Write(payload[cut:])
	}))
	defer server.Close()
	destination := filepath.Join(t.TempDir(), "artifact.bin")
	downloader := NewDownloader(testLogger(t, t.TempDir(), "resume"), true)
	artifact := Artifact{URL: server.URL, Size: int64(len(payload)), SHA256: sha256Bytes(payload)}
	if err := downloader.DownloadArtifact(context.Background(), artifact, destination); err != nil {
		t.Fatal(err)
	}
	actual, err := os.ReadFile(destination)
	if err != nil || string(actual) != string(payload) {
		t.Fatalf("resumed artifact differs: bytes=%d err=%v", len(actual), err)
	}
	rangesMu.Lock()
	defer rangesMu.Unlock()
	if len(ranges) < 2 || ranges[1] != fmt.Sprintf("bytes=%d-", cut) {
		t.Fatalf("download did not resume at %d: %#v", cut, ranges)
	}
}

func TestDownloaderRejectsMismatchedContentRange(t *testing.T) {
	payload := []byte("0123456789")
	destination := filepath.Join(t.TempDir(), "artifact.bin")
	if err := os.WriteFile(destination+".partial", payload[:4], 0o600); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Length", "6")
		writer.Header().Set("Content-Range", "bytes 3-8/10")
		writer.WriteHeader(http.StatusPartialContent)
		_, _ = writer.Write(payload[4:])
	}))
	defer server.Close()
	downloader := NewDownloader(testLogger(t, t.TempDir(), "bad-range"), true)
	err := downloader.DownloadArtifact(context.Background(), Artifact{URL: server.URL, Size: 10, SHA256: sha256Bytes(payload)}, destination)
	if err == nil || !strings.Contains(err.Error(), "Content-Range") {
		t.Fatalf("mismatched range was not rejected: %v", err)
	}
	if _, statErr := os.Stat(destination); !os.IsNotExist(statErr) {
		t.Fatalf("mismatched range produced a destination file: %v", statErr)
	}
}
