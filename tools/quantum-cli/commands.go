package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

func emitJSON(v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	fmt.Println(string(b))
	return nil
}

func header(o options, src source, what string) {
	if !o.json {
		fmt.Printf("⚡ QUANTUM CLI — %s\n   source: %s\n\n", what, src.Mode())
	}
}

func cmdStatus(o options, src source) error {
	rows, err := src.Status()
	if err != nil {
		return err
	}
	names := map[string]string{}
	if svcs, err := src.Services(); err == nil {
		for _, s := range svcs {
			names[s.ID] = s.Name
		}
	}
	if o.json {
		return emitJSON(rows)
	}
	header(o, src, "Service Status")
	up, down := 0, 0
	for _, r := range rows {
		dot, label := "●", strings.ToUpper(r.Status)
		name := names[r.ID]
		if name == "" {
			name = r.ID
		}
		lat := "—"
		if r.LatencyMs != nil {
			lat = fmt.Sprintf("%dms", *r.LatencyMs)
		}
		fmt.Printf(" %-22s %s %-9s %-7s unit:%s\n", name, dot, label, lat, r.ActiveState)
		if r.Status == "up" {
			up++
		} else {
			down++
		}
	}
	fmt.Printf("\n %d up · %d not-up of %d\n", up, down, len(rows))
	return nil
}

func cmdServices(o options, src source) error {
	rows, err := src.Services()
	if err != nil {
		return err
	}
	if o.json {
		return emitJSON(rows)
	}
	header(o, src, "Services (registry)")
	for _, s := range rows {
		port := "—"
		if s.Port != nil {
			port = strconv.Itoa(*s.Port)
		}
		runtime := s.Unit
		if runtime == "" {
			runtime = "container:" + s.Container
		}
		fmt.Printf(" %-12s %-28s port:%-6s %-8s %s\n", s.ID, s.Name, port, s.Exposure, runtime)
	}
	fmt.Printf("\n %d services registered\n", len(rows))
	return nil
}

func bar(pct int, width int) string {
	filled := pct * width / 100
	if filled > width {
		filled = width
	}
	return strings.Repeat("█", filled) + strings.Repeat("░", width-filled)
}

func cmdDisks(o options, src source) error {
	rows, err := src.Storage()
	if err != nil {
		return err
	}
	sort.Slice(rows, func(i, j int) bool { return rows[i].Pct > rows[j].Pct })
	if o.json {
		return emitJSON(rows)
	}
	header(o, src, "Disk Usage")
	for _, r := range rows {
		verdict := "OK"
		switch {
		case r.Pct >= 95:
			verdict = "HARD STOP"
		case r.Pct >= 90:
			verdict = "URGENT"
		case r.Pct >= 85:
			verdict = "WARN"
		}
		fmt.Printf(" %-14s %s %3d%%  %.1fG used / %.1fG  %s\n",
			r.Mount, bar(r.Pct, 24), r.Pct, r.UsedGB, r.SizeGB, verdict)
	}
	fmt.Println("\n Thresholds: 85% warn · 90% urgent · 95% hard stop (no new data)")
	return nil
}

func cmdVitals(o options, src source) error {
	v, err := src.Vitals()
	if err != nil {
		return err
	}
	if o.json {
		return emitJSON(v)
	}
	header(o, src, "Vitals")
	cpu := "—"
	if v.CPUPct != nil {
		cpu = fmt.Sprintf("%.0f%%", *v.CPUPct)
	}
	fmt.Printf(" CPU %s · load %.2f / %.2f / %.2f (%d threads)\n", cpu, v.Load1, v.Load5, v.Load15, v.Nproc)
	fmt.Printf(" MEM %d%% — %.1fG / %.1fG · SWAP %d%% — %.1fG / %.1fG\n",
		v.MemPct, v.MemUsedGB, v.MemTotalGB, v.SwapPct, v.SwapUsedGB, v.SwapTotalGB)
	fmt.Printf(" Uptime %s\n", formatDuration(v.UptimeSec))
	for _, g := range v.GPUs {
		parts := []string{g.Name}
		if g.BusyPct != nil {
			parts = append(parts, fmt.Sprintf("busy %.0f%%", *g.BusyPct))
		}
		if g.TempC != nil {
			parts = append(parts, fmt.Sprintf("%.0f°C", *g.TempC))
		}
		if g.MemUsedMB != nil && g.MemTotalMB != nil {
			parts = append(parts, fmt.Sprintf("vram %.0f/%.0f MB", *g.MemUsedMB, *g.MemTotalMB))
		}
		fmt.Printf(" GPU %s\n", strings.Join(parts, " · "))
	}
	return nil
}

