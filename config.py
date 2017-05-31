import os
import logging
from copy import deepcopy

import pybitcoin

DEBUG = False
if os.environ.get("ZONEFILEMANAGE_DEBUG") == "1":
    DEBUG = False

REINDEX_FREQUENCY = 300 # seconds
if os.environ.get("ZONEFILEMANAGE_TEST") == "1":
    REINDEX_FREQUENCY = 1

FIRST_BLOCK_MAINNET = 373601

if os.environ.get("ZONEFILEMANAGE_TEST", None) is not None and os.environ.get("ZONEFILEMANAGE_TEST_FIRST_BLOCK", None) is not None:
    FIRST_BLOCK_MAINNET = int(os.environ.get("ZONEFILEMANAGE_TEST_FIRST_BLOCK"))


TX_MIN_CONFIRMATIONS = 6
if os.environ.get("ZONEFILEMANAGE_TEST", None) == "1":
    # test environment
    TX_MIN_CONFIRMATIONS = 0


running = False

voting_strategy = 0

server = None

VOTEPORT = 16288

GENESIS_SNAPSHOT = {
    str(FIRST_BLOCK_MAINNET-4): "17ac43c1d8549c3181b200f1bf97eb7d",
    str(FIRST_BLOCK_MAINNET-3): "17ac43c1d8549c3181b200f1bf97eb7d",
    str(FIRST_BLOCK_MAINNET-2): "17ac43c1d8549c3181b200f1bf97eb7d",
    str(FIRST_BLOCK_MAINNET-1): "17ac43c1d8549c3181b200f1bf97eb7d",
}


MAGIC_BYTES = 'rt'

# Opcodes
NAME_REGISTER = ':'
NAME_UPDATE = '+'
NAME_TRANSFER = '>'
NAME_REVOKE = '~'

OPCODES = [
    NAME_REGISTER,
    NAME_UPDATE,
    NAME_TRANSFER,
    NAME_REVOKE
]

NAME_OPCODES = {
    "NAME_REGISTER": NAME_REGISTER,
    "NAME_UPDATE": NAME_UPDATE,
    "NAME_TRANSFER": NAME_TRANSFER,
    "NAME_REVOKE": NAME_REVOKE
}

OPCODES_NAMES = {
    NAME_REGISTER: "NAME_REGISTER",
    NAME_UPDATE: "NAME_UPDATE",
    NAME_TRANSFER: "NAME_TRANSFER",
    NAME_REVOKE: "NAME_REVOKE"
}

BLOCK_BATCH_SIZE = 10


OPCODE_NAME_STATE_CREATIONS = [
    "NAME_REGISTER"
]

OPCODE_NAME_STATE_TRANSITIONS = [
    "NAME_UPDATE",
    "NAME_TRANSFER",
    "NAME_REVOKE"
]


bitcoin_regtest_opts = None

RPC_SERVER_PORT = 16264

NAMEREC_FIELDS = [
    'name',  # the name itself
    'value_hash',  # the hash of the name's associated profile
    'block_number',  # the block number when this name record was created (preordered for the first time)
    'first_registered',  # the block number when this name was registered by the current owner
    'last_renewed',  # the block number when this name was renewed by the current owner
    'revoked',  # whether or not the name is revoked
    'op',  # byte sequence describing the last operation to affect this name
    'txid',  # the ID of the last transaction to affect this name
    'vtxindex',  # the index in the block of the transaction.
]



# op-return formats
LENGTHS = {
    'magic_bytes': 2,
    'opcode': 1,
    'name_update': 17,
    'consensus_hash': 16,
    'namelen': 1,
    'name_min': 1,
    'name_max': 34,
    'fqn_min': 3,
    'fqn_max': 37,
    'name_hash': 16,
    'name_consensus_hash': 16,
    'value_hash': 20,
    'announce': 20,
    'max_op_length': 80
}




def get_logger(name="ZONEFILEMANAGE"):
    """
    Get virtualchain's logger
    """

    level = logging.CRITICAL
    if DEBUG:
        logging.disable(logging.NOTSET)
        level = logging.DEBUG
    else:
        logging.disable(logging.NOTSET)
        level = logging.INFO
    if name is None:
        name = "<unknown>"
        level = logging.CRITICAL

    log = logging.getLogger(name=name)
    log.setLevel(level)
    console = logging.StreamHandler()
    console.setLevel(level)
    file_handler = logging.FileHandler("test.log")
    file_handler.setLevel(level)
    # if DEBUG else '%(message)s'
    log_format = ('[%(asctime)s] [%(levelname)s] [%(module)s:%(lineno)d] (' + str(
        os.getpid()) + '.%(thread)d) %(message)s')
    formatter = logging.Formatter(log_format)
    console.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    log.propagate = False

    if len(log.handlers) > 0:
        for i in xrange(0, len(log.handlers)):
            log.handlers.pop(0)

    log.addHandler(console)
    log.addHandler(file_handler)
    return log


