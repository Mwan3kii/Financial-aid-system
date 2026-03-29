from flask import Flask, render_template, request, redirect, url_for, flash
from flask_bcrypt import Bcrypt
from config import Config
from models import mysql
from routes.auth import auth_bp, bcrypt as auth_bcrypt
from routes.student import student_bp
from routes.officer import officer_bp
from routes.provider import provider_bp
from routes.admin import admin_bp, bcrypt as admin_bcrypt

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Init extensions
    mysql.init_app(app)
    auth_bcrypt.init_app(app)
    admin_bcrypt.init_app(app)

    # Public routes
    @app.route('/')
    def landing():
        return render_template('landing_page.html')
    
    @app.route('/login')
    def login():
        return render_template('login.html')
    
    # @app.route('/login', methods=['POST'])
    # def login_submit():
    #     try:
    #         email = request.form.get('email')
    #         password = request.form.get('password')
            
    #         if not email or not password:
    #             flash('Email and password required', 'error')
    #             return redirect(url_for('login'))
            
    #         cursor = mysql.connection.cursor()
    #         cursor.execute("SELECT user_id, password_hash, role FROM users WHERE email = %s", (email,))
    #         user = cursor.fetchone()
    #         cursor.close()
            
    #         if not user:
    #             flash('Invalid email or password', 'error')
    #             return redirect(url_for('login'))
            
    #         # Check password
    #         if not auth_bcrypt.check_password_hash(user[1], password):
    #             flash('Invalid email or password', 'error')
    #             return redirect(url_for('login'))
            
    #         # Redirect based on role (strip whitespace and convert to lowercase)
    #         role = str(user[2]).strip().lower()
            
    #         if role == 'student':
    #             flash('Welcome back!', 'success')
    #             return redirect(url_for('status'))
    #         elif role == 'officer':
    #             flash('Welcome back!', 'success')
    #             return redirect(url_for('officer_dashboard'))
    #         elif role == 'provider':
    #             flash('Welcome back!', 'success')
    #             return redirect(url_for('provider_dashboard'))
    #         elif role == 'admin':
    #             flash('Welcome back!', 'success')
    #             return redirect(url_for('admin_dashboard'))
    #         else:
    #             flash(f'Unknown role: {role}', 'error')
    #             return redirect(url_for('landing'))
        
    #     except Exception as e:
    #         flash(f'Login error: {str(e)}', 'error')
    #         return redirect(url_for('login'))
    
    @app.route('/signup')
    def signup():
        return render_template('signup.html')
    
    @app.route('/signup', methods=['POST'])
    def signup_submit():
        try:
            firstname = request.form.get('first_name')
            lastname = request.form.get('last_name')
            email = request.form.get('email')
            password = request.form.get('password')
            
            # Validation
            if not firstname or not lastname or not email or not password:
                flash('All fields are required', 'error')
                return redirect(url_for('signup'))
            
            if len(password) < 6:
                flash('Password must be at least 6 characters', 'error')
                return redirect(url_for('signup'))
            
            # Check if user exists
            cursor = mysql.connection.cursor()
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                flash('Email already registered', 'error')
                cursor.close()
                return redirect(url_for('signup'))
            
            # Hash password and create user
            hashed_password = auth_bcrypt.generate_password_hash(password).decode('utf-8')
            cursor.execute(
                "INSERT INTO users (first_name, last_name, email, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
                (firstname, lastname, email, hashed_password, 'student')
            )
            mysql.connection.commit()
            cursor.close()
            
            flash('Account created! Please login.', 'success')
            return redirect(url_for('login'))
        
        except Exception as e:
            flash(f'Error creating account: {str(e)}', 'error')
            return redirect(url_for('signup'))
    
    # Student routes
    # @app.route('/student/apply')
    # def apply():
    #     return render_template('application_form.html')
    
    # @app.route('/student/status')
    # def status():
    #     return render_template('application_status.html')
    
    # @app.route('/student/notifications')
    # def student_notifications():
    #     return render_template('notifications.html')
    
    # Officer routes
    # @app.route('/officer/dashboard')
    # def officer_dashboard():
    #     return render_template('officer_dashboard.html')
    
    # @app.route('/officer/verify')
    # def verify():
    #     return render_template('verification.html')
    
    # Provider routes
    # @app.route('/provider/dashboard')
    # def provider_dashboard():
    #     return render_template('provider_dashboard.html')
    
    # Admin routes
    # @app.route('/admin/dashboard')
    # def admin_dashboard():
    #     return render_template('admin.html')
    
    # @app.route('/admin/manage')
    # def manage_applications():
    #     return render_template('manage_applications.html')
    
    @app.route('/admin/assessment')
    def assessment():
        return render_template('assessment.html')

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(officer_bp)
    app.register_blueprint(provider_bp)
    app.register_blueprint(admin_bp)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='localhost', port=8000)