func formatDuration(sec int) string {
	d := sec / 86400
	h := (sec % 86400) / 3600
	m := (sec % 3600) / 60
	if d > 0 {
		return fmt.Sprintf("%dd %dh %dm", d, h, m)
	}
	if h > 0 {
		return fmt.Sprintf("%dh %dm", h, m)
	}
	return fmt.Sprintf("%dm", m)
}

func cmdLogs(o options, src source, args []string) error {
	if len(args) == 0 {
		return &exitError{code: 2, msg: "logs needs a service id — e.g. `quantum logs hub-api`"}
	}
	id := args[0]
	lines := 60
	for i := 1; i < len(args); i++ {
		if args[i] == "-n" && i+1 < len(args) {
			if n, err := strconv.Atoi(args[i+1]); err == nil {
				lines = n
			}
			i++
		}
	}
	res, err := src.Logs(id, lines)
	if err != nil {
		return err
	}
	if res.Error != "" {
		return &exitError{code: 2, msg: res.Error}
	}
	if o.json {
		return emitJSON(res)
	}
	header(o, src, "Logs — "+id)
	if res.Unit != nil {
		fmt.Printf(" unit: %s\n\n", *res.Unit)
	}
	if res.Note != "" {
		fmt.Println(" note:", res.Note)
	}
	for _, l := range res.Lines {
		fmt.Println(" ", l)
	}
	return nil
}

func cmdTracker(o options, src source, args []string) error {
	if len(args) == 0 {
		return &exitError{code: 2, msg: "tracker needs a subcommand: list | get <TRK-id> (add is gated in v0)"}
	}
	switch args[0] {
	case "add", "comment", "update":
		return gated("quantum tracker " + args[0])
	case "list":
		status := ""
		for i := 1; i < len(args); i++ {
			if args[i] == "--status" && i+1 < len(args) {
				status = args[i+1]
				i++
			}
		}
		rows, err := src.TrackerList(status)
		if err != nil {
			return err
		}
		if o.json {
			return emitJSON(rows)
		}
		header(o, src, "Tracker")
		for _, r := range rows {
			fmt.Printf(" %-9s %-12s %s\n", r.ID, r.Status, r.Title)
		}
		fmt.Printf("\n %d records (provider: fixture snapshot — live provider via the hub MCP facade is the next slice)\n", len(rows))
		return nil
	case "get":
		if len(args) < 2 {
			return &exitError{code: 2, msg: "tracker get needs an id — e.g. `quantum tracker get TRK-0044`"}
		}
		it, err := src.TrackerGet(args[1])
		if err != nil {
			return err
		}
		if o.json {
			return emitJSON(it)
		}
		header(o, src, "Tracker — "+it.ID)
		fmt.Printf(" Title:    %s\n Status:   %s\n", it.Title, it.Status)
		if it.Kind != "" {
			fmt.Printf(" Kind:     %s\n", it.Kind)
		}
		if it.Priority != "" {
			fmt.Printf(" Priority: %s\n", it.Priority)
		}
		if it.Assignee != "" {
			fmt.Printf(" Assignee: %s\n", it.Assignee)
		}
		if len(it.Tags) > 0 {
			fmt.Printf(" Tags:     %s\n", strings.Join(it.Tags, ", "))
		}
		if it.Body != "" {
			fmt.Printf(" Body:     %s\n", it.Body)
		}
		return nil
	default:
		return &exitError{code: 2, msg: fmt.Sprintf("unknown tracker subcommand %q", args[0])}
	}
}

func cmdMemory(o options, src source, args []string) error {
	if len(args) == 0 || args[0] != "search" {
		return &exitError{code: 2, msg: "usage: quantum memory search <query>"}
	}
	q := strings.Join(args[1:], " ")
	rows, err := src.MemorySearch(q)
	if err != nil {
		return err
	}
	if o.json {
		return emitJSON(rows)
	}
	header(o, src, "Memory search — "+strconv.Quote(q))
	if len(rows) == 0 {
		fmt.Println(" no matches in the fixture snapshot (Hive 2294–2298 bundled in v0)")
		return nil
	}
	for _, e := range rows {
		fmt.Printf(" #%d [%s] %s\n   %s\n   tags: %s\n", e.ID, e.Kind, e.Title, e.Summary, strings.Join(e.Tags, ", "))
	}
	fmt.Printf("\n %d match(es) (provider: fixture snapshot — live Hive provider is the next slice)\n", len(rows))
	return nil
}
