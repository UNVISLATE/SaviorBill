package heap

import (
	"testing"
	"time"
)

func TestTimerHeapOrderingAndVersionDeduplication(t *testing.T) {
	h := New()
	now := time.Now().UTC()

	h.Upsert(10, now.Add(20*time.Second), 1)
	h.Upsert(20, now.Add(5*time.Second), 1)
	// Перенос задачи 10 на более раннее время с version=2
	h.Upsert(10, now.Add(2*time.Second), 2)
	// Устаревшая версия (version=1) не должна откатывать таймер
	h.Upsert(10, now.Add(60*time.Second), 1)

	if h.Len() != 2 {
		t.Fatalf("expected len 2, got %d", h.Len())
	}

	due := h.PopDue(now.Add(10*time.Second), 10)
	if len(due) != 2 {
		t.Fatalf("expected 2 due entries, got %d", len(due))
	}
	if due[0].ID != 10 || due[1].ID != 20 {
		t.Fatalf("unexpected order: %+v", due)
	}
}
