import uuid
from abc import ABC, abstractmethod

from wacryptolib.encryption import _decrypt_via_rsa_oaep
from wacryptolib.key_generation import (
    generate_asymmetric_keypair,
    load_asymmetric_key_from_pem_bytestring,
)
from wacryptolib.signature import sign_message

#: Special value in containers, to invoke a device-local escrow
LOCAL_ESCROW_PLACEHOLDER = "_local_"


class KeyStorageBase(ABC):
    """
    Subclasses of this storage interface can be implemented to store/retrieve keys from
    miscellaneous locations (disk, database...), without permission checks.
    """

    # TODO use exceptions in case of key not found or unauthorized, instead of "None"!

    @abstractmethod
    def set_keys(
        self,
        *,
        keychain_uid: uuid.UUID,
        key_type: str,
        public_key: bytes,
        private_key: bytes,
    ):  # pragma: no cover
        """
        Store a pair of asymmetric keys into storage.

        Must raise an exception if a key pair already exists for these identifiers.

        :param keychain_uid: unique ID of the keychain
        :param key_type: one of SUPPORTED_ASYMMETRIC_KEY_TYPES
        :param public_key: public key in PEM format (potentially encrypted)
        :param private_key: private key in PEM format
        """
        raise NotImplementedError("KeyStorageBase.set_keypair()")

    @abstractmethod
    def get_public_key(
        self, *, keychain_uid: uuid.UUID, key_type: str
    ) -> bytes:  # pragma: no cover
        """
        Fetch a public key from persistent storage.

        :param keychain_uid: unique ID of the keychain
        :param key_type: one of SUPPORTED_ASYMMETRIC_KEY_TYPES

        :return: public key in PEM format, or None if unexisting.
        """
        raise NotImplementedError("KeyStorageBase.get_public_key()")

    @abstractmethod
    def get_private_key(
        self, *, keychain_uid: uuid.UUID, key_type: str
    ) -> bytes:  # pragma: no cover
        """
        Fetch a private key from persistent storage.

        :param keychain_uid: unique ID of the keychain
        :param key_type: one of SUPPORTED_ASYMMETRIC_KEY_TYPES

        :return: private key in PEM format (potentially encrypted), or None if unexisting.
        """
        raise NotImplementedError("KeyStorageBase.get_private_key()")


class EscrowApi:
    """
    This is the API meant to be exposed by escrow webservices, to allow end users to create safely encrypted containers.

    Subclasses must add their own permission checking, especially so that no decryption with private keys can occur
    outside the scope of a well defined legal procedure.
    """

    def __init__(self, key_storage: KeyStorageBase):
        self.key_storage = key_storage

    def _ensure_keypair_exists(self, keychain_uid: uuid.UUID, key_type: str):
        has_public_key = self.key_storage.get_public_key(
            keychain_uid=keychain_uid, key_type=key_type
        )
        if not has_public_key:
            keypair = generate_asymmetric_keypair(key_type=key_type, serialize=True)
            self.key_storage.set_keys(
                keychain_uid=keychain_uid,
                key_type=key_type,
                public_key=keypair["public_key"],
                private_key=keypair["private_key"],
            )

    def get_public_key(self, *, keychain_uid: uuid.UUID, key_type: str) -> bytes:
        """
        Return a public key in PEM format bytestring, that caller shall use to encrypt its own symmetric keys,
        or to check a signature.
        """
        self._ensure_keypair_exists(keychain_uid=keychain_uid, key_type=key_type)
        return self.key_storage.get_public_key(
            keychain_uid=keychain_uid, key_type=key_type
        )

    def get_message_signature(
        self,
        *,
        keychain_uid: uuid.UUID,
        message: bytes,
        key_type: str,
        signature_algo: str,
    ) -> dict:
        """
        Return a signature structure corresponding to the provided key and signature types.
        """
        self._ensure_keypair_exists(keychain_uid=keychain_uid, key_type=key_type)

        private_key_pem = self.key_storage.get_private_key(
            keychain_uid=keychain_uid, key_type=key_type
        )

        private_key = load_asymmetric_key_from_pem_bytestring(
            key_pem=private_key_pem, key_type=key_type
        )

        signature = sign_message(
            message=message, signature_algo=signature_algo, key=private_key
        )
        return signature

    def decrypt_with_private_key(
        self,
        *,
        keychain_uid: uuid.UUID,
        key_type: str,
        encryption_algo: str,
        cipherdict: dict,
    ) -> bytes:
        """
        Return the message (probably a symmetric key) decrypted with the corresponding key,
        as bytestring.
        """
        assert key_type.upper() == "RSA"  # Only supported key for now
        assert (
            encryption_algo.upper() == "RSA_OAEP"
        )  # Only supported asymmetric cipher for now
        self._ensure_keypair_exists(keychain_uid=keychain_uid, key_type=key_type)

        private_key_pem = self.key_storage.get_private_key(
            keychain_uid=keychain_uid, key_type=key_type
        )

        private_key = load_asymmetric_key_from_pem_bytestring(
            key_pem=private_key_pem, key_type=key_type
        )

        secret = _decrypt_via_rsa_oaep(cipherdict=cipherdict, key=private_key)
        return secret


class DummyKeyStorage(KeyStorageBase):
    """
    Dummy key storage for use in tests, where keys are kepts only instance-locally.
    """

    def __init__(self):
        self._cached_keypairs = {}

    def _get_keypair(self, *, keychain_uid, key_type):
        return self._cached_keypairs.get((keychain_uid, key_type))

    def set_keys(self, *, keychain_uid, key_type, public_key, private_key):
        if self._get_keypair(keychain_uid=keychain_uid, key_type=key_type):
            raise RuntimeError(
                "Can't save already existing key %s/%s" % (keychain_uid, key_type)
            )
        self._cached_keypairs[(keychain_uid, key_type)] = dict(
            public_key=public_key, private_key=private_key
        )

    def get_public_key(self, *, keychain_uid, key_type):
        keypair = self._get_keypair(keychain_uid=keychain_uid, key_type=key_type)
        return keypair["public_key"] if keypair else None

    def get_private_key(self, *, keychain_uid, key_type):
        keypair = self._get_keypair(keychain_uid=keychain_uid, key_type=key_type)
        return keypair["private_key"] if keypair else None
