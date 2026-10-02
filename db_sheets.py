"""Google Sheets backend for trips, people and expenses.

The spreadsheet gets four tabs (created automatically if missing):

    trips     id | name | currency | created_at
    people    id | trip_id | name
    expenses  id | trip_id | spent_on | description | amount | payer_id | paid_by | split_mode | split_among | created_at
    shares    expense_id | person_id | person | share

Amounts are written in normal currency units (e.g. 33.34) so the sheet is easy to
read; the app works in integer cents internally. "paid_by", "split_among" and
"person" are human-readable copies of names and are not read back.
"""

from __future__ import annotations

import time
from datetime import date, datetime

import gspread

from errors import DuplicateError

HEADERS = {
    "trips": ["id", "name", "currency", "created_at"],
    "people": ["id", "trip_id", "name"],
    "expenses": ["id", "trip_id", "spent_on", "description", "amount", "payer_id",
                 "paid_by", "split_mode", "split_among", "created_at"],
    "shares": ["expense_id", "person_id", "person", "share"],
}
INT_COLUMNS = {"id", "trip_id", "payer_id", "expense_id", "person_id"}
MONEY_COLUMNS = {"amount", "share"}
CACHE_SECONDS = 15


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_cents(value) -> int:
    return int(round(float(value or 0) * 100))


