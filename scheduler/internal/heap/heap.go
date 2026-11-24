package heap

import (
	"container/heap"
	"sync"
	"time"
)

type Entry struct {
	ID      int64
	RunAt   time.Time
	Version int32
	index   int
}

type minHeap []*Entry

func (h minHeap) Len() int { return len(h) }

func (h minHeap) Less(i, j int) bool {
	if h[i].RunAt.Equal(h[j].RunAt) {
		return h[i].ID < h[j].ID
	}
	return h[i].RunAt.Before(h[j].RunAt)
}

func (h minHeap) Swap(i, j int) {
	h[i], h[j] = h[j], h[i]
	h[i].index = i
	h[j].index = j
}

func (h *minHeap) Push(x any) {
	e := x.(*Entry)
	e.index = len(*h)
	*h = append(*h, e)
}

func (h *minHeap) Pop() any {
	old := *h
	n := len(old)
	e := old[n-1]
	old[n-1] = nil
	e.index = -1
	*h = old[:n-1]
	return e
}

// TimerHeap — потокобезопасная min-heap с O(1) дедупликацией по task ID.
type TimerHeap struct {
	mu   sync.Mutex
	h    minHeap
	byID map[int64]*Entry
}

func New() *TimerHeap {
	th := &TimerHeap{
		byID: make(map[int64]*Entry),
	}
	heap.Init(&th.h)
	return th
}

func (th *TimerHeap) Len() int {
	th.mu.Lock()
	defer th.mu.Unlock()
	return len(th.h)
}

// Upsert добавляет или обновляет таймер, игнорируя устаревшие версии.
func (th *TimerHeap) Upsert(id int64, runAt time.Time, version int32) {
	th.mu.Lock()
	defer th.mu.Unlock()

	if existing, ok := th.byID[id]; ok {
		if version < existing.Version {
			return
		}
		existing.RunAt = runAt
		existing.Version = version
		heap.Fix(&th.h, existing.index)
		return
	}

	e := &Entry{
		ID:      id,
		RunAt:   runAt,
		Version: version,
	}
	th.byID[id] = e
	heap.Push(&th.h, e)
}

func (th *TimerHeap) Remove(id int64) {
	th.mu.Lock()
	defer th.mu.Unlock()
	if existing, ok := th.byID[id]; ok {
		heap.Remove(&th.h, existing.index)
		delete(th.byID, id)
	}
}

func (th *TimerHeap) Peek() (Entry, bool) {
	th.mu.Lock()
	defer th.mu.Unlock()
	if len(th.h) == 0 {
		return Entry{}, false
	}
	e := th.h[0]
	return *e, true
}

// PopDue извлекает до limit созревших элементов (RunAt <= now).
func (th *TimerHeap) PopDue(now time.Time, limit int) []Entry {
	th.mu.Lock()
	defer th.mu.Unlock()

	out := make([]Entry, 0, limit)
	for len(th.h) > 0 && len(out) < limit {
		top := th.h[0]
		if top.RunAt.After(now) {
			break
		}
		popped := heap.Pop(&th.h).(*Entry)
		delete(th.byID, popped.ID)
		out = append(out, *popped)
	}
	return out
}
