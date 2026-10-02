"""Simple username/password login, configured in Streamlit secrets:

    [auth]
    username = "admin"
    password = "..."

Without an [auth] section the app runs without a login.
"""

from __future__ import annotations

import hmac
import time

import streamlit as st


def _credentials() -> tuple[str, str] | None:
    try:
        auth = st.secrets.get("auth", {})
    except FileNotFoundError:  # no secrets file
        return None
    username, password = auth.get("username"), auth.get("password")
    return (str(username), str(password)) if username and password else None


def _matches(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode(), expected.encode())


def require_login() -> None:
    """Show the login page and stop the script until the user has signed in."""
    creds = _credentials()
    if creds is None:
        st.session_state["_auth_disabled"] = True
        return
    if st.session_state.get("logged_in_as"):
        return

    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.title("💸 Trip Splitter")
        st.subheader("Log in")
        with st.form("login"):
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Log in", type="primary", width="stretch")
        if submitted:
            # Check both fields every time so a wrong username takes as long as a wrong password.
            ok_user = _matches(username.strip(), creds[0])
            ok_pass = _matches(password, creds[1])
            if ok_user and ok_pass:
                st.session_state["logged_in_as"] = creds[0]
                st.rerun()
            time.sleep(1)  # slow down password guessing
            st.error("Wrong username or password.")
    st.stop()


def sidebar_account() -> None:
    """Logged-in user and a log-out button, for the sidebar."""
    if st.session_state.get("_auth_disabled"):
        st.caption("🔓 Login is off (no `[auth]` in secrets)")
        return
    user = st.session_state.get("logged_in_as")
    if user:
        col_user, col_btn = st.columns([3, 2], vertical_alignment="center")
        col_user.caption(f"👤 Logged in as **{user}**")
        if col_btn.button("Log out", width="stretch"):
            st.session_state.clear()
            st.rerun()