def get_virtualchain_name():
    return "zonefilemanage_server"



def get_snapshots_filename(impl=None):
    """
    Get the absolute path to the chain's consensus snapshots file
    """
    impl = get_impl(impl)

    working_dir = get_working_dir(impl)
    snapshots_filename = get_virtualchain_name() + ".snapshots"

    return os.path.join(working_dir, snapshots_filename)




def get_db_filename( impl=None ):
    """
    Get the absolute path to the last-block file
    """
    impl = get_impl(impl)
    db_filename = get_virtualchain_name() + ".db"
    working_dir = get_working_dir(impl=impl)

    return os.path.join(working_dir, db_filename)

def get_lastblock_filename(impl = None):
    """
    Get the absote path to the last-block file
    """
    impl = get_impl(impl)
    lastblock_filename = get_virtualchain_name() + ".lastblock"
    working_dir = get_working_dir(impl=impl)

    return os.path.join(working_dir, lastblock_filename)


def set_implementation( impl ):
    """
    The method should be called before anything else
    """

    global IMPL
    IMPL = impl

def get_implementation():
    global IMPL
    return IMPL


def get_impl(impl):
    """
    Get the implementation-- either the given or the globaly set
    """
    global IMPL
    if impl is not None:
        return impl
    elif IMPL is not None:
        return IMPL
    raise Exception("No virtualchain implmentation set")

def get_working_dir(impl = None):
    """
    Get the absolute path to the working directory
    """
    if os.environ.has_key("VIRTUALCHAIN_WORKING_DIR"):
        return os.environ["VIRTUALCHAIN_WORKING_DIR"]

    # impl = get_impl(impl)
    #
    # from os.path import expanduser
    # home = expanduser("~")
    #
    # working_dir = None
    # if hasattr(impl, "working_dir") and impl.working_dir is not None:
    #     working_dir = impl.working_dir
    #
    # else:
    #     working_dir = os.path.join(home, "." + impl.get_virtual_chain_name())
    #
    # if not os.path.exists(working_dir):
    #     os.makedirs(working_dir)
    #
    # return working_dir


def op_get_opcode_name(op_string):
    """
    Get the name of an opcode, given the operation's 'op' byte sequence
    """

    op = op_string[0]
    if op not in OPCODES_NAMES.keys():
        raise Exception("No such operation '%s'" % op)

    return OPCODES_NAMES[op]


def set_bitcoin_regtest_opts(opts):
    global bitcoin_regtest_opts
    if bitcoin_regtest_opts is None:
        bitcoin_regtest_opts = opts


def get_bitcoin_regtest_opts():
    return bitcoin_regtest_opts


def get_tx_broadcaster():
    utxo_opts = get_bitcoin_regtest_opts()
    return pybitcoin.BitcoindClient(utxo_opts['rpc_username'], utxo_opts['rpc_password'],
                                    use_https=utxo_opts['use_https'], server=utxo_opts['server'],
                                    port=utxo_opts['port'], version_byte=utxo_opts['version_byte'])



def set_running( status ):
    """
    Set running flag
    """
    global running
    running = status


def is_running():
    """
    Check running flag
    """
    global running
    return running


def get_p2p_hosts():
    ips = "172.17.0.2-4"
    ip_parts = ips.split('.')
    assert len(ip_parts) == 4, "ips %s is not correct" % ips
    ip_range = ip_parts[3].split('-')
    ip_start = int(ip_range[0])
    ip_end  = int(ip_range[1])

    new_ip_parts = deepcopy(ip_parts)
    new_ip_parts.pop()
    ips = []
    for i in xrange(ip_start, ip_end+1):
        ip = ".".join(new_ip_parts + [str(i)])
        ips.append(ip)

    return ips

def get_previous_ips():
    my_ip = get_my_ip()
    hosts = get_p2p_hosts()
    my_ip_index = hosts.index(my_ip)
    return hosts[:my_ip_index]


def get_my_ip():
    import commands, re
    ret, out = commands.getstatusoutput(
        "ifconfig | grep 'inet addr:' | grep 'Bcast'| awk '{print $2}' | awk -F':' '{print $2}'")
    pattern = re.compile("^\d+\.\d+\.\d+\.\d+$")
    match = pattern.match(out)
    if match:
        return match.group()
    else:
        raise Exception("Ip config is not right")
        return None


def get_global_server():
    global server
    return server

def set_global_server(server_inst):
    global server
    if server is None:
        server = server_inst


def set_global_db(inst):
    global db_inst
    if db_inst is None:
        db_inst = inst

def is_main_worker():
    my_ip = get_my_ip()
    return my_ip == '172.17.0.2'


if __name__ == '__main__':
    ips = get_p2p_hosts\
        ()
    print ips

