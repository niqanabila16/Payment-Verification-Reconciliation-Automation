# Revision 3 - card dashboard, blocking, card request form, Excel reports, CS rights

## What changed (by request number)
1. **Dashboard** (`cards/_dashboard.html`, shown on Teller "Card activation" pages above the tabs, and on CS Cards / Activation requests / Blocked cards): Total Undisbursed, Total Disbursed, Collected by Customer, Remaining, Block. "All branches" card, own branch large (Teller), every other branch as a card.
2. **Live numbers**: counted from the card table with one grouped query (`services.dashboard`), nothing stored, so it cannot drift. Pages refresh every 15 s (`dashboard.json`, `js/card_dashboard.js`).
   - new batch -> Undisbursed +n; deliver -> Undisbursed -n, Disbursed +n, Remaining +n; card request -> Remaining -1, Collected +1; block -> Remaining -1, Block +1.
3. **New branch** appears automatically (active branches); until it received a card every figure shows `-`.
4. **Block card**: CS with the Block right selects cards the branch still holds + writes a reason; list for everybody at `Cards > Blocked cards`.
5. **Finance report**: no "Receipt #"; one "Account holder" column (the former "Name"); the second account-holder column was removed.
6. **Finance Reject**: reason dropdown Nama Beda / Amaun Salah / lain-lain (optional remark kept with lain-lain).
7. **CS Reject**: type (Incomplete Data / Return / Close) + reason (Nama Ibu Kandung / Tanda Tangan Berbeda / TTL Berbeda / KTP Tidak Sesuai DUKCAPIL).
8. **Teller "Request new card"**: Name, No Rekening, No ID, No Phone, Alasan ganti kad (Terbit Kartu Baru / Ganti Kartu / Kad Expired), Card No = fixed BIN `461699` (setting `CARD_BIN`) + typed rest with search-as-you-type suggestions from the cards delivered to the own branch, + the customer PDF.
9. **Generate Report** (Excel like the business files): Teller `Card - <Branch> d_m_yyyy.xlsx`, CS/Admin `Card Monitoring - HQ d_m_yyyy.xlsx` (sheets Master Data + Card Stock). Rows with a Follow Up turn red (conditional format).
10. **CS rights** (Admin > Users > CS): Add card batch & deliver / Process card activation / Block card.

## Rules decided (change in one place if the business wants otherwise)
- A card used for a request becomes *Collected* at once; a card still "Delivered" is marked received at the same moment.
- Reject types: *Incomplete Data* and *Return* can be corrected and sent again by the Teller; *Close* is final (`models.RESUBMITTABLE`). The card stays Collected in all cases.
- Only cards a branch still holds (Delivered / Accepted) can be blocked. Remaining = Delivered + Accepted (blocked ones are not remaining).
- Others Income = collected cards x RM 30 (`CARD_OTHERS_INCOME_RM`); "Money Received" is the same number (the system does not record payments).
- Customer Collection Date = when the Teller sent the request; Date Submit to HQ = the request's sent time; Submit to Mabes = Activation Requested; Activation Date = Card Activated.

## Database (efficiency)
| Change | Why |
|---|---|
| `Card.status`, `ActivationRequest.status`: text -> SMALLINT code | 2 bytes instead of up to 20 |
| `Card.card_no`: VARCHAR(40) -> VARCHAR(19) | longest card number is 19 digits |
| Card indexes: (branch,status) + status -> one (status,branch) | one index serves tab lists, dashboard and branch lists |
| `resubmit_count` -> SMALLINT; `follow_up`, `reject_reason`, `reason` SMALLINT, NULL when unused | no wasted text |
| Blocked data in its own table `CardBlock` (PK = card) | blocks are rare: no empty columns on the big card table |
| CS rights: bit flags in one SMALLINT `User.cs_permissions` | no join table |
| Customer text columns sized to the data (name 100, account/ID/phone 20) | no TEXT columns |
| Dashboard numbers not stored | computed live, cannot become wrong |

Migrations: `accounts.0005`, `cards.0002` (converts existing rows, reversible). Existing CS accounts keep Batch + Activation; Block must be granted. Old rejected requests become "Incomplete Data" (can still be sent again); their free-text note stays in `cs_note` and is still shown.

## Files
See the list in the hand-over message / `git diff` against the previous zip.

## Follow-up rounds

- Dashboard is its own page (header menu). Own branch card: first, blue with white text, shadow, same size as the others.
- Blocked cards are a tab of the CS card list (no separate page). CS rights are switches, shown only for the CS role.
- Table actions update in place (live regions), no reload or jump to the top.
- Hint texts removed site-wide; UI and code comments are in English (dropdown values and report content unchanged).
- Input rules warn after the value is entered (paste is never blocked).
- A differing Reference is marked red like a name typo (not a matching key).
- PostgreSQL: `select_for_update(of=("self",))` fixes "FOR UPDATE cannot be applied to the nullable side of an outer join".
- Error summary: only real form-level problems; a wrong-file upload and a duplicate entry no longer show "Fix 1 problem before continuing".
