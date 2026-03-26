import os
from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, session)
from functools import wraps
from models import (
    get_applications_by_student, get_application_by_id,
    create_application, get_documents_by_application,
    create_document, get_notifications_by_recipient,
    mark_notification_read, count_unread_notifications,
    upsert_foreign_student
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
    print("Current student_id in session:", student_id)
    # Get all applications for this student
    applications = get_applications_by_student(student_id)
    print("DEBUG applications:", applications)
    # Include documents for each application
    for app in applications:
        app['documents'] = get_documents_by_application(app['application_id'])
    
    # Count unread notifications
    unread = count_unread_notifications(student_id)

    return render_template(
        'application_status.html',
        applications=applications,
        unread=unread
    )

# ── Screen 3: Submit Application Form ────────────────────────────
@student_bp.route('/submit', methods=['GET', 'POST'])
@student_required
def submit_application():
    student_id = session['user_id']

    if request.method == 'POST':
        required_fields = [
            'first_name', 'last_name', 'date_of_birth', 'gender', 'nationality',
            'marital_status', 'passport_number', 'phone_number', 'email', 'home_address',
            'level_of_study', 'institution_name', 'program_of_study', 'admission_number',
            'year_of_admission', 'expected_completion', 'current_year', 'gpa',
            'loan_amount', 'purpose'
        ]

        missing_fields = [f for f in required_fields if not request.form.get(f, '').strip()]
        if missing_fields:
            flash(f"Please fill in all required fields: {', '.join(missing_fields)}", 'error')
            return render_template('application_form.html', form=request.form)
        
        # Get form data
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        date_of_birth = request.form.get('date_of_birth')
        gender = request.form.get('gender')
        nationality = request.form.get('nationality')
        marital_status = request.form.get('marital_status')
        passport_number = request.form.get('passport_number')
        phone_number = request.form.get('phone_number')
        email = request.form.get('email')
        home_address = request.form.get('home_address')
        
        level_of_study = request.form.get('level_of_study')
        institution_name = request.form.get('institution_name')
        admission_number = request.form.get('admission_number')
        program_of_study = request.form.get('program_of_study')
        year_of_admission = request.form.get('year_of_admission')
        expected_completion = request.form.get('expected_completion')
        current_year = request.form.get('current_year')
        gpa = request.form.get('gpa')
        
        loan_amount = request.form.get('loan_amount')
        purpose = request.form.get('purpose')

        # Basic validation
        if not loan_amount or not purpose:
            flash('Loan amount and purpose are required.', 'error')
            return render_template('application_form.html')

        try:
            amount = float(loan_amount.replace(',', ''))
        except ValueError:
            flash('Please enter a valid loan amount.', 'error')
            return render_template('application_form.html')

        # Upsert foreign student details
        student_data = {
            'passport_number': passport_number,
            'nationality': nationality,
            'date_of_birth': date_of_birth,
            'institution': institution_name,
            'program_of_study': program_of_study,
            'home_country': home_address,
            'gpa': gpa
        }
        upsert_foreign_student(student_id, **student_data)

        # Create application
        app_id = create_application(
            student_id,
            amount,
            purpose,
        )

        # Handle document uploads
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        doc_fields = {
            'passport':    'PASSPORT',
            'transcript':  'TRANSCRIPT',
            'admission':   'ADMISSION',
            'bank_stmt':   'BANK_STATEMENT',
            'medical':     'MEDICAL',
            'other':       'OTHER',
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

    return render_template('application_form.html')


# ── Screen 4: Notifications ───────────────────────────────────────
@student_bp.route('/notifications')
@student_required
def notifications():
    user_id = session['user_id']
    notifs  = get_notifications_by_recipient(user_id)
    unread  = sum(1 for n in notifs if not n['is_read'])
    return render_template('notifications.html',
                           notifications=notifs,
                           unread_count=unread)


@student_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@student_required
def mark_read(notif_id):
    mark_notification_read(notif_id)
    return redirect(url_for('student.notifications'))

