package bootstrap

import (
	"crypto/ed25519"
	"crypto/rand"
	"testing"
)

func TestDetachedSignatureRejectsTampering(t *testing.T) {
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	payload := []byte("signed update contract")
	signature, err := SignBytes(payload, privateKey)
	if err != nil {
		t.Fatal(err)
	}
	if err := VerifyBytes(payload, signature, publicKey); err != nil {
		t.Fatalf("valid signature rejected: %v", err)
	}
	if err := VerifyBytes([]byte("changed update contract"), signature, publicKey); err == nil {
		t.Fatal("tampered payload was accepted")
	}
}

func TestDetachedSignatureRejectsAnotherKey(t *testing.T) {
	_, privateKey, _ := ed25519.GenerateKey(rand.Reader)
	otherPublic, _, _ := ed25519.GenerateKey(rand.Reader)
	signature, err := SignBytes([]byte("payload"), privateKey)
	if err != nil {
		t.Fatal(err)
	}
	if err := VerifyBytes([]byte("payload"), signature, otherPublic); err == nil {
		t.Fatal("signature from another key was accepted")
	}
}
