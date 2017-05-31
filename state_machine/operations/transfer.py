from config import *
from pybitcoin import make_op_return_tx
import virtualchain
from state_machine.nameset import *
from state_machine.nameset.state_checker import state_transition
from state_machine.script import *
from pybitcoin.transactions.scripts import *
from pybitcoin.transactions.network import *
import binascii

FIELDS = NAMEREC_FIELDS

def build(name):
    """
    Takes in the name that was preordered, including the namespace ID (but not the id: scheme)
    Returns a hex string representing up to the maximum-length name's bytes.

    Record format:

    0    2  3                             39
    |----|--|-----------------------------|
    magic op   name (37 bytes)

    """

    readable_script = "NAME_TRANSFER %s" % (name)
    script = parse_op(readable_script)
    packaged_script = add_magic_bytes(script)

    return packaged_script


def get_registration_recipient_from_outputs( outputs ):

    ret = []

    for output in outputs:

        output_script = output['scriptPubkey']
        output_asm = output_script.get('asm')
        output_hex = output_script.get('hex')

        output_address = output_script.get('address')

        if output_asm[0:9] != 'OP_RETURN' and output_hex is not None:
            ret.append(output_hex)
    if ret is None:
        raise Exception("No registration address found")

    assert len(ret) == 2, "the address length is not correct"
    return ret

def tx_extract( payload, senders, inputs, outputs, block_id, vtxindex, txid):
    """
    sender:  the script_pubkey (as a hex string) of the principal that sent the name preorder transaction
    address:  the address from the sender script
    recipient:  the script_pubkey (as a hex string) of the principal that is meant to receive the name
    recipient_address:  the address from the recipient script
    """
    try:
        recipient_list = get_registration_recipient_from_outputs( outputs )

        sender = recipient_list[0]
        sender_address = virtualchain.script_hex_address(sender)
        recipient = recipient_list[1]
        recipient_address = virtualchain.script_hex_address(recipient)
        old_address = virtualchain.script_hex_address(recipient_list[0])


        assert old_address is not None
        assert recipient_address is not None

    except Exception, e:
        log.exception(e)
        raise Exception("Failed to extract")

    parsed_payload = parse(payload)
    assert parsed_payload is not None

    ret = {
        "value_hash": None,
        "sender": sender,
        "sender_address": sender_address,
        "recipient": recipient_list[0],
        "recipient_address": recipient_address,
        "revoked": False,
        "last_renewed": block_id,
        "vtxindex": vtxindex,
        "txid": txid,
        "first_registered": block_id,  # NOTE: will get deleted if this is a renew
        "last_renewed": block_id,  # NOTE: will get deleted if this is a renew
        "op": NAME_TRANSFER
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
        'opcode': 'NAME_TRANSFER',
        'name': fqn
    }

def calculate_change_amount(inputs, send_amount, fee):
    # calculate the total amount  coming into the transaction from the inputs
    total_amount_in = sum([input['value'] for input in inputs])
    # change = whatever is left over from the amount sent & the transaction fee
    change_amount = total_amount_in - send_amount - fee
    # check to ensure the change amount is a non-negative value and return it
    if change_amount < 0:
        raise ValueError('Not enough inputs for transaction (total: %s, to spend: %s, fee: %s).' % (total_amount_in, send_amount, fee))
    return change_amount

def make_op_return_outputs(data, inputs, last_address, change_address, fee=100,
                           send_amount=0, format='bin'):
    """ Builds the outputs for an OP_RETURN transaction.
    """
    return [
        # main output
        { "script_hex": make_op_return_script(data, format=format), "value": send_amount },
        # last owner output
        {
            "script_hex": make_pay_to_address_script(last_address),
            "value": calculate_change_amount(inputs, send_amount, fee)/2
        },
        # change output
        { "script_hex": make_pay_to_address_script(change_address),
          "value": calculate_change_amount(inputs, send_amount, fee)/2
        }
    ]
def make_transaction(name, payment_privkey_info, owner_address, zonefilemanage_client):

    data = build(name)
    private_key_obj, from_address, inputs = analyze_private_key(virtualchain.BitcoinPrivateKey(payment_privkey_info),
                                                                zonefilemanage_client)
    outputs = make_op_return_outputs(data, inputs, from_address, owner_address,
                                     fee=100000)

    # serialize the transaction
    unsigned_tx = serialize_transaction(inputs, outputs)

    # generate a scriptSig for each input
    for i in xrange(0, len(inputs)):
        signed_tx = sign_transaction(unsigned_tx, i, private_key_obj.to_hex())
        unsigned_tx = signed_tx

    # return the signed tx
    return signed_tx


@state_transition( "name", "name_records", "check_name_collision" )
def check_transfer(state_engine, nameop, block_id, checked_ops):
    """
    Verify the validity of a registration nameop.

    """
    name = nameop['name']
    records = state_engine.get_name(name)

    if records is None:
        log.error("No such record for name %s" % name)
        return False
    if records['recipient_address'] != nameop['sender_address']:
        log.error("Owner address of %s is not matched, expected %s, but %s" % (
            name, records['recipient_address'], name['sender_address']))
        return False
    log.info("Transfer %s check is succeed" % name)
    return True


