import urllib.request
import urllib.error
import json
import sys

def main():
    url = "http://localhost:8000/links/"
    data = {
        "long_url": "http://\\\\evil.com"
    }
    
    # Encode JSON data
    encoded_data = json.dumps(data).encode("utf-8")
    
    req = urllib.request.Request(
        url,
        data=encoded_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    print("Sending request with invalid URL bypass (http://\\\\evil.com)...")
    try:
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            print("ERROR: Request succeeded and stored the invalid URL!")
            print(f"Response (201 Created): {body}")
            sys.exit(1)
    except urllib.error.HTTPError as e:
        if e.code == 422:
            body = e.read().decode("utf-8")
            response_json = json.loads(body)
            print("SUCCESS: Request was correctly rejected with status 422 Unprocessable Entity!")
            print(f"Error detail: {response_json['detail'][0]['msg']}")
            sys.exit(0)
        else:
            print(f"ERROR: Received unexpected HTTP status code {e.code}")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to connect to the server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
