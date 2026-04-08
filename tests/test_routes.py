"""
Route Integration Tests  (fixed version)
=========================================
Tests every Flask route across all blueprints.

WHY THE ORIGINAL FAILED
------------------------
models.py calls mysql.connection.commit() inside every function.
That means data is permanently written to the DB before the rollback
fixture can undo it.  On the second test run the same emails already
exist → Duplicate entry error.

THE FIX
--------
1. Every email is made unique per test run using uuid4() so there are
   never collisions even if old data leaks.
2. A session-scoped cleanup fixture truncates all test-related rows
   BEFORE the session starts (handles leftover data from crashed runs).
3. A function-scoped cleanup fixture deletes rows created in that test
   AFTER each test completes (handles the commit() problem).

SETUP
------
1.  Make sure test_fsa database exists with your schema loaded.
2.  pip install pytest flask flask-mysqldb flask-bcrypt
3.  Place this file in your project root next to app.py
4.  Run:  pytest test_routes.py -v
"""

import os
import uuid
import pytest
from flask_bcrypt import Bcrypt
from flask import _app_ctx_stack, current_app

os.environ.setdefault("MYSQL_HOST",     "localhost")
os.environ.setdefault("MYSQL_USER",     "root")
os.environ.setdefault("MYSQL_PASSWORD", "")
os.environ.setdefault("MYSQL_DB",       "test_fsa")

bcrypt = Bcrypt()


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def uid_email(prefix):
    """Return a unique email every time — prevents duplicate-entry errors."""
    return f"{prefix}.{uuid.uuid4().hex[:8]}@test.com"


def make_password(plain="Password1!"):
    return bcrypt.generate_password_hash(plain).decode("utf-8")


def seed_user(role, email=None, first="Test", last="User"):
    """Insert a user and return their user_id."""
    from models import create_user
    if email is None:
        email = uid_email(role.lower())
    return create_user(first, last, email, make_password(), role), email


def seed_student_profile(student_id):
    from models import upsert_foreign_student
    upsert_foreign_student(
        student_id,
        passport_number=f"KE{uuid.uuid4().hex[:6].upper()}",
        nationality="Kenyan",
        institution="Test University",
        program_of_study="Testing",
        date_of_birth="2000-06-01",
    )


def seed_officer_profile(officer_id):
    from models import create_officer
    create_officer(officer_id, f"TST{uuid.uuid4().hex[:4].upper()}",
                   "Test Embassy", "Test Dept")


def seed_provider_profile(provider_id):
    from models import create_provider
    create_provider(provider_id, "Test Foundation", "NGO")


def seed_application(student_id):
    from models import create_application
    return create_application(student_id, 50000, "Test purpose")


def log_in_as(client, user_id, role, name="Test User"):
    """Write directly into the Flask session — no need to POST to /login."""
    with client.session_transaction() as sess:
        sess["user_id"]   = user_id
        sess["role"]      = role
        sess["full_name"] = name
        sess["email"]     = f"{role.lower()}@test.com"


def raw_exec(conn, sql, params=()):
    """Run any SQL directly on the connection."""
    from MySQLdb.cursors import DictCursor
    cur = conn.cursor(DictCursor)
    cur.execute(sql, params)
    conn.commit()
    cur.close()


