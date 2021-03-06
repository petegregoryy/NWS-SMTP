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
        self.state = "START"
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self._selector.register(self._sock, events, data=None)

        self.data_file = open("serverData.txt","a")
        self.mail_file = open("mails.txt", "a")
        self.helo_result = ""
        self.sender = ""
        self.rcpt = ""
        self.mail_message = ""

    def run(self):
        try:
            self._create_message("220 OK")
            while True:
                if self._sock != None:
                    events = self._selector.select(timeout=None)
                    for key, mask in events:
                        try:
                            if mask & selectors.EVENT_READ:
                                if self._sock != None:
                                    self._read()
                            if mask & selectors.EVENT_WRITE and not self._outgoing_buffer.empty():
                                if self._sock != None:
                                    self._write()
                        except Exception:
                            print(
                                "main: error: exception for",
                                f"{self._addr}:\n{traceback.format_exc()}",
                            )
                            if self._sock != None:
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
        if self.state != "DATASTATE":
            if len(message) >= header_length:
                self._module_processor(message[0:header_length], message[header_length:])
        else:
            self._module_processor(message[0:1], message[1:])

    def _module_processor(self, command, message):
        print(self.state)
        valid = False
        data_input = False
        crlf_received = False
        print(command)
        print(message)
        if self.state == "START":
            if command != "NOOP" and command != "HELO" and command != "HELP" and command != "QUIT":
                self._create_message("503 Bad Sequence")
            else:
                valid = True
        elif self.state == "MAILPROCESS":
            if command != "NOOP" and command != "RSET" and command != "HELP" and command != "QUIT" and command != "MAIL"  and command != "RCPT" and command != "DATA":
                self._create_message("503 Bad Sequence")
            else:
                valid = True

        elif self.state == "DATASTATE":
            valid = False
            data_input = True


        if self.state == "CLEANING":
            if command != "QUIT":
                valid = False
                self._create_message("503 Bad Sequence")
            else:
                valid = True

        if data_input:
            if command == ".":
                print("CLEARCLEAR")
                mail_file = open("mails.txt", "a")
                mail_file.write("[\n" +self.rcpt + "|" + self.mail_message + "\n")
                self._create_message("250 OK")
                self.state = "CLEANING"
                data_input = False
                crlf_received = True
            else:

                line = command+message
                self.mail_message = message
                print(line)
                data_input = True
                crlf_received = False

        if valid:
            if command == "NOOP":
                self._create_message("250 OK")
                print("Received a NOOP")
            elif command == "HELP":
                self._create_message(f"250 This is a help message: {message}")
                print("Received a HELP")
            elif command == "DATA":
                self._create_message(f"354 Data: {message}")
                print("Received a DATA")
                if self.state == "MAILPROCESS":
                    self.state = "DATASTATE"
            elif command == "HELO":
                self._create_message(f"250 Hello: {message}")
                print("Received a HELO")
                f = open("serverData.txt","a")
                f_read = open("serverData.txt","r")
                dupe = False
                addr = self._addr
                if message != "":
                    for line in f_read.readlines():
                        if line == message + "|" + str(addr):
                            dupe = True
                    if not dupe:
                        f.write(message + "|")
                        f.write(str(addr))
                        f.write("\n")
                        print("wrote to file ",message, addr)
                if self.state == "START":
                    self.state = "MAILPROCESS"
            elif command == "MAIL":
                self._create_message(f"250 Mail from: {message}")
                self.sender = message
                print("Received a MAIL FROM")
            elif command == "RCPT":
                self._create_message(f"250 Recipient: {message}")
                self.rcpt = message
                print("Received a RCPT TO")
            elif command == "VRFY":
                self._create_message(f"250 Verify: {message}")
                print("Received a VRFY")
            elif command == "EXPN":
                self._create_message(f"250 Expand: {message}")
                print("Received a EXPN")
            elif command == "RSET":
                self._create_message(f"250 Reset")
                self.state = "START"
                print("Received a RSET")
            elif command == "QUIT":
                self._create_message(f"221 Quit: {message}")
                print("Received a QUIT")
                self.state = "CLEANUP"
                self.close()
            else:
                self._create_message("500 Unknown command")
                print("Received an unknown command")



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
            return Thread
