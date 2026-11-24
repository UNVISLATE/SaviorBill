package valkey

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

type Bus struct {
	client     *redis.Client
	signingKey string
	stream     string
	group      string
	dlqStream  string
	instanceID string
	sampler    *procSampler
}

func NewBus(valkeyURL, signingKey, stream, group, dlqStream, instanceID string) (*Bus, error) {
	opts, err := redis.ParseURL(valkeyURL)
	if err != nil {
		return nil, fmt.Errorf("parse valkey url: %w", err)
	}
	client := redis.NewClient(opts)
	return &Bus{
		client:     client,
		signingKey: signingKey,
		stream:     stream,
		group:      group,
		dlqStream:  dlqStream,
		instanceID: instanceID,
		sampler:    newProcSampler(),
	}, nil
}

func (b *Bus) Close() error {
	return b.client.Close()
}

func (b *Bus) Ping(ctx context.Context) error {
	return b.client.Ping(ctx).Err()
}

// SignFields подписывает поля по контракту src/security/sec/bus_sign.py.
func SignFields(key string, fields map[string]string, now time.Time) map[string]string {
	out := make(map[string]string, len(fields)+2)
	for k, v := range fields {
		out[k] = v
	}
	if key == "" {
		return out
	}
	out["ts"] = strconv.FormatInt(now.Unix(), 10)

	keys := make([]string, 0, len(out))
	for k := range out {
		if k != "sig" {
			keys = append(keys, k)
		}
	}
	sort.Strings(keys)

	parts := make([]string, 0, len(keys))
	for _, k := range keys {
		parts = append(parts, k+"="+out[k])
	}
	canonical := strings.Join(parts, "\x1f")

	mac := hmac.New(sha256.New, []byte(key))
	mac.Write([]byte(canonical))
	out["sig"] = hex.EncodeToString(mac.Sum(nil))
	return out
}

func (b *Bus) PendingBacklog(ctx context.Context) (int64, error) {
	xlen, err := b.client.XLen(ctx, b.stream).Result()
	if err != nil {
		return 0, err
	}
	pending, err := b.client.XPending(ctx, b.stream, b.group).Result()
	if err != nil {
		// Группа может быть ещё не создана до старта billing — возвращаем XLEN.
		return xlen, nil
	}
	if pending != nil && pending.Count > xlen {
		return pending.Count, nil
	}
	return xlen, nil
}

func (b *Bus) PublishReady(ctx context.Context, fields map[string]string) error {
	signed := SignFields(b.signingKey, fields, time.Now().UTC())
	args := &redis.XAddArgs{
		Stream: b.stream,
		MaxLen: 10000,
		Approx: true,
		Values: signed,
	}
	return b.client.XAdd(ctx, args).Err()
}

func (b *Bus) PublishDLQ(ctx context.Context, fields map[string]string) error {
	args := &redis.XAddArgs{
		Stream: b.dlqStream,
		MaxLen: 1000,
		Approx: true,
		Values: fields,
	}
	return b.client.XAdd(ctx, args).Err()
}

func (b *Bus) PushHeartbeat(ctx context.Context, ttl time.Duration, extra map[string]any) error {
	key := "scheduler:metrics:" + b.instanceID
	startedAt, rssMB, cpuPct := b.sampler.sample()
	fields := map[string]any{
		"instance_id":  b.instanceID,
		"service":      "scheduler",
		"started_at":   strconv.FormatInt(startedAt, 10),
		"last_seen_at": strconv.FormatInt(time.Now().UTC().Unix(), 10),
		"rss_mb":       fmtFloat(rssMB),
		"cpu_percent":  fmtFloat(cpuPct),
	}
	for k, v := range extra {
		fields[k] = v
	}
	pipe := b.client.Pipeline()
	pipe.HSet(ctx, key, fields)
	pipe.Expire(ctx, key, ttl)
	_, err := pipe.Exec(ctx)
	return err
}
