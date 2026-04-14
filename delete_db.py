import os
db_path = "C:\\Users\\aenit\\Desktop\\elysia\\backend\\app_metadata.db"
if os.path.exists(db_path):
    os.remove(db_path)
    print("Database deleted successfully")
else:
    print("Database file does not exist")
