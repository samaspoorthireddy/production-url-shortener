import sys
import os
from sqlalchemy import text

# Add parent directory to path to import database config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine

def main():
    print("Connecting to database and running schema updates...")
    with engine.connect() as conn:
        # 1. Add tags column to links table if not exists
        check_tags_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='links' AND column_name='tags';
        """)
        tags_exists = conn.execute(check_tags_query).fetchone()
        
        if tags_exists:
            print("Column 'tags' already exists in table 'links'.")
        else:
            print("Adding column 'tags' to 'links' table...")
            alter_query = text("""
                ALTER TABLE links 
                ADD COLUMN tags VARCHAR(30)[] NOT NULL DEFAULT '{}';
            """)
            conn.execute(alter_query)
            conn.commit()
            print("Successfully added tags column!")

        # 2. Add GIN index for FTS on long_url
        print("Creating GIN index for Full-Text Search on long_url...")
        fts_index_query = text("""
            CREATE INDEX IF NOT EXISTS links_long_url_fts_idx 
            ON links USING gin(to_tsvector('english', long_url));
        """)
        conn.execute(fts_index_query)
        conn.commit()
        print("FTS index verified/created.")

        # 3. Add GIN index for tags array
        print("Creating GIN index for tags array...")
        tags_index_query = text("""
            CREATE INDEX IF NOT EXISTS links_tags_gin_idx 
            ON links USING gin(tags);
        """)
        conn.execute(tags_index_query)
        conn.commit()
        print("Tags GIN index verified/created.")
        
        print("Schema updates completed successfully!")

if __name__ == "__main__":
    main()
