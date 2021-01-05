import sys
import selectors
import queue
import json
import struct
from datetime import datetime
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

        # Set up encryption
        self.encryption = SMTPClientEncryption.nws_encryption()
        self.encryption.toggle_enable()
        self.encryption.set_method("caesar")
        self.encryption.set_caesar_key("8")

        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self._selector.register(self._sock, events, data=None)

        self.stage = "START"
        self.step = 0
        self.client_data = open("clientData.txt", "r")
        self.mode = 0
        self.last_command = ""
        # Set recipient and sender
        self.rcpt = ""
        self.send = ""
        # Set bools for use in DATA and HELO commands
        self.body_finish = False
        self.helo_sent = False

    def run(self):

            try:
                while True:
                    # Check if socket has been removed
                    if self._sock != None:
                        events = self._selector.select(timeout=1)
                        for key, mask in events:
                            message = key.data
                            try:
                                if mask & selectors.EVENT_READ:
                                    # Check if socket has been removed
                                    if self._sock != None:
                                        self._read()
                                if mask & selectors.EVENT_WRITE and not self._outgoing_buffer.empty():
                                    # Check if socket has been removed
                                    if self._sock != None:
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
        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
        except ConnectionResetError:
            print("Connection closed.")
            self.close()
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
            print(message[0:header_length], message[header_length :])
        # Check for 220 response when connected
        if message[0:header_length] == "220" and self.stage == "START":
            self.step = 1
            print("received 220")
        #  Check for 250 response when HELO is sent
        elif message[0:header_length] == "250" and self.step == 1:
            self.stage = "MAILPROCESS"
            self.step = 2
        # Check for 250 response when MAIL is sent
        elif message[0:header_length] == "250" and self.step == 2 and self.stage == "MAILPROCESS":
            self.step = 3
        # Check for 250 response when RCPT is sent
        elif message[0:header_length] == "250" and self.step == 3:
            self.step = 4
        # Check for 354 response when DATA is sent
        elif message[0:header_length] == "354" and self.step == 4:
            self.step = 5
            self.stage = "DATASTATE"
        # Check for 250 response when . is sent to end DATA entry
        elif message[0:header_length] == "250" and self.step == 5 and self.stage == "DATASTATE":
            self.step = 6
            # Check for 221 response when QUIT is sent
        elif message[0:header_length] == "221" and self.step == 6:
            self.step = 7

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
            return Thread

    def setup_info(self,address):
        self._email = address

    def accepted_connection(self):

        with open("clientData.txt", "r") as current:
            lines = current.readlines()
            if not lines:
                print("FILE IS EMPTY")

        if not self.helo_sent :
            # Create and send HELO message
            m = "HELO" + lines[0]
            self.create_message(m)
            self.last_command = "HELO"
            self.helo_sent = True

        # Get and process user mode request
        if self.mode == 0:
            self.last_command = ""
            print("What would you like to do? \n [1] Compose email and receive mailbox \n [q] Disconnect")

            entry = input("> ")
            if entry == "1":
                # Set to compose mode and start composing email.
                self.mode = 1
                self.compose()
            if entry == "q":
                # Set to quit mode, then run compose to quit.
                self.mode = 2
                self.step = 6
                self.compose()
        elif self.mode == 1:
            self.compose()


    def compose(self):

        lines = [""]
        with open("clientData.txt", "r") as current:
            lines = current.readlines()
            if not lines:
                print("FILE IS EMPTY")

        # Check for mail step and stage, then ask for sender address
        if self.step == 2 and self.stage == "MAILPROCESS":
            print("Enter the sender address. Leave blank to use your inputted address (" + lines[0] + ")")
            self.send = input("> ")
            # Use pre-entered sender address (Entered during setup)
            if self.send == "":
                self.send = lines[0]
                # Create and send mail message using user input
            self.create_message("MAIL" + self.send)
            self.last_command = "MAIL"
        if self.step == 3:
            print("Enter the recipient address.")
            self.rcpt = input("> ")
            self.create_message("RCPT" + self.rcpt)
            self.last_command = "RCPT"

        if self.step == 4:
            self.create_message("DATA Start Data")
            self.last_command = "DATA"


        if self.step == 5:
            fullmessage = []
            date = datetime.now()
            # Ask user for subject
            print("Email Subject")
            subject = input("> ")
            # Start creating full email message.  The entire mail is created locally in one string, then sent in one
            # command. This is due to errors when sending more than 2 commands to the server, all would send, however
            # only 2 would be processed, the rest would not be processed.
            fullmessage.append(
                "Time: " + date.strftime('%d/%m/%Y %H:%M:%S') + "|From: " + self.send + "|To: " + self.rcpt+ "|Subject: " +subject + "||")

            print("\nEnter the body of the email.  To finish, put a single '.' on a new line.")

            while True:
                enter = input("> ")
                if enter == '.':
                    break
                else:
                    # Add the body to the end of local email composition, including a | character for every new line.
                    # The | character is replaced with a \n in the server processing.
                    fullmessage.append(enter + "|")

            #Combine entire message into one string and send along with a final message.
            self.create_message(''.join(fullmessage))
            self.create_message(".")

        if self.step == 6:
            self.create_message("QUIT")
            print("QUIT")



