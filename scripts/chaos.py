"""Simulator CLI.  Usage: python scripts\\chaos.py <command> [args]

  status
  start | stop | reset
  rps <n>
  burst <rps> [seconds]
  attack [card_testing|takeover] [count]
  drift <mild|severe> [ramp_seconds]
  drift-set amount=0.5 online=0.3 distance=0 night=0.2 ramp=20
  drift-clear
  replay <filename_in_simulator\\data> [rps]
  replay-stop
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:4010"


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "detail": e.read().decode()[:500]}
    except urllib.error.URLError as e:
        return {"error": f"cannot reach {BASE}: {e.reason}"}


def main(argv):
    if not argv:
        print(__doc__)
        return
    cmd, a = argv[0], argv[1:]
    if cmd == "status":
        out = call("/status")
    elif cmd in ("start", "stop", "reset"):
        out = call(f"/control/{cmd}", {})
    elif cmd == "rps":
        out = call("/control/rps", {"rps": float(a[0])})
    elif cmd == "burst":
        out = call("/control/burst", {"rps": float(a[0]), "duration_s": float(a[1]) if len(a) > 1 else 20})
    elif cmd == "attack":
        out = call("/control/attack", {"kind": a[0] if a else "card_testing",
                                       "n_attacks": int(a[1]) if len(a) > 1 else 1})
    elif cmd == "drift":
        out = call("/control/drift", {"preset": a[0], "ramp_seconds": float(a[1]) if len(a) > 1 else 30})
    elif cmd == "drift-set":
        body = {}
        for kv in a:
            k, v = kv.split("=")
            body["ramp_seconds" if k == "ramp" else k] = float(v)
        out = call("/control/drift", body)
    elif cmd == "drift-clear":
        out = call("/control/drift/clear", {})
    elif cmd == "replay":
        body = {"file": a[0]}
        if len(a) > 1:
            body["rps"] = float(a[1])
        out = call("/control/replay", body)
    elif cmd == "replay-stop":
        out = call("/control/replay/stop", {})
    else:
        print(__doc__)
        return
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])