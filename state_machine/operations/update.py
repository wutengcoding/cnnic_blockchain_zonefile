import xmlrpclib

from state_machine.nameset import *
from state_machine.script import *
from state_machine.b40 import *
from pybitcoin import make_op_return_tx
from state_machine.nameset.state_checker import state_transition
from config import *

FIELDS = NAMEREC_FIELDS[:] + [
    'value_hash',
    'consensus_hash'
]


def make_regular_name(name):
    assert len(name) < 18, "the length of name is too long"
    adding_part = '&'.join([''] * (18-len(name)))
    return '{}{}'.format(name, adding_part)

def build(name, value_hash):
    """
    Takes in the name that was preordered, including the namespace ID (but not the id: scheme)
    Returns a hex string representing up to the maximum-length name's bytes.

    Record format:

    0    2  3                20            39
    |----|--|----------------|-------------|
    magic op   name             value_hash

    """
    name = make_regular_name(name)
    name_value = name + value_hash
    readable_script = "NAME_UPDATE %s" % (name_value)
    script = parse_op(readable_script)
    packaged_script = add_magic_bytes(script)

    return packaged_script

def get_update_recipient_from_outputs( outputs ):

    ret = None

    for output in outputs:

        output_script = output['scriptPubkey']
        output_asm = output_script.get('asm')
        output_hex = output_script.get('hex')

        output_address = output_script.get('address')

        if output_asm[0:9] != 'OP_RETURN' and output_hex is not None:
            ret = output_hex
            break
    if ret is None:
        raise Exception("No registration address found")

    return ret

def make_transaction(name, payment_privkey_info, value_hash, zonefilemanage_client):

    data = build(name, value_hash)
    tx = make_op_return_tx(data, virtualchain.BitcoinPrivateKey(payment_privkey_info), zonefilemanage_client, fee=100000,
                       format='bin')
    return tx



def tx_extract( payload, senders, inputs, outputs, block_id, vtxindex, txid ):

    try:
        recipient = get_update_recipient_from_outputs(outputs)
        recipient_address = virtualchain.script_hex_address(recipient)

        assert recipient is not None
        assert recipient_address is not None
    except Exception, e:
        log.exception(e)
        raise Exception("Failed to extract")

    sender_pubkey_hex = None

    parsed_payload = parse(payload)
    assert parsed_payload is not None

    ret = {
        "vtxindex": vtxindex,
        "txid": txid,
        "recipient": recipient,
        "recipient_address": recipient_address,
        "op": NAME_UPDATE
    }

    ret.update(parsed_payload)

    if sender_pubkey_hex is not None:
        ret['sender_pubkey'] = sender_pubkey_hex

    return ret


def parse(bin_payload):
    """
    Parse a payload to get back the name and update hash.
    NOTE: bin_payload excludes the leading three bytes.
    """

    if len(bin_payload) != LENGTHS['name_update'] + LENGTHS['value_hash']:
        log.error("Invalid update length %s" % len(bin_payload))
        return None

    name_update = bin_payload[:LENGTHS['name_update']]
    value_hash = bin_payload[LENGTHS['value_hash']:]

    # Filter the unnecessary &
    name_update = name_update[:name_update.find('&')]

    return {
        'opcode': 'NAME_UPDATE',
        'name': name_update,
        'value_hash': value_hash
    }


def update_sanity_test(name, consensus_hash, data_hash):
    """
    Verify the validity of an update's data

    Return True if valid
    Raise exception if not
    """

    if name is not None and (not is_b40(name) or "+" in name or name.count(".") > 1):
        raise Exception("Name '%s' has non-base-38 characters" % name)

    if data_hash is not None and not is_hex(data_hash):
        raise Exception("Invalid hex string '%s': not hex" % (data_hash))

    if len(data_hash) != 2 * LENGTHS['value_hash']:
        raise Exception("Invalid hex string '%s': bad length" % (data_hash))

    return True

@state_transition( "name", "name_records", "check_name_collision" )
def check_update(state_engine, nameop, block_id, checked_ops):
    """
    Verify the validity of a update nameop.

    """
    name = nameop['name']
    records =  state_engine.get_name(name)

    if records is None:
        log.error("No such record for name %s" % name)
        return False
    if records['recipient_address'] != nameop['recipient_address']:
        log.error("Owner address of %s is not matched, expected %s, but %s" % (
        name, records['recipient_address'], name['recipient_address']))
        return False
    log.info("Update %s check is succeed" % name)
    return True



