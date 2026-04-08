from flask_mysqldb import MySQL
from MySQLdb.cursors import DictCursor

mysql = MySQL()


# ─── Users ───────────────────────────────────────────────────────

def get_user_by_email(email):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    if user:
        user['role'] = user['role']  # ensure role is always uppercase
    return user


def get_user_by_id(user_id):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    if user:
        user['role'] = user['role']  # ensure role is always uppercase
    return user


def get_all_users():
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT u.user_id, u.first_name, u.last_name, u.email,
               u.role, u.is_active, u.created_at
        FROM users u
        ORDER BY u.created_at DESC
    """)
    users = cur.fetchall()
    cur.close()
    return users


def create_user(first_name, last_name, email, password_hash, role):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        INSERT INTO users (first_name, last_name, email, password_hash, role)
        VALUES (%s, %s, %s, %s, %s)
    """, (first_name, last_name, email, password_hash, role))
    mysql.connection.commit()
    user_id = cur.lastrowid
    cur.close()
    return user_id


def delete_user(user_id):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
    mysql.connection.commit()
    cur.close()

def update_user(user_id, first_name, last_name, email, role):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        UPDATE users
        SET first_name = %s,
            last_name  = %s,
            email      = %s,
            role       = %s
        WHERE user_id = %s
    """, (first_name, last_name, email, role, user_id))
    mysql.connection.commit()
    cur.close()


def update_user_status(user_id, is_active):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute(
        "UPDATE users SET is_active = %s WHERE user_id = %s",
        (is_active, user_id)
    )
    mysql.connection.commit()
    cur.close()


def count_users_by_role():
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT role, COUNT(*) as total
        FROM users
        GROUP BY role
    """)
    rows = cur.fetchall()
    cur.close()
    return {r['role']: r['total'] for r in rows}


# ─── Foreign Students ─────────────────────────────────────────────

def get_student_by_user_id(user_id):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT fs.*, u.first_name, u.last_name, u.email
        FROM foreign_students fs
        JOIN users u ON fs.student_id = u.user_id
        WHERE fs.student_id = %s
    """, (user_id,))
    student = cur.fetchone()
    cur.close()
    return student


# ─── Applications ─────────────────────────────────────────────────

def get_applications_by_student(student_id):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT a.*,
               fs.passport_number,
               fs.institution,
               fs.program_of_study,
               u.first_name, u.last_name,
               u_off.first_name AS officer_first,
               u_off.last_name  AS officer_last
        FROM applications a
        LEFT JOIN foreign_students fs ON a.student_id = fs.student_id  -- ← LEFT JOIN
        JOIN users u             ON a.student_id = u.user_id           -- ← join on users directly
        LEFT JOIN verification_officers vo
               ON a.assigned_officer_id = vo.officer_id
        LEFT JOIN users u_off
               ON vo.officer_id = u_off.user_id
        WHERE a.student_id = %s
        ORDER BY a.submitted_at DESC
    """, (student_id,))
    apps = cur.fetchall()
    cur.close()
    return apps

def get_all_applications():
    """For admin."""
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT a.*, u.first_name, u.last_name,
               fs.institution, fs.nationality
        FROM applications a
        JOIN foreign_students fs ON a.student_id = fs.student_id
        JOIN users u             ON fs.student_id = u.user_id
        ORDER BY a.submitted_at DESC
    """)
    apps = cur.fetchall()
    cur.close()
    return apps

def get_application_by_id(application_id):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT a.*,
               u.first_name, u.last_name, u.email,
               fs.passport_number, fs.nationality, fs.institution,
               fs.program_of_study
        FROM applications a
        LEFT JOIN foreign_students fs ON a.student_id = fs.student_id  -- changed to LEFT JOIN
        JOIN users u ON a.student_id = u.user_id
        WHERE a.application_id = %s
    """, (application_id,))
    app = cur.fetchone()
    cur.close()
    return app


