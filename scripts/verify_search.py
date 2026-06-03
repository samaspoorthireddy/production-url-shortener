import sys
import os
import urllib.request
import json

# Add parent directory to path to import database config and models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import Link, ClickEvent

BASE_URL = "http://localhost:3000"
HEADERS_A = {
    "X-API-Key": "API_KEY_A",
    "Content-Type": "application/json"
}
HEADERS_B = {
    "X-API-Key": "API_KEY_B",
    "Content-Type": "application/json"
}

def make_request(url, headers, method="GET", data=None):
    req_data = None
    if data:
        req_data = json.dumps(data).encode("utf-8")
    
    req = urllib.request.Request(url, headers=headers, method=method, data=req_data)
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            body = json.loads(body)
        except:
            pass
        return e.code, body

def main():
    print("====================================================")
    print("      STARTING MODULE 8 SEARCH VERIFICATION         ")
    print("====================================================")

    db = SessionLocal()
    try:
        # Clean up any existing test links to make our counts absolute
        print("Cleaning up old test links...")
        db.query(ClickEvent).delete()
        db.query(Link).delete()
        db.commit()

        # 1. Direct SQLAlchemy Seeding to bypass API rate limiter
        print("\n--- 1. Seeding Links directly via SQLAlchemy ---")
        links_a = [
            Link(code="gogSearch", long_url="https://www.google.com/search?q=apple", created_by="user_a", tags=["tech", "search"]),
            Link(code="gitTrend", long_url="https://github.com/trending", created_by="user_a", tags=["tech", "code"]),
            Link(code="hnNews", long_url="https://news.ycombinator.com/", created_by="user_a", tags=["news", "tech"]),
            Link(code="yaFinance", long_url="https://finance.yahoo.com", created_by="user_a", tags=["finance"]),
            Link(code="wikiRef", long_url="https://www.wikipedia.org", created_by="user_a", tags=["reference"])
        ]
        for l in links_a:
            db.add(l)
        
        link_b = Link(code="gogMaps", long_url="https://www.google.com/maps", created_by="user_b", tags=["search", "maps"])
        db.add(link_b)
        db.commit()

        # Refresh to get IDs
        for l in links_a:
            db.refresh(l)
        db.refresh(link_b)

        print(f"Seeded 5 links for user_a and 1 link for user_b successfully.")

        # 2. Simulate clicks directly in the database
        # 3 clicks on hnNews (id=links_a[2]), 1 click on yaFinance (id=links_a[3])
        print("\n--- 2. Simulating Clicks directly in Database ---")
        clicks = [
            ClickEvent(link_id=links_a[2].id, user_agent="TestBot", referrer="direct"),
            ClickEvent(link_id=links_a[2].id, user_agent="TestBot", referrer="direct"),
            ClickEvent(link_id=links_a[2].id, user_agent="TestBot", referrer="direct"),
            ClickEvent(link_id=links_a[3].id, user_agent="TestBot", referrer="direct"),
        ]
        for c in clicks:
            db.add(c)
        db.commit()
        print("Simulated clicks seeded.")

    except Exception as e:
        print(f"Failed to seed test data: {str(e)}")
        db.rollback()
        return
    finally:
        db.close()

    # 3. Perform API Searches using requests
    print("\n--- 3. Verification: Keyword Search (FTS) ---")
    status, res = make_request(f"{BASE_URL}/links/search?q=trending", HEADERS_A)
    assert status == 200, f"Keyword search failed: {status} {res}"
    results = res["results"]
    metadata = res["metadata"]
    print(f"Search 'q=trending' matches: {len(results)} links")
    assert len(results) == 1, "Should match exactly 1 link"
    assert "github.com/trending" in results[0]["long_url"], "Should match GitHub trending link"
    assert metadata["total_records"] == 1, "Metadata total_records should be 1"
    print("FTS Keyword search verified successfully!")

    print("\n--- 4. Verification: Tag Filtering ---")
    status, res = make_request(f"{BASE_URL}/links/search?tag=tech", HEADERS_A)
    assert status == 200, f"Tag search failed: {status} {res}"
    results = res["results"]
    metadata = res["metadata"]
    print(f"Search 'tag=tech' matches: {len(results)} links")
    assert len(results) == 3, "Should match exactly 3 links with tag 'tech'"
    for r in results:
        assert "tech" in r["tags"], "Matched links must contain the 'tech' tag"
    print("Tag array filtering verified successfully!")

    print("\n--- 5. Verification: Pagination & Capping ---")
    status, res = make_request(f"{BASE_URL}/links/search?page_size=500", HEADERS_A)
    assert status == 200
    metadata = res["metadata"]
    print(f"Requested page_size=500. Capped metadata: {metadata}")
    assert metadata["page_size"] == 100, "Should be capped to 100"
    
    # Test multi-page offset navigation
    status, res = make_request(f"{BASE_URL}/links/search?page_size=2&page=2", HEADERS_A)
    assert status == 200
    results = res["results"]
    metadata = res["metadata"]
    print(f"Page size 2, Page 2 metadata: {metadata}")
    assert len(results) == 2, "Page 2 should return 2 records"
    assert metadata["total_records"] == 5, "Total records should be 5"
    assert metadata["total_pages"] == 3, "Total pages should be 3 (ceil(5/2))"
    print("Pagination and capping verified successfully!")

    print("\n--- 6. Verification: Sorting by Click Count ---")
    status, res = make_request(f"{BASE_URL}/links/search?sort_by=click_count&sort_order=desc", HEADERS_A)
    assert status == 200
    results = res["results"]
    print("Results sorted by click_count descending:")
    for r in results:
        print(f"Link code={r['code']} click_count={r['click_count']} url={r['long_url']}")
    
    assert results[0]["code"] == "hnNews", "First link should be hnNews (3 clicks)"
    assert results[1]["code"] == "yaFinance", "Second link should be yaFinance (1 click)"
    print("Click count sorting verified successfully!")

    print("\n--- 7. Verification: Scoping Security Boundaries ---")
    status, res = make_request(f"{BASE_URL}/links/search", HEADERS_B)
    assert status == 200
    results = res["results"]
    metadata = res["metadata"]
    print(f"User B search matches: {len(results)} links (Total: {metadata['total_records']})")
    assert len(results) == 1, "User B should only see their own link"
    assert results[0]["code"] == "gogMaps", "Should only see User B's seeded link"
    print("Owner-scoping security boundaries verified successfully!")

    print("\n====================================================")
    print("     ALL SEARCH AND PAGINATION TESTS PASSED!        ")
    print("====================================================")

if __name__ == "__main__":
    main()
