from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, session)
from functools import wraps
from flask_bcrypt import Bcrypt
from models import (
    get_all_users, create_user, delete_user,
    update_user_status, count_users_by_role,
    get_all_applications, delete_application,
    count_applications_by_status, get_application_by_id, get_documents_by_application
)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
bcrypt   = Bcrypt()


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session['role'].upper() != 'ADMIN':
            flash('Access restricted to administrators.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ── Screen 9: Manage Users ────────────────────────────────────────
@admin_bp.route('/users')
@admin_required
def manage_users():
    users      = get_all_users()
    role_stats = count_users_by_role()
    total      = sum(role_stats.values())
    return render_template('admin.html',
                           users=users,
                           role_stats=role_stats,
                           total=total)


@admin_bp.route('/users/add', methods=['POST'])
@admin_required
def add_user():
    first_name = request.form.get('first_name', '').strip()
    last_name  = request.form.get('last_name', '').strip()
    email      = request.form.get('email', '').strip()
    password   = request.form.get('password', '')
    role       = request.form.get('role', 'OFFICER')

    if not all([first_name, last_name, email, password]):
        flash('All fields are required.', 'error')
        return redirect(url_for('admin.manage_users'))

    pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    create_user(first_name, last_name, email, pw_hash, role)
    flash(f'User {first_name} {last_name} created.', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def remove_user(user_id):
    if user_id == session['user_id']:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.manage_users'))
    delete_user(user_id)
    flash('User deleted.', 'success')
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    from models import get_user_by_id, update_user  # add update_user to models
    user = get_user_by_id(user_id)

    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.manage_users'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name', '').strip()
        email      = request.form.get('email', '').strip()
        role       = request.form.get('role', '').strip()

        if not all([first_name, last_name, email, role]):
            flash('All fields are required.', 'error')
            return redirect(url_for('admin.edit_user', user_id=user_id))

        update_user(user_id, first_name, last_name, email, role)
        flash(f'User {first_name} {last_name} updated.', 'success')
        return redirect(url_for('admin.manage_users'))

    return render_template('edit_user.html', user=user)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user(user_id):
    is_active = request.form.get('is_active') == '1'
    update_user_status(user_id, is_active)
    flash('User status updated.', 'success')
    return redirect(url_for('admin.manage_users'))


# ── Screen 10: Manage Applications ───────────────────────────────
@admin_bp.route('/applications')
@admin_required
def manage_applications():
    apps      = get_all_applications()
    status_f  = request.args.get('status', '')
    if status_f:
        apps = [a for a in apps if a['status'] == status_f]
    counts    = count_applications_by_status()
    return render_template('manage_applications.html',
                           applications=apps,
                           counts=counts,
                           status_filter=status_f)


@admin_bp.route('/applications/<int:application_id>/delete', methods=['POST'])
@admin_required
def remove_application(application_id):
    delete_application(application_id)
    flash('Application deleted.', 'success')
    return redirect(url_for('admin.manage_applications'))

@admin_bp.route('/applications/<int:application_id>')
@admin_required
def view_application(application_id):
    app  = get_application_by_id(application_id)
    if not app:
        flash('Application not found.', 'error')
        return redirect(url_for('admin.manage_applications'))
    docs = get_documents_by_application(application_id)
    return render_template('view_application.html', app=app, docs=docs)