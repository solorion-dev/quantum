// Registry: enrolled agents, their signed cards, and per-skill policy
// metadata (minTier / requiresApproval live here, NOT on the wire card —
// the wire card stays vanilla A2A; the registry record is our profile's
// extension point, echoed in task metadata as dev.dsect.* on request).
//
// Seeded from code for the dev instance; enrollment changes are operator
// actions recorded in the Tracker (TRK-0424) — the registry file is a
// runtime cache of the seed, so the fleet's discovery view has one shape
// whether it comes from here or, later, the Tracker people/agents data.
import { buildCard, validateCard } from "../../../packages/a2a/src/card.js";
import { signCard } from "../../../packages/a2a/src/jws.js";

export class Registry {
  constructor(store, config, signing) {
    this.store = store;
    this.config = config;
    this.signing = signing; // { privatePem, kid, jwk }
    this.agents = new Map();
    this._seed();
  }

  _seed() {
    const base = this.config.baseUrl;
    const seeds = [
      {
        agentId: "qubit",
        adapter: "hermes",
        cardSpec: {
          name: "Qubit",
          description:
            "Team Quantum fleet agent (Hermes, local Qwen3.6-35B). Takes delegated research and system-lookup work, does it with its own tools, and returns artifacts.",
          providerOrg: "DSECT / Team Quantum",
          providerUrl: "https://dsect.net",
          documentationUrl: `${base}/docs`,
          baseUrl: `${base}/agents/qubit`,
          oidcDiscoveryUrl: this.config.oidcDiscoveryUrl,
          streaming: true,
          pushNotifications: true,
          skills: [
            {
              id: "public-status",
              name: "Public status",
              description:
                "Names and count of currently running containers on the host. Low-sensitivity liveness view, open to registered guests.",
              tags: ["status", "public", "docker"],
              examples: ["What is running on the host right now?"],
            },
            {
              id: "fleet-brief",
              name: "Fleet brief",
              description:
                "Produce a short markdown brief on live fleet state (services, uptime, load) and write it to the agent workspace as an artifact file.",
              tags: ["research", "brief", "fleet"],
              examples: ["Brief me on the current state of the fleet."],
            },
            {
              id: "gated-file-read",
              name: "Gated file read",
              description:
                "Read one allow-listed document from the agent's own home and summarize it. APPROVAL-GATED: tasks pause in auth-required until Scotty or a delegated approver approves in-task.",
              tags: ["files", "summary", "approval-gated"],
              examples: ["Summarize AGENT_STANDARD.md from your home directory."],
            },
          ],
        },
        skillMeta: {
          "public-status": { minTier: 1, requiresApproval: false },
          "fleet-brief": { minTier: 3, requiresApproval: false },
          "gated-file-read": { minTier: 3, requiresApproval: true },
        },
      },
      {
        agentId: "cooper",
        adapter: "inbox",
        cardSpec: {
          name: "Cooper",
          description:
            "Scotty's chief-of-staff agent. Hosted endpoint: tasks are queued to Cooper's inbox and worked in session (asynchronous by design — Cooper is an intermittent, session-based agent).",
          providerOrg: "DSECT / Team Quantum",
          providerUrl: "https://dsect.net",
          documentationUrl: `${base}/docs`,
          baseUrl: `${base}/agents/cooper`,
          oidcDiscoveryUrl: this.config.oidcDiscoveryUrl,
          streaming: true,
          pushNotifications: true,
          skills: [
            {
              id: "coordination-notes",
              name: "Coordination notes",
              description:
                "Leave a structured note/request for Cooper (tasking, questions, handoffs). Delivered to Cooper's A2A inbox; replies come back as task artifacts.",
              tags: ["coordination", "async", "notes"],
              examples: ["Note for Cooper: check the morning brief sources."],
            },
          ],
        },
        skillMeta: {
          "coordination-notes": { minTier: 3, requiresApproval: false },
        },
      },
    ];
    for (const seed of seeds) {
      const card = buildCard(seed.cardSpec);
      const problems = validateCard(card);
      if (problems.length) throw new Error(`card ${seed.agentId}: ${problems.join("; ")}`);
      const sig = signCard(card, this.signing.privatePem, this.signing.kid);
      const signedCard = { ...card, signatures: [sig] };
      this.agents.set(seed.agentId, { ...seed, card: signedCard });
    }
  }

  get(agentId) {
    return this.agents.get(agentId);
  }

  list() {
    return [...this.agents.values()];
  }

  /** T0-public discovery view: signed cards only, no policy internals. */
  publicList() {
    return this.list().map((a) => ({
      agentId: a.agentId,
      card: a.card,
    }));
  }

  /** Skill search across enrolled agents (drives a2a_discover). */
  search({ skill, tag, query } = {}) {
    const out = [];
    for (const a of this.list()) {
      for (const s of a.card.skills) {
        if (skill && s.id !== skill) continue;
        if (tag && !s.tags.includes(tag)) continue;
        if (
          query &&
          !`${s.id} ${s.name} ${s.description} ${a.agentId}`.toLowerCase().includes(query.toLowerCase())
        )
          continue;
        out.push({
          agentId: a.agentId,
          agentName: a.card.name,
          endpoint: a.card.supportedInterfaces[0].url,
          skill: s,
          policy: a.skillMeta[s.id] ?? { minTier: 3, requiresApproval: false },
        });
      }
    }
    return out;
  }
}
