"""Start tonix2: python run.py   (then use the page that opens in your browser)."""
import argparse
import sys
import threading
import webbrowser

if sys.version_info < (3, 10):
    sys.exit("tonix2 needs Python 3.10 or newer.")

try:
    from tonix2.web import create_app
except ImportError as exc:
    sys.exit(f"A required package is missing ({exc.name}). Run:  pip install -r requirements.txt")


def main():
    ap = argparse.ArgumentParser(description="Find your papers and their citations for Sonix.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}/"
    print(f"tonix2 is running at {url}")
    print("Close this window or press Ctrl+C to stop it.")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    create_app().run(host="127.0.0.1", port=args.port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
