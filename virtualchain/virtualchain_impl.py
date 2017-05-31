import os

import config
import datetime
from state_machine.nameset import indexer
from config import get_logger

log = get_logger("virtual_")
def setup_virtualchain( impl = None ):
    if impl is not None:
        config.set_implementation( impl )

def sync_virtualchain(bitcoind_opts, last_block, state_engine, expected_snapshots={}, tx_filter=None):
    """
    Synchronize the virtualchain state up until a given block
    """

    rc = False
    start = datetime.datetime.now()
    while True:
        # advance the state
        try:
            rc = indexer.StateEngine.build(bitcoind_opts, last_block+1, state_engine, expected_snapshots=expected_snapshots, tx_filter=tx_filter)
            break
        except Exception, e:
            log.exception(e)
            log.error("Failed to synchronized chain; exiting to safety")
            os.abort()

    time_taken = "%s seconds" % (datetime.datetime.now() - start).seconds
    log.info(time_taken)

    return rc



