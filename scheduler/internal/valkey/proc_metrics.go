package valkey

import (
	"fmt"
	"os"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"
)

type procSampler struct {
	mu         sync.Mutex
	startedAt  int64
	lastWall   time.Time
	lastCPU    float64
	hasLastCPU bool
}

func newProcSampler() *procSampler {
	return &procSampler{
		startedAt: time.Now().UTC().Unix(),
		lastWall:  time.Now(),
	}
}

func (p *procSampler) sample() (startedAt int64, rssMB float64, cpuPct float64) {
	p.mu.Lock()
	defer p.mu.Unlock()

	startedAt = p.startedAt
	rssMB = readRSSMB()
	cpuPct = p.readCPUPercent()
	return startedAt, rssMB, cpuPct
}

func readRSSMB() float64 {
	// В Linux контейнерах читаем реальный RSS из /proc/self/statm (второе поле — страницы).
	if raw, err := os.ReadFile("/proc/self/statm"); err == nil {
		fields := strings.Fields(string(raw))
		if len(fields) >= 2 {
			if pages, err := strconv.ParseInt(fields[1], 10, 64); err == nil {
				bytes := float64(pages * int64(os.Getpagesize()))
				return float64(int64((bytes/(1024*1024))*100)) / 100
			}
		}
	}
	var ms runtime.MemStats
	runtime.ReadMemStats(&ms)
	return float64(int64((float64(ms.Sys)/(1024*1024))*100)) / 100
}

func (p *procSampler) readCPUPercent() float64 {
	raw, err := os.ReadFile("/proc/self/stat")
	if err != nil {
		return 0.0
	}
	// После закрывающей ')' поля начинаются с 3-го; utime=14, stime=15 (индексы 11 и 12 после ')').
	idx := strings.LastIndexByte(string(raw), ')')
	if idx < 0 || idx+2 >= len(raw) {
		return 0.0
	}
	fields := strings.Fields(string(raw[idx+2:]))
	if len(fields) <= 12 {
		return 0.0
	}
	utime, err1 := strconv.ParseFloat(fields[11], 64)
	stime, err2 := strconv.ParseFloat(fields[12], 64)
	if err1 != nil || err2 != nil {
		return 0.0
	}
	// Стандартный USER_HZ в Linux = 100 тиков/сек.
	totalSec := (utime + stime) / 100.0
	now := time.Now()
	if !p.hasLastCPU {
		p.lastCPU = totalSec
		p.lastWall = now
		p.hasLastCPU = true
		return 0.0
	}
	dt := now.Sub(p.lastWall).Seconds()
	dCPU := totalSec - p.lastCPU
	p.lastCPU = totalSec
	p.lastWall = now
	if dt <= 0 || dCPU < 0 {
		return 0.0
	}
	pct := (dCPU / dt) * 100.0
	return float64(int64(pct*100)) / 100
}

func fmtFloat(v float64) string {
	return fmt.Sprintf("%.2f", v)
}
