import xmlrpclib

import pybitcoin
import virtualchain
from config import get_logger
from state_machine.operations import *
from pybitcoin import broadcast_transaction
from virtualchain.bitcoin_blockchain.keys import *
from state_machine import nameset as state_engine
log = get_logger("nameops")

default_proxy = None
def set_default_proxy(proxy):
    global default_proxy
    default_proxy = proxy

default_db_inst = None

def get_default_db_inst():
    global default_db_inst
    if default_db_inst is None:
        default_db_inst = state_engine.get_readonly_db_state(disposition=state_engine.DISPOSITION_RO)
    return default_db_inst

def do_name_register(name, payment_privkey_info, utxo_client, tx_broadcaster, consensus_hash=None, proxy=None, safety_check=None):
    db = get_default_db_inst()
    records = db.get_name(name)
    if records is not None:
        log.error("The name %s has been registered" % name)
        return {"error": "Name %s has already exist" % name}

    try:
        payment_address = virtualchain.BitcoinPrivateKey(payment_privkey_info).public_key().address()
    except Exception, e:
        log.error("Invalid private key info")
        return {'error': 'Name register can only use a single private key with a P2PKH script'}
    try:
        signed_tx = name_register_tx(name, payment_privkey_info, consensus_hash, payment_address, utxo_client)
    except ValueError, ve:
        log.exception(ve)
        log.error("Failed to create name register tx")
        return {'error': 'Failed to create name register tx'}

    resp = {}

    try:
        resp = broadcast_transaction(signed_tx, tx_broadcaster)
    except Exception, e:
        log.exception(e)
        log.error("Failed to sign and broadcast tx")
        return {'error': 'Failed to sign and broadcast namespace preorder transaction'}

    return resp


def do_name_update(name, data_hash, payment_privkey_info, tx_broadcaster):
    owner_address = get_privkey_info_address(payment_privkey_info)
    # Check ownership
    db = get_default_db_inst()
    records = db.get_name(name)
    if records is None:
        log.error("No such record for name %s" % name)
        return {'error': "The name record doesn't exist"}
    if records['recipient_address'] != owner_address:
        log.error("Owner address of %s is not matched, expected %s, but %s" % (name, records['recipient_address'], owner_address))
        return {'error': 'The owner address is not correct'}

    log.info(
        "Owner address of %s is matched, expected %s, got %s" % (name, records['recipient_address'], owner_address))

    try:
        signed_tx = name_update_tx(name, payment_privkey_info , data_hash, tx_broadcaster)
    except ValueError, ve:
        log.exception(ve)
        log.error("Failed to create name update tx")
        return {'error': 'Failed to create name update tx'}

    resp = {}

    try:
        resp = broadcast_transaction(signed_tx, tx_broadcaster)
    except Exception, e:
        log.exception(e)
        log.error("Failed to sign and broadcast tx")
        return {'error': 'Failed to sign and broadcast namespace preorder transaction'}

    return resp

def do_name_revoke(name, payment_privkey_info, tx_broadcaster):
    owner_address = get_privkey_info_address(payment_privkey_info)
    # Check ownership
    db = get_default_db_inst()
    records = db.get_name(name)

    if records is None:
        log.error("No such record for name %s" % name)
        return {'error': "The name record doesn't exist"}
    if records['recipient_address'] != owner_address:
        log.error("Owner address of %s is not matched, expected %s, but %s" % (
        name, records['recipient_address'], owner_address))
        return {'error': 'The owner address is not correct'}

    log.info("Owner address of %s is matched, expected %s, got %s" % (
        name, records['recipient_address'], owner_address))
    try:
        signed_tx = name_revoke_tx(name, payment_privkey_info, tx_broadcaster)
    except ValueError, ve:
        log.exception(ve)
        log.error("Failed to create name update tx")
        return {'error': 'Failed to create name update tx'}

    resp = {}

    try:
        resp = broadcast_transaction(signed_tx, tx_broadcaster)
    except Exception, e:
        log.exception(e)
        log.error("Failed to sign and broadcast tx")
        return {'error': 'Failed to sign and broadcast namespace preorder transaction'}

    return resp

def do_name_transfer(name, payment_privkey_info, owner_privkey_info, tx_broadcaster):

    previous_owner_address = get_privkey_info_address(payment_privkey_info)
    new_owner_address = get_privkey_info_address(owner_privkey_info)

    # Check name ownership
    db = get_default_db_inst()
    records = db.get_name(name)

    if records is None:
        log.error("No such record for name %s" % name)
        return {'error': "The name record doesn't exist"}
    if records['recipient_address'] != previous_owner_address:
        log.error("Owner address of %s is not matched, expected %s, but %s" % (
            name, records['recipient_address'], previous_owner_address))
        return {'error': 'The owner address is not correct'}

    log.info("Owner address of %s is matched, expected %s, got %s" % (
        name, records['recipient_address'], previous_owner_address))

    try:
        signed_tx = name_transfer_tx(name, payment_privkey_info, new_owner_address,tx_broadcaster)
    except ValueError, ve:
        log.exception(ve)
        log.error("Failed to create name update tx")
        return {'error': 'Failed to create name update tx'}

    resp = {}

    try:
        resp = broadcast_transaction(signed_tx, tx_broadcaster)
    except Exception, e:
        log.exception(e)
        log.error("Failed to sign and broadcast tx")
        return {'error': 'Failed to sign and broadcast namespace preorder transaction'}

    return resp



def name_register_tx(name, private_key, consensus_hash, payment_address, utxo_client):
    tx = make_tx_name_register(name, private_key, consensus_hash, payment_address, utxo_client)
    return tx

def name_update_tx(name, private_key, data_hash, tx_broadcaster):
    tx = make_tx_name_update(name, private_key, data_hash, tx_broadcaster)
    return tx


def name_revoke_tx(name, private_key, tx_broadcaster):
    tx = make_tx_name_revoke(name, private_key, tx_broadcaster)
    return tx


def name_transfer_tx(name, payment_privkey_info, owner_address, tx_broadcaster):
    tx = make_tx_name_transfer(name, payment_privkey_info, owner_address, tx_broadcaster)
    return tx



def get_name_record(name):
    s = xmlrpclib.ServerProxy('http://%s:%s' % ('0.0.0.0', RPC_SERVER_PORT))
    name_records = s.rpc_get_name(name)
    return name_records




