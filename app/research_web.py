from __future__ import annotations

import argparse
from contextlib import closing, contextmanager, suppress
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import sqlite3
from threading import Timer
from urllib.parse import urlsplit
import webbrowser

from plotly.offline import get_plotlyjs

from core import series_research

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "app/web_research"
MAX_BODY = 12 * 1024 * 1024
TRANSFORMS = ("level", "diff", "return", "yoy")
MIME_TYPES = {".html": "text/html", ".js": "application/javascript", ".css": "text/css",
              ".svg": "image/svg+xml", ".json": "application/json"}


def metadata(series):
    info = {key: value for key, value in series.items() if key != "points"}
    points = series["points"]
    first, last = min(points, key=lambda row: row["date"]), max(points, key=lambda row: row["date"])
    return {**info, "first": first["date"], "last": last["date"], "latest": last["value"], "count": len(points)}


def _choice(data, key, options, default):
    value = data.get(key, default)
    if value not in options:
        raise ValueError(f"{key}: unsupported option")
    return value


def _integer(data, key, low, high, default):
    value = data.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{key}: expected an integer from {low} to {high}")
    return value


def _text(data, key):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{key}: expected text")
    return value


def _series_options(data):
    start, end = data.get("start") or None, data.get("end") or None
    if any(value is not None and not isinstance(value, str) for value in (start, end)):
        raise ValueError("start/end: expected date strings")
    return {
        "frequency": _choice(data, "frequency", ("D", "M", "Q"), "M"),
        "aggregation": _choice(data, "aggregation", ("last", "mean", "sum"), "last"),
        "start": start,
        "end": end,
    }


class ResearchService:
    def __init__(self, builtins, storage: Path):
        self.builtins = {series["id"]: series for series in builtins}
        self.storage = storage
        storage.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._database() as database:
            database.execute("CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, data TEXT NOT NULL)")

    @contextmanager
    def _database(self):
        with closing(sqlite3.connect(self.storage)) as database, database:
            yield database

    def catalog(self):
        with self._database() as database:
            imports = [json.loads(row[0]) for row in database.execute("SELECT data FROM imports ORDER BY rowid")]
        return {"series": [metadata(s) for s in (*self.builtins.values(), *imports)]}

    def _find(self, series_id):
        if not isinstance(series_id, str):
            raise ValueError("請選擇資料序列")
        if series_id in self.builtins:
            return self.builtins[series_id]
        with self._database() as database:
            row = database.execute("SELECT data FROM imports WHERE id = ?", (series_id,)).fetchone()
        if row is None:
            raise ValueError(f"找不到序列：{series_id}")
        return json.loads(row[0])

    def _save_import(self, incoming):
        rows = [(series["id"], json.dumps(series, ensure_ascii=False, allow_nan=False)) for series in incoming]
        with self._database() as database:
            database.executemany(
                "INSERT INTO imports (id, data) VALUES (?, ?) ON CONFLICT (id) DO UPDATE SET data = excluded.data",
                rows,
            )

    def dispatch(self, path, data):
        if not isinstance(data, dict):
            raise ValueError("需要 JSON 物件")
        if path == "/api/csv/preview":
            return series_research.preview_csv(_text(data, "text"))
        if path == "/api/csv/import":
            columns = data.get("columns")
            available = data.get("available_column") or None
            frequency = _choice(data, "frequency", (None, "", "D", "M", "Q"), None) or None
            if not isinstance(columns, list) or not 1 <= len(columns) <= 100 or not all(
                isinstance(column, str) for column in columns
            ):
                raise ValueError("請選擇 1 至 100 個數值欄")
            if available is not None and not isinstance(available, str):
                raise ValueError("可用日期欄不正確")
            incoming = series_research.import_csv(
                _text(data, "text"), _text(data, "filename"), _text(data, "date_column"), columns,
                available, _text(data, "source"), _text(data, "unit"), frequency=frequency,
            )
            self._save_import(incoming)
            return {"series": [metadata(series) for series in incoming]}
        options = _series_options(data)
        if path == "/api/chart":
            requests = data.get("series")
            if not isinstance(requests, list) or len(requests) > 12:
                raise ValueError("單一圖表最多 12 條序列")
            chart = []
            for item in requests:
                if not isinstance(item, dict):
                    raise ValueError("序列格式不正確")
                series = self._find(item.get("id"))
                transform = _choice(item, "transform", TRANSFORMS, "level")
                points = series_research.chart_data(series, **options, transform=transform)
                chart.append({**metadata(series), "transform": transform, "points": points})
            return {"series": chart}
        if path == "/api/analyze":
            strict = data.get("strict", False)
            if not isinstance(strict, bool):
                raise ValueError("strict: expected true or false")
            return series_research.analyze(
                self._find(data.get("x")), self._find(data.get("y")),
                **options, x_transform=_choice(data, "x_transform", TRANSFORMS, "level"),
                y_transform=_choice(data, "y_transform", TRANSFORMS, "level"),
                lag=_integer(data, "lag", -60, 60, 0), window=_integer(data, "window", 3, 200, 12),
                strict=strict,
            )
        raise ValueError("未知的研究操作")


