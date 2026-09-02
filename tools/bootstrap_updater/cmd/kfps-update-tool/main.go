package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/heyitshestia/kloudys-forza-painter-suite/tools/bootstrap_updater/internal/bootstrap"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	var err error
	switch os.Args[1] {
	case "keygen":
		err = keygen(os.Args[2:])
	case "sign":
		err = sign(os.Args[2:])
	case "verify":
		err = verify(os.Args[2:])
	case "build":
		err = buildPayload(os.Args[2:])
	default:
		usage()
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "KFPS update publication tool")
	fmt.Fprintln(os.Stderr, "  keygen --private FILE --public FILE")
	fmt.Fprintln(os.Stderr, "  sign --private FILE --input FILE --output FILE [--overwrite]")
	fmt.Fprintln(os.Stderr, "  verify --public FILE --input FILE --signature FILE")
	fmt.Fprintln(os.Stderr, "  build --app-root DIR --python-root DIR --updater FILE --private FILE --public FILE --output DIR --base-url URL --sequence N")
}

func keygen(arguments []string) error {
	flags := flag.NewFlagSet("keygen", flag.ContinueOnError)
	privatePath := flags.String("private", "", "private key output")
	publicPath := flags.String("public", "", "public key output")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if *privatePath == "" || *publicPath == "" {
		return fmt.Errorf("--private and --public are required")
	}
	for _, path := range []string{*privatePath, *publicPath} {
		if _, err := os.Stat(path); err == nil || !os.IsNotExist(err) {
			return fmt.Errorf("refusing to overwrite %s", path)
		}
	}
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return err
	}
	if err := writeNew(*privatePath, []byte(bootstrap.EncodePrivateKey(privateKey)+"\n"), 0o600); err != nil {
		return err
	}
	if err := writeNew(*publicPath, []byte(bootstrap.EncodePublicKey(publicKey)+"\n"), 0o644); err != nil {
		_ = os.Remove(*privatePath)
		return err
	}
	fmt.Println("Key ID:", bootstrap.KeyID(publicKey))
	return nil
}

func sign(arguments []string) error {
	flags := flag.NewFlagSet("sign", flag.ContinueOnError)
	privatePath := flags.String("private", "", "private key")
	inputPath := flags.String("input", "", "payload")
	outputPath := flags.String("output", "", "detached signature output")
	overwrite := flags.Bool("overwrite", false, "replace an existing signature output")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	privatePayload, err := os.ReadFile(*privatePath)
	if err != nil {
		return err
	}
	privateKey, err := bootstrap.DecodePrivateKey(string(privatePayload))
	if err != nil {
		return err
	}
	payload, err := os.ReadFile(*inputPath)
	if err != nil {
		return err
	}
	signature, err := bootstrap.SignBytes(payload, privateKey)
	if err != nil {
		return err
	}
	if *overwrite {
		return writeReplacing(*outputPath, append(signature, '\n'), 0o644)
	}
	return writeNew(*outputPath, append(signature, '\n'), 0o644)
}

func verify(arguments []string) error {
	flags := flag.NewFlagSet("verify", flag.ContinueOnError)
	publicPath := flags.String("public", "", "public key")
	inputPath := flags.String("input", "", "payload")
	signaturePath := flags.String("signature", "", "detached signature")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	publicPayload, err := os.ReadFile(*publicPath)
	if err != nil {
		return err
	}
	publicKey, err := bootstrap.DecodePublicKey(string(publicPayload))
	if err != nil {
		return err
	}
	payload, err := os.ReadFile(*inputPath)
	if err != nil {
		return err
	}
	signature, err := os.ReadFile(*signaturePath)
	if err != nil {
		return err
	}
	if err := bootstrap.VerifyBytes(payload, signature, publicKey); err != nil {
		return err
	}
	fmt.Println("Signature verified with key", bootstrap.KeyID(publicKey))
	return nil
}

func writeNew(path string, payload []byte, mode os.FileMode) error {
	if path == "" {
		return fmt.Errorf("output path is required")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, mode)
	if err != nil {
		return err
	}
	if _, err := file.Write(payload); err != nil {
		file.Close()
		_ = os.Remove(path)
		return err
	}
	if err := file.Sync(); err != nil {
		file.Close()
		_ = os.Remove(path)
		return err
	}
	return file.Close()
}

func writeReplacing(path string, payload []byte, mode os.FileMode) error {
	if path == "" {
		return fmt.Errorf("output path is required")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), "."+filepath.Base(path)+".sign-*.tmp")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if err := temporary.Chmod(mode); err != nil {
		temporary.Close()
		return err
	}
	if _, err := temporary.Write(payload); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	return bootstrap.ReplaceFileAtomically(temporaryPath, path)
}
