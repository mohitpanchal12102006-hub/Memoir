"""python -m memoir_engine  ->  starts Memoir on http://127.0.0.1:8787"""
import argparse
import sys
import threading
import webbrowser


def main():
    ap = argparse.ArgumentParser(prog="memoir", description="Memoir: lossless chronology and Takeout organizer")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1", help="Keep 127.0.0.1 so only this computer can use the app.")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    import uvicorn
    from . import exif
    if not exif.available():
        print("WARNING: exiftool was not found. Scanning and export need it. Install it from https://exiftool.org", file=sys.stderr)
    url = f"http://{args.host}:{args.port}"
    print(f"Memoir is running at {url}  (press Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("memoir_engine.api:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
