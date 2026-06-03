import sys
import os
from sqlalchemy import text

# Add parent directory to path to import database config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine

def main():
    print("Connecting to database and adding request_id column if not exists...")
    with engine.connect() as conn:
        # Check if the column already exists
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='click_events' AND column_name='request_id';
        """)
        result = conn.execute(check_query).fetchone()
        
        if result:
            print("Column 'request_id' already exists in table 'click_events'.")
        else:
            print("Adding column 'request_id' to 'click_events' table...")
            alter_query = text("""
                ALTER TABLE click_events 
                ADD COLUMN request_id VARCHAR(255) UNIQUE;
            """)
            conn.execute(alter_query)
            conn.commit()
            print("Successfully added request_id column!")

if __name__ == "__main__":
    main()
