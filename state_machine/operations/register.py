from pybitcoin import make_op_return_tx
import random
import time
import virtualchain
import threading
from config import *
from state_machine.nameset import *
from state_machine.nameset.state_checker import state_create
from state_machine.script import *
from bin.zonefilemanage_client import *
FIELDS = NAMEREC_FIELDS


def build(name):
    """
    Takes in the name that was preordered, including the namespace ID (but not the id: scheme)
    Returns a hex string representing up to the maximum-length name's bytes.

    Record format:

    0    2  3     4                         39
    |----|--|-----|--------------------------|
    magic op status name (37 bytes)

    """

    readable_script = "NAME_REGISTER %s" % (name)
    script = parse_op(readable_script)
    packaged_script = add_magic_bytes(script)

    return packaged_script


def get_registration_recipient_from_outputs( outputs ):

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
        recipient = get_registration_recipient_from_outputs( outputs )
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
        "revoked": False,
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
        'opcode': 'NAME_REGISTER',
        'name': fqn
    }


def make_transaction(name, payment_privkey_info, consensus_hash, payment_addr, zonefilemanage_client):

    data = build(name)
    tx = make_op_return_tx(data, virtualchain.BitcoinPrivateKey(payment_privkey_info), zonefilemanage_client, fee=100000,
                       format='bin')
    return tx

@state_create( "name", "name_records", "check_name_collision" )
def check_register(state_engine, nameop, block_id, checked_ops):
    """
    Verify the validity of a registration nameop.

    """
    name = nameop['name']
    status = name[0]
    name = name[1:]

    nameop['name'] = name

    if status == '0':
        poll = True

        # num = random.randint(1, 10)
        # if num <= 1:
        #     poll = True
        #
        # if is_main_worker():
        #     poll = True
        # t = threading.Timer(5.0, vote_for_name, [name, "REGISTER", nameop['block_number'], poll])
        # t.start()

        vote_for_name(name, "REGISTER", nameop['block_number'], poll)
        return False

    elif status == '1':
        log.info("The check method goes here for name: %s and status: %s" % (name, status))

        if voting_strategy == 0:
            server = get_global_server()
            vote_res = server.collect_vote("%s_REGISTER" % name)
            log.info("Get name: %s action status is %s" % (name, vote_res))
            if not vote_res:
                return False
            else:
                server.clear_old_ops(name, "REGISTER")

        elif voting_strategy == 1:
            # Trust unconditionly
            pass
        else:
            # PBFT
            pass

    if state_engine.is_name_registered(name):
        return False
    else:
        log.info("Register %s check is succeed" % name)
        return True

