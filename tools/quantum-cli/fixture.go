package main

import (
	"embed"
	"encoding/json"
	"fmt"
	"strings"
)

// Fixtures are embedded so the binary stays a single drop-in artifact (the
// prototype's ethos). They are REAL snapshots/shapes pulled 2026-10-25:
// tracker rows are the live in_progress board, tracker-get is TRK-0044's
// full record, memory rows are Hive 2294–2298; hub payloads are modelled
// field-for-field on hub-api's handlers with values from the same night.
//
//go:embed fixtures/*.json
var fixtureFS embed.FS

type fixtureSource struct{}

func (fixtureSource) Mode() string { return "fixture (bundled snapshot, 2026-10-25)" }

func loadFixture(name string, out any) error {
	b, err := fixtureFS.ReadFile("fixtures/" + name)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, out)
}

func (f fixtureSource) Status() ([]ServiceStatus, error) {
	var v []ServiceStatus
	return v, loadFixture("status.json", &v)
}
func (f fixtureSource) Services() ([]Service, error) {
	var v []Service
	return v, loadFixture("services.json", &v)
}
func (f fixtureSource) Storage() ([]StorageRow, error) {
	var v []StorageRow
	return v, loadFixture("storage.json", &v)
}
func (f fixtureSource) Vitals() (Vitals, error) {
	var v Vitals
	return v, loadFixture("vitals.json", &v)
}
func (f fixtureSource) Logs(id string, lines int) (LogsResult, error) {
	var v LogsResult
	if err := loadFixture("logs.json", &v); err != nil {
		return v, err
	}
	// The fixture carries one service's tail (hub-api); answer honestly for others.
	if id != "" && id != "hub-api" {
		return LogsResult{Error: "no such service in fixture (only hub-api is bundled)"}, nil
	}
	if lines > 0 && lines < len(v.Lines) {
		v.Lines = v.Lines[len(v.Lines)-lines:]
	}
	return v, nil
}
func (f fixtureSource) TrackerList(status string) ([]TrackerItem, error) {
	var v []TrackerItem
	if err := loadFixture("tracker-list.json", &v); err != nil {
		return nil, err
	}
	if status == "" {
		return v, nil
	}
	out := v[:0]
	for _, it := range v {
		if it.Status == status {
			out = append(out, it)
		}
	}
	return out, nil
}
func (f fixtureSource) TrackerGet(id string) (TrackerItem, error) {
	id = strings.ToUpper(id)
	if id == "TRK-0044" {
		var v TrackerItem
		return v, loadFixture("tracker-get.json", &v)
	}
	list, err := f.TrackerList("")
	if err != nil {
		return TrackerItem{}, err
	}
	for _, it := range list {
		if it.ID == id {
			it.Body = "(fixture: summary row from the board snapshot — full record only bundled for TRK-0044)"
			return it, nil
		}
	}
	return TrackerItem{}, fmt.Errorf("tracker record %s not found in the fixture snapshot", id)
}
func (f fixtureSource) MemorySearch(q string) ([]MemoryEntry, error) {
	var v []MemoryEntry
	if err := loadFixture("memory.json", &v); err != nil {
		return nil, err
	}
	q = strings.ToLower(strings.TrimSpace(q))
	if q == "" {
		return v, nil
	}
	var out []MemoryEntry
	for _, e := range v {
		hay := strings.ToLower(e.Title + " " + e.Summary + " " + strings.Join(e.Tags, " "))
		if strings.Contains(hay, q) {
			out = append(out, e)
		}
	}
	return out, nil
}
