from app import app, db, User

with app.app_context():
    # Get all users
    users = User.query.all()
    print("Current users in the database:")
    print("ID | Username | Name | Role | Department | College | Year | Room")
    print("-" * 80)
    for user in users:
        print(f"{user.id} | {user.username} | {user.name} | {user.role} | {getattr(user, 'department', 'N/A')} | {getattr(user, 'college_name', 'N/A')} | {getattr(user, 'year', 'N/A')} | {getattr(user, 'room_number', 'N/A')}")
    
    # Check if the users table exists
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    print("\nTables in database:", inspector.get_table_names())
    
    # Check columns in users table
    if 'user' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('user')]
        print("\nColumns in user table:", columns)
