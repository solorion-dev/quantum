// Command quantum is the official Quantum CLI — the fleet's scriptable,
// read-only command surface over Quantum services (TRK-0044).
//
// v0 implements the read-only command set against the real hub API shapes:
//
//	quantum status            service health (GET /api/status)
//	quantum services          service registry (GET /api/services)
//	quantum disks             disk usage (GET /api/storage) with 85/90/95 thresholds
//	quantum vitals            CPU / memory / GPU vitals (GET /api/vitals)
//	quantum logs <id> [-n N]  journal tail (GET /api/logs?id=&lines=)
//	quantum tracker list|get  work tracker (provider interface; fixture in v0)
//	quantum memory search <q> Hive memory (provider interface; fixture in v0)
//
// Every command accepts --json. Hub commands are live-wired; tracker and
// memory run on a fixture provider seeded with real snapshots until their
// live provider (over the hub MCP facade) lands. --fixture forces fixture
// mode for every command (offline / demo / verification).
//
// Write commands (services restart, tracker add) are designed but GATED in
// v0: they print the gate and exit 3 without sending anything.
package main

import (
	"fmt"
	"os"
	"strings"
)

type options struct {
	json    bool
	fixture bool
	hubURL  string
	args    []string
}

func main() {
	opts, rest, err := parseGlobal(os.Args[1:])
	if err != nil {
		fmt.Fprintln(os.Stderr, "quantum:", err)
		os.Exit(2)
	}
	opts.args = rest
	if len(rest) == 0 {
		printHelp()
		return
	}
	if err := dispatch(opts, rest[0], rest[1:]); err != nil {
		if ee, ok := err.(*exitError); ok {
			fmt.Fprintln(os.Stderr, "quantum:", ee.msg)
			os.Exit(ee.code)
		}
		fmt.Fprintln(os.Stderr, "quantum:", err)
		os.Exit(2)
	}
}

type exitError struct {
	code int
	msg  string
}

func (e *exitError) Error() string { return e.msg }

func gated(what string) error {
	return &exitError{code: 3, msg: fmt.Sprintf("%s is a write command — designed but GATED in v0 (read-only). "+
		"It sends nothing. Writes land after review of this PR and hub-api#34.", what)}
}

func parseGlobal(argv []string) (options, []string, error) {
	o := options{hubURL: os.Getenv("QUANTUM_HUB_URL")}
	if o.hubURL == "" {
		o.hubURL = "http://127.0.0.1:8091"
	}
	var rest []string
	for i := 0; i < len(argv); i++ {
		a := argv[i]
		switch {
		case a == "--json":
			o.json = true
		case a == "--fixture":
			o.fixture = true
		case a == "--hub":
			if i+1 >= len(argv) {
				return o, nil, fmt.Errorf("--hub needs a URL")
			}
			i++
			o.hubURL = argv[i]
		case strings.HasPrefix(a, "--hub="):
			o.hubURL = strings.TrimPrefix(a, "--hub=")
		default:
			rest = append(rest, a)
		}
	}
	return o, rest, nil
}

func dispatch(o options, cmd string, args []string) error {
	src := newSource(o)
	switch cmd {
	case "help", "-h", "--help":
		printHelp()
		return nil
	case "status":
		return cmdStatus(o, src)
	case "services":
		if len(args) > 0 && (args[0] == "restart" || args[0] == "start" || args[0] == "stop") {
			return gated("quantum services " + args[0])
		}
		return cmdServices(o, src)
	case "disks":
		return cmdDisks(o, src)
	case "vitals":
		return cmdVitals(o, src)
	case "logs":
		return cmdLogs(o, src, args)
	case "tracker":
		return cmdTracker(o, src, args)
	case "memory":
		return cmdMemory(o, src, args)
	default:
		return &exitError{code: 2, msg: fmt.Sprintf("unknown command %q — run `quantum help`", cmd)}
	}
}

func printHelp() {
	fmt.Print(`⚡ QUANTUM CLI — fleet command surface (v0, read-only)

Usage: quantum [--json] [--fixture] [--hub URL] <command> [args]

Commands:
  status                  Service health across Tritium (hub /api/status)
  services                Service registry (hub /api/services)
  disks                   Disk usage with 85/90/95 thresholds (hub /api/storage)
  vitals                  CPU, load, memory, swap, GPUs (hub /api/vitals)
  logs <id> [-n N]        Tail a service journal (hub /api/logs)
  tracker list [--status] Work tracker board (fixture provider in v0)
  tracker get <TRK-id>    One tracker record (fixture provider in v0)
  memory search <query>   Search the Hive (fixture provider in v0)
  help                    This help

Flags:
  --json                  Machine-readable output (for scripting/agents)
  --fixture               Use bundled fixture data instead of the live hub
  --hub URL               Hub base URL (default $QUANTUM_HUB_URL or http://127.0.0.1:8091)

Environment:
  QUANTUM_HUB_URL         Hub base URL (the hub is tailnet-only)
  QUANTUM_TOKEN           Bearer token for the hub, when set (never stored in this repo)

Gated (designed, not implemented in v0): services restart|start|stop, tracker add.
`)
}
