"""Load test of the console: N people at once, each opening pages in a loop (with the API calls those pages make),
plus W people watching the live camera. Prints throughput, latency percentiles and errors per endpoint.

  pip install httpx websockets
  python scripts/loadtest.py <console url> <email> <password> <people> <live viewers> <seconds> [camera id]

Use a test copy or a quiet moment: it signs in once and only reads. One Python process can only drive ~25
people before it becomes the bottleneck itself, so run several at once for more (docs/deploy.md).
Results 2026-11-15: docs/deploy.md, "Load test"."""
import asyncio, statistics, sys, time, random, json
import httpx, websockets

BASE, EMAIL, PW = sys.argv[1], sys.argv[2], sys.argv[3]
USERS, VIEWERS, SECS = int(sys.argv[4]), int(sys.argv[5]), float(sys.argv[6])
CAM = sys.argv[7] if len(sys.argv) > 7 else "cam_01"
PAGES = [  # what the console's pages ask for
    ["/api/auth/me", "/api/incidents?limit=8", "/api/stats?hours=24", "/api/cameras", "/api/rules"],     # overview
    ["/api/incidents?limit=50", "/api/incidents?status=open&limit=50"],                                  # incidents
    ["/api/stats?hours=168", "/api/incidents?hours=168&limit=200"],                                      # analytics
    ["/api/cameras", f"/api/cameras/{CAM}/frame", f"/api/zones?camera_id={CAM}"],                        # cameras
    ["/api/rules"],                                                                                      # rules
]
results = {}   # path -> [latencies], errors
errors = {}

def norm(path): return path.split("?")[0]

async def user(client, stop):
    while time.time() < stop:
        for path in random.choice(PAGES):
            t = time.perf_counter()
            try:
                r = await client.get(BASE + path, timeout=30)
                ok = r.status_code < 400
            except Exception as e:
                ok = False
            dt = (time.perf_counter() - t) * 1000
            results.setdefault(norm(path), []).append(dt)
            if not ok: errors[norm(path)] = errors.get(norm(path), 0) + 1
        await asyncio.sleep(random.uniform(0.5, 2.0))   # a person reads the page

async def viewer(token, stop, counts):
    url = BASE.replace("http", "ws", 1) + f"/api/cameras/{CAM}/live"
    origin = BASE
    try:
        async with websockets.connect(url, additional_headers={"Cookie": f"sm_session={token}", "Origin": origin}, max_size=None) as ws:
            while time.time() < stop:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    continue
                counts.append(time.time()); await ws.send("1")
    except Exception as e:
        errors["live (websocket)"] = errors.get("live (websocket)", 0) + 1

async def main():
    async with httpx.AsyncClient() as c:
        r = await c.post(BASE + "/api/auth/login", json={"email": EMAIL, "password": PW}, headers={"Origin": BASE})
        r.raise_for_status(); token = c.cookies.get("sm_session")
    stop = time.time() + SECS
    limits = httpx.Limits(max_connections=USERS * 2)
    async with httpx.AsyncClient(cookies={"sm_session": token}, limits=limits, http2=False) as client:
        counts = []
        t0 = time.time()
        await asyncio.gather(*[user(client, stop) for _ in range(USERS)], *[viewer(token, stop, counts) for _ in range(VIEWERS)])
        dur = time.time() - t0
    total = sum(len(v) for v in results.values())
    print(f"{USERS} people browsing + {VIEWERS} watching live for {dur:.0f} s: {total} requests ({total/dur:.0f}/s), errors: {sum(errors.values())}")
    for path, lat in sorted(results.items()):
        lat.sort()
        p = lambda q: lat[min(len(lat)-1, int(len(lat)*q))]
        print(f"  {path:32s} n={len(lat):5d}  median {p(0.5):6.0f} ms  95% {p(0.95):6.0f} ms  worst {lat[-1]:6.0f} ms  errors {errors.get(path, 0)}")
    if VIEWERS:
        print(f"  live view: {len(counts)/dur/VIEWERS:.1f} pictures/s per viewer, errors {errors.get('live (websocket)', 0)}")
asyncio.run(main())
