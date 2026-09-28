"""OBSClient against a fake obs-websocket v5 server with authentication."""
import base64
import hashlib
import json
import socket
import struct
import threading
import unittest

from pspkit.obs import OBSClient, OBSError

PASSWORD, SALT, CHALLENGE = "gizli", "tuz", "meydan"


def expected_auth(password):
    secret = base64.b64encode(hashlib.sha256((password + SALT).encode()).digest())
    return base64.b64encode(hashlib.sha256(secret + CHALLENGE.encode()).digest()).decode()


class FakeOBS(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(4)
        self.port = self.srv.getsockname()[1]
        self.scene = "Kamera"
        self.recording = False
        self.requests = []

    def run(self):
        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self.serve, args=(conn,), daemon=True).start()

    @staticmethod
    def recv_frame(conn, buf):
        def need(n):
            while len(buf[0]) < n:
                chunk = conn.recv(4096)
                if not chunk:
                    raise ConnectionError
                buf[0] += chunk
            out, buf[0] = buf[0][:n], buf[0][n:]
            return out
        b0, b1 = need(2)
        n = b1 & 0x7F
        if n == 126:
            (n,) = struct.unpack(">H", need(2))
        mask = need(4)
        data = need(n)
        return bytes(b ^ mask[i % 4] for i, b in enumerate(data)).decode()

    @staticmethod
    def send_frame(conn, obj):
        data = json.dumps(obj).encode()
        head = bytes([0x81, len(data)]) if len(data) < 126 else bytes([0x81, 126]) + struct.pack(">H", len(data))
        conn.sendall(head + data)

    def serve(self, conn):
        buf = [b""]
        head = b""
        while b"\r\n\r\n" not in head:
            head += conn.recv(1024)
        buf[0] = head.split(b"\r\n\r\n", 1)[1]
        conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
        self.send_frame(conn, {"op": 0, "d": {"rpcVersion": 1,
                                             "authentication": {"challenge": CHALLENGE, "salt": SALT}}})
        try:
            identify = json.loads(self.recv_frame(conn, buf))
            if identify["d"].get("authentication") != expected_auth(PASSWORD):
                conn.close()
                return
            self.send_frame(conn, {"op": 2, "d": {"negotiatedRpcVersion": 1}})
            while True:
                req = json.loads(self.recv_frame(conn, buf))["d"]
                self.requests.append(req["requestType"])
                data, ok = {}, True
                if req["requestType"] == "SetCurrentProgramScene":
                    self.scene = req["requestData"]["sceneName"]
                elif req["requestType"] == "GetCurrentProgramScene":
                    data = {"currentProgramSceneName": self.scene}
                elif req["requestType"] == "ToggleRecord":
                    self.recording = not self.recording
                    data = {"outputActive": self.recording}
                else:
                    ok = False
                self.send_frame(conn, {"op": 7, "d": {"requestType": req["requestType"],
                                                     "requestId": req["requestId"],
                                                     "requestStatus": {"result": ok, "code": 100 if ok else 204,
                                                                       "comment": None if ok else "yok"},
                                                     "responseData": data}})
        except (ConnectionError, OSError, ValueError):
            conn.close()

    def stop(self):
        self.srv.close()


class OBSTest(unittest.TestCase):
    def setUp(self):
        self.obs = FakeOBS()
        self.obs.start()

    def tearDown(self):
        self.obs.stop()

    def test_scene_and_record(self):
        client = OBSClient("127.0.0.1", self.obs.port, PASSWORD)
        client.request("SetCurrentProgramScene", {"sceneName": "Ekran"})
        self.assertEqual(client.request("GetCurrentProgramScene")["currentProgramSceneName"], "Ekran")
        self.assertTrue(client.request("ToggleRecord")["outputActive"])
        self.assertEqual(self.obs.requests, ["SetCurrentProgramScene", "GetCurrentProgramScene", "ToggleRecord"])
        client.close()

    def test_failed_request_raises(self):
        client = OBSClient("127.0.0.1", self.obs.port, PASSWORD)
        with self.assertRaises(OBSError):
            client.request("Uydurma")
        client.close()

    def test_wrong_password(self):
        client = OBSClient("127.0.0.1", self.obs.port, "yanlis")
        with self.assertRaises(OBSError):
            client.request("GetCurrentProgramScene")

    def test_no_server_backs_off(self):
        client = OBSClient("127.0.0.1", 1, "")
        with self.assertRaises(OBSError):
            client.request("GetCurrentProgramScene")
        with self.assertRaises(OBSError) as ctx:  # second call must not wait on the network again
            client.request("GetCurrentProgramScene")
        self.assertIn("birazdan", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
