import selectors
import queue
import traceback
import SMTPServerEncryption
from threading import Thread

class Module(Thread):
    def __init__(self, sock, addr):
        Thread.__init__(self)

        self._selector = selectors.DefaultSelector()
        self._sock = sock
        self._addr = addr

        self._incoming_buffer = queue.Queue()
        self._outgoing_buffer = queue.Queue()

        self.encryption = SMTPServerEncryption.nws_encryption()

        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self._selector.register(self._sock, events, data=None)
        self._create_message("220 OK")
    def run(self):
        try:
            while True:
                events = self._selector.select(timeout=None)
                for key, mask in events:
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
                if not self._selector.get_map():
                    break
        except KeyboardInterrupt:
            print("caught keyboard interrupt, exiting")
        finally:
            self._selector.close()

    def _read(self):
        try:
            data = self._sock.recv(4096)
        except BlockingIOError:
            print("blocked")
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
        except ConnectionResetError:
            print("Connection closed by Peer")
            pass
        else:
            if data:
                self._incoming_buffer.put(self.encryption.decrypt(data.decode()))
            else:
                raise RuntimeError("Peer closed.")

        self._process_response()

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

    def _create_message(self, content):
        encoded = self.encryption.encrypt(content)
        nwencoded = encoded.encode()
        self._outgoing_buffer.put(nwencoded)

    def _process_response(self):
        message = self._incoming_buffer.get()
        header_length = 4
        if len(message) >= header_length:
            self._module_processor(message[0:header_length], message[header_length:])

    def _module_processor(self, command, message):
        if command == "NOOP":
            self._create_message("250 OK")
            print("Received a NOOP")
        elif command == "HELP":
            self._create_message(f"250 This is a help message: {message}")
            print("Received a HELP")
        elif command == "DATA":
            self._create_message(f"354 Data: {message}")
            print("Received a DATA")
        elif command == "HELO":
            self._create_message(f"250 Hello: {message}")
            print("Received a HELO")
        elif command == "MAIL":
            self._create_message(f"250 Mail from: {message}")
            print("Received a MAIL FROM")
        elif command == "RCPT":
            self._create_message(f"250 Recipient: {message}")
            print("Received a RCPT TO")
        elif command == "VRFY":
            self._create_message(f"250 Verify: {message}")
            print("Received a VRFY")
        elif command == "EXPN":
            self._create_message(f"250 Expand: {message}")
            print("Received a EXPN")
        elif command == "RSET":
            self._create_message(f"250 Reset: {message}")
            print("Received a RSET")
        elif command == "QUIT":
            self._create_message(f"221 Quit: {message}")
            print("Received a QUIT")

        else:
            self._create_message("500 Unknown command")
            print ("Received an unknown command")

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

