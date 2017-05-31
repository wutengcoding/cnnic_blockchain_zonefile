import os
import tempfile

import errno

import virtualchain
import pybitcoin


from config import get_logger, get_bitcoin_regtest_opts
import name_service
from blockchain.session import get_bitcoind_connection
log = get_logger("testlib")

snapshots_dir = None

state_engine = None





class TestAPIProxy(object):
    def __init__(self):
        global utxo_opts

        client_path = os.environ.get("ZONEFILEMANAGE_CLIENT_CONFIG", None)
        assert client_path is not None



class Wallet(object):
    def __init__(self, pk_wif, ignored):

        pk = virtualchain.BitcoinPrivateKey(pk_wif)

        self._pk = pk

        if pk_wif.startswith("c"):
            #already a privkey
            self.privkey = pk_wif
        else:
            self.privkey = pk.to_wif()

        self.pubkey_hex = pk.public_key().to_hex()
        self.addr = pk.public_key().address()

        log.info("Wallet %s(%s)" % (self.privkey, self.addr))

class MultisigWallet(object):
    def __init__(self, m, *pks):

        self.privkey = virtualchain.make_multisig_info( m, pks )
        self.m = m
        self.n = len(pks)

        self.addr = self.privkey['address']

        log.info("Multisig wallet %s " % (self.addr))



def set_default_payment_wallet( w ):
    global default_payment_wallet
    default_payment_wallet = w

# set up for test environment
def set_utxo_opts( opts ):
    global utxo_opts
    utxo_opts = opts

def set_bitcoind( b ):
    global bitcoind
    bitcoind = b

def set_state_engine( s ):
    global state_eigine
    state_eigine = s



def next_block( **kw ):
    """
    Advance the mock blockchain by one block
    """
    global snapshots_dir, state_engine

    if snapshots_dir is None:
        snapshots_dir = tempfile.mkdtemp(prefix='zonefilemanage-test-databases-')


    # Flush all transactions and reset state engine
    kw['next_block_upcall']()
    kw['sync_virtualchain_upcall']()



def zonefilemanage_export_db(path, block_height, **kwargs):

    global state_engine

    try:
        state_engine.export_db(path + (".%s" % block_height))
    except IOError, ie:
        if ie.errno == errno.ENOENT:
            log.error("No such file or directory: %s" + path)
            pass
        else:
            raise

def zonefilemanage_name_register(name, privatekey, status = '0', consensus_hash = None, safety_checks = False):
    """
    Register a name
    """
    log.info("Register a name %s" % name)
    test_proxy = make_proxy()
    name_service.set_default_proxy(test_proxy)

    resp = name_service.do_name_register(status + name,  privatekey,
                                                   test_proxy, test_proxy, consensus_hash=consensus_hash,
                                                   proxy=test_proxy)
    return resp

def zonefilemanage_name_update(name, data_hash, privatekey, consensus_hash=None, safety_checks = False):
    """
    Update a name
    """
    log.info("Update a name %s, data_hash is %s" % (name, data_hash ))
    test_proxy = make_proxy()
    name_service.set_default_proxy(test_proxy)

    resp = name_service.do_name_update(name, data_hash, privatekey, test_proxy)

    return resp


def zonefilemanage_name_revoke(name, privatekey):
    """
    Revoke a name
    """
    log.info("Revoke a name %s" % name)
    test_proxy = make_proxy()
    name_service.set_default_proxy(test_proxy)

    resp = name_service.do_name_revoke(name, privatekey, test_proxy)
    return resp


def zonefilemanage_name_transfer(name, previous_privkey, change_privkey):
    """
    Transfer a name
    """
    log.info("Transfer a name %s" % name)
    test_proxy = make_proxy()
    name_service.set_default_proxy(test_proxy)

    resp = name_service.do_name_transfer(name, previous_privkey, change_privkey, test_proxy)
    return resp


def get_utxo_client():
    opts = get_bitcoin_regtest_opts()
    utxo_provider = pybitcoin.BitcoindClient(opts.get("bitcoind_user", None), opts.get("bitcoind_passwd"), \
                                             use_https=opts.get("bitcoind_use_https", None),server=opts.get("bitcoind_server", None),port=opts.get("bitcoind_port"), version_byte=virtualchain.version_byte)
    return utxo_provider


def make_proxy():
    proxy = get_utxo_client()
    return proxy