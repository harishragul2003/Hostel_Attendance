import os
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta, time
from sqlalchemy import case

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, '..', 'frontend', 'templates')

# Use DATABASE_URL from environment (PostgreSQL on Render), fallback to SQLite locally
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:////tmp/hostel.db')
# Render gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize DB and default admin on startup (runs with gunicorn too)
def init_db():
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                password='admin123',
                role='admin',
                name='Administrator',
                department='Administration',
                room_number='ADMIN'
            )
            db.session.add(admin)
            db.session.commit()
            print('Default admin created: admin / admin123')

# Add Jinja2 template filters
@app.template_filter('format_time')
def format_time(time_obj):
    if time_obj:
        return time_obj.strftime('%I:%M %p')
    return ''

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # 'admin' or 'student'
    name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(50), nullable=False, default='General')
    year = db.Column(db.Integer, nullable=False, default=1)
    room_number = db.Column(db.String(10), nullable=False)
    total_bill = db.Column(db.Float, default=0.0)
    last_bill_date = db.Column(db.DateTime)
    attendance = db.relationship('Attendance', backref='user', lazy=True)

class MealSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    cost = db.Column(db.Float, nullable=False, default=0.0)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    breakfast = db.Column(db.Boolean, default=False)
    breakfast_time = db.Column(db.DateTime)
    lunch = db.Column(db.Boolean, default=False)
    lunch_time = db.Column(db.DateTime)
    dinner = db.Column(db.Boolean, default=False)
    dinner_time = db.Column(db.DateTime)
    leave_status = db.Column(db.Boolean, default=False)
    daily_cost = db.Column(db.Float, default=0.0)

class WeeklyMenu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10), nullable=False)  # e.g. Monday
    meal_type = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    cost = db.Column(db.Float, nullable=False, default=0.0)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Run DB init (works with both gunicorn and direct python)
init_db()

@app.context_processor
def utility_processor():
    return {
        'datetime': datetime,
        'timedelta': timedelta,
        'format_time': format_time
    }

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Prevent caching of the login page
    response = make_response()
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:  # In production, use proper password hashing
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
        return redirect(url_for('login'))
    
    # Clear the form data
    response.data = render_template('login.html')
    return response

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    # Get meal schedules
    schedules = MealSchedule.query.all()
    
    # Get attendance for the past week
    today = datetime.now().date()
    week_ago = today - timedelta(days=6)
    week_attendance = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        Attendance.date >= week_ago,
        Attendance.date <= today
    ).order_by(Attendance.date.desc()).all()

    # Calculate total meals this month
    first_day_of_month = today.replace(day=1)
    monthly_attendance = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        Attendance.date >= first_day_of_month,
        Attendance.date <= today
    ).all()
    
    # Count meals for the current month
    breakfast_count = sum(1 for att in monthly_attendance if att.breakfast)
    lunch_count = sum(1 for att in monthly_attendance if att.lunch)
    dinner_count = sum(1 for att in monthly_attendance if att.dinner)
    
    # Get meal costs
    meal_costs = {s.meal_type: s.cost for s in schedules}
    
    # Calculate total cost for the month
    total_cost = (
        (breakfast_count * meal_costs.get('breakfast', 0)) +
        (lunch_count * meal_costs.get('lunch', 0)) +
        (dinner_count * meal_costs.get('dinner', 0))
    )
    
    return render_template('student_dashboard.html', 
                         schedules=schedules,
                         week_attendance=week_attendance,
                         total_bill=current_user.total_bill,
                         breakfast_count=breakfast_count,
                         lunch_count=lunch_count,
                         dinner_count=dinner_count,
                         monthly_cost=total_cost,
                         meal_costs=meal_costs)

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied')
        return redirect(url_for('dashboard'))
    
    # Get today's date
    today = datetime.now().date()
    
    # Get all students grouped by department
    departments = {}
    students = User.query.filter_by(role='student').order_by(User.department, User.name).all()
    
    # Group students by department
    for student in students:
        if student.department not in departments:
            departments[student.department] = []
        departments[student.department].append(student)
    
    # Get today's attendance records
    attendance = {}
    today_attendance = Attendance.query.filter_by(date=today).all()
    
    # Count meal attendance
    breakfast_count = sum(1 for att in today_attendance if att.breakfast)
    lunch_count = sum(1 for att in today_attendance if att.lunch)
    dinner_count = sum(1 for att in today_attendance if att.dinner)
    
    for att in today_attendance:
        attendance[att.user_id] = att
    
    # Get available departments for filter
    all_departments = [dept[0] for dept in db.session.query(User.department).distinct().all() if dept[0]]
    
    return render_template('admin_dashboard.html', 
                         departments=departments,
                         attendance=attendance,
                         today=today,
                         all_departments=all_departments,
                         breakfast_count=breakfast_count,
                         lunch_count=lunch_count,
                         dinner_count=dinner_count,
                         total_students=len(students))

