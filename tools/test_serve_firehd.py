import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from serve_firehd import make_handler


class FireServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / 'snapshot.json'
        self.source.write_text(json.dumps({'schemaVersion': 1, 'generatedAt': '2026-11-04T00:00:00Z',
            'credentials': 'must-not-export', 'providers': [{'id': 'codex', 'windows': [], 'secret': 'must-not-export'}]}))
        page = Path(self.directory.name) / 'index.html'
        page.write_text('<title>AI Usage</title>')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.source, page, {'127.0.0.1'}, {'test'}))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, host='test', **extra):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        self.addCleanup(conn.close)
        conn.request('GET', path, headers={'Host': host, **extra})
        response = conn.getresponse()
        return response.status, response.read()

    def test_only_documented_quota_fields_are_exported(self):
        status, body = self.request('/usage.json')
        self.assertEqual(status, 200)
        self.assertNotIn(b'must-not-export', body)
        self.assertNotIn(b'credentials', body)

    def test_paths_and_foreign_hosts_are_rejected(self):
        self.assertEqual(self.request('/../../README.md')[0], 404)
        self.assertEqual(self.request('/usage.json', host='attacker.test')[0], 403)
        self.assertEqual(self.request('/usage.json', **{'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_unavailable_or_invalid_snapshot_returns_failure(self):
        self.source.write_text('{}')
        self.assertEqual(self.request('/usage.json')[0], 503)
        self.source.unlink()
        self.assertEqual(self.request('/usage.json')[0], 503)


if __name__ == '__main__':
    unittest.main()
