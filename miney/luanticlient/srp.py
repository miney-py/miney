from hashlib import sha256
import random
import logging
import os


logger = logging.getLogger(__name__)


class SRPClient:
    """
    SRP (Secure Remote Password) client implementation that matches Luanti's approach.
    """

    def __init__(self, username: str, password: str, hash_alg=sha256):
        """
        Initialize the SRP client with playername and password.
        
        Parameters
        ----------
        username
            The playername for authentication
        password
            The password for authentication
        hash_alg
            The hash algorithm to use, defaults to SHA-256
        """
        self.username = username
        self.password = password
        self.hash_alg = hash_alg
        self.hash_size = 32  # SHA-256 hash size in bytes

        # SRP parameters (2048-bit group from Luanti's implementation)
        self.N_hex = ("AC6BDB41324A9A9BF166DE5E1389582FAF72B6651987EE07"
                      "FC3192943DB56050A37329CBB4A099ED8193E0757767A13DD5"
                      "2312AB4B03310DCD7F48A9DA04FD50E8083969EDB767B0CF609"
                      "5179A163AB3661A05FBD5FAAAE82918A9962F0B93B855F97993"
                      "EC975EEAA80D740ADBF4FF747359D041D5C33EA71D281E446B14"
                      "773BCA97B43A23FB801676BD207A436C6481F1D2B9078717461A"
                      "5B9D32E688F87748544523B524B0D57D5EA77A2775D2ECFA032C"
                      "FBDBF52FB3786160279004E57AE6AF874E7303CE53299CCC041C7"
                      "BC308D82A5698F3A8D0C38271AE35F8E9DBFBB694B5C803D89F7A"
                      "E435DE236D525F54759B65E372FCD68EF20FA7111F9E4AFF73")
        self.g_hex = "02"

        self.N = int(self.N_hex, 16)
        self.g = int(self.g_hex, 16)

        # Generate a random private value 'a'
        self.a = self._random_bigint()

        # Compute public value 'A' = g^a % N
        self.A = pow(self.g, self.a, self.N)

        # Convert A to bytes for transmission (padded to full N-length)
        self.bytes_A = self.A.to_bytes((self.N.bit_length() + 7) // 8, byteorder='big')

        # Will be populated during authentication
        self.salt = None
        self.B = None
        self.u = None
        self.S = None
        self.K = None
        self.M = None
        self.H_AMK = None
        self.authenticated = False

    def _hash(self, data: bytes) -> bytes:
        """
        Create a hash of the provided data.
        
        Parameters
        ----------
        data
            The data to hash
            
        Returns
        -------
        bytes
            The resulting hash digest
        """
        hasher = self.hash_alg()
        hasher.update(data)
        return hasher.digest()

    def _random_bigint(self) -> int:
        """
        Generate a random big integer for SRP calculations.
        
        Returns
        -------
        int
            A random integer between 2 and N-1
        """
        return random.randint(2, self.N - 1)

    def _calculate_x(self, salt: bytes, username: str, password: str) -> int:
        """
        Calculate the x value for SRP authentication.
        
        Parameters
        ----------
        salt
            The salt value from the server
        username
            The playername for authentication
        password
            The password for authentication
            
        Returns
        -------
        int
            The calculated x value
        """
        # x = H(salt || H(playername:password))
        inner_hash = self.hash_alg((username.lower() + ":" + password).encode("utf-8")).digest()
        x_hash = self.hash_alg(salt + inner_hash).digest()
        return int.from_bytes(x_hash, byteorder='big')

    def _calculate_u(self, A: int, B: int) -> int:
        """
        Calculate the u value for SRP authentication.
        
        Parameters
        ----------
        A
            The client's public value
        B
            The server's public value
            
        Returns
        -------
        int
            The calculated u value
        """
        A_bytes = A.to_bytes((A.bit_length() + 7) // 8, byteorder='big')
        B_bytes = B.to_bytes((B.bit_length() + 7) // 8, byteorder='big')
        u_hash = self.hash_alg(A_bytes + B_bytes).digest()
        return int.from_bytes(u_hash, byteorder='big')

    def _calculate_k(self) -> int:
        """
        Calculate the k value for SRP authentication.
        
        Returns
        -------
        int
            The calculated k value
        """
        n_bytes_len = (self.N.bit_length() + 7) // 8
        N_bytes = self.N.to_bytes(n_bytes_len, byteorder='big')
        g_full = self.g.to_bytes(n_bytes_len, byteorder='big')
        k_hash = self.hash_alg(N_bytes + g_full).digest()
        return int.from_bytes(k_hash, byteorder='big')

    def _calculate_M(self, username: str, salt: bytes, A: int, B: int, K: bytes) -> bytes:
        """
        Calculate the M value (client proof) for SRP authentication.
        
        Parameters
        ----------
        username
            The playername for authentication
        salt
            The salt value from the server
        A
            The client's public value
        B
            The server's public value
        K
            The session key
            
        Returns
        -------
        bytes
            The calculated M value (client proof)
        """
        n_bytes_len = (self.N.bit_length() + 7) // 8
        N_bytes = self.N.to_bytes(n_bytes_len, byteorder='big')
        g_min_bytes = self.g.to_bytes((self.g.bit_length() + 7) // 8, byteorder='big')
        h_N = self._hash(N_bytes)
        h_g = self._hash(g_min_bytes)
        h_xor = bytes(a ^ b for a, b in zip(h_N, h_g))
        h_I = self._hash(username.lower().encode('utf-8'))
        A_bytes = A.to_bytes((A.bit_length() + 7) // 8, byteorder='big')
        B_bytes = B.to_bytes((B.bit_length() + 7) // 8, byteorder='big')

        return self.hash_alg(h_xor + h_I + salt + A_bytes + B_bytes + K).digest()

    def _calculate_H_AMK(self, A: int, M: bytes, K: bytes) -> bytes:
        """
        Calculate the H_AMK value for SRP authentication verification.
        
        Parameters
        ----------
        A
            The client's public value
        M
            The client proof
        K
            The session key
            
        Returns
        -------
        bytes
            The calculated H_AMK value
        """
        A_bytes = A.to_bytes((A.bit_length() + 7) // 8, byteorder='big')
        return self.hash_alg(A_bytes + M + K).digest()

    def start_authentication(self) -> tuple[str, bytes]:
        """
        Start the SRP authentication process.
        
        Returns
        -------
        tuple[str, bytes]
            A tuple containing the playername and the client's public value A
        """
        return self.username, self.bytes_A

    def process_challenge(self, salt: bytes, bytes_B: bytes) -> bytes:
        """
        Process the server's challenge and generate the client proof.
        
        Parameters
        ----------
        salt
            The salt value from the server
        bytes_B
            The server's public value B
            
        Returns
        -------
        bytes
            The client proof M
            
        Raises
        ------
        ValueError
            If the server's public value B is invalid
            If the shared random value u is invalid
        """
        self.salt = salt
        self.B = int.from_bytes(bytes_B, byteorder='big')
        if (self.B % self.N) == 0:
            raise ValueError("Invalid server public value B")

        n_bytes_len = (self.N.bit_length() + 7) // 8
        self.u = self._calculate_u(self.A, self.B)
        if self.u == 0:
            raise ValueError("Invalid shared random value u")

        x = self._calculate_x(self.salt, self.username.lower(), self.password)
        v = pow(self.g, x, self.N)
        k = self._calculate_k()
        kv = (k * v) % self.N
        base = (self.B - kv) % self.N
        exp = self.a + self.u * x
        self.S = pow(base, exp, self.N)

        S_bytes = self.S.to_bytes((self.S.bit_length() + 7) // 8, byteorder='big')
        self.K = self._hash(S_bytes)
        self.M = self._calculate_M(self.username.lower(), self.salt, self.A, self.B, self.K)
        self.H_AMK = self._calculate_H_AMK(self.A, self.M, self.K)
        return self.M

    def verify_session(self, H_AMK: bytes) -> bool:
        """
        Verify the server's response to complete authentication.
        
        Parameters
        ----------
        H_AMK
            The server's verification value
            
        Returns
        -------
        bool
            True if verification succeeds, False otherwise
        """
        if self.H_AMK == H_AMK:
            self.authenticated = True
            return True
        return False

    def get_session_key(self) -> bytes:
        """
        Get the established session key.
        
        Returns
        -------
        bytes
            The session key, or None if authentication hasn't completed
        """
        return self.K
        
    def generate_first_srp_data(self) -> tuple[bytes, bytes, bool]:
        """
        Generate the data needed for FIRST_SRP registration.
        
        Returns
        -------
        tuple[bytes, bytes, bool]
            A tuple containing (salt, verifier, is_empty_password)
        """
        # Generate Salt (16 bytes)
        salt = os.urandom(16)
        
        # Calculate the verifier according to SRP-6a
        username_lower = self.username.lower()
        
        # Calculate x = H(s | H(I | ":" | P))
        inner_hash = self.hash_alg((username_lower + ":" + self.password).encode("utf-8")).digest()
        x_hash = self.hash_alg(salt + inner_hash).digest()
        x = int.from_bytes(x_hash, byteorder='big')
        
        # Calculate v = g^x % N
        v = pow(self.g, x, self.N)
        
        # Convert v to bytes
        v_bytes = v.to_bytes((v.bit_length() + 7) // 8, byteorder='big')
        
        # Empty password flag (True if password is empty)
        is_empty = not self.password
        
        return salt, v_bytes, is_empty
