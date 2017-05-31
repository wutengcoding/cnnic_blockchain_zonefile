from config import *
FIELDS = NAMEREC_FIELDS
from state_machine.nameset.state_checker import state_transition
from state_machine.script import *
from state_machine.nameset import *
from pybitcoin import make_op_return_tx

def build(name):
    """
    Takes in the name that was preordered, including the namespace ID (but not the id: scheme)
    Returns a hex string representing up to the maximum-length name's bytes.

    Record format:

    0    2  3                             39
    |----|--|-----------------------------|
    magic op   name (37 bytes)

    """

    readable_script = "NAME_REVOKE %s" % (name)
    script = parse_op(readable_script)
    packaged_script = add_magic_bytes(script)

    return packaged_script


def get_revoke_recipient_from_outputs( outputs ):

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

def tx_extract( payload, senders, inputs, outputs, block_id, vtxindex, txid):
    """
    sender:  the script_pubkey (as a hex string) of the principal that sent the name preorder transaction
    address:  the address from the sender script
    recipient:  the script_pubkey (as a hex string) of the principal that is meant to receive the name
    recipient_address:  the address from the recipient script
    """
    try:
        recipient = get_revoke_recipient_from_outputs( outputs )
        recipient_address = virtualchain.script_hex_address(recipient)

        assert recipient is not None
        assert recipient_address is not None

    except Exception, e:
        log.exception(e)
        raise Exception("Failed to extract")

    parsed_payload = parse(payload)
    assert parsed_payload is not None

    ret = {
        "value_hash": None,
        "recipient": recipient,
        "recipient_address": recipient_address,
        "revoked": True,
        "last_renewed": block_id,
        "vtxindex": vtxindex,
        "txid": txid,
        "first_registered": block_id,  # NOTE: will get deleted if this is a renew
        "last_renewed": block_id,  # NOTE: will get deleted if this is a renew
        "op": NAME_REGISTER
    }

    ret.update(parsed_payload)

    return ret


def parse(bin_payload):
    """
    Interpret a block's nulldata back into a name.  The first three bytes (2 magic + 1 opcode)
    will not be present in bin_payload.

    The name will be directly represented by the bytes given.
    """

    fqn = bin_payload

    # if not is_name_valid(fqn):
    #     return None

    return {
        'opcode': 'NAME_REVOKE',
        'name': fqn,
        'revoked': True
    }


def make_transaction(name, payment_privkey_info, zonefilemanage_client):

    data = build(name)
    tx = make_op_return_tx(data, virtualchain.BitcoinPrivateKey(payment_privkey_info), zonefilemanage_client, fee=100000,
                       format='bin')
    return tx

@state_transition( "name", "name_records", "check_name_collision" )
def check_revoke(state_engine, nameop, block_id, checked_ops):
    """
    Verify the validity of a registration nameop.

    """
    name = nameop['name']
    records = state_engine.get_name(name)

    if records is None:
        log.error("No such record for name %s" % name)
        return False
    if records['recipient_address'] != nameop['recipient_address']:
        log.error("Owner address of %s is not matched, expected %s, but %s" % (
            name, records['recipient_address'], name['recipient_address']))
        return False
    log.info("Revoke %s check is succeed" % name)
    return True

