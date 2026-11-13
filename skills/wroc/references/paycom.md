# Paycom pull procedure

1. Paycom login is in Secure Vault (saved Sept 27, 2026). Scotty's last-4 was shared in chat on 9/27 — re-read that conversation when needed; never store the digits.
2. Every login needs a fresh six-digit code emailed to Scotty — ask him for it each time.
3. Paycom is read-only unless Scotty explicitly asks for editing/submission.
4. Record per shift: date, clock-in, clock-out, and the service/punch code (33 vs 36).
5. Translate to the week YAML: one `days` entry per workday with `shift1`/`shift2` start/end times in "H:MM AM/PM" form. The generator computes the totals; sanity-check them against Paycom's.

## Mileage expense entries (new expense flow)

- Flow: Expenses → Add New Expense → Expense type = Mileage. Save as **draft only**; Scotty reviews the summary before anything is submitted.
- Allocation defaults (confirmed in Paycom 2026-09-30; exact option text): Regions = "ME ANDROSCOGGIN COUNTY - [AND01]"; Office = "Lewiston - [13]"; Program = "ME Personal Supports - [33]" (Home Supports); Individual 1 = "C Joshua - [0004825]".
- Cross-check against the most recent prior mileage entries for the same route before creating new ones (e.g. the 09/14/2026 and 09/16/2026 "JC - ... POD ..." entries) and copy Regions/Office/Program/Individual 1 from those. Never guess an address or mileage number.
- Typical legs for JC's POD days: client home → Personal Onsite Development (~13.9 mi) and back (~14.1 mi), at $0.70/mile. Naming pattern: "JC - Client Home to POD Auburn" / "JC - POD Auburn to Client Home".
- Typical legs for JC's STRIVE (Portland) Thursdays: client home → STRIVE Portland (~29.7 mi) and back (~29.8 mi), at $0.70/mile (copied from 09/03–09/04/2026 entries). Naming pattern: "JC - Client Home to STRIVE Portland" / "JC - STRIVE Portland to Client Home".
- Check for existing entries on the target dates first; never create duplicates.