@app.route('/leave_list')
@login_required
def leave_list():
    # Admin-only leave list page
    if current_user.role != 'admin':
        flash('Access denied')
        return redirect(url_for('dashboard'))
    today = datetime.now().date()
    records = Attendance.query.filter_by(date=today, leave_status=True).all()
    return render_template('leave_list.html', records=records)

@app.route('/meal_schedule', methods=['GET', 'POST'])
@login_required
def meal_schedule():
    if current_user.role != 'admin':
        flash('Only admin can manage meal schedules')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        meal_type = request.form['meal_type']
        start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
        end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()
        
        schedule = MealSchedule.query.filter_by(meal_type=meal_type).first()
        if schedule:
            schedule.start_time = start_time
            schedule.end_time = end_time
        else:
            schedule = MealSchedule(meal_type=meal_type, start_time=start_time, end_time=end_time)
            db.session.add(schedule)
        
        db.session.commit()
        flash(f'{meal_type.title()} schedule updated successfully')
        return redirect(url_for('meal_schedule'))

    schedules = MealSchedule.query.all()
    return render_template('meal_schedule.html', schedules=schedules)

@app.route('/update_meal_cost/<int:schedule_id>', methods=['POST'])
@login_required
def update_meal_cost(schedule_id):
    if current_user.role != 'admin':
        flash('Only admin can update meal costs')
        return redirect(url_for('dashboard'))

    schedule = MealSchedule.query.get_or_404(schedule_id)
    cost = float(request.form['cost'])
    schedule.cost = cost
    db.session.commit()
    flash(f'{schedule.meal_type.title()} cost updated to ₹{cost:.2f}')
    return redirect(url_for('meal_schedule'))

@app.route('/mark_attendance', methods=['POST'])
@login_required
def mark_attendance():
    if current_user.role != 'student':
        flash('Only students can mark attendance')
        return redirect(url_for('dashboard'))

    meal = request.form['meal']
    date = datetime.strptime(request.form.get('date', datetime.now().date().isoformat()), '%Y-%m-%d').date()
    action = request.form.get('action', 'mark')  # 'mark' or 'unmark'
    now = datetime.now()
    
    attendance = Attendance.query.filter_by(
        user_id=current_user.id,
        date=date
    ).first()
    
    if not attendance:
        attendance = Attendance(user_id=current_user.id, date=date)
        db.session.add(attendance)
    
    # Get meal schedule and cost
    schedule = MealSchedule.query.filter_by(meal_type=meal).first()
    if not schedule:
        flash(f'No schedule found for {meal}')
        return redirect(url_for('dashboard'))
    
    meal_cost = schedule.cost if action == 'mark' else -schedule.cost
    
    # Update attendance and cost
    if meal == 'breakfast':
        attendance.breakfast = action == 'mark'
        attendance.breakfast_time = now if action == 'mark' else None
    elif meal == 'lunch':
        attendance.lunch = action == 'mark'
        attendance.lunch_time = now if action == 'mark' else None
    elif meal == 'dinner':
        attendance.dinner = action == 'mark'
        attendance.dinner_time = now if action == 'mark' else None
    
    attendance.daily_cost = attendance.daily_cost or 0.0
    attendance.daily_cost += meal_cost
    
    db.session.commit()
    flash(f'{meal.title()} marked as {"present" if action == "mark" else "absent"}')
    return redirect(url_for('dashboard'))

