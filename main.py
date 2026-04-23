import logging
import mimetypes
import multiprocessing
import os
import socket
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pymongo import MongoClient
from pymongo.errors import PyMongoError


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "front-init"

HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "3000"))

SOCKET_BIND_HOST = os.getenv("SOCKET_BIND_HOST", "0.0.0.0")
SOCKET_HOST = os.getenv("SOCKET_HOST", "127.0.0.1")
SOCKET_PORT = int(os.getenv("SOCKET_PORT", "5000"))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "messages_db")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "messages")

HTML_ROUTES = {
    "/": FRONTEND_DIR / "index.html",
    "/index.html": FRONTEND_DIR / "index.html",
    "/message": FRONTEND_DIR / "message.html",
    "/message.html": FRONTEND_DIR / "message.html",
}

STATIC_ROUTES = {
    "/style.css": FRONTEND_DIR / "style.css",
    "/logo.png": FRONTEND_DIR / "logo.png",
}


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(processName)s %(levelname)s %(message)s",
    )


def get_mongo_collection(retries: int = 15, delay: int = 2):
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            client.admin.command("ping")
            logging.info("Connected to MongoDB on attempt %s", attempt)
            return client[MONGO_DB][MONGO_COLLECTION]
        except PyMongoError as error:
            last_error = error
            logging.warning(
                "MongoDB is unavailable on attempt %s/%s: %s",
                attempt,
                retries,
                error,
            )
            time.sleep(delay)
    raise RuntimeError("Could not connect to MongoDB") from last_error


def send_to_socket_server(data: bytes) -> None:
    with socket.create_connection((SOCKET_HOST, SOCKET_PORT), timeout=2) as client_socket:
        client_socket.sendall(data)


def build_document(data: bytes) -> dict[str, str]:
    parsed_data = parse_qs(data.decode("utf-8"), keep_blank_values=True)
    return {
        "date": str(datetime.now()),
        "username": parsed_data.get("username", [""])[0],
        "message": parsed_data.get("message", [""])[0],
    }


def run_socket_server() -> None:
    configure_logging()
    collection = get_mongo_collection()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((SOCKET_BIND_HOST, SOCKET_PORT))
        server_socket.listen()
        logging.info("Socket server started on %s:%s", SOCKET_BIND_HOST, SOCKET_PORT)
        while True:
            connection, address = server_socket.accept()
            with connection:
                payload = bytearray()
                while chunk := connection.recv(4096):
                    payload.extend(chunk)

                try:
                    document = build_document(bytes(payload))
                    collection.insert_one(document)
                    logging.info("Saved message from %s", address)
                except (UnicodeDecodeError, PyMongoError, ValueError) as error:
                    logging.exception("Failed to process socket payload: %s", error)


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        route = urlparse(self.path).path

        if route in HTML_ROUTES:
            self.serve_file(HTML_ROUTES[route])
            return

        if route in STATIC_ROUTES:
            self.serve_file(STATIC_ROUTES[route])
            return

        self.serve_file(
            FRONTEND_DIR / "error.html",
            status=HTTPStatus.NOT_FOUND,
        )

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if route not in {"/message", "/message.html"}:
            self.serve_file(
                FRONTEND_DIR / "error.html",
                status=HTTPStatus.NOT_FOUND,
            )
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            send_to_socket_server(body)
        except OSError as error:
            logging.exception("Could not send data to socket server: %s", error)
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Socket server unavailable")
            return

        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.end_headers()

    def serve_file(self, filepath: Path, status: HTTPStatus = HTTPStatus.OK) -> None:
        if not filepath.exists():
            self.serve_file(FRONTEND_DIR / "error.html", status=HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(filepath)
        self.send_response(status)
        if filepath.suffix in {".html", ".css"}:
            content_type = f"{content_type or 'text/plain'}; charset=utf-8"
        self.send_header("Content-Type", content_type or "text/plain; charset=utf-8")
        self.end_headers()

        with open(filepath, "rb") as file:
            self.wfile.write(file.read())

    def log_message(self, format: str, *args) -> None:
        logging.info("%s - %s", self.address_string(), format % args)


def run_http_server() -> None:
    configure_logging()
    server = HTTPServer((HTTP_HOST, HTTP_PORT), AppHandler)
    logging.info("HTTP server started on %s:%s", HTTP_HOST, HTTP_PORT)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    configure_logging()

    socket_process = multiprocessing.Process(
        target=run_socket_server,
        name="socket-server",
    )
    http_process = multiprocessing.Process(
        target=run_http_server,
        name="http-server",
    )

    socket_process.start()
    time.sleep(0.5)
    http_process.start()

    processes = [socket_process, http_process]

    try:
        while True:
            for process in processes:
                if not process.is_alive():
                    raise RuntimeError(f"{process.name} stopped unexpectedly")
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutdown requested")
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join()


if __name__ == "__main__":
    main()
