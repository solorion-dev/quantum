package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

// Data shapes — modelled field-for-field on hub-api (server.js):
// getStatus / checkOne / getUnitInfo, loadRegistry (services.json),
// getStorage, getVitals, getLogs.

type ServiceStatus struct {
	ID          string `json:"id"`
	Status      string `json:"status"` // up | down | degraded | unknown
	LatencyMs   *int   `json:"latencyMs"`
	Code        *int   `json:"code"`
	ActiveState string `json:"activeState"`
	SinceSec    *int   `json:"sinceSec"`
}

type Service struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	Cat       string `json:"cat"`
	Port      *int   `json:"port"`
	Exposure  string `json:"exposure"`
	URL       string `json:"url"`
	Unit      string `json:"unit"`
	Container string `json:"container"`
}

type StorageRow struct {
	Filesystem string  `json:"filesystem"`
	Mount      string  `json:"mount"`
	Fstype     string  `json:"fstype"`
	SizeGB     float64 `json:"sizeGB"`
	UsedGB     float64 `json:"usedGB"`
	AvailGB    float64 `json:"availGB"`
	Pct        int     `json:"pct"`
}

type GPU struct {
	Vendor     string   `json:"vendor"`
	Name       string   `json:"name"`
	TempC      *float64 `json:"tempC"`
	PowerW     *float64 `json:"powerW"`
	BusyPct    *float64 `json:"busyPct"`
	MemUsedMB  *float64 `json:"memUsedMB"`
	MemTotalMB *float64 `json:"memTotalMB"`
}

type Vitals struct {
	CPUPct      *float64 `json:"cpuPct"`
	Nproc       int      `json:"nproc"`
	Load1       float64  `json:"load1"`
	Load5       float64  `json:"load5"`
	Load15      float64  `json:"load15"`
	MemPct      int      `json:"memPct"`
	MemUsedGB   float64  `json:"memUsedGB"`
	MemTotalGB  float64  `json:"memTotalGB"`
	SwapPct     int      `json:"swapPct"`
	SwapUsedGB  float64  `json:"swapUsedGB"`
	SwapTotalGB float64  `json:"swapTotalGB"`
	UptimeSec   int      `json:"uptimeSec"`
	GPUs        []GPU    `json:"gpus"`
	RxKBs       *float64 `json:"rxKBs"`
	TxKBs       *float64 `json:"txKBs"`
}

type LogsResult struct {
	Unit  *string  `json:"unit"`
	Lines []string `json:"lines"`
	Note  string   `json:"note,omitempty"`
	Error string   `json:"error,omitempty"`
}

type TrackerItem struct {
	ID        string   `json:"id"`
	Title     string   `json:"title"`
	Status    string   `json:"status"`
	Kind      string   `json:"kind,omitempty"`
	Priority  string   `json:"priority,omitempty"`
	Assignee  string   `json:"assignee,omitempty"`
	Body      string   `json:"body,omitempty"`
	Tags      []string `json:"tags,omitempty"`
	CreatedAt string   `json:"created_at,omitempty"`
	UpdatedAt string   `json:"updated_at,omitempty"`
}

type MemoryEntry struct {
	ID      int      `json:"id"`
	Title   string   `json:"title"`
	Kind    string   `json:"kind"`
	Summary string   `json:"summary"`
	Tags    []string `json:"tags"`
}

// source abstracts where command data comes from: the live hub API, or the
// bundled fixtures. Tracker and memory have no hub HTTP route, so in v0 they
// are served by the fixture provider in both modes; their live provider (over
// the hub MCP facade) slots in behind this same interface.
type source interface {
	Status() ([]ServiceStatus, error)
	Services() ([]Service, error)
	Storage() ([]StorageRow, error)
	Vitals() (Vitals, error)
	Logs(id string, lines int) (LogsResult, error)
	TrackerList(status string) ([]TrackerItem, error)
	TrackerGet(id string) (TrackerItem, error)
	MemorySearch(q string) ([]MemoryEntry, error)
	Mode() string
}

func newSource(o options) source {
	if o.fixture {
		return fixtureSource{}
	}
	return liveSource{base: strings.TrimRight(o.hubURL, "/"), token: os.Getenv("QUANTUM_TOKEN")}
}

// ---- live hub client ----

type liveSource struct {
	base  string
	token string
}

func (l liveSource) Mode() string { return "live hub at " + l.base }

func (l liveSource) get(path string, out any) error {
	req, err := http.NewRequest(http.MethodGet, l.base+path, nil)
	if err != nil {
		return err
	}
	if l.token != "" {
		req.Header.Set("Authorization", "Bearer "+l.token)
	}
	client := &http.Client{Timeout: 10 * time.Second}
	res, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("hub unreachable at %s (%v) — the hub is tailnet-only; run on Tritium or a tailnet device, or use --fixture", l.base, err)
	}
	defer res.Body.Close()
	body, err := io.ReadAll(res.Body)
	if err != nil {
		return err
	}
	if res.StatusCode == 401 {
		return fmt.Errorf("hub answered 401 for %s — set QUANTUM_TOKEN (pointer: the caller's hub credential lives in the DSECT Vaultwarden / Secure Vault, never in this repo)", path)
	}
	if res.StatusCode != 200 {
		return fmt.Errorf("hub answered %d for %s: %s", res.StatusCode, path, strings.TrimSpace(string(body)))
	}
	return json.Unmarshal(body, out)
}

func (l liveSource) Status() ([]ServiceStatus, error) {
	var v []ServiceStatus
	return v, l.get("/api/status", &v)
}
func (l liveSource) Services() ([]Service, error) {
	var v []Service
	return v, l.get("/api/services", &v)
}
func (l liveSource) Storage() ([]StorageRow, error) {
	var v []StorageRow
	return v, l.get("/api/storage", &v)
}
func (l liveSource) Vitals() (Vitals, error) {
	var v Vitals
	return v, l.get("/api/vitals", &v)
}
func (l liveSource) Logs(id string, lines int) (LogsResult, error) {
	var v LogsResult
	return v, l.get(fmt.Sprintf("/api/logs?id=%s&lines=%d", id, lines), &v)
}

// Tracker/memory: no hub HTTP route in v0 — fixture provider (see PLAN.md).
func (l liveSource) TrackerList(s string) ([]TrackerItem, error) {
	return fixtureSource{}.TrackerList(s)
}
func (l liveSource) TrackerGet(id string) (TrackerItem, error) {
	return fixtureSource{}.TrackerGet(id)
}
func (l liveSource) MemorySearch(q string) ([]MemoryEntry, error) {
	return fixtureSource{}.MemorySearch(q)
}
