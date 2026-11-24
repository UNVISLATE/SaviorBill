package pg

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type HorizonItem struct {
	ID      int64
	RunAt   time.Time
	Version int32
}

type DispatchedTask struct {
	ID          int64
	DedupKey    *string
	TaskKind    string
	RefID       *int64
	Payload     []byte
	Version     int32
	Attempts    int32
	MaxAttempts int32
}

type DeadTask struct {
	ID          int64
	DedupKey    *string
	TaskKind    string
	RefID       *int64
	Attempts    int32
	MaxAttempts int32
}

type NotifyEvent struct {
	ID      int64   `json:"id"`
	RunAt   float64 `json:"run_at"`
	Version int32   `json:"version"`
}

type Store struct {
	pool        *pgxpool.Pool
	databaseURL string
}

func NewStore(ctx context.Context, databaseURL string) (*Store, error) {
	cfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse database url: %w", err)
	}
	cfg.MaxConns = 4
	cfg.MinConns = 1
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("connect postgres: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping postgres: %w", err)
	}
	return &Store{pool: pool, databaseURL: databaseURL}, nil
}

func (s *Store) Close() {
	s.pool.Close()
}

func (s *Store) Ping(ctx context.Context) error {
	return s.pool.Ping(ctx)
}

// AcquireLeader держит advisory-lock соединение для режима Active-Passive HA.
func (s *Store) AcquireLeader(ctx context.Context, lockKey string) (*pgxpool.Conn, error) {
	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return nil, err
	}
	var acquired bool
	err = conn.QueryRow(ctx, "SELECT pg_try_advisory_lock(hashtext($1))", lockKey).Scan(&acquired)
	if err != nil {
		conn.Release()
		return nil, err
	}
	if !acquired {
		conn.Release()
		return nil, nil
	}
	return conn, nil
}

func (s *Store) LoadHorizon(ctx context.Context, horizon time.Duration, limit int) ([]HorizonItem, error) {
	secs := int64(horizon.Seconds())
	rows, err := s.pool.Query(
		ctx,
		`SELECT id, run_at, version
		 FROM scheduled_tasks
		 WHERE status = 'pending' AND run_at <= now() + ($1 * interval '1 second')
		 ORDER BY run_at ASC
		 LIMIT $2`,
		secs,
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var items []HorizonItem
	for rows.Next() {
		var it HorizonItem
		if err := rows.Scan(&it.ID, &it.RunAt, &it.Version); err != nil {
			return nil, err
		}
		items = append(items, it)
	}
	return items, rows.Err()
}

func (s *Store) DispatchBatch(ctx context.Context, ids []int64) ([]DispatchedTask, error) {
	if len(ids) == 0 {
		return nil, nil
	}
	rows, err := s.pool.Query(
		ctx,
		`UPDATE scheduled_tasks
		 SET status = 'dispatched',
		     locked_until = now() + interval '5 minutes',
		     updated_at = now()
		 WHERE id = ANY($1) AND status = 'pending'
		 RETURNING id, dedup_key, task_kind, ref_id, payload, version, attempts, max_attempts`,
		ids,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []DispatchedTask
	for rows.Next() {
		var t DispatchedTask
		if err := rows.Scan(
			&t.ID, &t.DedupKey, &t.TaskKind, &t.RefID,
			&t.Payload, &t.Version, &t.Attempts, &t.MaxAttempts,
		); err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, rows.Err()
}

// ReconcileStale возвращает потерянные в Valkey задачи обратно в pending,
// либо переводит исчерпавшие попытки задачи в dead.
func (s *Store) ReconcileStale(ctx context.Context) (requeued int64, dead []DeadTask, err error) {
	tag, err := s.pool.Exec(
		ctx,
		`UPDATE scheduled_tasks
		 SET status = 'pending',
		     attempts = attempts + 1,
		     version = version + 1,
		     locked_until = NULL,
		     run_at = now() + (LEAST(300, 15 * power(2, LEAST(attempts, 5))) * interval '1 second'),
		     last_error = COALESCE(last_error, 'dispatch timeout / valkey recovery'),
		     updated_at = now()
		 WHERE status = 'dispatched'
		   AND locked_until IS NOT NULL
		   AND locked_until < now()
		   AND attempts + 1 < max_attempts`,
	)
	if err != nil {
		return 0, nil, err
	}
	requeued = tag.RowsAffected()

	rows, err := s.pool.Query(
		ctx,
		`UPDATE scheduled_tasks
		 SET status = 'dead',
		     attempts = attempts + 1,
		     version = version + 1,
		     locked_until = NULL,
		     last_error = COALESCE(last_error, 'dispatch timeout / max attempts exceeded'),
		     updated_at = now()
		 WHERE status = 'dispatched'
		   AND locked_until IS NOT NULL
		   AND locked_until < now()
		   AND attempts + 1 >= max_attempts
		 RETURNING id, dedup_key, task_kind, ref_id, attempts, max_attempts`,
	)
	if err != nil {
		return requeued, nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var d DeadTask
		if err := rows.Scan(&d.ID, &d.DedupKey, &d.TaskKind, &d.RefID, &d.Attempts, &d.MaxAttempts); err != nil {
			return requeued, dead, err
		}
		dead = append(dead, d)
	}
	return requeued, dead, rows.Err()
}

// ListenLoop подписывается на канал sb_sched_events и отправляет события в ch.
func (s *Store) ListenLoop(ctx context.Context, ch chan<- NotifyEvent) {
	for {
		if ctx.Err() != nil {
			return
		}
		if err := s.listenOnce(ctx, ch); err != nil && ctx.Err() == nil {
			log.Printf("pg listen error (reconnecting in 3s): %v", err)
			select {
			case <-ctx.Done():
				return
			case <-time.After(3 * time.Second):
			}
		}
	}
}

func (s *Store) listenOnce(ctx context.Context, ch chan<- NotifyEvent) error {
	conn, err := pgx.Connect(ctx, s.databaseURL)
	if err != nil {
		return err
	}
	defer conn.Close(context.Background())

	if _, err := conn.Exec(ctx, "LISTEN sb_sched_events"); err != nil {
		return err
	}
	log.Printf("pg listener subscribed to sb_sched_events")

	for {
		notif, err := conn.WaitForNotification(ctx)
		if err != nil {
			return err
		}
		var ev NotifyEvent
		if err := json.Unmarshal([]byte(notif.Payload), &ev); err != nil {
			log.Printf("invalid notify payload %q: %v", notif.Payload, err)
			continue
		}
		select {
		case ch <- ev:
		case <-ctx.Done():
			return ctx.Err()
		}
	}
}
