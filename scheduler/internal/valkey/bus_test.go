package valkey

import (
	"testing"
	"time"
)

func TestSignFieldsMatchesPythonContract(t *testing.T) {
	now := time.Unix(1700000000, 0).UTC()
	signed := SignFields("secret-key", map[string]string{
		"task_id":   "42",
		"task_kind": "svc_expire",
	}, now)

	if signed["ts"] != "1700000000" {
		t.Fatalf("unexpected ts: %s", signed["ts"])
	}
	if len(signed["sig"]) != 64 {
		t.Fatalf("expected 64-char sha256 hex sig, got %q", signed["sig"])
	}

	// Без ключа подпись отключена
	unsigned := SignFields("", map[string]string{"task_id": "1"}, now)
	if _, ok := unsigned["sig"]; ok {
		t.Fatalf("did not expect sig when key is empty")
	}
}
