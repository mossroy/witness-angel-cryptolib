import uuid

import pytest
from Crypto.Random import get_random_bytes

from wacryptolib.encryption import _encrypt_via_rsa_oaep
from wacryptolib.escrow import EscrowApi, DummyKeyStorage, KeyStorageBase
from wacryptolib.key_generation import load_asymmetric_key_from_pem_bytestring
from wacryptolib.signature import verify_message_signature


def test_escrow_api_workflow():

    key_storage = DummyKeyStorage()
    escrow_api = EscrowApi(key_storage=key_storage)

    keychain_uid = uuid.uuid4()
    secret = get_random_bytes(101)

    public_key_pem = escrow_api.get_public_key(
        keychain_uid=keychain_uid, key_type="RSA"
    )
    public_key = load_asymmetric_key_from_pem_bytestring(
        key_pem=public_key_pem, key_type="RSA"
    )

    signature = escrow_api.get_message_signature(
        keychain_uid=keychain_uid, message=secret, key_type="RSA", signature_algo="PSS"
    )
    verify_message_signature(
        message=secret, signature=signature, key=public_key, signature_algo="PSS"
    )

    signature["digest"] += b"xyz"
    with pytest.raises(ValueError, match="Incorrect signature"):
        verify_message_signature(
            message=secret, signature=signature, key=public_key, signature_algo="PSS"
        )

    cipherdict = _encrypt_via_rsa_oaep(plaintext=secret, key=public_key)

    decrypted = escrow_api.decrypt_with_private_key(
        keychain_uid=keychain_uid,
        key_type="RSA",
        encryption_algo="RSA_OAEP",
        cipherdict=cipherdict,
    )

    cipherdict["digest_list"].append(b"aaabbbccc")
    with pytest.raises(ValueError, match="Ciphertext with incorrect length"):
        escrow_api.decrypt_with_private_key(
            keychain_uid=keychain_uid,
            key_type="RSA",
            encryption_algo="RSA_OAEP",
            cipherdict=cipherdict,
        )

    assert decrypted == secret


def test_key_storage_base():

    key_storage = DummyKeyStorage()

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        KeyStorageBase()

    # Sanity checks on dummy key storage used

    _tmp_keychain_uid = uuid.uuid4()

    key_storage.set_keys(
        keychain_uid="aaa", key_type="bbb", public_key=b"public", private_key=b"private"
    )
    with pytest.raises(RuntimeError):
        key_storage.set_keys(
            keychain_uid="aaa",
            key_type="bbb",
            public_key=b"public",
            private_key=b"private",
        )
    with pytest.raises(RuntimeError):
        key_storage.set_keys(
            keychain_uid="aaa",
            key_type="bbb",
            public_key=b"public2",
            private_key=b"private2",
        )

    assert key_storage.get_public_key(keychain_uid="aaa", key_type="bbb") == b"public"
    assert key_storage.get_private_key(keychain_uid="aaa", key_type="bbb") == b"private"

    assert key_storage.get_public_key(keychain_uid="aaa", key_type="bbbX") == None
    assert key_storage.get_private_key(keychain_uid="aaa", key_type="bbbX") == None

    assert key_storage.get_public_key(keychain_uid="aaaX", key_type="bbb") == None
    assert key_storage.get_private_key(keychain_uid="aaaX", key_type="bbb") == None