@app.route('/apply_leave', methods=['POST'])
@login_required
def apply_leave():
    if current_user.role != 'student':
        flash('Only students can apply for leave')
        return redirect(url_for('dashboard'))

    date = datetime.strptime(request.form.get('date', datetime.now().date().isoformat()), '%Y-%m-%d').date()
    
    attendance = Attendance.query.filter_by(
        user_id=current_user.id,
        date=date
    ).first()
    
    if not attendance:
        attendance = Attendance(user_id=current_user.id, date=date)
        db.session.add(attendance)
    
    attendance.leave_status = True
    attendance.breakfast = False
    attendance.lunch = False
    attendance.dinner = False
    attendance.daily_cost = 0.0
    
    db.session.commit()
    flash('Leave applied successfully')
    return redirect(url_for('dashboard'))

@app.route('/cancel_leave', methods=['POST'])
@login_required
def cancel_leave():
    if current_user.role != 'student':
        flash('Only students can cancel leave')
        return redirect(url_for('dashboard'))

    date = datetime.strptime(request.form.get('date', datetime.now().date().isoformat()), '%Y-%m-%d').date()
    
    attendance = Attendance.query.filter_by(
        user_id=current_user.id,
        date=date
    ).first()
    
    if attendance:
        attendance.leave_status = False
        db.session.commit()
        flash('Leave cancelled successfully')
    
    return redirect(url_for('dashboard'))

@app.route('/calculate_bills')
@login_required
def calculate_bills():
    if current_user.role != 'admin':
        flash('Only admin can calculate bills')
        return redirect(url_for('dashboard'))

    students = User.query.filter_by(role='student').all()
    for student in students:
        # Get all attendance records since last bill date
        query = Attendance.query.filter_by(user_id=student.id)
        if student.last_bill_date:
            query = query.filter(Attendance.date > student.last_bill_date.date())
        
        new_charges = sum(record.daily_cost for record in query.all())
        student.total_bill = (student.total_bill or 0.0) + new_charges
        student.last_bill_date = datetime.now()
    
    db.session.commit()
    flash('All student bills have been calculated')
    return redirect(url_for('reports'))

@app.route('/reports')
@login_required
def reports():
    if current_user.role != 'admin':
        flash('Only admin can view reports')
        return redirect(url_for('dashboard'))

    # Get all students and meal schedules
    students = User.query.filter_by(role='student').order_by(User.name).all()
    meal_schedules = {s.meal_type: s.cost for s in MealSchedule.query.all()}
    
    # Calculate detailed statistics for each student
    for student in students:
        attendance_records = student.attendance
        
        # Initialize statistics
        stats = {
            'total_days': len(attendance_records),
            'breakfast_count': 0,
            'lunch_count': 0,
            'dinner_count': 0,
            'leave_days': 0,
            'breakfast_cost': 0,
            'lunch_cost': 0,
            'dinner_cost': 0,
            'total_cost': 0,
            'avg_daily_cost': 0,
            'attendance_records': []
        }
        
        # Process each attendance record
        for record in attendance_records:
            if record.leave_status:
                stats['leave_days'] += 1
            else:
                if record.breakfast:
                    stats['breakfast_count'] += 1
                    stats['breakfast_cost'] += meal_schedules.get('breakfast', 0)
                if record.lunch:
                    stats['lunch_count'] += 1
                    stats['lunch_cost'] += meal_schedules.get('lunch', 0)
                if record.dinner:
                    stats['dinner_count'] += 1
                    stats['dinner_cost'] += meal_schedules.get('dinner', 0)
            
            # Add record to detailed list
            stats['attendance_records'].append({
                'date': record.date,
                'breakfast': record.breakfast,
                'lunch': record.lunch,
                'dinner': record.dinner,
                'leave_status': record.leave_status,
                'daily_cost': record.daily_cost
            })
        
        # Calculate totals and averages
        stats['total_cost'] = stats['breakfast_cost'] + stats['lunch_cost'] + stats['dinner_cost']
        
        # Calculate average daily cost (excluding leave days)
        days_with_meals = stats['total_days'] - stats['leave_days']
        if days_with_meals > 0:
            stats['avg_daily_cost'] = stats['total_cost'] / days_with_meals
        else:
            stats['avg_daily_cost'] = 0
        
        # Sort records by date (newest first)
        stats['attendance_records'].sort(key=lambda x: x['date'], reverse=True)
        
        # Add stats to student object
        student.stats = stats
    
    return render_template('reports.html', students=students)

