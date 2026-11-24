package config

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	DatabaseURL          string
	ValkeyURL            string
	BusSigningKey        string
	ReadyStream          string
	ReadyGroup           string
	DLQStream            string
	InstanceID           string
	HTTPAddr             string
	Horizon              time.Duration
	SweepInterval        time.Duration
	BatchSize            int
	MaxPending           int64
	CronMediaCleanup     time.Duration
	CronMediaSweep       time.Duration
	MetricsInterval      time.Duration
	MetricsTTL           time.Duration
	AdvisoryLockKey      string
}

func Load() Config {
	host, _ := os.Hostname()
	if host == "" {
		host = "scheduler"
	}

	return Config{
		DatabaseURL:      resolveDatabaseURL(),
		ValkeyURL:        resolveValkeyURL(),
		BusSigningKey:    os.Getenv("BUS_SIGNING_KEY"),
		ReadyStream:      envOr("BILLING_READY_STREAM", "billing:tasks:ready"),
		ReadyGroup:       envOr("BILLING_READY_GROUP", "billingexecutors"),
		DLQStream:        envOr("BILLING_QUEUE_DLQ", "billing:queue:dead"),
		InstanceID:       envOr("INSTANCE_ID", fmt.Sprintf("scheduler-%s-%d", host, os.Getpid())),
		HTTPAddr:         envOr("SCHEDULER_HTTP_ADDR", ":8090"),
		Horizon:          time.Duration(envInt("SCHEDULER_HORIZON_SEC", 3600)) * time.Second,
		SweepInterval:    time.Duration(envInt("SCHEDULER_SWEEP_INTERVAL_SEC", 300)) * time.Second,
		BatchSize:        envInt("SCHEDULER_BATCH_SIZE", 50),
		MaxPending:       int64(envInt("SCHEDULER_MAX_PENDING", 5000)),
		CronMediaCleanup: time.Duration(envInt("SCHEDULER_CRON_MEDIA_CLEANUP_SEC", 600)) * time.Second,
		CronMediaSweep:   time.Duration(envInt("SCHEDULER_CRON_MEDIA_SWEEP_SEC", 60)) * time.Second,
		MetricsInterval:  time.Duration(envInt("SELF_METRICS_INTERVAL_SEC", 10)) * time.Second,
		MetricsTTL:       time.Duration(envInt("SELF_METRICS_TTL_SEC", 30)) * time.Second,
		AdvisoryLockKey:  envOr("SCHEDULER_LOCK_KEY", "scheduler_leader"),
	}
}

func resolveDatabaseURL() string {
	if raw := strings.TrimSpace(os.Getenv("DATABASE_URL")); raw != "" {
		// SQLAlchemy использует postgresql+asyncpg:// — приводим к стандартному postgresql:// для pgx.
		return strings.Replace(raw, "postgresql+asyncpg://", "postgresql://", 1)
	}
	host := envOr("DB_HOST", "postgres")
	port := envOr("DB_PORT", "5432")
	user := url.QueryEscape(envOr("DB_USER", "saviorbill"))
	passRaw := os.Getenv("DB_PASSWORD")
	if passRaw == "" {
		passRaw = envOr("DB_PASS", "saviorbill")
	}
	pass := url.QueryEscape(passRaw)
	name := envOr("DB_NAME", "saviorbill")
	return fmt.Sprintf("postgresql://%s:%s@%s:%s/%s?sslmode=disable", user, pass, host, port, name)
}

func resolveValkeyURL() string {
	if raw := strings.TrimSpace(os.Getenv("VALKEY_URL")); raw != "" {
		return raw
	}
	host := envOr("VALKEY_HOST", "valkey")
	port := envOr("VALKEY_PORT", "6379")
	db := envOr("VALKEY_DB", "0")
	pass := os.Getenv("VALKEY_PASSWORD")
	if pass != "" {
		return fmt.Sprintf("redis://:%s@%s:%s/%s", url.QueryEscape(pass), host, port, db)
	}
	return fmt.Sprintf("redis://%s:%s/%s", host, port, db)
}

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func envInt(key string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return fallback
	}
	return n
}
