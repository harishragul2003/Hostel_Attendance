from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta, time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Change this to a secure key in production
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hostel.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

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
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'student'
    name = db.Column(db.String(120), nullable=False)
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
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:  # In production, use proper password hashing
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

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

    return render_template('student_dashboard.html', 
                         schedules=schedules,
                         week_attendance=week_attendance)

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied')
        return redirect(url_for('dashboard'))
    
    # Get today's date
    today = datetime.now().date()
    
    # Get all students
    students = User.query.filter_by(role='student').all()
    
    # Get today's attendance records
    attendance = Attendance.query.filter_by(date=today).all()
    
    return render_template('admin_dashboard.html', 
                         students=students,
                         attendance=attendance)

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

    students = User.query.filter_by(role='student').all()
    
    # Calculate detailed statistics for each student
    for student in students:
        attendance_records = student.attendance
        
        # Initialize statistics
        student.stats = {
            'total_days': len(attendance_records),
            'breakfast_count': 0,
            'lunch_count': 0,
            'dinner_count': 0,
            'leave_days': 0,
            'breakfast_cost': 0,
            'lunch_cost': 0,
            'dinner_cost': 0,
            'total_cost': 0,
            'avg_daily_cost': 0
        }
        
        # Calculate statistics
        for record in attendance_records:
            if record.breakfast:
                student.stats['breakfast_count'] += 1
                student.stats['breakfast_cost'] += MealSchedule.query.filter_by(meal_type='breakfast').first().cost
            if record.lunch:
                student.stats['lunch_count'] += 1
                student.stats['lunch_cost'] += MealSchedule.query.filter_by(meal_type='lunch').first().cost
            if record.dinner:
                student.stats['dinner_count'] += 1
                student.stats['dinner_cost'] += MealSchedule.query.filter_by(meal_type='dinner').first().cost
            if record.leave_status:
                student.stats['leave_days'] += 1
            
            student.stats['total_cost'] += record.daily_cost
        
        # Calculate average daily cost excluding leave days
        denominator = student.stats['total_days'] - student.stats['leave_days']
        if denominator > 0:
            student.stats['avg_daily_cost'] = student.stats['total_cost'] / denominator
        else:
            student.stats['avg_daily_cost'] = 0
    
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
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        room_number = request.form['room_number']
        # prevent duplicate usernames
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        # create new student user
        user = User(username=username, password=password, name=name, room_number=room_number, role='student')
        db.session.add(user)
        db.session.commit()
        flash('Account created successfully. Please login')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/weekly_menu', methods=['GET','POST'])
@login_required
def weekly_menu():
    if current_user.role != 'admin':
        flash('Only admin can manage weekly menu')
        return redirect(url_for('dashboard'))
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
    menus = WeeklyMenu.query.order_by(WeeklyMenu.day, WeeklyMenu.meal_type).all()
    return render_template('weekly_menu.html', menus=menus)

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
    with app.app_context():
        db.create_all()
        
        # Create default admin user if it doesn't exist
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                password='admin123',  # Change this in production!
                role='admin',
                name='Administrator',
                room_number='ADMIN'
            )
            db.session.add(admin)
            db.session.commit()
            print('Default admin user created!')
            print('Username: admin')
            print('Password: admin123')
    
    app.run(debug=True)
