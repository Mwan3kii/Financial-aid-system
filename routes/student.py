import os
from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, session)
from functools import wraps
from models import (
    get_applications_by_student, get_application_by_id,
    create_application, get_documents_by_application,
    create_document, get_notifications_by_recipient,
    mark_notification_read, count_unread_notifications
)

student_bp = Blueprint('student', __name__, url_prefix='/student')
UPLOAD_FOLDER = 'static/uploads'


def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session['role'] != 'STUDENT':
            flash('Please log in as a student.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ── Screen 2: Application Status ─────────────────────────────────
@student_bp.route('/status')
@student_required
def app_status():
    student_id = session['user_id']
    apps  = get_applications_by_student(student_id)
    app   = apps[0] if apps else None
    docs  = get_documents_by_application(app['application_id']) if app else []
    unread = count_unread_notifications(student_id)

    return render_template('student/app_status.html',
                           application=app,
                           documents=docs,
                           unread=unread)


# ── Screen 3: Submit Application Form ────────────────────────────
@student_bp.route('/submit', methods=['GET', 'POST'])
@student_required
def submit_application():
    student_id = session['user_id']

    if request.method == 'POST':
        requested_amount   = request.form.get('loan_amount')
        purpose_statement  = request.form.get('purpose')
        institution        = request.form.get('institution')
        program            = request.form.get('program')
        loan_bank          = request.form.get('bank_name')
        loan_account       = request.form.get('account_number')

        # Basic validation
        if not requested_amount or not purpose_statement:
            flash('Loan amount and purpose are required.', 'error')
            return render_template('student/submit_form.html')

        try:
            amount = float(requested_amount.replace(',', ''))
        except ValueError:
            flash('Please enter a valid loan amount.', 'error')
            return render_template('student/submit_form.html')

        # Create application
        app_id = create_application(
            student_id, amount, purpose_statement,
            institution, program, loan_bank, loan_account
        )

        # Handle document uploads
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        doc_fields = {
            'passport':    'PASSPORT',
            'transcript':  'TRANSCRIPT',
            'admission':   'ADMISSION',
            'bank_stmt':   'BANK_STATEMENT',
            'medical':     'MEDICAL',
        }
        for field_name, doc_type in doc_fields.items():
            file = request.files.get(field_name)
            if file and file.filename:
                filename = f"{app_id}_{field_name}_{file.filename}"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                create_document(
                    app_id, doc_type, file.filename,
                    os.path.getsize(filepath), filepath
                )

        flash('Application submitted successfully!', 'success')
        return redirect(url_for('student.app_status'))

    return render_template('student/submit_form.html')


# ── Screen 4: Notifications ───────────────────────────────────────
@student_bp.route('/notifications')
@student_required
def notifications():
    user_id = session['user_id']
    notifs  = get_notifications_by_recipient(user_id)
    unread  = sum(1 for n in notifs if not n['is_read'])
    return render_template('student/notifications.html',
                           notifications=notifs,
                           unread_count=unread)


@student_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@student_required
def mark_read(notif_id):
    mark_notification_read(notif_id)
    return redirect(url_for('student.notifications'))