def get_pending_applications():
    """For embassy officer — all SUBMITTED/UNDER_REVIEW apps."""
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT a.*, u.first_name, u.last_name,
               fs.nationality, fs.institution
        FROM applications a
        JOIN foreign_students fs ON a.student_id = fs.student_id
        JOIN users u             ON fs.student_id = u.user_id
        WHERE a.status IN ('SUBMITTED', 'UNDER_REVIEW', 'DOCS_REQUESTED')
        ORDER BY a.submitted_at ASC
    """)
    apps = cur.fetchall()
    cur.close()
    return apps

# def get_all_officer_applications():
#     """For officer dashboard — all applications across every status."""
#     cur = mysql.connection.cursor(DictCursor)
#     cur.execute("""
#         SELECT a.*, u.first_name, u.last_name,
#                fs.nationality, fs.institution
#         FROM applications a
#         JOIN foreign_students fs ON a.student_id = fs.student_id
#         JOIN users u             ON fs.student_id = u.user_id
#         ORDER BY a.submitted_at ASC
#     """)
#     apps = cur.fetchall()
#     cur.close()
#     return apps

def count_applications_by_doc_status():
    """Count applications grouped by their most recent document verification_status."""
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT d.verification_status AS doc_status, COUNT(*) AS total
        FROM applications a
        LEFT JOIN (
            SELECT application_id,
                   verification_status,
                   ROW_NUMBER() OVER (
                       PARTITION BY application_id
                       ORDER BY uploaded_at DESC
                   ) AS rn
            FROM documents
        ) d ON d.application_id = a.application_id AND d.rn = 1
        GROUP BY d.verification_status
    """)
    rows = cur.fetchall()
    cur.close()
    return {r['doc_status']: r['total'] for r in rows}

def get_verified_applications():
    """For provider — only applications with status VERIFIED."""
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT a.*, u.first_name, u.last_name,
               fs.nationality, fs.institution, fs.program_of_study
        FROM applications a
        JOIN foreign_students fs ON a.student_id = fs.student_id
        JOIN users u             ON fs.student_id = u.user_id
        WHERE a.status = 'VERIFIED'
        ORDER BY a.submitted_at ASC
    """)
    apps = cur.fetchall()
    cur.close()
    return apps

def save_assessment(application_id, provider_id, decision_outcome,
                    approved_amount, justification):
    """Save provider assessment — simplified, no scoring fields."""
    final_status = 'APPROVED' if 'APPROVED' in decision_outcome else 'REJECTED'
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        UPDATE applications SET
            assessed_by_id    = %s,
            decision_outcome  = %s,
            approved_amount   = %s,
            assessment_comments = %s,
            assessed_at       = NOW(),
            status            = %s,
            last_updated = NOW()
        WHERE application_id = %s
    """, (provider_id, decision_outcome, approved_amount,
          justification, final_status, application_id))
    mysql.connection.commit()
    cur.close()


def get_all_officer_applications():
    """For officer dashboard — applications grouped by their document verification status."""
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT a.*, u.first_name, u.last_name,
               fs.nationality, fs.institution,
               d.verification_status AS doc_status
        FROM applications a
        JOIN foreign_students fs ON a.student_id = fs.student_id
        JOIN users u             ON fs.student_id = u.user_id
        LEFT JOIN (
            SELECT application_id,
                   verification_status,
                   ROW_NUMBER() OVER (
                       PARTITION BY application_id
                       ORDER BY uploaded_at DESC
                   ) AS rn
            FROM documents
        ) d ON d.application_id = a.application_id AND d.rn = 1
        ORDER BY a.submitted_at ASC
    """)
    apps = cur.fetchall()
    cur.close()
    return apps

def create_application(student_id, amount, purpose):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        INSERT INTO applications
        (student_id, requested_amount, purpose, submitted_at, status)
        VALUES (%s, %s, %s, NOW(), 'SUBMITTED')
    """, (student_id, amount, purpose))
    mysql.connection.commit()
    app_id = cur.lastrowid
    cur.close()
    return app_id


def upsert_foreign_student(student_id, **kwargs):
    """Insert or update foreign student details"""
    cur = mysql.connection.cursor(DictCursor)
    
    # Check if student exists
    cur.execute("SELECT student_id FROM foreign_students WHERE student_id = %s", (student_id,))
    exists = cur.fetchone()
    
    if exists:
        # Update
        fields = []
        values = []
        for key, value in kwargs.items():
            if value is not None:
                fields.append(f"{key} = %s")
                values.append(value)
        if fields:
            query = f"UPDATE foreign_students SET {', '.join(fields)} WHERE student_id = %s"
            values.append(student_id)
            cur.execute(query, values)
    else:
        # Insert
        fields = ['student_id'] + list(kwargs.keys())
        placeholders = ['%s'] * len(fields)
        values = [student_id] + list(kwargs.values())
        query = f"INSERT INTO foreign_students ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
        cur.execute(query, values)
    
    mysql.connection.commit()
    cur.close()


def update_application_status(application_id, new_status,
                               remarks='', officer_id=None):
    cur = mysql.connection.cursor(DictCursor)
    if officer_id:
        cur.execute("""
            UPDATE applications
            SET status = %s, status_remarks = %s,
                assigned_officer_id = %s, last_updated = NOW()
            WHERE application_id = %s
        """, (new_status, remarks, officer_id, application_id))
    else:
        cur.execute("""
            UPDATE applications
            SET status = %s, status_remarks = %s,
                last_updated = NOW()
            WHERE application_id = %s
        """, (new_status, remarks, application_id))
    mysql.connection.commit()
    cur.close()




def delete_application(application_id):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute(
        "DELETE FROM applications WHERE application_id = %s",
        (application_id,)
    )
    mysql.connection.commit()
    cur.close()


def count_applications_by_status():
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT status, COUNT(*) as total
        FROM applications
        GROUP BY status
    """)
    rows = cur.fetchall()
    cur.close()
    return {r['status']: r['total'] for r in rows}


