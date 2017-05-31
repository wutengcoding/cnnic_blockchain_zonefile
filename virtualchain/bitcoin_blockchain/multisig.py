import pybitcoin
import bitcoin

import os

from .keys import *

def make_multisig_info(m, pks):
    """
    Make a multisig address and redeem script
    """

    pubs = []
    prikeys = []
    for pk in pks:
        priv = BitcoinPrivateKey(pk)
        priv_wif = priv.to_wif()
        pub = priv.public_key().to_hex()

        prikeys.append(priv_wif)
        pubs.append(pub)

    script = bitcoin.mk_multisig_script( pubs, m)
    addr = bitcoin.p2sh_scriptaddr(script, multisig_version_byte)

    return {
        'address': addr,
        'redeem_script': script,
        'private_keys': prikeys
    }