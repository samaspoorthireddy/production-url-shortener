# repro_race.py
# Minimal reproduction: concurrent redirects on a single short link
import asyncio
import aiohttp

SHORT_CODE = "OJvJow5E"  # A link that exists in the DB (like the one from the lab notebook)
CONCURRENCY = 10
BASE_URL = f"http://localhost:3000/{SHORT_CODE}"


async def make_request(session):
    async with session.get(BASE_URL, allow_redirects=False) as resp:
        return resp.status


async def main():
    async with aiohttp.ClientSession() as session:
        # Fire all requests simultaneously
        tasks = [make_request(session) for _ in range(CONCURRENCY)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if isinstance(r, int) and r in (301, 302)]
    errors = [r for r in results if isinstance(r, int) and r == 500]
    exceptions = [r for r in results if isinstance(r, Exception)]

    print(f"Results: {len(successes)} redirects, {len(errors)} errors, "
          f"{len(exceptions)} exceptions")

    if errors:
        print("BUG REPRODUCED: 500 errors under concurrent load")
    else:
        print("No errors this run. Try again or increase CONCURRENCY.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error running repro script: {e}")
