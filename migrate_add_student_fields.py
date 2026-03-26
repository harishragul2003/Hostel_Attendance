from app import app, db
from app import User

def add_student_fields():
    with app.app_context():
        # Add new columns with default values
        try:
            # Add college_name column
            db.engine.execute('ALTER TABLE user ADD COLUMN college_name VARCHAR(100) DEFAULT ""')
            
            # The department column was already added in the previous migration
            # Update existing users with default department 'General' if not set
            db.engine.execute('UPDATE user SET department = "General" WHERE department IS NULL')
            
            # Add year column with default value 1
            db.engine.execute('ALTER TABLE user ADD COLUMN year INTEGER DEFAULT 1')
            
            # Update existing admin user with college name
            admin = User.query.filter_by(username='admin').first()
            if admin:
                admin.college_name = 'Administration'
                admin.department = 'Administration'
                admin.year = 0
                db.session.commit()
            
            print("Migration completed successfully!")
        except Exception as e:
            print(f"Error during migration: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    add_student_fields()
