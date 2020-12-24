import sys
import selectors
import queue
import json
import io
import struct
import traceback
import SMTPClientEncryption
from threading import Thread

class Module (Thread):
    def __init__(self, sock, addr):
        Thread.__init__(self)

        self._selector = selectors.DefaultSelector()
        self._sock = sock
        self._addr = addr
        self._incoming_buffer = queue.Queue()
        self._outgoing_buffer = queue.Queue()

        self.encryption = SMTPClientEncryption.nws_encryption()
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self._selector.register(self._sock, events, data=None)

        self.stage = 0

    def run(self):
            try:
                while True:
                    events = self._selector.select(timeout=1)
                    for key, mask in events:
                        message = key.data
                        try:
                            if mask & selectors.EVENT_READ:
                                self._read()
                            if mask & selectors.EVENT_WRITE and not self._outgoing_buffer.empty():
                                self._write()
                        except Exception:
                            print(
                                "main: error: exception for",
                                f"{self._addr}:\n{traceback.format_exc()}",
                            )
                            self._sock.close()
                    # Check for a socket being monitored to continue.
                    if not self._selector.get_map():
                        break
            finally:
                self._selector.close()

    def _read(self):
        try:
            data = self._sock.recv(4096)
            print("DATA READ")
        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
        else:
            if data:
                self._incoming_buffer.put(self.encryption.decrypt(data.decode()))
            else:
                raise RuntimeError("Peer closed.")

        self._process_response()
        self.accepted_connection()

    def _write(self):
        try:
            message = self._outgoing_buffer.get_nowait()
        except:
            message = None

        if message:
            print("sending", repr(message), "to", self._addr)
            try:
                sent = self._sock.send(message)
            except BlockingIOError:
                # Resource temporarily unavailable (errno EWOULDBLOCK)
                pass

    def create_message(self, content):
        encoded = self.encryption.encrypt(content)
        nwencoded = encoded.encode()
        self._outgoing_buffer.put(nwencoded)

    def _process_response(self):
        message = self._incoming_buffer.get()
        header_length = 3
        if len(message) >= header_length:
            print(message[0:header_length ], message[header_length :])
        if message[0:header_length] == "220" and self.stage == 0:
            self.stage = 1
        elif message[0:header_length] == "250" and self.stage == 1:
            self.stage = 2
        elif message[0:header_length] == "250" and self.stage == 2:
            self.stage = 3
        elif message[0:header_length] == "250" and self.stage == 3:
            self.stage = 4
        elif message[0:header_length] == "354" and self.stage == 4:
            self.stage = 5
        elif message[0:header_length] == "221" and self.stage == 5:
            self.stage = 6
        print("Processing thing")

    def close(self):
        print("closing connection to", self._addr)
        try:
            self._selector.unregister(self._sock)
        except Exception as e:
            print(
                f"error: selector.unregister() exception for",
                f"{self._addr}: {repr(e)}",
            )
        try:
            self._sock.close()
        except OSError as e:
            print(
                f"error: socket.close() exception for",
                f"{self._addr}: {repr(e)}",
            )
        finally:
            # Delete reference to socket object for garbage collection
            self._sock = None

    def setup_info(self,address):
        self._email = address
    def accepted_connection(self):
        print(self.stage)
        if self.stage == 1:
            print("received 220")
            self.create_message("HELO email@server.com")
        if self.stage == 2:
            self.create_message("MAIL email2@otherserver.co.uk")
        if self.stage == 3:
            self.create_message("RCPT email@server.com")
        if self.stage == 4:
            self.create_message("DATA This is an email")
        if self.stage == 5:
            self.create_message("QUIT")
            print("QUIT")