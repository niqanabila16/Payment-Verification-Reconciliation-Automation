"""
Shows how the reader understands a bank statement file, without importing anything.
Use it when a real ALB / PBB / MBB file is not read the way you expect:

    python manage.py inspect_statement "C:\\path\\statement.csv" alb

It prints the bank it thinks the file belongs to, the header row it found, which columns became Date / Reference /
Debit / Credit / ..., and the first rows as they would be stored. To teach the reader a new column title, add the
title (letters and digits only, lower case) to the matching alias set in apps/reconciliation/services/bank_profiles.py.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.reconciliation.services.bank_profiles import PROFILES, detect_bank, key, map_headers
from apps.reconciliation.services.parser import StatementParseError, parse_statement, read_rows


class Command(BaseCommand):
    help = "Show how a bank statement file is read (nothing is imported)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("bank", choices=sorted(PROFILES))
        parser.add_argument("--rows", type=int, default=5, help="How many parsed rows to print.")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        data = path.read_bytes()
        extension = path.suffix.lower()
        rows = read_rows(data, extension)
        self.stdout.write(f"Rows in file: {len(rows)}")
        self.stdout.write(f"Looks like: {detect_bank(rows) or 'cannot tell from the file'}  (selected: {options['bank']})")
        try:
            parsed = parse_statement(data, path.name, options["bank"])
        except StatementParseError as exc:
            self.stdout.write(self.style.ERROR(f"Not readable: {exc}"))
            for number, row in enumerate(rows[:8], start=1):
                self.stdout.write(f"  row {number}: {[c for c in row if c][:10]}")
            return
        profile = PROFILES[options["bank"]]
        header = rows[parsed.header_row - 1]
        mapping = map_headers(header, profile)
        self.stdout.write(self.style.SUCCESS(f"Header row: {parsed.header_row}   Account: {parsed.account_number or '-'}   Statement date: {parsed.statement_date}"))
        for canonical, index in mapping.items():
            self.stdout.write(f"  {canonical:12} <- column {index + 1}: {header[index]!r}")
        unmapped = [h for i, h in enumerate(header) if i not in mapping.values() and h.strip()]
        self.stdout.write(f"Other columns (ignored): {unmapped}")
        self.stdout.write(f"Usable rows: {len(parsed.rows)}   skipped: {len(parsed.skipped)}   repeated in file: {parsed.duplicates_in_file}")
        for row in parsed.rows[: options["rows"]]:
            self.stdout.write(f"  row {row.source_row}: amount={row.amount} date={row.transaction_date} ref={row.reference!r} name={row.counterparty_name!r} desc={row.description!r} matchable={row.matchable}")
        self.stdout.write(f"(column keys the reader compares: {[key(h) for h in header if h.strip()][:12]})")
