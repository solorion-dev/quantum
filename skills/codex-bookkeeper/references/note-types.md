# Note types: classify, template, file

Use during intake. Each rough item from a spill, a brain-dump or a loose note becomes exactly one
row's worth of note, or an append to an existing note. **Search for an existing home first.** The
right answer is often "append to X", not "create Y".

| the item is… | it becomes | template | lands in |
|---|---|---|---|
| Substantial work: more than one sitting, or something another agent may pick up | **goal** (`ABBR-NNN`) | `system/template_goal.md` (Templater: `_templates/Goal.md`) | `projects/<Project>/goals/`, plus rows in the project `INDEX.md` **and** `projects/README.md` |
| A step of work that already has a goal | **task** on that goal | Tasks checkbox `- [ ] #task … ➕ date` | the goal note's `## Tasks` |
| A whole new line of work | **project** | rationale first, then `system/template_project_{overview,roadmap,index}.md` | `projects/project_rationales/Rationale <P>.md` + `projects/<P>/` |
| An idea not yet committed to | **proposal** | plain note, full frontmatter, `status: "Draft"` | `projects/Proposals/`, cross-checked against active goals for overlap |
| A choice between options, made or needed | **decision** | `_templates/Decision.md` | the folder of the state it governs; link it from that hub's index |
| A failure, outage or broken run | **post-mortem** | `_templates/Post-Mortem.md` | `insights_and_breakthroughs/post_mortems/` (Commandment 7) |
| Something that worked and should be reused | **breakthrough** | `_templates/Breakthrough.md` | `insights_and_breakthroughs/breakthroughs/` |
| A measured fact or spec that outlives one goal | **reference** | plain note | `projects/<P>/reference/` |
| A research question to test | **study** | `_templates/Research Study.md` | `DSECT/Labs/Studies/` |
| A paper or write-up for publication | **paper** | `_templates/Paper Draft.md` | `DSECT/Labs/Papers/` |
| A reusable instruction for an agent or model | **prompt card** | `_templates/Prompt Card.md` | `Agents/Prompts/<Roles/Tasks/Goals/Model Instructions>/` |
| A machine, server or device | **device record** | `_templates/Device Record.md` | `DSECT/Systems/Devices/` |
| Company identity, mission, policy | **handbook** edit | edit the existing doc | `DSECT/Company/`, or the relevant division note |
| A new skill | **skill** | `<name>/SKILL.md` with `name` + `description` | `Skills/<name>/SKILL.md` + a row in `Skills/SKILL INDEX.md` |
| An agent's identity or soul | *not yours to write* | none | tell the owning agent; `Quantum Agents/<Name>/` is theirs |
| Something about money, trading, legal, accounts | *decision-tier* | none | **Needs Scott** in your report, never acted on |
| Personal or family | *private* | none | `Haven/` only if Scott asked; otherwise leave it where it is |
| Pure noise, or an exact duplicate of a filed note | nothing | none | say so in the Triage table; archive the duplicate |

## Picking codes and names

- **ABBR**: 2–4 capitals, one per project, registered in `projects/README.md`. Check the table
  before inventing one.
- **NNN**: next unused number in that project; never reuse one, even if cancelled.
- **CODENAME**: one uppercase word, unique **across every project**. Search `projects/README.md`
  for it first.
- **Study IDs**: `LAB-S001` and up, in `DSECT/Labs/DSECT Labs.md`'s study register.

## When the classification is unclear

Default to the less committal type (proposal before goal, task before goal) and say so in the
Triage table. Promoting a note is easy. Unwinding a premature goal leaves dead IDs in the register.
