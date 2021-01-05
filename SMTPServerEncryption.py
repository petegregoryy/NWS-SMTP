class nws_encryption:
    def __init__(self):
        self._enabled = False
        self._method = None
        self._alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!£$%^&*()-+={}[]:;@'<,>.?/\\# "
        self._caesarkey = None
        self._vignerekey = None

    def toggle_enable(self):
        self._enabled = not self._enabled
        return self._enabled

    def set_caesar_key(self, key):
        try:
            self._caesarkey = int(key)
        except TypeError:
            self._caesarkey = 0
            return None
        return self._caesarkey

    def set_vigenere_key(self, key):
        try:
            self._vigenerekey = str(key)
        except TypeError:
            self._vignerekey = "Derby"
            return None
        return self._caesarkey

    def set_method(self, method):
        if method.lower() == "caesar":
            self._method = "caesar"
        elif method.lower() == "vigenere":
            self._method = "vigenere"
        else:
            self._method = None

    def encrypt(self, message) -> str:
        if self._enabled:
            if self._method == "caesar":
                return self._caesar_cipher_encrypt(message)
            elif self._method == "vigenere":
                return self._vigenere_square_encrypt(message)
        return message

    def decrypt(self, message) -> str:
        if self._enabled:
            if self._method == "caesar":
                return self._caesar_cipher_decrypt(message)
            elif self._method == "vigenere":
                return self._vigenere_square_decrypt(message)
        return message

    def _caesar_cipher_encrypt(self, message) -> str:
        try:
            message = str(message)
        except TypeError:
            return ""

        shift = self._caesarkey
        #cipher = message[0:3]
        #message = message[3:]
        cipher = ''
        for char in message:
            if char == ' ':
                cipher = cipher + char
            elif char.isupper():
                cipher = cipher + chr((ord(char) + shift))
            else:
                cipher = cipher + chr((ord(char) + shift))
        return cipher
        # perform caesar cipher here

    def _vigenere_square_encrypt(self, message) -> str:
        try:
            message = str(message)
        except TypeError:
            return ""
        print("vigenere square encryption not supported")
        return message
        # perform vigenere square here

    def _caesar_cipher_decrypt(self, message) -> str:
        try:
            message = str(message)
        except TypeError:
            return ""

        shift = self._caesarkey
        cipher = ''
        for char in message:
            if char == ' ':
                cipher = cipher + char
            elif char.isupper():
                cipher = cipher + chr((ord(char) - shift))
            else:
                cipher = cipher + chr((ord(char) - shift))
        return cipher

    def _vigenere_square_decrypt(self, message) -> str:
        try:
            message = str(message)
        except TypeError:
            return ""
        print("vigenere square encryption not supported")
        return message

        # perform vigenere square here