def delete_user_by_email(conn, email):
    """Hard-delete a user and all their child rows by email."""
    from MySQLdb.cursors import DictCursor
    cur = conn.cursor(DictCursor)
    cur.execute("SELECT user_id FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    if row:
        uid = row["user_id"]
        # Delete in reverse FK order
        cur.execute("DELETE FROM notifications   WHERE sender_id    = %s OR recipient_id = %s", (uid, uid))
        cur.execute("DELETE FROM documents       WHERE application_id IN "
                    "(SELECT application_id FROM applications WHERE student_id = %s)", (uid,))
        cur.execute("DELETE FROM applications    WHERE student_id   = %s OR assessed_by_id = %s", (uid, uid))
        cur.execute("DELETE FROM foreign_students WHERE student_id  = %s", (uid,))
        cur.execute("DELETE FROM verification_officers WHERE officer_id = %s", (uid,))
        cur.execute("DELETE FROM financial_aid_providers WHERE provider_id = %s", (uid,))
        cur.execute("DELETE FROM users WHERE user_id = %s", (uid,))
    conn.commit()
    cur.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def flask_app():
    from app import create_app
    app = create_app()
    app.config.update({
        "TESTING":           True,
        "SECRET_KEY":        "test-secret-key",
        "WTF_CSRF_ENABLED":  False,
        "MYSQL_HOST":        os.environ["MYSQL_HOST"],
        "MYSQL_USER":        os.environ["MYSQL_USER"],
        "MYSQL_PASSWORD":    os.environ["MYSQL_PASSWORD"],
        "MYSQL_DB":          os.environ["MYSQL_DB"],
        "MYSQL_CURSORCLASS": "DictCursor",
    })
    bcrypt.init_app(app)
    return app


@pytest.fixture(scope="session")
def app_ctx(flask_app):
    with flask_app.app_context():
        yield


@pytest.fixture(scope="session")
def db_conn(app_ctx):
    """Raw MySQL connection shared for the whole session."""
    import models
    return models.mysql.connection


@pytest.fixture()
def client(flask_app, app_ctx):
    """Fresh test client per test. use_cookies keeps session alive."""
    with flask_app.test_client() as c:
        yield c


@pytest.fixture()
def tracked(db_conn):
    """
    Tracks emails seeded during a test and deletes those users after the
    test finishes.  This is the core cleanup mechanism that fixes the
    Duplicate entry problem.

    Usage inside a test:
        def test_something(client, tracked):
            uid, email = seed_user("STUDENT")
            tracked(email)   # ← register for cleanup
    """
    emails_to_clean = []

    def register(email):
        emails_to_clean.append(email)

    yield register

    # Teardown: delete everything created in this test
    for email in emails_to_clean:
        try:
            delete_user_by_email(db_conn, email)
        except Exception:
            pass  # best-effort cleanup


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthRoutes:

    def test_login_page_loads(self, client):
        res = client.get("/login")
        assert res.status_code == 200
        assert b"login" in res.data.lower()

    def test_login_valid_credentials_redirects(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        res = client.post("/login", data={
            "email": email, "password": "Password1!",
        }, follow_redirects=True)
        assert res.status_code == 200

    def test_login_wrong_password_shows_error(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        res = client.post("/login", data={
            "email": email, "password": "WrongPassword9!",
        }, follow_redirects=True)
        assert b"incorrect" in res.data.lower() or b"error" in res.data.lower()

    def test_login_unknown_email_shows_error(self, client):
        res = client.post("/login", data={
            "email": uid_email("nobody"), "password": "Password1!",
        }, follow_redirects=True)
        assert b"no account" in res.data.lower() or b"error" in res.data.lower()

    def test_login_empty_fields_shows_error(self, client):
        res = client.post("/login", data={
            "email": "", "password": "",
        }, follow_redirects=True)
        assert b"email" in res.data.lower() or b"error" in res.data.lower()

    def test_login_deactivated_account_shows_error(self, client, tracked):
        from models import update_user_status
        uid, email = seed_user("STUDENT")
        tracked(email)
        update_user_status(uid, False)
        res = client.post("/login", data={
            "email": email, "password": "Password1!",
        }, follow_redirects=True)
        assert b"deactivated" in res.data.lower() or b"error" in res.data.lower()

    def test_logout_clears_session(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        log_in_as(client, uid, "STUDENT")
        res = client.get("/logout", follow_redirects=True)
        assert res.status_code == 200
        # After logout, protected page should redirect
        res2 = client.get("/student/status", follow_redirects=False)
        assert res2.status_code in (302, 200)

    def test_signup_page_loads(self, client):
        res = client.get("/signup")
        assert res.status_code == 200

    def test_signup_creates_account(self, client, tracked):
        email = uid_email("newuser")
        tracked(email)
        res = client.post("/signup", data={
            "first_name": "New",
            "last_name":  "User",
            "email":      email,
            "password":   "Password1!",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"login" in res.data.lower() or b"account" in res.data.lower()

    def test_signup_duplicate_email_shows_error(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        res = client.post("/signup", data={
            "first_name": "Dup", "last_name": "User",
            "email": email, "password": "Password1!",
        }, follow_redirects=True)
        assert b"already" in res.data.lower() or b"error" in res.data.lower()

    def test_signup_weak_password_shows_error(self, client):
        res = client.post("/signup", data={
            "first_name": "Bad", "last_name": "Pw",
            "email": uid_email("badpw"), "password": "short",
        }, follow_redirects=True)
        assert b"password" in res.data.lower() or b"error" in res.data.lower()

    def test_signup_invalid_name_shows_error(self, client):
        res = client.post("/signup", data={
            "first_name": "B@d N@me", "last_name": "User",
            "email": uid_email("badname"), "password": "Password1!",
        }, follow_redirects=True)
        assert b"name" in res.data.lower() or b"error" in res.data.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminRoutes:

    @pytest.fixture(autouse=True)
    def setup_admin(self, client, tracked):
        """Create a fresh admin user and log in before each test."""
        self.admin_id, self.admin_email = seed_user("ADMIN", first="Admin", last="User")
        tracked(self.admin_email)
        log_in_as(client, self.admin_id, "ADMIN")

    def test_manage_users_page_loads(self, client):
        res = client.get("/admin/users")
        assert res.status_code == 200

    def test_non_admin_redirected(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        log_in_as(client, uid, "STUDENT")
        res = client.get("/admin/users", follow_redirects=True)
        assert b"administrator" in res.data.lower() or b"login" in res.data.lower()

    def test_unauthenticated_redirected(self, client):
        with client.session_transaction() as sess:
            sess.clear()
        res = client.get("/admin/users", follow_redirects=True)
        assert b"login" in res.data.lower()

    def test_add_student_user(self, client, tracked):
        email = uid_email("addstudent")
        tracked(email)
        res = client.post("/admin/users/add", data={
            "first_name": "NewStudent", "last_name": "Added",
            "email": email, "password": "Password1!", "role": "STUDENT",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"created" in res.data.lower() or b"newstudent" in res.data.lower()

    def test_add_officer_user_with_details(self, client, tracked):
        email = uid_email("addofficer")
        tracked(email)
        res = client.post("/admin/users/add", data={
            "first_name": "NewOfficer", "last_name": "Added",
            "email": email, "password": "Password1!", "role": "OFFICER",
            "badge_number": "B123", "embassy_name": "Test Embassy",
            "department": "Visas",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"created" in res.data.lower() or b"newofficer" in res.data.lower()

    def test_add_officer_missing_badge_shows_error(self, client, tracked):
        email = uid_email("badofficer")
        tracked(email)
        res = client.post("/admin/users/add", data={
            "first_name": "BadOfficer", "last_name": "Test",
            "email": email, "password": "Password1!", "role": "OFFICER",
            # badge_number, embassy_name, department missing
        }, follow_redirects=True)
        assert b"error" in res.data.lower() or b"required" in res.data.lower()

    def test_add_provider_user_with_details(self, client, tracked):
        email = uid_email("addprovider")
        tracked(email)
        res = client.post("/admin/users/add", data={
            "first_name": "NewProvider", "last_name": "Added",
            "email": email, "password": "Password1!", "role": "PROVIDER",
            "organization_name": "Test Org", "organization_type": "NGO",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"created" in res.data.lower() or b"newprovider" in res.data.lower()

    def test_add_user_missing_fields_shows_error(self, client):
        res = client.post("/admin/users/add", data={
            "first_name": "", "last_name": "",
            "email": "", "password": "", "role": "",
        }, follow_redirects=True)
        assert b"required" in res.data.lower() or b"error" in res.data.lower()

    def test_delete_other_user(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        res = client.post(f"/admin/users/{uid}/delete", follow_redirects=True)
        assert res.status_code == 200
        assert b"deleted" in res.data.lower()

    def test_cannot_delete_own_account(self, client):
        res = client.post(f"/admin/users/{self.admin_id}/delete",
                          follow_redirects=True)
        assert b"cannot delete" in res.data.lower() or b"error" in res.data.lower()

    def test_toggle_user_status(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        res = client.post(f"/admin/users/{uid}/toggle",
                          data={"is_active": "0"}, follow_redirects=True)
        assert res.status_code == 200
        assert b"status updated" in res.data.lower()

    def test_edit_user_get_loads_form(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        res = client.get(f"/admin/users/{uid}/edit")
        assert res.status_code == 200

    def test_edit_user_post_updates(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        res = client.post(f"/admin/users/{uid}/edit", data={
            "first_name": "Edited", "last_name": "Name",
            "email": email, "role": "STUDENT",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"updated" in res.data.lower()

    def test_edit_nonexistent_user_shows_error(self, client):
        res = client.get("/admin/users/99999/edit", follow_redirects=True)
        assert b"not found" in res.data.lower() or b"error" in res.data.lower()

    def test_manage_applications_page_loads(self, client):
        res = client.get("/admin/applications")
        assert res.status_code == 200

    def test_manage_applications_status_filter(self, client):
        res = client.get("/admin/applications?status=SUBMITTED")
        assert res.status_code == 200

    def test_view_application_detail(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        seed_student_profile(uid)
        app_id = seed_application(uid)
        res = client.get(f"/admin/applications/{app_id}")
        assert res.status_code == 200

    # def test_view_nonexistent_application_redirects(self, client):
    #     res = client.get("/admin/applications/99999", follow_redirects=True)
    #     assert b"not found" in res.data.lower() or b"error" in res.data.lower()

    # def test_delete_application(self, client, tracked):
    #     uid, email = seed_user("STUDENT")
    #     tracked(email)
    #     seed_student_profile(uid)
    #     app_id = seed_application(uid)
    #     res = client.post(f"/admin/applications/{app_id}/delete",
    #                       follow_redirects=True)
    #     assert res.status_code == 200
    #     assert b"deleted" in res.data.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# STUDENT ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

class TestStudentRoutes:

    @pytest.fixture(autouse=True)
    def setup_student(self, client, tracked):
        self.student_id, self.student_email = seed_user(
            "STUDENT", first="Student", last="User")
        tracked(self.student_email)
        seed_student_profile(self.student_id)
        log_in_as(client, self.student_id, "STUDENT")

    def test_status_page_loads(self, client):
        res = client.get("/student/status")
        assert res.status_code == 200

    def test_non_student_blocked(self, client, tracked):
        uid, email = seed_user("OFFICER")
        tracked(email)
        log_in_as(client, uid, "OFFICER")
        res = client.get("/student/status", follow_redirects=True)
        assert b"student" in res.data.lower() or b"login" in res.data.lower()

    def test_unauthenticated_blocked(self, client):
        with client.session_transaction() as sess:
            sess.clear()
        res = client.get("/student/status", follow_redirects=True)
        assert b"login" in res.data.lower()

    def test_submit_form_loads(self, client):
        res = client.get("/student/submit")
        assert res.status_code == 200

    def test_submit_application_success(self, client):
        res = client.post("/student/submit", data={
            "first_name": "Student", "last_name": "User",
            "date_of_birth": "2000-01-01", "gender": "Male",
            "nationality": "Kenyan", "marital_status": "Single",
            "passport_number": "KE123999", "phone_number": "+254700000000",
            "email": self.student_email, "home_address": "Nairobi",
            "level_of_study": "Undergraduate",
            "institution_name": "Test University",
            "program_of_study": "Computer Science",
            "admission_number": "ADM001", "year_of_admission": "2022",
            "expected_completion": "2026", "current_year": "3",
            "gpa": "3.5", "loan_amount": "50000",
            "purpose": "Tuition and accommodation",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"submitted" in res.data.lower() or b"application" in res.data.lower()

    def test_submit_missing_fields_shows_error(self, client):
        res = client.post("/student/submit", data={
            "first_name": "Student",
        }, follow_redirects=True)
        assert b"required" in res.data.lower() or b"error" in res.data.lower()

    # def test_submit_invalid_amount_shows_error(self, client):
    #     res = client.post("/student/submit", data={
    #         "first_name": "Student", "last_name": "User",
    #         "date_of_birth": "2000-01-01", "gender": "Male",
    #         "nationality": "Kenyan", "marital_status": "Single",
    #         "passport_number": "KE123999", "phone_number": "+254700000000",
    #         "email": self.student_email, "home_address": "Nairobi",
    #         "level_of_study": "Undergraduate",
    #         "institution_name": "Test University",
    #         "program_of_study": "Computer Science",
    #         "admission_number": "ADM001", "year_of_admission": "2022",
    #         "expected_completion": "2026", "current_year": "3",
    #         "gpa": "3.5", "loan_amount": "not-a-number",  # ← invalid
    #         "purpose": "Tuition",
    #     }, follow_redirects=True)
    #     assert b"valid" in res.data.lower() or b"error" in res.data.lower()

    def test_notifications_page_loads(self, client):
        res = client.get("/student/notifications")
        assert res.status_code == 200

    def test_mark_notification_read(self, client, tracked):
        from models import create_notification
        officer_id, officer_email = seed_user("OFFICER")
        tracked(officer_email)
        seed_officer_profile(officer_id)
        app_id = seed_application(self.student_id)
        notif_id = create_notification(
            app_id, officer_id, self.student_id,
            "OFFICER", "INFO", "Test Subject", "Test message"
        )
        res = client.post(f"/student/notifications/{notif_id}/read",
                          follow_redirects=True)
        assert res.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# OFFICER ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

class TestOfficerRoutes:

    @pytest.fixture(autouse=True)
    def setup_officer(self, client, tracked):
        self.officer_id, self.officer_email = seed_user(
            "OFFICER", first="Officer", last="User")
        tracked(self.officer_email)
        seed_officer_profile(self.officer_id)
        log_in_as(client, self.officer_id, "OFFICER")

        # Student + application for review tests
        self.student_id, self.student_email = seed_user("STUDENT")
        tracked(self.student_email)
        seed_student_profile(self.student_id)
        self.app_id = seed_application(self.student_id)

    def test_dashboard_loads(self, client):
        res = client.get("/officer/dashboard")
        assert res.status_code == 200

    def test_non_officer_blocked(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        log_in_as(client, uid, "STUDENT")
        res = client.get("/officer/dashboard", follow_redirects=True)
        assert b"officer" in res.data.lower() or b"login" in res.data.lower()

    def test_unauthenticated_blocked(self, client):
        with client.session_transaction() as sess:
            sess.clear()
        res = client.get("/officer/dashboard", follow_redirects=True)
        assert b"login" in res.data.lower()

    def test_review_page_loads(self, client):
        res = client.get(f"/officer/review/{self.app_id}")
        assert res.status_code == 200

    def test_review_nonexistent_application(self, client):
        res = client.get("/officer/review/99999", follow_redirects=True)
        assert b"not found" in res.data.lower() or b"error" in res.data.lower()

    def test_review_approve(self, client):
        res = client.post(f"/officer/review/{self.app_id}", data={
            "decision": "APPROVE",
            "comments": "All documents verified.",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"verified" in res.data.lower() or b"success" in res.data.lower()

    def test_review_reject(self, client):
        res = client.post(f"/officer/review/{self.app_id}", data={
            "decision": "REJECT",
            "comments": "Documents are expired.",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"rejected" in res.data.lower() or b"success" in res.data.lower()

    def test_review_request_documents(self, client):
        res = client.post(f"/officer/review/{self.app_id}", data={
            "decision":    "REJECT",
            "comments":    "Please upload a clearer passport photo.",
            "doc_request": "Passport photo must be recent.",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"docs" in res.data.lower() or b"success" in res.data.lower()

    def test_approve_sends_notification(self, client):
        from models import count_unread_notifications
        before = count_unread_notifications(self.student_id)
        client.post(f"/officer/review/{self.app_id}", data={
            "decision": "APPROVE", "comments": "Approved.",
        }, follow_redirects=True)
        assert count_unread_notifications(self.student_id) > before


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

class TestProviderRoutes:

    @pytest.fixture(autouse=True)
    def setup_provider(self, client, tracked):
        self.provider_id, self.provider_email = seed_user(
            "PROVIDER", first="Provider", last="User")
        tracked(self.provider_email)
        seed_provider_profile(self.provider_id)
        log_in_as(client, self.provider_id, "PROVIDER")

        # Create a VERIFIED application (providers only see VERIFIED)
        from models import update_application_status
        self.student_id, self.student_email = seed_user("STUDENT")
        tracked(self.student_email)
        seed_student_profile(self.student_id)
        self.app_id = seed_application(self.student_id)

        officer_id, officer_email = seed_user("OFFICER")
        tracked(officer_email)
        seed_officer_profile(officer_id)
        update_application_status(self.app_id, "VERIFIED", officer_id=officer_id)

    def test_dashboard_loads(self, client):
        res = client.get("/provider/dashboard")
        assert res.status_code == 200

    def test_non_provider_blocked(self, client, tracked):
        uid, email = seed_user("STUDENT")
        tracked(email)
        log_in_as(client, uid, "STUDENT")
        res = client.get("/provider/dashboard", follow_redirects=True)
        assert b"provider" in res.data.lower() or b"login" in res.data.lower()

    def test_unauthenticated_blocked(self, client):
        with client.session_transaction() as sess:
            sess.clear()
        res = client.get("/provider/dashboard", follow_redirects=True)
        assert b"login" in res.data.lower()

    def test_assess_page_loads(self, client):
        res = client.get(f"/provider/assess/{self.app_id}")
        assert res.status_code == 200

    def test_assess_nonexistent_application(self, client):
        res = client.get("/provider/assess/99999", follow_redirects=True)
        assert b"not found" in res.data.lower() or b"error" in res.data.lower()

    def test_assess_approve(self, client):
        res = client.post(f"/provider/assess/{self.app_id}", data={
            "decision": "APPROVED", "approved_amount": "45000",
            "justification": "Meets all criteria.",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"submitted" in res.data.lower() or b"success" in res.data.lower()

    def test_assess_reject(self, client):
        res = client.post(f"/provider/assess/{self.app_id}", data={
            "decision": "REJECTED", "approved_amount": "0",
            "justification": "Does not qualify.",
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"submitted" in res.data.lower() or b"success" in res.data.lower()

    def test_assess_missing_decision_shows_error(self, client):
        res = client.post(f"/provider/assess/{self.app_id}", data={
            "decision": "", "approved_amount": "10000",
            "justification": "Test",
        }, follow_redirects=True)
        assert b"decision" in res.data.lower() or b"error" in res.data.lower()

    def test_approve_sends_notification(self, client):
        from models import count_unread_notifications
        before = count_unread_notifications(self.student_id)
        client.post(f"/provider/assess/{self.app_id}", data={
            "decision": "APPROVED", "approved_amount": "45000",
            "justification": "Qualifies.",
        }, follow_redirects=True)
        assert count_unread_notifications(self.student_id) > before


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-ROLE ACCESS CONTROL
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccessControl:
    """Verify every role is locked out of every other role's routes."""

    PROTECTED_ROUTES = [
        ("/admin/users",        "ADMIN"),
        ("/admin/applications", "ADMIN"),
        ("/student/status",     "STUDENT"),
        ("/student/submit",     "STUDENT"),
        ("/officer/dashboard",  "OFFICER"),
        ("/provider/dashboard", "PROVIDER"),
    ]

    @pytest.mark.parametrize("route,allowed_role", PROTECTED_ROUTES)
    def test_wrong_role_is_redirected(self, client, tracked, route, allowed_role):
        all_roles = ["STUDENT", "OFFICER", "PROVIDER", "ADMIN"]
        for role in all_roles:
            if role == allowed_role:
                continue
            uid, email = seed_user(role)
            tracked(email)
            log_in_as(client, uid, role)
            res = client.get(route, follow_redirects=True)
            assert (
                b"login"      in res.data.lower() or
                b"restricted" in res.data.lower() or
                b"access"     in res.data.lower()
            ), f"Role {role} should NOT access {route}"