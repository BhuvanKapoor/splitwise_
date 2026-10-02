"""Picks the storage backend: Google Sheets when configured, otherwise local SQLite.

Google Sheets is used when `.streamlit/secrets.toml` (or the Streamlit Cloud
secrets box) has [google_sheets] spreadsheet = "<sheet URL or key>" plus the
service account key, either as a [gcp_service_account] section or pasted as JSON
in [google_sheets] service_account_json. See README.md.
"""

from __future__ import annotations

import json

from errors import DuplicateError  # noqa: F401  (re-exported for the app)

_backend = None
BACKEND_NAME = "SQLite"


def _sheets_config():
    try:
        import streamlit as st

        sheets = st.secrets.get("google_sheets", {})
        sheet = sheets.get("spreadsheet")
        account = st.secrets.get("gcp_service_account")
        if not account and sheets.get("service_account_json"):
            # The JSON key file pasted as-is, which is easier than converting it to TOML.
            account = json.loads(sheets["service_account_json"])
    except FileNotFoundError:  # no secrets file
        return None
    return (account, sheet) if account and sheet else None


def _get():
    global _backend, BACKEND_NAME
    if _backend is None:
        config = _sheets_config()
        if config:
            import db_sheets

            _backend = db_sheets.connect(*config)
            BACKEND_NAME = "Google Sheets"
        else:
            import db_sqlite

            _backend = db_sqlite
            BACKEND_NAME = "SQLite"
    return _backend


def init_db():
    return _get().init_db()


def list_trips():
    return _get().list_trips()


def create_trip(name, currency):
    return _get().create_trip(name, currency)


def rename_trip(trip_id, name, currency):
    return _get().rename_trip(trip_id, name, currency)


def delete_trip(trip_id):
    return _get().delete_trip(trip_id)


def list_people(trip_id):
    return _get().list_people(trip_id)


def add_person(trip_id, name):
    return _get().add_person(trip_id, name)


def person_in_use(person_id):
    return _get().person_in_use(person_id)


def delete_person(person_id):
    return _get().delete_person(person_id)


def list_expenses(trip_id):
    return _get().list_expenses(trip_id)


def add_expense(trip_id, description, amount, payer_id, split_mode, shares, spent_on):
    return _get().add_expense(trip_id, description, amount, payer_id, split_mode, shares, spent_on)


def delete_expense(expense_id):
    return _get().delete_expense(expense_id)