@app.route('/generate_report/<int:student_id>/<string:report_type>')
@login_required
def generate_report(student_id, report_type):
    if current_user.role != 'admin':
        flash('Access denied')
        return redirect(url_for('dashboard'))
    
    student = User.query.get_or_404(student_id)
    
    # Get date range for the report
    end_date = datetime.now().date()
    if report_type == 'monthly':
        start_date = end_date - timedelta(days=30)
    else:
        start_date = end_date - timedelta(days=7)  # Default to weekly
    
    # Get attendance records
    attendance_records = Attendance.query.filter(
        Attendance.user_id == student_id,
        Attendance.date.between(start_date, end_date)
    ).order_by(Attendance.date.desc()).all()
    
    # Calculate statistics
    total_days = (end_date - start_date).days + 1
    present_days = len([a for a in attendance_records if not a.leave_status])
    leave_days = len([a for a in attendance_records if a.leave_status])
    breakfast_count = len([a for a in attendance_records if a.breakfast])
    lunch_count = len([a for a in attendance_records if a.lunch])
    dinner_count = len([a for a in attendance_records if a.dinner])
    
    total_cost = sum([a.daily_cost for a in attendance_records])
    avg_daily_cost = total_cost / total_days if total_days > 0 else 0
    
    stats = {
        'total_days': total_days,
        'present_days': present_days,
        'leave_days': leave_days,
        'breakfast_count': breakfast_count,
        'lunch_count': lunch_count,
        'dinner_count': dinner_count,
        'total_cost': total_cost,
        'avg_daily_cost': avg_daily_cost,
        'attendance_percentage': (present_days / total_days * 100) if total_days > 0 else 0
    }
    
    # Generate appropriate report based on type
    if report_type == 'monthly':
        return render_template('reports/monthly_report.html', 
                            student=student, 
                            stats=stats,
                            records=attendance_records,
                            start_date=start_date,
                            end_date=end_date)
    
    elif report_type == 'attendance':
        return render_template('reports/attendance_report.html',
                            student=student,
                            stats=stats,
                            records=attendance_records,
                            start_date=start_date,
                            end_date=end_date)
    
    elif report_type == 'bill':
        return render_template('reports/bill_report.html',
                            student=student,
                            stats=stats,
                            records=attendance_records,
                            start_date=start_date,
                            end_date=end_date)
    
    # Default to detailed report (modal)
    return render_template('reports/detailed_report.html',
                        student=student,
                        stats=stats,
                        records=attendance_records,
                        start_date=start_date,
                        end_date=end_date)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # Define available departments and years for the form
    departments = ['Computer Science', 'Information Technology', 'Mechanical', 'Civil', 
                  'Electronics', 'Electrical', 'Aerospace', 'Biotechnology']
    years = [1, 2, 3, 4]
    
    if request.method == 'POST':
        try:
            # Get form data with proper stripping
            form_data = {
                'username': request.form.get('username', '').strip(),
                'password': request.form.get('password', '').strip(),
                'name': request.form.get('name', '').strip(),
                'department': request.form.get('department', '').strip(),
                'year': request.form.get('year', '1').strip(),
                'room_number': request.form.get('room_number', '').strip().upper()  # Convert to uppercase for consistency
            }
            
            print("\n=== Registration Attempt ===")
            print("Form data received:", form_data)
            
            # Check for missing fields
            missing_fields = [field for field, value in form_data.items() if not value]
            if missing_fields:
                error_msg = f'Missing required fields: {", ".join(missing_fields)}'
                print(error_msg)
                flash('All fields are required', 'error')
                return render_template('register.html',
                                    departments=departments,
                                    years=years,
                                    form_data=form_data)
            
            # Validate year
            try:
                year_int = int(form_data['year'])
                if year_int < 1 or year_int > 4:
                    print(f"Invalid year: {year_int}")
                    flash('Please select a valid year (1-4)', 'error')
                    return render_template('register.html',
                                        departments=departments,
                                        years=years,
                                        form_data=form_data)
            except ValueError:
                print(f"Invalid year value: {form_data['year']}")
                flash('Invalid year selected', 'error')
                return render_template('register.html',
                                    departments=departments,
                                    years=years,
                                    form_data=form_data)
            
            # Check room number format
            if not all(c.isalnum() or c in ' -_' for c in form_data['room_number']):
                print(f"Invalid room number format: {form_data['room_number']}")
                flash('Room number can only contain letters, numbers, spaces, hyphens, and underscores', 'error')
                return render_template('register.html',
                                    departments=departments,
                                    years=years,
                                    form_data=form_data)
            
            # Check username availability (case-insensitive)
            existing_user = User.query.filter(db.func.lower(User.username) == form_data['username'].strip().lower()).first()
            if existing_user:
                print(f"Username '{form_data['username']}' already exists (case-insensitive match with {existing_user.username})")
                flash('This username is already taken. Please choose a different one.', 'error')
                form_data['username'] = ''
                return render_template('register.html',
                                    departments=departments,
                                    years=years,
                                    form_data=form_data)
            
            # Check if name already exists (case-insensitive)
            existing_name = User.query.filter(db.func.lower(User.name) == form_data['name'].strip().lower()).first()
            if existing_name:
                print(f"User with name '{form_data['name']}' already exists (case-insensitive match with {existing_name.name})")
                flash('A user with this name is already registered. Please use a different name or contact support if this is a mistake.', 'error')
                form_data['name'] = ''
                return render_template('register.html',
                                    departments=departments,
                                    years=years,
                                    form_data=form_data)
            
            # Check room number format (alphanumeric and some special chars)
            if not all(c.isalnum() or c in ' -_' for c in form_data['room_number']):
                print(f"Invalid room number format: {form_data['room_number']}")
                flash('Room number can only contain letters, numbers, spaces, hyphens, and underscores', 'error')
                return render_template('register.html',
                                    departments=departments,
                                    years=years,
                                    form_data=form_data)
            
            # Validate year
            try:
                year_int = int(form_data['year'])
                if year_int < 1 or year_int > 4:
                    print(f"Invalid year: {year_int}")
                    flash('Please select a valid year (1-4)', 'error')
                    return render_template('register.html',
                                        departments=departments,
                                        years=years,
                                        form_data=form_data)
            except ValueError:
                print(f"Invalid year value: {form_data['year']}")
                flash('Invalid year selected', 'error')
                return render_template('register.html',
                                    departments=departments,
                                    years=years,
                                    form_data=form_data)
            
            print("Creating new user...")
            # Create new user with student role by default
            new_user = User(
                username=form_data['username'].lower(),
                password=form_data['password'],  # In production, use: generate_password_hash(form_data['password'])
                name=form_data['name'].title(),
                department=form_data['department'],
                year=year_int,
                room_number=form_data['room_number'].upper(),
                role='student'
            )
            
            db.session.add(new_user)
            db.session.flush()  # This will generate the ID but not commit
            print(f"New user created with ID: {new_user.id}")
            
            # Commit the transaction
            db.session.commit()
            print("User successfully saved to database")
            
            flash('Registration successful! You can now login with your credentials.', 'success')
            # Redirect to login page after successful registration
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            error_msg = f'Registration error: {str(e)}'
            print("\n!!! ERROR DURING REGISTRATION !!!")
            print(error_msg)
            print("Error type:", type(e).__name__)
            print("Database URL:", app.config['SQLALCHEMY_DATABASE_URI'])
            
            # More specific error messages
            if 'UNIQUE constraint failed' in str(e) and 'username' in str(e):
                flash('This username is already taken. Please choose a different one.', 'error')
            elif 'UNIQUE constraint failed' in str(e) and 'name' in str(e):
                flash('A user with this name is already registered.', 'error')
            else:
                flash(f'An error occurred during registration: {str(e)}', 'error')
            
            # Return form with entered data
            return render_template('register.html',
                                departments=departments,
                                years=years,
                                form_data=form_data if 'form_data' in locals() else {})
    
    # For GET request, show empty form
    print("Displaying registration form")
    return render_template('register.html', 
                         departments=departments, 
                         years=years,
                         form_data=request.form if request.method == 'POST' else {})

