import http.server
import json
import os


class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))


def main():
    port = int(os.environ.get("PORT", 8080))
    server = http.server.HTTPServer(("", port), HealthHandler)
    print(f"Health check server running on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
