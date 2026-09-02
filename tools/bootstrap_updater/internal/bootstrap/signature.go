package bootstrap

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
)

func DecodePublicKey(encoded string) (ed25519.PublicKey, error) {
	raw, err := base64.StdEncoding.DecodeString(strings.TrimSpace(encoded))
	if err != nil {
		return nil, fmt.Errorf("decode updater public key: %w", err)
	}
	if len(raw) != ed25519.PublicKeySize {
		return nil, fmt.Errorf("updater public key has %d bytes; expected %d", len(raw), ed25519.PublicKeySize)
	}
	return ed25519.PublicKey(raw), nil
}

func DecodePrivateKey(encoded string) (ed25519.PrivateKey, error) {
	raw, err := base64.StdEncoding.DecodeString(strings.TrimSpace(encoded))
	if err != nil {
		return nil, fmt.Errorf("decode updater private key: %w", err)
	}
	if len(raw) == ed25519.SeedSize {
		return ed25519.NewKeyFromSeed(raw), nil
	}
	if len(raw) != ed25519.PrivateKeySize {
		return nil, fmt.Errorf("updater private key has %d bytes; expected %d or %d", len(raw), ed25519.SeedSize, ed25519.PrivateKeySize)
	}
	return ed25519.PrivateKey(raw), nil
}

func EncodePublicKey(key ed25519.PublicKey) string {
	return base64.StdEncoding.EncodeToString(key)
}

func EncodePrivateKey(key ed25519.PrivateKey) string {
	return base64.StdEncoding.EncodeToString(key)
}

func KeyID(key ed25519.PublicKey) string {
	sum := sha256.Sum256(key)
	return hex.EncodeToString(sum[:8])
}

func SignBytes(payload []byte, key ed25519.PrivateKey) ([]byte, error) {
	pub, ok := key.Public().(ed25519.PublicKey)
	if !ok {
		return nil, fmt.Errorf("private key did not expose an Ed25519 public key")
	}
	record := DetachedSignature{
		Schema:    SignatureSchema,
		Algorithm: "ed25519",
		KeyID:     KeyID(pub),
		Signature: base64.StdEncoding.EncodeToString(ed25519.Sign(key, payload)),
	}
	return json.MarshalIndent(record, "", "  ")
}

func VerifyBytes(payload, signatureJSON []byte, key ed25519.PublicKey) error {
	var record DetachedSignature
	if err := decodeStrictJSON(signatureJSON, &record); err != nil {
		return fmt.Errorf("decode detached signature: %w", err)
	}
	if record.Schema != SignatureSchema || record.Algorithm != "ed25519" {
		return fmt.Errorf("unsupported detached signature contract")
	}
	if record.KeyID != KeyID(key) {
		return fmt.Errorf("signature key id %q does not match trusted key %q", record.KeyID, KeyID(key))
	}
	signature, err := base64.StdEncoding.DecodeString(record.Signature)
	if err != nil || len(signature) != ed25519.SignatureSize {
		return fmt.Errorf("detached signature is malformed")
	}
	if !ed25519.Verify(key, payload, signature) {
		return fmt.Errorf("detached signature verification failed")
	}
	return nil
}
