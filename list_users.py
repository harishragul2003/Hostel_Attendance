from app import app, db, User

with app.app_context():
    print("Existing users in the database:")
    print("-" * 50)
    users = User.query.all()
    if not users:
        print("No users found in the database.")
    else:
        print(f"{'ID':<5} {'Username':<20} {'Name':<30} {'Role':<10}")
        print("-" * 50)
        for user in users:
            print(f"{user.id:<5} {user.username:<20} {user.name:<30} {user.role}")
