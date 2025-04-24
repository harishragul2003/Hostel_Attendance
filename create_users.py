from app import app, db, User, MealSchedule
from datetime import datetime, time

def create_test_users():
    with app.app_context():
        # Create database tables
        db.create_all()
        
        # Create admin user
        admin = User(
            username='admin',
            password='admin123',  # In production, use proper password hashing
            role='admin',
            name='Admin User',
            room_number='ADMIN'
        )

        # Create student user
        student = User(
            username='student',
            password='student123',  # In production, use proper password hashing
            role='student',
            name='John Doe',
            room_number='A101',
            total_bill=0.0
        )

        # Create default meal schedules with costs
        breakfast = MealSchedule(
            meal_type='breakfast',
            start_time=time(7, 0),  # 7:00 AM
            end_time=time(9, 0),    # 9:00 AM
            cost=50.0               # ₹50 for breakfast
        )

        lunch = MealSchedule(
            meal_type='lunch',
            start_time=time(12, 0),  # 12:00 PM
            end_time=time(14, 0),    # 2:00 PM
            cost=100.0              # ₹100 for lunch
        )

        dinner = MealSchedule(
            meal_type='dinner',
            start_time=time(19, 0),  # 7:00 PM
            end_time=time(21, 0),    # 9:00 PM
            cost=100.0              # ₹100 for dinner
        )

        # Add all to database
        db.session.add(admin)
        db.session.add(student)
        db.session.add(breakfast)
        db.session.add(lunch)
        db.session.add(dinner)
        db.session.commit()

if __name__ == '__main__':
    create_test_users()
    print("Test users created successfully!")
    print("Admin credentials: username='admin', password='admin123'")
    print("Student credentials: username='student', password='student123'")
    print("\nDefault meal schedules created:")
    print("Breakfast: 7:00 AM - 9:00 AM (₹50)")
    print("Lunch: 12:00 PM - 2:00 PM (₹100)")
    print("Dinner: 7:00 PM - 9:00 PM (₹100)")