@app.route('/weekly_menu', methods=['GET','POST'])
@login_required
def weekly_menu():
    if current_user.role == 'admin':
        if request.method == 'POST':
            day = request.form['day']
            meal_type = request.form['meal_type']
            description = request.form['description']
            cost = float(request.form['cost'])
            entry = WeeklyMenu(day=day, meal_type=meal_type, description=description, cost=cost)
            db.session.add(entry)
            db.session.commit()
            flash('Weekly menu entry added')
            return redirect(url_for('weekly_menu'))
        order_case = case({
            'Monday': 1, 'Tuesday': 2, 'Wednesday': 3,
            'Thursday': 4, 'Friday': 5, 'Saturday': 6, 'Sunday': 7
        }, value=WeeklyMenu.day, else_=8)
        menus = WeeklyMenu.query.order_by(order_case, WeeklyMenu.meal_type).all()
        # Load current meal schedule costs
        schedules = MealSchedule.query.all()
        schedule_dict = {ms.meal_type: ms.cost for ms in schedules}
        return render_template('weekly_menu.html', menus=menus, schedules=schedule_dict)
    elif current_user.role == 'student':
        # Student view: weekly menu with checkboxes
        # Group menus by weekday
        menus = WeeklyMenu.query.all()
        menus_by_day = {}
        for m in menus:
            menus_by_day.setdefault(m.day, {})[m.meal_type] = m
        today = datetime.now().date()
        start = today - timedelta(days=today.weekday())  # Monday
        dates = [start + timedelta(days=i) for i in range(7)]
        if request.method == 'POST':
            for key in request.form:
                if key.startswith('meal_'):
                    _, date_str, meal = key.split('_', 2)
                    date_val = datetime.strptime(date_str, '%Y-%m-%d').date()
                    attendance = Attendance.query.filter_by(user_id=current_user.id, date=date_val).first()
                    if not attendance:
                        attendance = Attendance(user_id=current_user.id, date=date_val)
                        db.session.add(attendance)
                    setattr(attendance, meal, True)
            db.session.commit()
            flash('Weekly attendance selected')
            return redirect(url_for('dashboard'))
        return render_template('student_weekly_menu.html', dates=dates, menus_by_day=menus_by_day)

@app.route('/weekly_menu/edit/<int:menu_id>', methods=['GET','POST'])
@login_required
def edit_weekly_menu(menu_id):
    if current_user.role != 'admin':
        flash('Only admin can edit weekly menu')
        return redirect(url_for('dashboard'))
    entry = WeeklyMenu.query.get_or_404(menu_id)
    if request.method == 'POST':
        entry.day = request.form['day']
        entry.meal_type = request.form['meal_type']
        entry.description = request.form['description']
        entry.cost = float(request.form['cost'])
        db.session.commit()
        flash('Weekly menu entry updated')
        return redirect(url_for('weekly_menu'))
    return render_template('edit_weekly_menu.html', entry=entry)

@app.route('/weekly_menu/delete/<int:menu_id>', methods=['POST'])
@login_required
def delete_weekly_menu(menu_id):
    if current_user.role != 'admin':
        flash('Only admin can delete weekly menu')
        return redirect(url_for('dashboard'))
    entry = WeeklyMenu.query.get_or_404(menu_id)
    db.session.delete(entry)
    db.session.commit()
    flash('Weekly menu entry deleted')
    return redirect(url_for('weekly_menu'))

if __name__ == '__main__':
    app.run(debug=True)

