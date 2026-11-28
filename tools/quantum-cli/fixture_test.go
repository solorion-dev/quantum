package main

import "testing"

func TestFixtureStatusLoads(t *testing.T) {
	rows, err := fixtureSource{}.Status()
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) == 0 {
		t.Fatal("status fixture is empty")
	}
	for _, r := range rows {
		if r.ID == "" || r.Status == "" {
			t.Fatalf("status row missing id/status: %+v", r)
		}
	}
}

func TestFixtureTrackerGet44(t *testing.T) {
	it, err := fixtureSource{}.TrackerGet("TRK-0044")
	if err != nil {
		t.Fatal(err)
	}
	if it.Title != "Quantum CLI prototype" || it.Kind != "goal" {
		t.Fatalf("unexpected TRK-0044 record: %+v", it)
	}
	if _, err := (fixtureSource{}).TrackerGet("TRK-9999"); err == nil {
		t.Fatal("expected an error for a record outside the snapshot")
	}
}

func TestFixtureMemorySearch(t *testing.T) {
	hits, err := fixtureSource{}.MemorySearch("rules")
	if err != nil {
		t.Fatal(err)
	}
	if len(hits) == 0 {
		t.Fatal("expected rules matches in the fixture snapshot")
	}
	found := false
	for _, h := range hits {
		if h.ID == 2298 {
			found = true
		}
	}
	if !found {
		t.Fatal("expected Hive 2298 (rules index) among matches")
	}
}

func TestBarThresholds(t *testing.T) {
	if got := len([]rune(bar(100, 24))); got != 24 {
		t.Fatalf("bar width = %d, want 24", got)
	}
	if got := len([]rune(bar(0, 24))); got != 24 {
		t.Fatalf("empty bar width = %d, want 24", got)
	}
}