# ─── Documents ────────────────────────────────────────────────────

def get_documents_by_application(application_id):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT d.*,
               u.first_name AS verified_by_first,
               u.last_name  AS verified_by_last
        FROM documents d
        LEFT JOIN verification_officers vo
               ON d.verified_by_id = vo.officer_id
        LEFT JOIN users u
               ON vo.officer_id = u.user_id
        WHERE d.application_id = %s
        ORDER BY d.uploaded_at ASC
    """, (application_id,))
    docs = cur.fetchall()
    cur.close()
    return docs


def create_document(application_id, document_type,
                    file_name, file_size, storage_path):
    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO documents
            (application_id, document_type, file_name,
             file_size_bytes, storage_path, verification_status)
        VALUES (%s, %s, %s, %s, %s, 'PENDING')
    """, (application_id, document_type,
          file_name, file_size, storage_path))
    mysql.connection.commit()
    doc_id = cur.lastrowid
    cur.close()
    return doc_id


def update_document_status(document_id, status, officer_id,
                            rejection_reason=''):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        UPDATE documents
        SET verification_status = %s,
            verified_by_id      = %s,
            verified_at         = NOW(),
            rejection_reason    = %s
        WHERE document_id = %s
    """, (status, officer_id, rejection_reason, document_id))
    mysql.connection.commit()
    cur.close()


# ─── Notifications ────────────────────────────────────────────────

def get_notifications_by_recipient(user_id):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT n.*,
               u.first_name AS sender_first,
               u.last_name  AS sender_last,
               u.role       AS sender_role_name
        FROM notifications n
        JOIN users u ON n.sender_id = u.user_id
        WHERE n.recipient_id = %s
        ORDER BY n.sent_at DESC
    """, (user_id,))
    notifs = cur.fetchall()
    cur.close()
    return notifs


def create_notification(application_id, sender_id, recipient_id,
                         sender_role, notif_type, subject, message):
    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO notifications
            (application_id, sender_id, recipient_id, sender_role,
             type, subject, message, is_read, sent_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NOW())
    """, (application_id, sender_id, recipient_id,
          sender_role, notif_type, subject, message))
    mysql.connection.commit()
    notif_id = cur.lastrowid
    cur.close()
    return notif_id


def mark_notification_read(notification_id):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute(
        "UPDATE notifications SET is_read = TRUE WHERE notification_id = %s",
        (notification_id,)
    )
    mysql.connection.commit()
    cur.close()


def count_unread_notifications(user_id):
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT COUNT(*) as total
        FROM notifications
        WHERE recipient_id = %s AND is_read = FALSE
    """, (user_id,))
    row = cur.fetchone()
    cur.close()
    return row['total']

def create_officer(officer_id, badge_number, embassy_name, department):
    """Insert a row into verification_officers after user creation."""
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        INSERT INTO verification_officers
            (officer_id, badge_number, embassy_name, department)
        VALUES (%s, %s, %s, %s)
    """, (officer_id, badge_number, embassy_name, department))
    mysql.connection.commit()
    cur.close()

def create_provider(provider_id, organization_name, organization_type):
    """Insert a row into financial_aid_provider after user creation."""
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        INSERT INTO financial_aid_providers
            (provider_id, organization_name, organization_type)
        VALUES (%s, %s, %s)
    """, (provider_id, organization_name, organization_type))
    mysql.connection.commit()
    cur.close()