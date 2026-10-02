"""Streamlit trip expense splitter.

Run with:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd
import streamlit as st

import storage
from splitter import compute_balances, compute_settlements, equal_shares, fmt, to_cents

CURRENCIES = ["₹", "$", "€", "£", "¥", "AED", "SGD", "THB"]

st.set_page_config(page_title="Trip Splitter", page_icon="💸", layout="wide")
storage.init_db()


# ---------- helpers ----------

def flash(msg: str, kind: str = "success") -> None:
    st.session_state["_flash"] = (kind, msg)


def show_flash() -> None:
    item = st.session_state.pop("_flash", None)
    if item:
        kind, msg = item
        getattr(st, kind)(msg)


def select_trip(trip_id: int | None) -> None:
    st.session_state["trip_id"] = trip_id
    if trip_id is None:
        st.query_params.clear()
    else:
        st.query_params["trip"] = str(trip_id)


def money(cents: int, currency: str) -> str:
    return f"{currency} {fmt(cents)}"


# ---------- sidebar: trips ----------

trips = storage.list_trips()
trip_ids = [t["id"] for t in trips]

if "trip_id" not in st.session_state:
    qp = st.query_params.get("trip")
    st.session_state["trip_id"] = int(qp) if qp and qp.isdigit() and int(qp) in trip_ids else None
if st.session_state["trip_id"] not in trip_ids:
    st.session_state["trip_id"] = trip_ids[0] if trip_ids else None

with st.sidebar:
    st.title("💸 Trip Splitter")

    with st.expander("➕ New trip", expanded=not trips):
        with st.form("new_trip", clear_on_submit=True):
            new_name = st.text_input("Trip name", placeholder="e.g. Goa 2026")
            new_currency = st.selectbox("Currency", CURRENCIES)
            if st.form_submit_button("Create trip", type="primary", width="stretch"):
                name = new_name.strip()
                if not name:
                    st.error("Enter a trip name.")
                else:
                    try:
                        select_trip(storage.create_trip(name, new_currency))
                        flash(f"Created trip **{name}**. Add the people on this trip next.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"A trip called “{name}” already exists.")

    if trips:
        st.subheader("Your trips")
        for t in trips:
            label = f"{t['name']}  ·  {money(t['total'], t['currency'])}"
            is_current = t["id"] == st.session_state["trip_id"]
            if st.button(
                label,
                key=f"trip_btn_{t['id']}",
                type="primary" if is_current else "secondary",
                width="stretch",
            ):
                select_trip(t["id"])
                st.rerun()

trip_id = st.session_state["trip_id"]
if trip_id is None:
    st.header("Welcome 👋")
    st.write("Create your first trip from the sidebar. Every trip keeps its own people and expenses, "
             "saved so you can come back to it any time.")
    st.stop()

trip = next(t for t in trips if t["id"] == trip_id)
cur = trip["currency"]
people = storage.list_people(trip_id)
names = {p["id"]: p["name"] for p in people}
expenses = storage.list_expenses(trip_id)
balances = compute_balances(list(names), expenses)


# ---------- header ----------

st.header(trip["name"])
show_flash()
c1, c2, c3 = st.columns(3)
c1.metric("Total spent", money(sum(e["amount"] for e in expenses), cur))
c2.metric("Expenses", len(expenses))
c3.metric("People", len(people))

tab_add, tab_list, tab_bal, tab_people, tab_settings = st.tabs(
    ["➕ Add expense", "🧾 Expenses", "⚖️ Balances", "👥 People", "⚙️ Trip settings"]
)


# ---------- add expense ----------

def k(name: str) -> str:
    """Session-state key scoped to the current trip."""
    return f"t{trip_id}_{name}"


def reset_expense_form() -> None:
    st.session_state[k("desc")] = ""
    st.session_state[k("amount")] = 0.0
    for p in people:
        st.session_state[k(f"exact_{p['id']}")] = 0.0


def submit_expense() -> None:
    ss = st.session_state
    desc = ss[k("desc")].strip()
    amount = to_cents(ss[k("amount")])
    payer = ss[k("payer")]
    mode = ss[k("mode")]
    among = ss[k("among")]

    if not desc:
        return flash("Enter a description.", "error")
    if amount <= 0:
        return flash("Enter an amount greater than 0.", "error")
    if not among:
        return flash("Choose at least one person to split with.", "error")

    if mode == "Equally":
        shares = equal_shares(amount, among)
    else:
        shares = {pid: to_cents(ss.get(k(f"exact_{pid}"), 0.0)) for pid in among}
        total = sum(shares.values())
        if total != amount:
            return flash(f"Exact amounts add up to {money(total, cur)} but the expense is {money(amount, cur)}.",
                         "error")

    storage.add_expense(trip_id, desc, amount, payer, "equal" if mode == "Equally" else "exact",
                        shares, ss[k("date")])
    flash(f"Added **{desc}** — {money(amount, cur)} paid by {names[payer]}.")
    reset_expense_form()


with tab_add:
    if not people:
        st.info("Add people to this trip in the **👥 People** tab first.")
    else:
        pids = list(names)
        col_a, col_b = st.columns([2, 1])
        col_a.text_input("Description", key=k("desc"), placeholder="e.g. Dinner at the beach shack")
        st.session_state.setdefault(k("date"), date.today())
        col_b.date_input("Date", key=k("date"))

        col_c, col_d = st.columns(2)
        col_c.number_input(f"Amount ({cur})", key=k("amount"), min_value=0.0, step=1.0, format="%.2f")
        col_d.selectbox("Paid by", pids, key=k("payer"), format_func=names.get)

        # Default to everyone: include people added since the last render, drop removed ones.
        known = st.session_state.get(k("among_known"), [])
        current = [p for p in st.session_state.get(k("among"), []) if p in names]
        st.session_state[k("among")] = current + [p for p in pids if p not in known and p not in current]
        st.session_state[k("among_known")] = pids
        st.multiselect("Split among", pids, key=k("among"), format_func=names.get)
        st.radio("How to split", ["Equally", "Exact amounts"], key=k("mode"), horizontal=True)

        among = st.session_state[k("among")]
        amount = to_cents(st.session_state[k("amount")])
        if st.session_state[k("mode")] == "Equally":
            if among:
                preview = equal_shares(amount, among)
                st.caption("Each share: " + ", ".join(f"{names[p]} {money(preview[p], cur)}" for p in among))
        else:
            cols = st.columns(min(len(among), 4) or 1)
            for i, pid in enumerate(among):
                cols[i % len(cols)].number_input(names[pid], key=k(f"exact_{pid}"), min_value=0.0,
                                                 step=1.0, format="%.2f")
            assigned = sum(to_cents(st.session_state.get(k(f"exact_{p}"), 0.0)) for p in among)
            left = amount - assigned
            status = "✅" if left == 0 else (f"{money(left, cur)} left" if left > 0 else f"{money(-left, cur)} over")
            st.caption(f"Assigned {money(assigned, cur)} of {money(amount, cur)} — {status}")

        st.button("Add expense", type="primary", on_click=submit_expense, width="stretch")


# ---------- expense list ----------

with tab_list:
    if not expenses:
        st.info("No expenses yet.")
    else:
        query = st.text_input("Search", placeholder="Filter by description or person", key=k("search"))
        q = query.strip().lower()
        shown = 0
        for e in expenses:
            among_names = ", ".join(names.get(p, "?") for p in e["shares"])
            payer_name = names.get(e["payer_id"], "?")
            if q and q not in f"{e['description']} {payer_name} {among_names}".lower():
                continue
            shown += 1
            with st.container(border=True):
                left, mid, right = st.columns([5, 2, 1])
                left.markdown(f"**{e['description']}**  \n"
                              f":gray[{e['spent_on']} · {payer_name} paid · split "
                              f"{'equally' if e['split_mode'] == 'equal' else 'by amount'} among {among_names}]")
                mid.markdown(f"### {money(e['amount'], cur)}")
                if right.button("🗑️", key=f"del_exp_{e['id']}", help="Delete expense"):
                    storage.delete_expense(e["id"])
                    flash(f"Deleted **{e['description']}**.")
                    st.rerun()
                with st.expander("Shares"):
                    st.write({names.get(p, "?"): money(s, cur) for p, s in e["shares"].items()})
        if shown == 0:
            st.caption("No expenses match.")

        rows = [
            {
                "Date": e["spent_on"],
                "Description": e["description"],
                "Amount": e["amount"] / 100,
                "Paid by": names.get(e["payer_id"], "?"),
                **{names[p]: e["shares"].get(p, 0) / 100 for p in names},
            }
            for e in expenses
        ]
        st.download_button(
            "⬇️ Download as CSV",
            pd.DataFrame(rows).to_csv(index=False).encode(),
            file_name=f"{trip['name']}.csv",
            mime="text/csv",
        )


# ---------- balances ----------

with tab_bal:
    if not people:
        st.info("No people on this trip yet.")
    else:
        paid = {p: 0 for p in names}
        owed = {p: 0 for p in names}
        for e in expenses:
            paid[e["payer_id"]] += e["amount"]
            for p, s in e["shares"].items():
                owed[p] += s
        df = pd.DataFrame(
            [
                {
                    "Person": names[p],
                    "Paid": money(paid[p], cur),
                    "Share of costs": money(owed[p], cur),
                    "Balance": ("gets back " + money(balances[p], cur)) if balances[p] > 0
                    else ("owes " + money(-balances[p], cur)) if balances[p] < 0 else "settled up",
                }
                for p in names
            ]
        )
        st.dataframe(df, hide_index=True, width="stretch")

        st.subheader("Settle up")
        settlements = compute_settlements(balances)
        if not settlements:
            st.success("Everyone is settled up 🎉")
        for frm, to, amt in settlements:
            st.markdown(f"- **{names[frm]}** pays **{names[to]}** {money(amt, cur)}")


# ---------- people ----------

with tab_people:
    with st.form(k("add_person"), clear_on_submit=True):
        col_n, col_btn = st.columns([4, 1], vertical_alignment="bottom")
        new_person = col_n.text_input("Add a person", placeholder="Name")
        if col_btn.form_submit_button("Add", width="stretch"):
            name = new_person.strip()
            if name:
                try:
                    storage.add_person(trip_id, name)
                    flash(f"Added **{name}**.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"{name} is already on this trip.")

    if not people:
        st.caption("No one added yet.")
    for p in people:
        col_name, col_del = st.columns([5, 1])
        col_name.write(f"👤 {p['name']}")
        if col_del.button("Remove", key=f"del_person_{p['id']}"):
            if storage.person_in_use(p["id"]):
                flash(f"{p['name']} is part of existing expenses — delete those expenses first.", "warning")
            else:
                storage.delete_person(p["id"])
                flash(f"Removed **{p['name']}**.")
            st.rerun()


# ---------- trip settings ----------

with tab_settings:
    with st.form(k("settings")):
        new_name = st.text_input("Trip name", value=trip["name"])
        new_cur = st.selectbox("Currency", CURRENCIES,
                               index=CURRENCIES.index(cur) if cur in CURRENCIES else 0)
        if st.form_submit_button("Save"):
            try:
                storage.rename_trip(trip_id, new_name.strip() or trip["name"], new_cur)
                flash("Trip updated.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Another trip already has that name.")

    st.divider()
    st.subheader("Danger zone")
    confirm = st.checkbox(f"Yes, permanently delete “{trip['name']}” and all its expenses", key=k("confirm_del"))
    if st.button("Delete trip", disabled=not confirm):
        storage.delete_trip(trip_id)
        select_trip(None)
        flash(f"Deleted trip **{trip['name']}**.")
        st.rerun()
