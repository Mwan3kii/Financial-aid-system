"""
Unit tests for models.py
Run with:  pytest test_models.py -v
Install deps first:  pip install pytest pytest-mock
"""

import pytest
from unittest.mock import MagicMock, patch, call


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_mysql(monkeypatch):
    """
    Patches the `mysql` object in models so no real DB connection is needed.
    Every test automatically gets this — you never touch a real database.
    """
    import models  # import your actual models file

    mock_mysql_obj = MagicMock()
    monkeypatch.setattr(models, "mysql", mock_mysql_obj)
    return mock_mysql_obj


def make_cursor(mock_mysql, rows=None, one=None, lastrowid=1):
    """
    Helper: configures the fake cursor that mysql.connection.cursor() returns.

    rows    – list of dicts returned by fetchall()
    one     – dict returned by fetchone()
    """
    cur = MagicMock()
    cur.fetchall.return_value = rows or []
    cur.fetchone.return_value = one
    cur.lastrowid = lastrowid
    mock_mysql.connection.cursor.return_value = cur
    return cur


# ─── Users ────────────────────────────────────────────────────────────────────

class TestGetUserByEmail:
    def test_returns_user_when_found(self, mock_mysql):
        import models
        fake_user = {"user_id": 1, "email": "alice@example.com", "role": "STUDENT"}
        make_cursor(mock_mysql, one=fake_user)

        result = models.get_user_by_email("alice@example.com")

        assert result == fake_user
        assert result["role"] == "STUDENT"

    def test_returns_none_when_not_found(self, mock_mysql):
        import models
        make_cursor(mock_mysql, one=None)

        result = models.get_user_by_email("nobody@example.com")

        assert result is None

    def test_cursor_closed_after_call(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql, one=None)
        models.get_user_by_email("x@x.com")
        cur.close.assert_called_once()


class TestGetUserById:
    def test_returns_user_when_found(self, mock_mysql):
        import models
        fake_user = {"user_id": 5, "email": "bob@example.com", "role": "OFFICER"}
        make_cursor(mock_mysql, one=fake_user)

        result = models.get_user_by_id(5)

        assert result["user_id"] == 5
        assert result["role"] == "OFFICER"

    def test_returns_none_when_not_found(self, mock_mysql):
        import models
        make_cursor(mock_mysql, one=None)

        result = models.get_user_by_id(999)

        assert result is None


class TestGetAllUsers:
    def test_returns_list_of_users(self, mock_mysql):
        import models
        fake_users = [
            {"user_id": 1, "first_name": "Alice"},
            {"user_id": 2, "first_name": "Bob"},
        ]
        make_cursor(mock_mysql, rows=fake_users)

        result = models.get_all_users()

        assert len(result) == 2
        assert result[0]["first_name"] == "Alice"

    def test_returns_empty_list_when_no_users(self, mock_mysql):
        import models
        make_cursor(mock_mysql, rows=[])

        result = models.get_all_users()

        assert result == []


class TestCreateUser:
    def test_returns_new_user_id(self, mock_mysql):
        import models
        make_cursor(mock_mysql, lastrowid=42)

        user_id = models.create_user("Alice", "Smith", "a@b.com", "hashed_pw", "STUDENT")

        assert user_id == 42

    def test_commits_transaction(self, mock_mysql):
        import models
        make_cursor(mock_mysql, lastrowid=1)

        models.create_user("A", "B", "a@b.com", "pw", "STUDENT")

        mock_mysql.connection.commit.assert_called_once()