class SheetsDB:
    def __init__(self, spreadsheet: gspread.Spreadsheet):
        self.sh = spreadsheet
        self._ws: dict[str, gspread.Worksheet] = {}
        self._cache: dict[str, tuple[float, list[dict]]] = {}

    # ---------- low level ----------

    def _worksheet(self, name: str) -> gspread.Worksheet:
        if name not in self._ws:
            try:
                ws = self.sh.worksheet(name)
            except gspread.WorksheetNotFound:
                ws = self.sh.add_worksheet(title=name, rows=100, cols=len(HEADERS[name]))
                ws.append_row(HEADERS[name], value_input_option="RAW")
            else:
                if not ws.row_values(1):
                    ws.append_row(HEADERS[name], value_input_option="RAW")
            self._ws[name] = ws
        return self._ws[name]

    def _rows(self, name: str) -> list[dict]:
        hit = self._cache.get(name)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        values = self._worksheet(name).get_all_values(value_render_option="UNFORMATTED_VALUE")
        header = [str(h) for h in values[0]] if values else HEADERS[name]
        rows = []
        for raw in values[1:]:
            if not any(str(v).strip() for v in raw):
                continue
            row = {}
            for i, col in enumerate(header):
                v = raw[i] if i < len(raw) else ""
                if col in INT_COLUMNS:
                    v = int(float(v)) if str(v).strip() else 0
                elif col in MONEY_COLUMNS:
                    v = _to_cents(v)
                else:
                    v = str(v)
                row[col] = v
            rows.append(row)
        self._cache[name] = (time.monotonic(), rows)
        return rows

    def _invalidate(self, *names: str) -> None:
        for n in names:
            self._cache.pop(n, None)

    def _append(self, name: str, records: list[dict]) -> None:
        if not records:
            return
        values = [[self._cell(col, r.get(col, "")) for col in HEADERS[name]] for r in records]
        self._worksheet(name).append_rows(values, value_input_option="RAW")
        self._invalidate(name)

    @staticmethod
    def _cell(col: str, value):
        if col in MONEY_COLUMNS:
            return value / 100
        return value

    def _next_id(self, name: str) -> int:
        return max((r["id"] for r in self._rows(name)), default=0) + 1

    def _delete_where(self, name: str, predicate) -> None:
        """Delete matching rows, grouping consecutive rows into single API calls."""
        self._invalidate(name)
        ws = self._worksheet(name)
        values = ws.get_all_values(value_render_option="UNFORMATTED_VALUE")
        header = [str(h) for h in values[0]]
        idx = {c: i for i, c in enumerate(header)}
        doomed = []
        for row_no, raw in enumerate(values[1:], start=2):
            rec = {c: (raw[i] if i < len(raw) else "") for c, i in idx.items()}
            for c in INT_COLUMNS & rec.keys():
                rec[c] = int(float(rec[c])) if str(rec[c]).strip() else 0
            if predicate(rec):
                doomed.append(row_no)
        # Delete bottom-up so earlier row numbers stay valid.
        ranges = []
        for r in sorted(doomed, reverse=True):
            if ranges and ranges[-1][0] == r + 1:
                ranges[-1][0] = r
            else:
                ranges.append([r, r])
        for start, end in ranges:
            ws.delete_rows(start, end)
        self._invalidate(name)

    # ---------- setup ----------

    def init_db(self) -> None:
        for name in HEADERS:
            self._worksheet(name)

    # ---------- trips ----------

    def list_trips(self) -> list[dict]:
        expenses = self._rows("expenses")
        trips = []
        for t in self._rows("trips"):
            mine = [e for e in expenses if e["trip_id"] == t["id"]]
            trips.append({**t, "expense_count": len(mine), "total": sum(e["amount"] for e in mine)})
        trips.sort(key=lambda t: (t["created_at"], t["id"]), reverse=True)
        return trips

    def create_trip(self, name: str, currency: str) -> int:
        if any(t["name"].lower() == name.lower() for t in self._rows("trips")):
            raise DuplicateError(name)
        trip_id = self._next_id("trips")
        self._append("trips", [{"id": trip_id, "name": name, "currency": currency, "created_at": _now()}])
        return trip_id

    def rename_trip(self, trip_id: int, name: str, currency: str) -> None:
        if any(t["name"].lower() == name.lower() and t["id"] != trip_id for t in self._rows("trips")):
            raise DuplicateError(name)
        ws = self._worksheet("trips")
        for row_no, t in enumerate(self._rows("trips"), start=2):
            if t["id"] == trip_id:
                ws.update(range_name=f"B{row_no}:C{row_no}", values=[[name, currency]],
                          value_input_option="RAW")
                break
        self._invalidate("trips")

    def delete_trip(self, trip_id: int) -> None:
        expense_ids = {e["id"] for e in self._rows("expenses") if e["trip_id"] == trip_id}
        self._delete_where("shares", lambda r: r["expense_id"] in expense_ids)
        self._delete_where("expenses", lambda r: r["trip_id"] == trip_id)
        self._delete_where("people", lambda r: r["trip_id"] == trip_id)
        self._delete_where("trips", lambda r: r["id"] == trip_id)

    # ---------- people ----------

    def list_people(self, trip_id: int) -> list[dict]:
        return sorted((p for p in self._rows("people") if p["trip_id"] == trip_id), key=lambda p: p["id"])

    def add_person(self, trip_id: int, name: str) -> int:
        if any(p["name"].lower() == name.lower() for p in self.list_people(trip_id)):
            raise DuplicateError(name)
        person_id = self._next_id("people")
        self._append("people", [{"id": person_id, "trip_id": trip_id, "name": name}])
        return person_id

    def person_in_use(self, person_id: int) -> bool:
        return any(e["payer_id"] == person_id for e in self._rows("expenses")) or any(
            s["person_id"] == person_id for s in self._rows("shares")
        )

    def delete_person(self, person_id: int) -> None:
        self._delete_where("people", lambda r: r["id"] == person_id)

    # ---------- expenses ----------

    def list_expenses(self, trip_id: int) -> list[dict]:
        expenses = [dict(e) for e in self._rows("expenses") if e["trip_id"] == trip_id]
        ids = {e["id"] for e in expenses}
        by_expense: dict[int, dict[int, int]] = {}
        for s in self._rows("shares"):
            if s["expense_id"] in ids:
                by_expense.setdefault(s["expense_id"], {})[s["person_id"]] = s["share"]
        for e in expenses:
            e["shares"] = by_expense.get(e["id"], {})
        expenses.sort(key=lambda e: (e["spent_on"], e["id"]), reverse=True)
        return expenses

    def add_expense(
        self,
        trip_id: int,
        description: str,
        amount: int,
        payer_id: int,
        split_mode: str,
        shares: dict[int, int],
        spent_on: date,
    ) -> int:
        names = {p["id"]: p["name"] for p in self.list_people(trip_id)}
        shares = {pid: s for pid, s in shares.items() if s > 0}
        # Also skip ids used by leftover share rows, so they can't attach to a new expense.
        expense_id = max([self._next_id("expenses")] + [s["expense_id"] + 1 for s in self._rows("shares")])
        # Shares are written first so a half-finished save never leaves an expense without them.
        self._append("shares", [
            {"expense_id": expense_id, "person_id": pid, "person": names.get(pid, ""), "share": s}
            for pid, s in shares.items()
        ])
        self._append("expenses", [{
            "id": expense_id,
            "trip_id": trip_id,
            "spent_on": spent_on.isoformat(),
            "description": description,
            "amount": amount,
            "payer_id": payer_id,
            "paid_by": names.get(payer_id, ""),
            "split_mode": split_mode,
            "split_among": ", ".join(names.get(pid, "") for pid in shares),
            "created_at": _now(),
        }])
        return expense_id

    def delete_expense(self, expense_id: int) -> None:
        self._delete_where("expenses", lambda r: r["id"] == expense_id)
        self._delete_where("shares", lambda r: r["expense_id"] == expense_id)


def connect(service_account_info: dict, spreadsheet: str) -> SheetsDB:
    """Open the spreadsheet by URL or key using a service account."""
    client = gspread.service_account_from_dict(dict(service_account_info))
    try:
        sh = client.open_by_url(spreadsheet) if spreadsheet.startswith("http") else client.open_by_key(spreadsheet)
    except PermissionError as exc:
        # gspread hides Google's explanation (API disabled, sheet not shared, ...) in the cause.
        cause = exc.__cause__
        detail = cause.response.json().get("error", {}).get("message") if isinstance(cause, gspread.exceptions.APIError) else None
        raise PermissionError(
            detail or f"No access to the sheet. Share it as Editor with {service_account_info.get('client_email')}."
        ) from exc
    return SheetsDB(sh)
