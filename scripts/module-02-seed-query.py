import sys
import os

# Add the parent directory to the python path so we can import database and models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, engine, Base
from models import Link, ClickEvent

def main():
    print("Initializing database tables...")
    # Explicitly create tables if they do not exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 1. Clean up any existing test links to avoid duplicate unique key error
        test_code = "testslug"
        db.query(Link).filter(Link.code == test_code).delete()
        db.commit()

        # 2. Insert code
        print(f"Inserting new link with code: {test_code}")
        new_link = Link(
            code=test_code,
            long_url="https://google.com",
            created_by="test-user"
        )
        db.add(new_link)
        db.commit()
        db.refresh(new_link)
        print(f"inserted code: {new_link.code}")

        # 3. Select code & match long_url
        print(f"Querying link by code: {test_code}")
        queried_link = db.query(Link).filter(Link.code == test_code).first()
        if queried_link:
            print(f"selected code: {queried_link.code}")
            print(f"matched long_url: {queried_link.long_url}")
        else:
            print("ERROR: Could not retrieve the inserted link!")
            sys.exit(1)

    except Exception as e:
        print(f"Database error occurred: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
