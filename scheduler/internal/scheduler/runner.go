package scheduler

import (
	"context"
	"log"
	"strconv"
	"sync/atomic"
	"time"

	"saviorbill/scheduler/internal/config"
	"saviorbill/scheduler/internal/heap"
	"saviorbill/scheduler/internal/pg"
	"saviorbill/scheduler/internal/valkey"
)

type Runner struct {
	cfg        config.Config
	store      *pg.Store
	bus        *valkey.Bus
	heap       *heap.TimerHeap
	dispatched atomic.Int64
	ready      atomic.Bool
}

func NewRunner(cfg config.Config, store *pg.Store, bus *valkey.Bus) *Runner {
	return &Runner{
		cfg:   cfg,
		store: store,
		bus:   bus,
		heap:  heap.New(),
	}
}

func (r *Runner) IsReady() bool {
	return r.ready.Load()
}

func (r *Runner) Run(ctx context.Context) error {
	// Захват лидерства для Active-Passive HA.
	leaderConn, err := r.waitLeadership(ctx)
	if err != nil {
		return err
	}
	defer leaderConn.Release()

	r.ready.Store(true)
	defer r.ready.Store(false)

	notifyCh := make(chan pg.NotifyEvent, 1024)
	go r.store.ListenLoop(ctx, notifyCh)

	// Начальная загрузка горизонта.
	r.sweep(ctx)

	sweepTicker := time.NewTicker(r.cfg.SweepInterval)
	defer sweepTicker.Stop()

	cronCleanupTicker := time.NewTicker(r.cfg.CronMediaCleanup)
	defer cronCleanupTicker.Stop()

	cronSweepTicker := time.NewTicker(r.cfg.CronMediaSweep)
	defer cronSweepTicker.Stop()

	metricsTicker := time.NewTicker(r.cfg.MetricsInterval)
	defer metricsTicker.Stop()

	timer := time.NewTimer(time.Hour)
	timer.Stop()
	defer timer.Stop()

	resetTimer := func() {
		if !timer.Stop() {
			select {
			case <-timer.C:
			default:
			}
		}
		next, ok := r.heap.Peek()
		if !ok {
			return
		}
		wait := time.Until(next.RunAt)
		if wait < 0 {
			wait = 0
		}
		timer.Reset(wait)
	}

	resetTimer()
	r.pushHeartbeat(ctx)

	for {
		select {
		case <-ctx.Done():
			return nil

		case ev := <-notifyCh:
			sec := int64(ev.RunAt)
			nsec := int64((ev.RunAt - float64(sec)) * 1e9)
			runAt := time.Unix(sec, nsec).UTC()
			r.heap.Upsert(ev.ID, runAt, ev.Version)
			resetTimer()

		case <-timer.C:
			r.dispatchDue(ctx)
			resetTimer()

		case <-sweepTicker.C:
			r.sweep(ctx)
			resetTimer()

		case <-cronCleanupTicker.C:
			r.publishCron(ctx, "cron_media_cleanup")

		case <-cronSweepTicker.C:
			r.publishCron(ctx, "cron_media_sweep")

		case <-metricsTicker.C:
			r.pushHeartbeat(ctx)
		}
	}
}

func (r *Runner) waitLeadership(ctx context.Context) (interface{ Release() }, error) {
	for {
		conn, err := r.store.AcquireLeader(ctx, r.cfg.AdvisoryLockKey)
		if err != nil {
			log.Printf("leader lock check error: %v", err)
		} else if conn != nil {
			log.Printf("acquired advisory leader lock (%s)", r.cfg.AdvisoryLockKey)
			return conn, nil
		}
		log.Printf("standing by: another scheduler instance holds leader lock")
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(5 * time.Second):
		}
	}
}

func (r *Runner) sweep(ctx context.Context) {
	requeued, dead, err := r.store.ReconcileStale(ctx)
	if err != nil {
		log.Printf("reconcile stale error: %v", err)
	} else {
		if requeued > 0 {
			log.Printf("requeued %d stale dispatched tasks", requeued)
		}
		for _, d := range dead {
			dedup := ""
			if d.DedupKey != nil {
				dedup = *d.DedupKey
			}
			ref := ""
			if d.RefID != nil {
				ref = strconv.FormatInt(*d.RefID, 10)
			}
			_ = r.bus.PublishDLQ(ctx, map[string]string{
				"task_id":   strconv.FormatInt(d.ID, 10),
				"dedup_key": dedup,
				"task_kind": d.TaskKind,
				"ref_id":    ref,
				"member":    dedup,
				"attempts":  strconv.FormatInt(int64(d.Attempts), 10),
				"error":     "dispatch timeout / max attempts exceeded",
				"at":        time.Now().UTC().Format(time.RFC3339),
			})
		}
	}

	items, err := r.store.LoadHorizon(ctx, r.cfg.Horizon, 10000)
	if err != nil {
		log.Printf("load horizon error: %v", err)
		return
	}
	for _, it := range items {
		r.heap.Upsert(it.ID, it.RunAt.UTC(), it.Version)
	}
}

func (r *Runner) dispatchDue(ctx context.Context) {
	backlog, err := r.bus.PendingBacklog(ctx)
	if err == nil && backlog >= r.cfg.MaxPending {
		log.Printf("backpressure active: stream backlog=%d >= %d", backlog, r.cfg.MaxPending)
		return
	}

	due := r.heap.PopDue(time.Now().UTC(), r.cfg.BatchSize)
	if len(due) == 0 {
		return
	}

	ids := make([]int64, len(due))
	for i, e := range due {
		ids[i] = e.ID
	}

	tasks, err := r.store.DispatchBatch(ctx, ids)
	if err != nil {
		log.Printf("dispatch batch error: %v", err)
		// Возвращаем в heap с короткой отсрочкой на случай кратковременного сбоя БД.
		retryAt := time.Now().UTC().Add(5 * time.Second)
		for _, e := range due {
			r.heap.Upsert(e.ID, retryAt, e.Version)
		}
		return
	}

	for _, t := range tasks {
		ref := ""
		if t.RefID != nil {
			ref = strconv.FormatInt(*t.RefID, 10)
		}
		fields := map[string]string{
			"task_id":   strconv.FormatInt(t.ID, 10),
			"task_kind": t.TaskKind,
			"ref_id":    ref,
			"version":   strconv.FormatInt(int64(t.Version), 10),
		}
		if err := r.bus.PublishReady(ctx, fields); err != nil {
			log.Printf("valkey xadd error for task=%d: %v", t.ID, err)
			continue
		}
		r.dispatched.Add(1)
	}
}

func (r *Runner) publishCron(ctx context.Context, kind string) {
	if err := r.bus.PublishReady(ctx, map[string]string{"task_kind": kind}); err != nil {
		log.Printf("publish cron %s error: %v", kind, err)
	}
}

func (r *Runner) pushHeartbeat(ctx context.Context) {
	err := r.bus.PushHeartbeat(ctx, r.cfg.MetricsTTL, map[string]any{
		"heap_size":        r.heap.Len(),
		"dispatched_total": r.dispatched.Load(),
	})
	if err != nil {
		log.Printf("heartbeat push error: %v", err)
	}
}
