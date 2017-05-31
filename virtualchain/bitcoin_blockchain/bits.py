import bitcoin
from opcodes import *
from config import get_logger
from keys import *

log = get_logger("bits")


def tx_script_to_asm(script_hex):
    """
    Decode a script into assembler
    """
    if len(script_hex) == 0:
        return ""

    try:
        script_array = bitcoin.deserialize_script(script_hex)
    except:
        log.error("Failed to convert '%s' to assembler" % script_hex)
        raise

    script_tokens = []
    for token in script_array:
        if token is None:
            token = 0

        token_name = None

        if type(token) in [int, long]:
            token_name = OPCODE_NAMES.get(token, None)
            if token_name is None:
                token_name = str(token)

        else:
            token_name = token

        script_tokens.append(token_name)

    return " ".join(script_tokens)

def tx_output_parse_scriptPubKey( scriptpubkey ):
    """
    Given the hex representation of a scriptPubKey,
    turn it into a nice, easy-to-read dict like what
    bitcoind would give us.
    """
    script_tokens = bitcoin.deserialize_script( scriptpubkey )
    script_type = None
    reqSigs = None
    addresses = []
    if scriptpubkey.startswith("76a914") and scriptpubkey.endswith("88ac") and len(scriptpubkey) == 50:
        script_type = "pubkeyhash"
        reqSigs = 1
        addresses = [ script_hex_to_address(scriptpubkey) ]

    elif scriptpubkey.startswith("a914") and scriptpubkey.endswith("87") and len(scriptpubkey) == 46:
        script_type = "scripthash"
        reqsigs = 1
        addresses = [ script_hex_to_address(scriptpubkey) ]

    elif script_tokens[-1] == OPCODE_VALUES["OP_CHECKMULTISIG"]:
        script_type = "multisig"

    elif script_tokens[0] == OPCODE_VALUES["OP_RETURN"] and len(script_tokens) == 2:
        script_type = "nulldata"

    elif len(script_tokens) == 2 and script_tokens[-1] == OPCODE_VALUES["OP_CHECKSIG"]:
        script_type = "pubkey"
        reqSigs = 1

    else:
        script_type = "nonstandard"

    ret = {
        "asm": tx_script_to_asm(scriptpubkey),
        "hex": scriptpubkey,
        "type": script_type
    }

    if addresses is not None:
        ret['addresses'] = addresses

    if reqSigs is not None:
        ret['reqSigs'] = reqSigs

    return ret