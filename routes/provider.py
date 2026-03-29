from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, session)
from functools import wraps
from models import (
    get_verified_applications, get_application_by_id,
    get_documents_by_application, save_assessment,
    create_notification, count_applications_by_status
)

provider_bp = Blueprint('provider', __name__, url_prefix='/provider')


def provider_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session['role'] != 'PROVIDER':
            flash('Access restricted to financial aid providers.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ── Screen 7: Provider Dashboard ──────────────────────────────────
@provider_bp.route('/dashboard')
@provider_required
def dashboard():
    apps   = get_verified_applications()
    counts = count_applications_by_status()
    stats  = {
        'verified':  counts.get('VERIFIED', 0) + counts.get('FORWARDED', 0),
        'approved':  counts.get('APPROVED', 0),
        'rejected':  counts.get('REJECTED', 0),
    }
    return render_template('provider_dashboard.html',
                           applications=apps,
                           stats=stats)


# ── Screen 8: Assessment Page ──────────────────────────────────────
@provider_bp.route('/assess/<int:application_id>', methods=['GET', 'POST'])
@provider_required
def assess(application_id):
    provider_id = session['user_id']
    app  = get_application_by_id(application_id)
    docs = get_documents_by_application(application_id)
 
    if not app:
        flash('Application not found.', 'error')
        return redirect(url_for('provider.dashboard'))
 
    if request.method == 'POST':
        decision_outcome = request.form.get('decision', '').strip()
        approved_amount  = float(
            request.form.get('approved_amount', '0').replace(',', '') or 0
        )
        justification = request.form.get('justification', '').strip()
 
        if not decision_outcome:
            flash('Please select a decision.', 'error')
            return redirect(url_for('provider.assess',
                                    application_id=application_id))
 
        save_assessment(
            application_id, provider_id,
            decision_outcome, approved_amount, justification
        )
 
        # Notify the student
        is_approved = 'APPROVED' in decision_outcome
        subject = ('Application Approved — Funds Will Be Disbursed'
                   if is_approved else 'Application Decision Issued')
        message = (
            f"Your application ({app['application_id']}) has been "
            f"{'approved' if is_approved else 'reviewed by the provider'}. "
            + (justification if justification else '')
        )
 
        create_notification(
            application_id,
            sender_id    = provider_id,
            recipient_id = app['student_id'],
            sender_role  = 'PROVIDER',
            notif_type   = 'DECISION',
            subject      = subject,
            message      = message
        )
 
        flash('Assessment submitted successfully.', 'success')
        return redirect(url_for('provider.dashboard'))
 
    return render_template('assessment.html',
                           application=app,
                           documents=docs)