@lru_cache(maxsize=1)
def _plotly() -> bytes:
    return get_plotlyjs().encode("utf-8")


class ResearchHandler(BaseHTTPRequestHandler):
    def _reply(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        with suppress(BrokenPipeError, ConnectionResetError):
            self.end_headers()
            self.wfile.write(body)

    def _json(self, status, response):
        self._reply(status, json.dumps(response, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                    "application/json; charset=utf-8")

    def _is_local_request(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host")
        return host in hosts and self.headers.get("Origin", f"http://{host}") == f"http://{host}"

    def do_GET(self):
        if not self._is_local_request():
            self._json(403, {"error": "僅限本機使用"})
            return
        path = urlsplit(self.path).path
        if path == "/api/catalog":
            self._json(200, self.server.research.catalog())
        elif path == "/vendor/plotly.js":
            self._reply(200, _plotly(), "application/javascript; charset=utf-8")
        else:
            name = "index.html" if path == "/" else path.removeprefix("/")
            if name.startswith("vendor/"):
                directory, name = WEB_ROOT / "vendor", name.removeprefix("vendor/")
            else:
                directory = WEB_ROOT
            file = directory / name
            if file.name != name or file.suffix not in MIME_TYPES or not file.is_file():
                self._json(404, {"error": "找不到頁面"})
                return
            self._reply(200, file.read_bytes(), MIME_TYPES[file.suffix] + "; charset=utf-8")

    def do_POST(self):
        if not self._is_local_request():
            self._json(403, {"error": "僅限本機使用"})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "需要 JSON"})
            return
        try:
            length = int(self.headers.get("Content-Length", -1))
            if not 0 < length <= MAX_BODY:
                self._json(413, {"error": "請求太大或缺少內容"})
                return
            data = json.loads(self.rfile.read(length))
            response = self.server.research.dispatch(urlsplit(self.path).path, data)
            self._json(200, response)
        except (ValueError, TypeError, KeyError) as error:
            self._json(400, {"error": str(error)})
        except (OSError, OverflowError, sqlite3.Error):
            logging.exception("Research request failed")
            self._json(500, {"error": "本機處理失敗，請確認資料範圍與儲存權限"})

    def log_message(self, *_args):
        pass


def launch_research_web(argv=None):
    parser = argparse.ArgumentParser(description="Chain Survey local research workspace")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--catalog-file", type=Path,
                        default=Path(os.environ.get("CHAIN_SURVEY_CATALOG", Path.home() / ".chain-survey/catalog.sqlite3")))
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    service = ResearchService(series_research.builtin_catalog(ROOT), args.catalog_file)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), ResearchHandler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ResearchHandler)
    with server:
        server.research = service
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Chain Survey: {url}", flush=True)
        if not args.no_browser:
            opener = Timer(0.2, webbrowser.open, args=(url,))
            opener.daemon = True
            opener.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    launch_research_web()
