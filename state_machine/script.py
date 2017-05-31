import traceback
from config import *
from state_machine.b40 import *
from virtualchain import *
import pybitcoin
import bitcoin
import ecdsa
from utilitybelt import is_hex, is_valid_int
log = get_logger("script")


def is_name_valid(fqn):
    """
    Is a fully-qualified name acceptable?
    Return True if so
    Return False if not

    TODO: DRY up; use client
    """

    if fqn.count(".") != 1:
        return False

    name, namespace_id = fqn.split(".")

    if len(name) == 0 or len(namespace_id) == 0:
        return False

    if not is_b40(name) or "+" in name or "." in name:
        return False

    return True


def get_public_key_hex_from_tx(inputs, address):
    """
    Given a list of inputs and the address of one of the inputs,
    find the public key.

    This only works for p2pkh scripts.
    """

    ret = None

    for inp in inputs:

        input_scriptsig = inp.get('scriptSig', None)
        if input_scriptsig is None:
            continue

        input_asm = input_scriptsig.get("asm")

        if len(input_asm.split(" ")) >= 2:

            # public key is the second hex string.  verify it matches the address
            pubkey_hex = input_asm.split(" ")[1]
            pubkey = None

            try:
                pubkey = virtualchain.BitcoinPublicKey(str(pubkey_hex))
            except Exception, e:
                traceback.print_exc()
                log.warning("Invalid public key '%s'" % pubkey_hex)
                continue

            if address != pubkey.address():
                continue

            ret = pubkey_hex
            break

    return ret


def tx_get_unspents(address, utxo_client, min_confirmations=TX_MIN_CONFIRMATIONS):
    """
    Given an address get unspent outputs (UTXOs)
    Return array of UTXOs on success
    Raise UTXOException on error
    """
    assert utxo_client is not None, "Utxo client is null"
    min_confirmations = 1
    if utxo_client is None:
        utxo_opts = get_bitcoin_regtest_opts()
        utxo_client =  pybitcoin.BitcoindClient(utxo_opts['bitcoind_user'], utxo_opts['bitcoind_passwd'],
                                        use_https=utxo_opts['bitcoind_use_https'], server=utxo_opts['bitcoind_server'],
                                        port=utxo_opts['bitcoind_port'])

    data = pybitcoin.get_unspents(address, utxo_client)

    try:
        assert type(data) == list, "No UTXO list returned"
        for d in data:
            assert isinstance(d, dict), 'Invalid UTXO information returned'
            assert 'value' in d, 'Missing value in UTXOs from {}'.format(address)

    except AssertionError, ae:
        log.exception(ae)
        raise

    # filter minimum confirmations
    return [d for d in data if d.get('confirmations', 0) >= min_confirmations]




def tx_sign_all_unsigned_inputs(private_key_info, unsigned_tx_hex):
    """
    Sign all unsigned inputs in the given transaction.

    @private_key_info: either a hex private key, or a dict with 'private_keys' and 'redeem_script'
    defined as keys.
    @unsigned_hex_tx: hex transaction with unsigned inputs

    Returns: signed hex transaction
    """
    inputs, outputs, locktime, version = pybitcoin.deserialize_transaction(unsigned_tx_hex)
    tx_hex = unsigned_tx_hex
    for i, input in enumerate(inputs):
        if input['script_sig']:
            continue

        # tx with index i signed with privkey
        tx_hex = tx_sign_input(str(unsigned_tx_hex), i, private_key_info)
        unsigned_tx_hex = tx_hex

    return tx_hex


def tx_sign_input(blockstack_tx, idx, private_key_info, hashcode=bitcoin.SIGHASH_ALL):
    """
    Sign a particular input in the given transaction.
    @private_key_info can either be a private key, or it can be a dict with 'redeem_script' and 'private_keys' defined
    """
    if is_singlesig(private_key_info):
        # single private key
        return tx_sign_singlesig(blockstack_tx, idx, private_key_info, hashcode=hashcode)

    elif is_multisig(private_key_info):

        redeem_script = private_key_info['redeem_script']
        private_keys = private_key_info['private_keys']

        redeem_script = str(redeem_script)

        # multisig
        return tx_sign_multisig(blockstack_tx, idx, redeem_script, private_keys, hashcode=bitcoin.SIGHASH_ALL)

    else:
        raise ValueError("Invalid private key info")

def tx_sign_singlesig(tx, idx, private_key_info, hashcode=bitcoin.SIGHASH_ALL):
    """
    Sign a p2pkh input
    Return the signed transaction

    TODO: move to virtualchain

    NOTE: implemented here instead of bitcoin, since bitcoin.sign() can cause a stack overflow
    while converting the private key to a public key.
    """
    pk = virtualchain.BitcoinPrivateKey(str(private_key_info))
    pubk = pk.public_key()

    pub = pubk.to_hex()
    addr = pubk.address()

    script = virtualchain.make_payment_script(addr)
    sig = tx_make_input_signature(tx, idx, script, private_key_info, hashcode)

    txobj = bitcoin.deserialize(str(tx))
    txobj['ins'][idx]['script'] = bitcoin.serialize_script([sig, pub])
    return bitcoin.serialize(txobj)

