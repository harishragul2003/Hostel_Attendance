from app import app, db
from app import User

def add_department_column():
    with app.app_context():
        # Add department column with default value 'General'
        db.engine.execute('ALTER TABLE user ADD COLUMN department VARCHAR(50) DEFAULT "General"')
        
        # Update existing admin user with department 'Administration'
        admin = User.query.filter_by(username='admin').first()
        if admin:
            admin.department = 'Administration'
            db.session.commit()
        
        print("Migration completed successfully!")

if __name__ == '__main__':
    add_department_column()
