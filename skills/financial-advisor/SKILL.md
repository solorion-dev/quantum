---
name: financial-advisor
version: 1.0.0
description: "Run Scotty's money operations: verify bill and debt status at the issuer, position Chime cash so payments never bounce, prepare and submit approved payments, keep due dates on his calendar, and log every payment in the finance ledger."
tags: [quantum]
status: active
provenance: quantum
aliases: [local-financial-advisor]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Financial Advisor — Operations

Scotty's operational money skill: check bill/debt status at the source, keep
cash positioned so nothing bounces, prepare and submit payments under his
approval, keep due dates on his calendar, and log every payment. Analysis and
payoff planning live in the bundled `financial_planning` skill; this skill is
the doing. It was built from the Oct 31, 2026 session that paid the OnePay
past-due balance, verified Avant/Bridgecrest/Synchrony at their own sites,
and caught a wrong default funding bank.

## Hard rules (never bend)

- **Approval fence.** No payment, transfer, or creditor message leaves without
  Scotty's approval of the exact amount, source account, and destination —
  except a payment he explicitly pre-approved in the same conversation. A
  confirmation covers only the action he saw.
- **Verify the funding source before submitting — every time.** Issuer
  payment flows carry defaults that may not be his intent. On Oct 31, 2026
  the OnePay flow defaulted to Alliant CU …9413; Scotty's rule: **the OnePay
  Walmart Spend Card is funded ONLY from Chime Checking …1088. Alliant is a
  secondary account and is never this card's bank.** Wrong/returned funding
  is his working theory for why Synchrony closed both of his accounts.
- **Never double-pay an autopay.** Before preparing any manual payment,
  check the account's AutoPay status at the issuer. (Oct 31: Google Store
  Financing already had autopay ON for the exact $29.24 prepared manually —
  the prepared duplicate was correctly never submitted.)
- **Verify at the authoritative surface.** A status claim ("past due",
  "current", "closed", an amount) is only as good as the surface read: the
  issuer's own site/statement or the bank's own record. Email summaries,
  Plaid recurring guesses, and old snapshots are leads, not facts. Name the
  surface in the report.
- **Secrets stay out of everything.** No full account numbers, card numbers,
  passwords, or codes in the ledger, calendar, memory, or chat. Last-4 only.
  Logins go through the Secure Vault / browser login agent; one-time codes
  through the protected code read (Gmail / his phone's messages).
- **Plaid is read-only.** It cannot move money, pay bills, or show Chime
  liabilities (`PRODUCTS_NOT_SUPPORTED`). Money moves happen in the browser
  on the bank's or issuer's own site, under the approval fence.

## The accounts map (verify before relying — balances/dates go stale)

- **Chime Checking …1088** (Stride Bank) — primary spending account; most
  autopays pull here.
- **Chime Savings …8463** — reserve; transfers to checking happen at
  chime.com (browser) or by Scotty in the app.
- **Alliant CU …9413** — secondary ONLY. Never the Spend Card's bank.
- **AvantCard (WebBank) …3503** — limit $750; AutoPay ON (total minimum,
  ~1st of month, from Chime …1088).
- **OnePay Walmart Spend Card (Synchrony) …3887** — CLOSED by Synchrony
  (confirmed on onepay.com Oct 31, 2026); balance survives; autopay exists
  for the minimum (~20th); funding must be Chime.
- **Google Store Financing (Synchrony) …9743** — CLOSED by Synchrony;
  balance survives; AutoPay ON (minimum, ~10th, from Chime …1088).
- **Bridgecrest auto loan** (2022 Bolt EV) — $321/mo, due ~14th, NO autopay
  (paid manually); extensions are by review: text 602-831-0050 or call
  800-967-8526; no portal message feature.
- **Self Visa (Lead Bank)** — status unverified as of Oct 31, 2026; do not
  state an amount or due date until read at the source.
- **MOHELA student loans** — administrative forbearance; no payments due.
- Standing bills: rent $600 to Steven (4th), Progressive ~$160–173 (~17th),
  Google Fi ~$51, Davis Chiropractic ~$83, Google One $19.99 (3rd),
  Wispr $15 (1st), OnStar $14.99 (29th), ElevenLabs $5, GitHub ~$10–17,
  Klarna installments as scheduled.

## Workflows

### 1. Bill / debt status check
1. Gather leads: Plaid `accounts` + `transactions-recurring` (Chime only),
   Gmail issuer notices (statements, past-due, over-limit), his own debt
   snapshots in Gmail.
2. Confirm at the source: browser sign-in to the issuer, read balance,
   minimum, due date, past-due amount, account open/closed, AutoPay status
   and funding bank. Report figures with the surface and date read.
3. Unknown stays unknown: label it unverified (Self Visa rule).

### 2. Cash positioning (make sure the money is there)
1. Project checking outflows to the horizon he cares about (autopays,
   scheduled payments, rent) from verified due dates.
2. Compare against Plaid balances; note Plaid lags — when a browser session
   is open at the bank, prefer its live balances.
3. If short: compute the exact savings→checking transfer (needed total −
   checking balance, capped at the savings balance; report any residual
   shortfall plainly). Execute at chime.com under his instruction, or hand
   him the exact figure to tap in the app.

### 3. Making a payment
1. Run workflow 1 for that account first — including AutoPay check
   (double-pay rule) and funding-source check (Alliant rule).
2. Prepare in the browser to the final review screen and STOP. Report the
   exact review contents (amount, date, source, destination).
3. Submit only on his approval of that exact payment. After submitting,
   capture the confirmation wording, any reference number (note when none
   is issued), posting ETA, and the account's new displayed status.
4. A user-only step (e.g., OnePay's 4-digit passcode) goes to Scotty via
   browser takeover; never ask for it in chat.

### 4. Calendar (standing instruction, Oct 31, 2026)
Every scheduled payment and due date gets an all-day, monthly-recurring
Google Calendar event on his primary calendar, titled with payee + amount,
description carrying balance/due-date/autopay notes. Add new ones as they're
verified; patch amounts when a statement changes them.

### 5. Ledger (standing instruction, Oct 31, 2026)
Log every payment made, scheduled autopay, and verified due in the Google
Sheet **"Finance Ledger - Payments and Bills"**
(spreadsheetId `1b322dmZFyLPBT0NsBWT7bNSn6m4R6W3FrV6Du-7aXtg`, Sheet1):
Date | Payee | Kind | Amount | Source account | Status | Confirmation/Ref |
Due date | Notes. Update a row's Status when a pending payment posts.
Never put secrets in the sheet.

### 6. Creditor outreach (forgiveness / leeway / deferral)
Draft first, send only on his approval of the final text. Medical-leave
asks cite: leave Oct 9, 2026 – Jan 4, 2027, return Jan 5, 2027, benefits
pending, payments brought current. Know the route before drafting:
Synchrony = phone + letter (OnePay Spend Card 1-866-664-0886; Google Store
1-866-794-8802; reinstatement is a stated-policy long shot — fee goodwill is
the realistic win); Bridgecrest = text/call only; Avant = account-center
support message. Drafts live in `~/workspace/finance/`.

### 7. Daily guard
The existing bill-guard cron (Chime vs upcoming charges) keeps running;
this skill is what it escalates into when something needs action.

## Output contract

Report: what was verified (surface + date), what was paid/prepared (exact
figures + confirmation state), what is still unverified, and the one next
decision that is his. Headline first in chat; the detail goes to the ledger,
the calendar, and `~/workspace/finance/` files.