def add_magic_bytes(script):
    return '{}{}'.format(MAGIC_BYTES, script)


def parse_op(script):
    parts = script.split(' ')
    for part in parts:
        if part in NAME_OPCODES:
            script = NAME_OPCODES[part]
        else:
            script += part
    return script

def tx_make_input_signature(tx, idx, script, privkey_str, hashcode):
    """
    Sign a single input of a transaction, given the serialized tx,
    the input index, the output's scriptPubkey, and the hashcode.

    TODO: move to virtualchain

    Return the hex signature.
    """

    pk = virtualchain.BitcoinPrivateKey(str(privkey_str))
    pubk = pk.public_key()

    priv = pk.to_hex()
    pub = pubk.to_hex()
    addr = pubk.address()

    signing_tx = bitcoin.signature_form(tx, idx, script, hashcode)
    txhash = bitcoin.bin_txhash(signing_tx, hashcode)

    # sign using uncompressed private key
    pk_uncompressed_hex, pubk_uncompressed_hex = get_uncompressed_private_and_public_keys(priv)

    sk = ecdsa.SigningKey.from_string(pk_uncompressed_hex.decode('hex'), curve=ecdsa.SECP256k1)
    sig_bin = sk.sign_digest(txhash, sigencode=ecdsa.util.sigencode_der)

    # enforce low-s
    sig_r, sig_s = ecdsa.util.sigdecode_der(sig_bin, ecdsa.SECP256k1.order)
    if sig_s * 2 >= ecdsa.SECP256k1.order:
        log.debug("High-S to low-S")
        sig_s = ecdsa.SECP256k1.order - sig_s

    sig_bin = ecdsa.util.sigencode_der(sig_r, sig_s, ecdsa.SECP256k1.order)

    # sanity check
    vk = ecdsa.VerifyingKey.from_string(pubk_uncompressed_hex[2:].decode('hex'), curve=ecdsa.SECP256k1)
    assert vk.verify_digest(sig_bin, txhash,
                            sigdecode=ecdsa.util.sigdecode_der), "Failed to verify signature ({}, {})".format(sig_r,
                                                                                                              sig_s)

    sig = sig_bin.encode('hex') + bitcoin.encode(hashcode, 16, 2)
    return sig

def tx_sign_multisig(tx, idx, redeem_script, private_keys, hashcode=bitcoin.SIGHASH_ALL):
    """
    Sign a p2sh multisig input.
    Return the signed transaction

    TODO: move to virtualchain
    """
    # sign in the right order
    privs = {virtualchain.BitcoinPrivateKey(str(pk)).public_key().to_hex(): str(pk) for pk in private_keys}
    m, public_keys = virtualchain.parse_multisig_redeemscript(str(redeem_script))

    used_keys, sigs = [], []
    for public_key in public_keys:
        if public_key not in privs:
            continue

        if len(used_keys) == m:
            break

        assert public_key not in used_keys, 'Tried to reuse key {}'.format(public_key)

        pk_str = privs[public_key]
        used_keys.append(public_key)

        pk_hex = virtualchain.BitcoinPrivateKey(str(pk_str)).to_hex()

        sig = tx_make_input_signature(tx, idx, redeem_script, pk_str, hashcode)
        # sig = bitcoin.multisign(tx, idx, str(redeem_script), pk_hex, hashcode=hashcode)
        sigs.append(sig)

    assert len(used_keys) == m, 'Missing private keys'
    return bitcoin.apply_multisignatures(tx, idx, str(redeem_script), sigs)

def zonefilemanage_script_to_hex(script):
    """ Parse the readable version of a script, return the hex version.
    """
    hex_script = ''
    parts = script.split(' ')
    for part in parts:
        if part in NAME_OPCODES:
            try:
                hex_script += '{:02x}'.format(ord(NAME_OPCODES[part]))
            except:
                raise Exception('Invalid opcode: {}'.format(part))
        elif part.startswith('0x'):
            # literal hex string
            hex_script += part[2:]
        elif is_valid_int(part):
            hex_part = '{:02x}'.format(int(part))
            if len(hex_part) % 2 != 0:
                hex_part = '0' + hex_part
            hex_script += hex_part
        elif is_hex(part) and len(part) % 2 == 0:
            hex_script += part
        else:
            raise ValueError(
                'Invalid script (at {}), contains invalid characters: {}'.format(part, script))

    if len(hex_script) % 2 != 0:
        raise ValueError('Invalid script: must have an even number of chars (got {}).'.format(hex_script))

    return hex_script
