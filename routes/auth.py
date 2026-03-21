from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_bcrypt import Bcrypt
from models import get_user_by_email

auth_bp = Blueprint('auth', __name__)
bcrypt  = Bcrypt()


@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Already logged in — go to correct dashboard
    if 'user_id' in session:
        return redirect_by_role(session['role'])

    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('login.html')

        user = get_user_by_email(email)

        if not user:
            flash('No account found with that email address.', 'error')
            return render_template('login.html')

        if not user['is_active']:
            flash('Your account has been deactivated. Contact admin.', 'error')
            return render_template('login.html')

        if not bcrypt.check_password_hash(user['password_hash'], password):
            flash('Incorrect password. Please try again.', 'error')
            return render_template('login.html')

        # Store session
        session['user_id']   = user['user_id']
        session['role']      = user['role']
        session['full_name'] = f"{user['first_name']} {user['last_name']}"
        session['email']     = user['email']

        return redirect_by_role(user['role'])

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


def redirect_by_role(role):
    destinations = {
        'STUDENT':  'student.app_status',
        'OFFICER':  'officer.dashboard',
        'PROVIDER': 'provider.dashboard',
        'ADMIN':    'admin.manage_users',
    }
    return redirect(url_for(destinations.get(role, 'auth.login')))