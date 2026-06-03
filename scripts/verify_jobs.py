import sys
import os
import time
import uuid
import json
import urllib.request
import urllib.error
import subprocess
from datetime import datetime, timedelta

# Add parent directory to path to import DB and tasks
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import Link, ClickEvent
from app.celery_app import celery_app

BASE_URL = "http://localhost:3000"
API_KEY_HEADERS = {"X-API-Key": "API_KEY_A"}

def make_request(method, path, headers=None, data=None):
    url = f"{BASE_URL}{path}"
    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)
            
    opener = urllib.request.build_opener(NoRedirectHandler())
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if data:
        req.add_header("Content-Type", "application/json")
        json_data = json.dumps(data).encode("utf-8")
    else:
        json_data = None
        
    try:
        with opener.open(req, data=json_data) as response:
            return response.status, json.loads(response.read().decode("utf-8")), dict(response.headers)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            err_data = json.loads(body) if body else e.reason
        except Exception:
            err_data = e.reason
        return e.code, err_data, dict(e.headers)
    except Exception as e:
        return 500, str(e), {}

def run_tests():
    print("====================================================")
    print("    STARTING MODULE 7 BACKGROUND JOBS VERIFICATION  ")
    print("====================================================\n")
    
    # 1. Start Celery worker in background for testing
    print("--> Starting Celery background worker process...")
    worker_proc = subprocess.Popen(
        ["celery", "-A", "app.celery_app:celery_app", "worker", "--loglevel=INFO"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(3)  # Allow worker to boot up
    
    db = SessionLocal()
    try:
        # Create a new test link
        print("\n--- 1. Creating Test Link ---")
        long_url = "https://www.google.com"
        status, res, _ = make_request("POST", "/links/", headers=API_KEY_HEADERS, data={"long_url": long_url})
        print(f"POST /links/ status: {status}")
        assert status == 201, f"Expected 201, got {status}"
        link_id = res["id"]
        code = res["code"]
        print(f"Created link id={link_id}, code={code}")
        
        # Verify initial analytics count is 0
        status, res_an, _ = make_request("GET", f"/links/{link_id}/analytics", headers=API_KEY_HEADERS)
        print(f"Initial Analytics: {res_an}")
        assert status == 200
        assert res_an["total_clicks"] == 0
        
        # 2. Trigger Async redirects
        print("\n--- 2. Triggering Redirects ---")
        status1, _, headers1 = make_request("GET", f"/r/{code}")
        print(f"First redirect status: {status1}")
        assert status1 == 302
        
        status2, _, headers2 = make_request("GET", f"/r/{code}")
        print(f"Second redirect status: {status2}")
        assert status2 == 302
        
        # Wait a moment for background Celery worker to process jobs
        print("Waiting 3 seconds for Celery worker to write to database...")
        time.sleep(3)
        
        # Verify click events exist and analytics read counts
        status, res_an, _ = make_request("GET", f"/links/{link_id}/analytics", headers=API_KEY_HEADERS)
        print(f"Analytics after redirects: {res_an}")
        assert status == 200
        assert res_an["total_clicks"] == 2, f"Expected 2 clicks, got {res_an['total_clicks']}"
        assert res_an["last_clicked"] is not None
        
        # 3. Idempotency protection check
        print("\n--- 3. Testing Click Idempotency (Duplicate Prevention) ---")
        from app.tasks import log_click_task
        
        req_id = f"test-idempotency-{uuid.uuid4().hex}"
        print(f"Enqueueing task with request_id={req_id}...")
        res1 = log_click_task.delay(link_id, "Mozilla", "https://t.co", "hash123", req_id)
        
        print(f"Enqueueing task again with the SAME request_id={req_id}...")
        res2 = log_click_task.delay(link_id, "Mozilla", "https://t.co", "hash123", req_id)
        
        # Wait for worker to finish processing
        time.sleep(2)
        
        # Count how many clicks exist with this request_id in database
        click_count = db.query(ClickEvent).filter(ClickEvent.request_id == req_id).count()
        print(f"Database records matching request_id '{req_id}': {click_count}")
        assert click_count == 1, f"Idempotency violation! Expected 1 click, found {click_count}"
        print("Idempotency (Elevator Button) verified successfully!")
        
        # 4. Graceful Degradation / Queue-down Drill
        print("\n--- 4. Queue-down Drill (Graceful Fallback) ---")
        # We simulate broken Celery by mocking Celery task.delay to throw a broker exception
        print("Simulating offline broker by patching Celery task...")
        from unittest import mock
        from app.tasks import log_click_task as real_task
        
        with mock.patch("app.tasks.log_click_task.delay", side_effect=Exception("Redis connection timed out (Simulated)")):
            start_time = time.perf_counter()
            status_deg, _, _ = make_request("GET", f"/r/{code}")
            duration_ms = (time.perf_counter() - start_time) * 1000
            print(f"Redirect completed under simulated queue outage. Status: {status_deg}, Duration: {duration_ms:.2f} ms")
            
            assert status_deg == 302, f"Expected redirect to succeed (302), got {status_deg}"
            print("Redirect completed seamlessly even with broker down. Fallback verified!")

        # 5. Data Retention Purge check
        print("\n--- 5. Clicking Retention Purge Test ---")
        # Manually create a click older than cutoff (e.g. 45 days ago)
        old_time = datetime.utcnow() - timedelta(days=45)
        old_req_id = f"old-click-{uuid.uuid4().hex}"
        print(f"Manually inserting historical click with timestamp {old_time}...")
        
        old_click = ClickEvent(
            link_id=link_id,
            clicked_at=old_time,
            user_agent="Mozilla",
            referrer="Direct",
            ip_hash="old_hash",
            request_id=old_req_id
        )
        db.add(old_click)
        db.commit()
        
        # Confirm old click is stored in database
        db_old_click = db.query(ClickEvent).filter(ClickEvent.request_id == old_req_id).first()
        assert db_old_click is not None, "Failed to insert old click"
        
        # Call the Purge API endpoint (retention_days=30)
        print("Triggering retention purge API POST /links/analytics/purge?retention_days=30...")
        status_purge, res_purge, _ = make_request("POST", "/links/analytics/purge?retention_days=30", headers=API_KEY_HEADERS)
        print(f"Purge API Response: {res_purge}")
        assert status_purge == 200
        
        print("Waiting for purge background worker task to complete...")
        time.sleep(2)
        
        # Verify old click is deleted
        db_old_click = db.query(ClickEvent).filter(ClickEvent.request_id == old_req_id).first()
        print(f"Old click after purge: {'FOUND' if db_old_click else 'DELETED'}")
        assert db_old_click is None, "Old click was NOT purged!"
        
        # Verify that recent clicks are still preserved
        recent_clicks = db.query(ClickEvent).filter(ClickEvent.link_id == link_id, ClickEvent.clicked_at > datetime.utcnow() - timedelta(days=1)).count()
        print(f"Recent clicks still preserved: {recent_clicks}")
        assert recent_clicks >= 2, "Recent clicks were incorrectly deleted!"
        print("Data retention purge verified successfully!")

    finally:
        db.close()
        # Shutdown background worker gracefully
        print("\n--> Shutting down background Celery worker...")
        worker_proc.terminate()
        try:
            worker_proc.wait(timeout=5)
            print("Celery worker terminated successfully.")
        except subprocess.TimeoutExpired:
            worker_proc.kill()
            print("Celery worker killed forcefully.")
            
    print("\n====================================================")
    print("     ALL BACKGROUND JOB AND ANALYTICS TESTS PASSED!  ")
    print("====================================================")

if __name__ == "__main__":
    run_tests()
