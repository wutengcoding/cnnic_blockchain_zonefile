from config import get_logger
from autoproxy import AuthServiceProxy
log = get_logger()

bitcoind_conn = None

def connect_bitcoind_impl( bitcoind_opts ):


    """
    Create a connection to bitconind using a dict of config
    """
    if 'bitcoind_port' in bitcoind_opts.keys() and bitcoind_opts['bitcoind_port'] is None:
        log.error("No port given")
        raise ValueError("No RPC port given (bitcoind_port)")

    if 'bitcoind_timeout' in bitcoind_opts.keys() and bitcoind_opts['bitcoind_timeout'] is None:
        # default
        bitcoind_opts['bitcoind_timeout'] = 300

    try:
        int(bitcoind_opts['bitcoind_port'])
    except:
        log.error("Not an int: %s " % bitcoind_opts['bitcoind_port'])
        pass

    try:
        float(bitcoind_opts['bitcoind_timeout'])
    except:
        log.error("Not a float: %s " % bitcoind_opts['bitcoind_timeout'])
        pass

    return create_bitcoind_connection(bitcoind_opts['bitcoind_user'], bitcoind_opts['bitcoind_passwd'], \
                                      bitcoind_opts['bitcoind_server'], bitcoind_opts['bitcoind_port'],\
                                      bitcoind_opts.get('bitcoind_use_https', False), float(bitcoind_opts.get('bitcoind_timeout', 300)) )

def create_bitcoind_connection( rpc_username, rpc_password, server, port, use_https, timeout ):
    """
    Create an RPC instance to a bitcoind instance.
    """
    protocol = 'https' if use_https else 'http'
    autoproxy_config_uri = '%s://%s:%s@%s:%s' % (protocol, rpc_username, rpc_password, server, port)

    if use_https:
        pass
    else:
        ret = AuthServiceProxy(autoproxy_config_uri)

    #remember the options
    bitcoind_opts = {
        "bitcoind_user": rpc_username,
        "bitcoind_passwd": rpc_password,
        "bitcoind_server": server,
        "bitcoind_port": port,
        "bitcoind_use_https": use_https,
        "bitcoind_timeout": timeout
    }
    setattr(ret, "opts", bitcoind_opts)

    global  bitcoind_conn
    if bitcoind_conn is None:
        bitcoind_conn = ret
    return ret


def get_bitcoind_connection():
    global bitcoind_conn
    if bitcoind_conn is not None:
        return bitcoind_conn