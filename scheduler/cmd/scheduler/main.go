package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os/signal"
	"syscall"
	"time"

	"saviorbill/scheduler/internal/config"
	"saviorbill/scheduler/internal/pg"
	"saviorbill/scheduler/internal/scheduler"
	"saviorbill/scheduler/internal/valkey"
)

func main() {
	cfg := config.Load()
	log.Printf("starting saviorbill scheduler (instance=%s)", cfg.InstanceID)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	store, err := pg.NewStore(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("postgres init failed: %v", err)
	}
	defer store.Close()

	bus, err := valkey.NewBus(
		cfg.ValkeyURL,
		cfg.BusSigningKey,
		cfg.ReadyStream,
		cfg.ReadyGroup,
		cfg.DLQStream,
		cfg.InstanceID,
	)
	if err != nil {
		log.Fatalf("valkey init failed: %v", err)
	}
	defer bus.Close()

	if err := bus.Ping(ctx); err != nil {
		log.Fatalf("valkey ping failed: %v", err)
	}

	runner := scheduler.NewRunner(cfg, store, bus)

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		pCtx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		if err := store.Ping(pCtx); err != nil {
			http.Error(w, "pg unhealthy", http.StatusServiceUnavailable)
			return
		}
		if err := bus.Ping(pCtx); err != nil {
			http.Error(w, "valkey unhealthy", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	srv := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}
	go func() {
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Printf("http server error: %v", err)
		}
	}()

	if err := runner.Run(ctx); err != nil && !errors.Is(err, context.Canceled) {
		log.Fatalf("scheduler exited with error: %v", err)
	}

	shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutCtx)
	log.Printf("scheduler stopped cleanly")
}
