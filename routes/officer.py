from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, session)
from functools import wraps
from models import (
    get_pending_applications, get_application_by_id,
    get_documents_by_application, update_application_status,
    update_document_status, create_notification,
    count_applications_by_status
)

officer_bp = Blueprint('officer', __name__, url_prefix='/officer')


def officer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session['role'] != 'OFFICER':
            flash('Access restricted to embassy officers.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ── Screen 5: Officer Dashboard ───────────────────────────────────
@officer_bp.route('/dashboard')
@officer_required
def officer_dashboard():
    apps   = get_pending_applications()
    counts = count_applications_by_status()
    stats  = {
        'pending':  counts.get('SUBMITTED', 0) + counts.get('UNDER_REVIEW', 0),
        'verified': counts.get('VERIFIED', 0),
        'rejected': counts.get('REJECTED', 0),
        'docs_req': counts.get('DOCS_REQUESTED', 0),
    }
    return render_template('officer_dashboard.html',
                           applications=apps,
                           stats=stats)


# ── Screen 6: Document Review ─────────────────────────────────────
@officer_bp.route('/review/<int:application_id>', methods=['GET', 'POST'])
@officer_required
def review(application_id):
    officer_id = session['user_id']
    app  = get_application_by_id(application_id)
    docs = get_documents_by_application(application_id)

    if not app:
        flash('Application not found.', 'error')
        return redirect(url_for('officer.officer_dashboard'))

    if request.method == 'POST':
        decision       = request.form.get('decision')       # 'APPROVE' or 'REJECT'
        comments       = request.form.get('comments', '')
        doc_request    = request.form.get('doc_request', '')

        if decision == 'APPROVE':
            new_status = 'VERIFIED'
            # Mark all documents as verified
            for doc in docs:
                update_document_status(
                    doc['document_id'], 'VERIFIED', officer_id
                )
        else:
            new_status = 'REJECTED' if not doc_request else 'DOCS_REQUESTED'
            # Mark rejected docs
            for doc in docs:
                update_document_status(
                    doc['document_id'], 'REJECTED', officer_id,
                    rejection_reason=comments
                )

        update_application_status(
            application_id, new_status, comments, officer_id
        )

        # Notify the student
        notif_type = 'STATUS_UPDATE' if decision == 'APPROVE' else 'DOC_REQUEST'
        subject    = ('Documents Verified — Application Forwarded'
                      if decision == 'APPROVE'
                      else 'Additional Documents Required')
        message    = comments or doc_request or 'Your application has been reviewed.'

        create_notification(
            application_id,
            sender_id   = officer_id,
            recipient_id= app['student_id'],
            sender_role = 'OFFICER',
            notif_type  = notif_type,
            subject     = subject,
            message     = message
        )

        flash(f'Application {new_status.replace("_"," ").title()}.', 'success')
        return redirect(url_for('officer.officer_dashboard'))

    return render_template('verification.html',
                           application=app,
                           documents=docs)