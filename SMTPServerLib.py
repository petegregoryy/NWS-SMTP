import selectors
import queue
import traceback
import SMTPServerEncryption
from threading import Thread


class Module(Thread) :
    def __init__(self, sock, addr) :
        Thread.__init__(self)

        self._selector = selectors.DefaultSelector()
        self._sock = sock
        self._addr = addr

        self._incoming_buffer = queue.Queue()
        self._outgoing_buffer = queue.Queue()

        # Setup encryption
        self.encryption = SMTPServerEncryption.nws_encryption()
        self.encryption.toggle_enable()
        self.encryption.set_method("caesar")
        self.encryption.set_caesar_key("8")
        self.state = "START"

        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self._selector.register(self._sock, events, data=None)

        # Setup initial values and load files.
        self.data_file = open("serverData.txt", "a")
        self.mail_file = open("mails.txt", "a")
        self.helo_result = ""
        self.sender = ""
        self.rcpt = ""
        self.mail_message = ""
        self.helo_received = False

    def run(self) :
        try :
            # Send client connection confirmation
            self._create_message("220 OK")
            while True :
                # Check that socket still exists
                if self._sock != None :
                    events = self._selector.select(timeout=None)
                    for key, mask in events :
                        try :
                            if mask & selectors.EVENT_READ :
                                if self._sock != None :
                                    self._read()
                            if mask & selectors.EVENT_WRITE and not self._outgoing_buffer.empty() :
                                if self._sock != None :
                                    self._write()
                        except Exception :
                            print(
                                "main: error: exception for",
                                f"{self._addr}:\n{traceback.format_exc()}",
                            )
                            if self._sock != None :
                                self._sock.close()
                    if not self._selector.get_map() :
                        break
        except KeyboardInterrupt :
            print("caught keyboard interrupt, exiting")
        finally :
            self._selector.close()

    def _read(self) :
        try :
            data = self._sock.recv(4096)
        except BlockingIOError :
            print("blocked")
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
        except ConnectionResetError :
            print("Connection closed by Peer")
            pass
        else :
            if data :
                self._incoming_buffer.put(self.encryption.decrypt(data.decode()))
            else :
                raise RuntimeError("Peer closed.")
        self._process_response()

    def _write(self) :
        try :
            message = self._outgoing_buffer.get_nowait()
        except :
            message = None

        if message :
            print("sending", repr(message), "to", self._addr)
            try :
                sent = self._sock.send(message)
            except BlockingIOError :
                # Resource temporarily unavailable (errno EWOULDBLOCK)
                pass

    def _create_message(self, content) :
        encoded = self.encryption.encrypt(content)
        nwencoded = encoded.encode()
        self._outgoing_buffer.put(nwencoded)

    def _process_response(self) :
        message = self._incoming_buffer.get()
        header_length = 4
        # If the server is not in DATASTATE, process the message with a header length of 4.
        # If it is, process with a header length of 1
        if self.state != "DATASTATE" :
            if len(message) >= header_length :
                self._module_processor(message[0 :header_length], message[header_length :])
        else :
            self._module_processor(message[0 :1], message[1 :])

    def _module_processor(self, command, message) :
        # Set intials for valid inputs and whether the server is in data mode
        valid = False
        data_input = False

        # If server is in START state, if command received is not any listed, return 503
        if self.state == "START" :
            if command != "NOOP" and command != "HELO" and command != "HELP" and command != "QUIT" :
                print("Start bad sequence")
                self._create_message("503 Bad Sequence")
            else :
                valid = True

        # If server is in MAILPROCESS state, if command received is not any listed, return 503
        elif self.state == "MAILPROCESS" :
            if command != "NOOP" and command != "RSET" and command != "QUIT" and command != "MAIL" \
                    and command != "RCPT" and command != "DATA" :
                print("mailproc bad sequence")
                self._create_message("503 Bad Sequence")
            else :
                valid = True

        # If server is in DATASTATE state, stop processing commands and set server into data mode
        elif self.state == "DATASTATE":
            valid = False
            data_input = True

        # If server is in CLEANING mode, only accept QUIT as valid command
        if self.state == "CLEANING" :
            if command != "QUIT" :
                print("cleaning bad sequence")
                valid = False
                self._create_message("503 Bad Sequence")
            else :
                valid = True
        # Data Mode processing
        if data_input :
            # Check if end command is sent
            if command == "." :
                print("CLEAR")

                # Open the recipients mailbox, if it doesnt exist create it
                mailbox_file = open((self.rcpt + "-mailbox.txt"), "a")
                # Open the mailbox register
                mail_file = open("mailboxes.txt", "r")

                # Duplication checking for the mailbox register
                dupe = False
                for lines in mail_file.readlines() :
                    if lines == self.rcpt :
                        dupe = True
                        break
                    else :
                        dupe = False

                # Close the mailbox register, then reopen to append
                mail_file.close()
                mail_file = open("mailboxes.txt", "a")

                # Append the recipient address to the end of the mailbox register.
                if not dupe :
                    mail_file.writelines(self.rcpt + '\n')

                # Write the contents of the mail message to the recipients mailbox then add a newline
                mailbox_file.write("{" + self.mail_message + "}\n")
                self._create_message("250 OK")

                # Turn off data mode and mark that the data entry end command has been received and processed.
                data_input = False
                crlf_received = True

            else :
                # Combine command and message to get original line, set as the mail message and continue data input.
                line = command + message
                self.mail_message = line
                print(line)
                data_input = True
                crlf_received = False

        # Processing for valid commands
        if valid :
            # NOOP sends a 250 reply to confirm server still exists
            if command == "NOOP" :
                self._create_message("250 OK")
                print("Received a NOOP")

            # HELP sends a list of available commands
            elif command == "HELP" :
                self._create_message(f"250 Available commands:\n  NOOP \n HELP \n HELO \n MAIL \n RCPT \n RSET \n QUIT"
                                     f" \n VRFY (Non Functioning \n EXPN (Non Functioning")
                print("Received a HELP")

            # DATA sends confirmation for data entry then changes the server to DATASTATE
            elif command == "DATA" :
                self._create_message(f"354 Begin Data Entry")
                print("Received a DATA")
                if self.state == "MAILPROCESS" :
                    self.state = "DATASTATE"

            # HELO sets helo_received and result, checks that the serverData file exists and then writes the HELO
            # message against the address of the client.
            elif command == "HELO" :
                print("Received a HELO")
                self.helo_received = True
                self.helo_result = message
                f = open("serverData.txt", "a")
                f_read = open("serverData.txt", "r")
                dupe = False
                addr = self._addr
                if message != "" :
                    for line in f_read.readlines() :
                        if line == message + "|" + str(addr) :
                            dupe = True
                    if not dupe :
                        f.write(message + "|")
                        f.write(str(addr))
                        f.write("\n")
                        print("wrote to file ", message, addr)

                # Checks that the mailbox file exists, otherwise returns a 550
                try :
                    file = open(message + "-mailbox.txt")
                    lines_together = []
                    lines = file.readlines()
                    # Combines all mails in clients mailbox and sends them to the client.
                    for line in lines :
                        # replaces the | characters with \n for formatting in the client console. The mail messages are
                        # stored with | characters instead of \n at the end of each line to keep each message to one
                        # line in the mailbox.  This allows ease of sorting
                        split = line.split('|')
                        newline_line = '\n'.join(split)
                        lines_together.append(newline_line)
                    # Send HELO reply with mailbox contents
                    self._create_message(f"250 Hello: {message} \n Mailbox: " + '\n'.join(lines_together))
                except(FileNotFoundError) :
                    self._create_message(
                        "550 No " + message + "-mailbox.txt Mailbox Found - No mail received on this server")
                # Change to the MAILPROCESS state
                if self.state == "START" :
                    self.state = "MAILPROCESS"

            # Store the sender of the mail and reply with confirmation
            elif command == "MAIL" :
                self._create_message(f"250 Mail from: {message}")
                self.sender = message
                print("Received a MAIL FROM")

            #Store the recipient of the mail and reply with confirmation
            elif command == "RCPT" :
                self._create_message(f"250 Recipient: {message}")
                self.rcpt = message
                print("Received a RCPT TO")

            # VRFY interrogates the mailbox file to see if a client has a mailbox with the server.
            elif command == "VRFY" :
                f = open("mailboxes.txt","r")
                exists = False
                for lines in f.readlines():
                    if message == lines:
                        exists = True
                        break
                    else:
                        exists = False
                if exists:
                    self._create_message(f"250: {message} found.")
                else:
                    self._create_message(f"252: Address not found.")

                print("Received a VRFY")

            # RSET resets the server to default STATE
            elif command == "RSET" :
                self._create_message(f"250 Reset")
                if self.helo_received :
                    self.state = "MAILPROCESS"
                else :
                    self.state = "START"
                print("Received a RSET")

            # QUIT closes the connection to the server
            elif command == "QUIT" :
                self._create_message(f"221 Quit: {message}")
                print("Received a QUIT")
                self.state = "CLEANUP"
                self.close()

            # Any other commands return 500
            else :
                self._create_message("500 Unknown command")
                print("Received an unknown command")

    def close(self) :
        print("closing connection to", self._addr)
        try :
            self._selector.unregister(self._sock)
        except Exception as e :
            print(
                f"error: selector.unregister() exception for",
                f"{self._addr}: {repr(e)}",
            )
        try :
            self._sock.close()
        except OSError as e :
            print(
                f"error: socket.close() exception for",
                f"{self._addr}: {repr(e)}",
            )
        finally :
            # Delete reference to socket object for garbage collection
            self._sock = None
            return Thread
