/**
 * Curated runner catalog for the Services & tools screen.
 *
 * The screen lists whatever `tools/list` returns, but only these curated
 * read-only tools get a real "Run" UI. Everything else classified mutating
 * (or unknown) is shown with a "Not run from mobile" badge and NO action
 * button — a destructive action must never be half-wired from a phone.
 *
 * `quantum_tailscale_status` (Tailscale device status) is published by the hub
 * gateway; the runner is ready to match it.
 */
export interface RunnerField {
  key: string;
  label: string;
  placeholder: string;
  required: boolean;
  type: 'text' | 'number' | 'toggle';
  defaultValue?: string | number | boolean;
  hint?: string;
}

export interface RunnerConfig {
  tool: string;
  title: string;
  description: string;
  fields: RunnerField[];
  /** Build the tools/call arguments from the field values. */
  buildArgs: (values: Record<string, string>) => Record<string, unknown>;
}

const READ_ONLY_RUNNERS: RunnerConfig[] = [
  {
    tool: 'quantum_services_status',
    title: 'Services status',
    description: 'Hub service registry health — which services are up, down, or degraded.',
    fields: [
      {
        key: 'only_problems',
        label: 'Only problems',
        placeholder: '',
        required: false,
        type: 'toggle',
        defaultValue: false,
        hint: 'Return only services that are not up.',
      },
    ],
    buildArgs: (values) => ({ only_problems: values['only_problems'] === 'true' }),
  },
  {
    tool: 'quantum_service_logs',
    title: 'Service logs',
    description: 'Tail docker logs for one service (allowlisted container names only).',
    fields: [
      {
        key: 'service',
        label: 'Service',
        placeholder: 'hub-api',
        required: true,
        type: 'text',
        hint: 'Container name, e.g. hub-api.',
      },
      {
        key: 'tail',
        label: 'Last N lines',
        placeholder: '100',
        required: false,
        type: 'number',
        defaultValue: 100,
        hint: 'Default 100, max 500.',
      },
    ],
    buildArgs: (values) => {
      const tail = Number(values['tail'] ?? 100);
      return { service: values['service'], tail: Number.isFinite(tail) ? tail : 100 };
    },
  },
  {
    tool: 'quantum_monitor_snapshot',
    title: 'Monitor snapshot',
    description: 'Latest host monitor snapshot — CPU, memory, disk, and temperatures.',
    fields: [],
    buildArgs: () => ({}),
  },
  {
    tool: 'quantum_whoami',
    title: 'Who am I',
    description: 'Show the role, key id, and audience behind this worker key.',
    fields: [],
    buildArgs: () => ({}),
  },
];

export function runnerFor(toolName: string): RunnerConfig | null {
  return READ_ONLY_RUNNERS.find((r) => r.tool === toolName) ?? null;
}

export const KNOWN_UNPUBLISHED_TOOLS: { tool: string; note: string }[] = [
  // quantum_tailscale_status is now published by the gateway; no gap entry needed.
];

/** Friendly display title for a tool not in the curated catalog. */
export function toolDisplayName(name: string): string {
  return name
    .replace(/^quantum_/, '')
    .split('_')
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ');
}
