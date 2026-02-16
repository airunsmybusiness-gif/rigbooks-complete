"""
RigBooks Auth Module — Password login for multi-user access.

Roles:
  - admin: Full access (Lily). Can create/delete users, edit all data.
  - viewer: Read + export access (accountant). Can view all pages, download reports.
"""
import logging
from typing import Optional

import bcrypt
import streamlit as st

from helpers.database import create_user, get_user, list_users

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, AttributeError) as e:
        logger.error("Password verification failed: %s", e)
        return False


def authenticate(username: str, password: str) -> Optional[dict]:
    """Authenticate a user. Returns user dict or None."""
    user = get_user(username)
    if user and verify_password(password, user["password_hash"]):
        logger.info("User '%s' authenticated successfully", username)
        return {"id": user["id"], "username": user["username"],
                "role": user["role"], "full_name": user["full_name"]}
    logger.warning("Failed login attempt for username: '%s'", username)
    return None


def ensure_admin_exists() -> None:
    """Create default admin account if no users exist."""
    users = list_users()
    if not users:
        pw_hash = hash_password("rigbooks2025")
        create_user("lily", pw_hash, "admin", "Lilibeth Sejera")
        logger.info("Created default admin user 'lily'")


def ensure_accountant_exists() -> None:
    """Create accountant viewer account if it doesn't exist."""
    user = get_user("accountant")
    if not user:
        pw_hash = hash_password("capebretoner2025")
        create_user("accountant", pw_hash, "viewer", "Accountant")
        logger.info("Created default accountant user")


def login_page() -> bool:
    """Render login form. Returns True if user is authenticated."""
    if "authenticated" in st.session_state and st.session_state.authenticated:
        return True

    st.markdown(
        """
        <div style="text-align: center; padding: 2rem 0;">
            <h1>🛢️ RigBooks</h1>
            <p style="color: #888;">Cape Bretoner's Oilfield Services Ltd.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter your username")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        submitted = st.form_submit_button("🔐 Log In", type="primary", use_container_width=True)

        if submitted:
            if not username or not password:
                st.error("Please enter both username and password.")
                return False

            user = authenticate(username, password)
            if user:
                st.session_state.authenticated = True
                st.session_state.current_user = user
                st.rerun()
            else:
                st.error("Invalid username or password.")
                return False

    st.markdown("---")
    st.caption("Contact Lily for login credentials.")
    return False


def logout_button() -> None:
    """Render logout button in sidebar."""
    user = st.session_state.get("current_user", {})
    role_label = "👑 Admin" if user.get("role") == "admin" else "👁️ Viewer"
    st.sidebar.markdown(f"**Logged in:** {user.get('full_name', 'Unknown')} ({role_label})")

    if st.sidebar.button("🚪 Logout"):
        st.session_state.authenticated = False
        st.session_state.current_user = {}
        st.rerun()


def is_admin() -> bool:
    """Check if current user is admin."""
    return st.session_state.get("current_user", {}).get("role") == "admin"


def require_admin() -> None:
    """Stop page execution if user is not admin."""
    if not is_admin():
        st.warning("⚠️ Admin access required for this action.")
        st.stop()