class TestDeleteUser:
    def test_executes_delete_and_commits(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.delete_user(7)

        cur.execute.assert_called_once()
        mock_mysql.connection.commit.assert_called_once()

    def test_cursor_closed(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)
        models.delete_user(7)
        cur.close.assert_called_once()


class TestUpdateUser:
    def test_executes_update_with_correct_args(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.update_user(1, "Alice", "Smith", "alice@x.com", "ADMIN")

        args = cur.execute.call_args[0][1]   # positional args passed to execute()
        assert "Alice" in args
        assert "ADMIN" in args
        assert 1 in args

    def test_commits(self, mock_mysql):
        import models
        make_cursor(mock_mysql)
        models.update_user(1, "A", "B", "a@b.com", "STUDENT")
        mock_mysql.connection.commit.assert_called_once()


class TestUpdateUserStatus:
    def test_sets_active(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.update_user_status(3, True)

        args = cur.execute.call_args[0][1]
        assert True in args
        assert 3 in args

    def test_sets_inactive(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.update_user_status(3, False)

        args = cur.execute.call_args[0][1]
        assert False in args


class TestCountUsersByRole:
    def test_returns_dict_keyed_by_role(self, mock_mysql):
        import models
        make_cursor(mock_mysql, rows=[
            {"role": "STUDENT", "total": 10},
            {"role": "OFFICER", "total": 3},
        ])

        result = models.count_users_by_role()

        assert result == {"STUDENT": 10, "OFFICER": 3}

    def test_returns_empty_dict_when_no_rows(self, mock_mysql):
        import models
        make_cursor(mock_mysql, rows=[])

        result = models.count_users_by_role()

        assert result == {}


# ─── Foreign Students ─────────────────────────────────────────────────────────

class TestGetStudentByUserId:
    def test_returns_student_when_found(self, mock_mysql):
        import models
        fake = {"student_id": 2, "passport_number": "A1234", "first_name": "Alice"}
        make_cursor(mock_mysql, one=fake)

        result = models.get_student_by_user_id(2)

        assert result["passport_number"] == "A1234"

    def test_returns_none_when_missing(self, mock_mysql):
        import models
        make_cursor(mock_mysql, one=None)

        result = models.get_student_by_user_id(999)

        assert result is None


class TestUpsertForeignStudent:
    def test_inserts_when_student_does_not_exist(self, mock_mysql):
        import models
        cur = MagicMock()
        # First call (SELECT) returns None → student does not exist
        cur.fetchone.return_value = None
        cur.lastrowid = 1
        mock_mysql.connection.cursor.return_value = cur

        models.upsert_foreign_student(10, passport_number="X999", nationality="Kenyan")

        # Should have called execute twice: SELECT then INSERT
        assert cur.execute.call_count == 2
        insert_sql = cur.execute.call_args_list[1][0][0]
        assert "INSERT" in insert_sql.upper()

    def test_updates_when_student_exists(self, mock_mysql):
        import models
        cur = MagicMock()
        cur.fetchone.return_value = {"student_id": 10}
        mock_mysql.connection.cursor.return_value = cur

        models.upsert_foreign_student(10, passport_number="X999")

        assert cur.execute.call_count == 2
        update_sql = cur.execute.call_args_list[1][0][0]
        assert "UPDATE" in update_sql.upper()

    def test_skips_none_values_on_update(self, mock_mysql):
        import models
        cur = MagicMock()
        cur.fetchone.return_value = {"student_id": 10}
        mock_mysql.connection.cursor.return_value = cur

        models.upsert_foreign_student(10, passport_number="X999", nationality=None)

        update_sql = cur.execute.call_args_list[1][0][0]
        # nationality=None should be excluded from SET clause
        assert "nationality" not in update_sql


# ─── Applications ─────────────────────────────────────────────────────────────

class TestCreateApplication:
    def test_returns_new_app_id(self, mock_mysql):
        import models
        make_cursor(mock_mysql, lastrowid=99)

        app_id = models.create_application(student_id=1, amount=5000, purpose="Tuition")

        assert app_id == 99

    def test_commits(self, mock_mysql):
        import models
        make_cursor(mock_mysql, lastrowid=1)
        models.create_application(1, 5000, "Tuition")
        mock_mysql.connection.commit.assert_called_once()


class TestGetApplicationsByStudent:
    def test_returns_list_for_student(self, mock_mysql):
        import models
        fake_apps = [
            {"application_id": 1, "student_id": 2, "status": "SUBMITTED"},
        ]
        make_cursor(mock_mysql, rows=fake_apps)

        result = models.get_applications_by_student(2)

        assert len(result) == 1
        assert result[0]["status"] == "SUBMITTED"

    def test_returns_empty_list_when_none(self, mock_mysql):
        import models
        make_cursor(mock_mysql, rows=[])

        result = models.get_applications_by_student(2)

        assert result == []


class TestGetApplicationById:
    def test_returns_application(self, mock_mysql):
        import models
        fake = {"application_id": 5, "status": "VERIFIED"}
        make_cursor(mock_mysql, one=fake)

        result = models.get_application_by_id(5)

        assert result["application_id"] == 5

    def test_returns_none_for_missing(self, mock_mysql):
        import models
        make_cursor(mock_mysql, one=None)

        result = models.get_application_by_id(999)

        assert result is None


class TestGetPendingApplications:
    def test_returns_pending_list(self, mock_mysql):
        import models
        fake = [{"application_id": 1, "status": "SUBMITTED"}]
        make_cursor(mock_mysql, rows=fake)

        result = models.get_pending_applications()

        assert result[0]["status"] == "SUBMITTED"


class TestGetVerifiedApplications:
    def test_returns_verified_list(self, mock_mysql):
        import models
        fake = [{"application_id": 2, "status": "VERIFIED"}]
        make_cursor(mock_mysql, rows=fake)

        result = models.get_verified_applications()

        assert result[0]["status"] == "VERIFIED"


class TestGetAllApplications:
    def test_returns_all(self, mock_mysql):
        import models
        make_cursor(mock_mysql, rows=[{"application_id": 1}, {"application_id": 2}])

        result = models.get_all_applications()

        assert len(result) == 2


class TestUpdateApplicationStatus:
    def test_with_officer_id_includes_officer(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.update_application_status(1, "UNDER_REVIEW", "Looks good", officer_id=7)

        sql = cur.execute.call_args[0][0]
        assert "assigned_officer_id" in sql

    def test_without_officer_id_excludes_officer(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.update_application_status(1, "UNDER_REVIEW")

        sql = cur.execute.call_args[0][0]
        assert "assigned_officer_id" not in sql

    def test_commits(self, mock_mysql):
        import models
        make_cursor(mock_mysql)
        models.update_application_status(1, "VERIFIED")
        mock_mysql.connection.commit.assert_called_once()


class TestDeleteApplication:
    def test_executes_and_commits(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.delete_application(3)

        cur.execute.assert_called_once()
        mock_mysql.connection.commit.assert_called_once()


class TestCountApplicationsByStatus:
    def test_returns_dict(self, mock_mysql):
        import models
        make_cursor(mock_mysql, rows=[
            {"status": "SUBMITTED", "total": 5},
            {"status": "APPROVED", "total": 2},
        ])

        result = models.count_applications_by_status()

        assert result == {"SUBMITTED": 5, "APPROVED": 2}


class TestSaveAssessment:
    def test_approved_outcome_sets_approved_status(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.save_assessment(1, provider_id=2,
                               decision_outcome="APPROVED",
                               approved_amount=3000,
                               justification="Looks good")

        args = cur.execute.call_args[0][1]
        # final_status should be 'APPROVED'
        assert "APPROVED" in args

    def test_rejected_outcome_sets_rejected_status(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.save_assessment(1, provider_id=2,
                               decision_outcome="REJECTED",
                               approved_amount=0,
                               justification="Insufficient docs")

        args = cur.execute.call_args[0][1]
        assert "REJECTED" in args


# ─── Documents ────────────────────────────────────────────────────────────────

class TestCreateDocument:
    def test_returns_doc_id(self, mock_mysql):
        import models
        make_cursor(mock_mysql, lastrowid=77)

        doc_id = models.create_document(
            application_id=1,
            document_type="PASSPORT",
            file_name="passport.pdf",
            file_size=204800,
            storage_path="/uploads/passport.pdf"
        )

        assert doc_id == 77

    def test_commits(self, mock_mysql):
        import models
        make_cursor(mock_mysql, lastrowid=1)
        models.create_document(1, "PASSPORT", "p.pdf", 1024, "/path")
        mock_mysql.connection.commit.assert_called_once()


class TestGetDocumentsByApplication:
    def test_returns_docs(self, mock_mysql):
        import models
        fake_docs = [{"document_id": 1, "document_type": "PASSPORT"}]
        make_cursor(mock_mysql, rows=fake_docs)

        result = models.get_documents_by_application(1)

        assert result[0]["document_type"] == "PASSPORT"

    def test_returns_empty_when_none(self, mock_mysql):
        import models
        make_cursor(mock_mysql, rows=[])

        result = models.get_documents_by_application(1)

        assert result == []


class TestUpdateDocumentStatus:
    def test_executes_and_commits(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.update_document_status(5, "VERIFIED", officer_id=2, rejection_reason="")

        cur.execute.assert_called_once()
        mock_mysql.connection.commit.assert_called_once()

    def test_passes_rejection_reason(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.update_document_status(5, "REJECTED", officer_id=2,
                                       rejection_reason="Blurry scan")

        args = cur.execute.call_args[0][1]
        assert "Blurry scan" in args


# ─── Notifications ────────────────────────────────────────────────────────────

class TestCreateNotification:
    def test_returns_notif_id(self, mock_mysql):
        import models
        make_cursor(mock_mysql, lastrowid=11)

        notif_id = models.create_notification(
            application_id=1, sender_id=2, recipient_id=3,
            sender_role="OFFICER", notif_type="STATUS_UPDATE",
            subject="Your app", message="It moved."
        )

        assert notif_id == 11

    def test_commits(self, mock_mysql):
        import models
        make_cursor(mock_mysql, lastrowid=1)
        models.create_notification(1, 2, 3, "OFFICER", "INFO", "Sub", "Msg")
        mock_mysql.connection.commit.assert_called_once()


class TestGetNotificationsByRecipient:
    def test_returns_list(self, mock_mysql):
        import models
        fake = [{"notification_id": 1, "subject": "Hello"}]
        make_cursor(mock_mysql, rows=fake)

        result = models.get_notifications_by_recipient(3)

        assert result[0]["subject"] == "Hello"

    def test_returns_empty_list(self, mock_mysql):
        import models
        make_cursor(mock_mysql, rows=[])

        result = models.get_notifications_by_recipient(3)

        assert result == []


class TestMarkNotificationRead:
    def test_executes_and_commits(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.mark_notification_read(1)

        cur.execute.assert_called_once()
        mock_mysql.connection.commit.assert_called_once()


class TestCountUnreadNotifications:
    def test_returns_count(self, mock_mysql):
        import models
        make_cursor(mock_mysql, one={"total": 4})

        result = models.count_unread_notifications(user_id=3)

        assert result == 4

    def test_returns_zero_when_none(self, mock_mysql):
        import models
        make_cursor(mock_mysql, one={"total": 0})

        result = models.count_unread_notifications(user_id=3)

        assert result == 0


# ─── Officer & Provider ───────────────────────────────────────────────────────

class TestCreateOfficer:
    def test_inserts_and_commits(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.create_officer(10, "B-001", "Nairobi Embassy", "Visas")

        cur.execute.assert_called_once()
        mock_mysql.connection.commit.assert_called_once()

    def test_passes_correct_args(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.create_officer(10, "B-001", "Nairobi Embassy", "Visas")

        args = cur.execute.call_args[0][1]
        assert 10 in args
        assert "B-001" in args
        assert "Nairobi Embassy" in args
        assert "Visas" in args


class TestCreateProvider:
    def test_inserts_and_commits(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.create_provider(20, "KCB Foundation", "BANK")

        cur.execute.assert_called_once()
        mock_mysql.connection.commit.assert_called_once()

    def test_passes_correct_args(self, mock_mysql):
        import models
        cur = make_cursor(mock_mysql)

        models.create_provider(20, "KCB Foundation", "BANK")

        args = cur.execute.call_args[0][1]
        assert 20 in args
        assert "KCB Foundation" in args
        assert "BANK" in args