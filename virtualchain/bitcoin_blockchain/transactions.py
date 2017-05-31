import random

import time

from config import get_logger
import os
from spv import SPVClient
from virtualchain.bitcoin_blockchain.blocks import BlockchainDownloader

log = get_logger("transactions")

def get_virtual_transactions( blockchain_opts, first_block_height, last_block_height, spv_last_block=None, first_block_hash=None, tx_filter=None):
    """
    Get the sequence of virtualchain transactions from the blockchain
    Each transaction will be a 'nulldata' transaction
    """
    headers_path = blockchain_opts['bitcoind_spv_path']
    bitcoind_server = "%s:%s" % (blockchain_opts['bitcoind_server'], blockchain_opts['bitcoind_p2p_port'])
    spv_last_block = spv_last_block if spv_last_block is not None else last_block_height - 1

    if headers_path is None:
        log.error("FATAL: bitcoind_spv_path not defined in blockchain options")
        os.abort()

    if not os.path.exists(headers_path):
        log.info("Will download SPV headers to %s " % headers_path)

    #synchronize SPV headers
    SPVClient.init(headers_path)

    rc = None

    for i in xrange(0, 100000000, 1):
        # basically try forever
        try:
            rc = SPVClient.sync_header_chain( headers_path, bitcoind_server, spv_last_block )
            if not rc:
                delay = min(3600, 2**i + ((2**i) * random.random()))
                log.error("Failed to synchronize SPV headers (%s) up to %s. Try again in %s seconds" % (headers_path, last_block_height, delay))
                time.sleep( delay )
            else:
                break
        except SystemExit, s:
            log.error("Aborting on SPV headers sync")
            os.abort()

        except Exception, e:
            log.exception(e)
            delay = min(3600, 2**i + ((2**i) * random.random()))
            time.sleep(delay)
            continue

    for i in xrange(0, 10000000000, 1):
        # basically try forever
        try:
            if first_block_hash > last_block_height - 1:
                break

                # fetch all blocks
            downloader = BlockchainDownloader(blockchain_opts, blockchain_opts['bitcoind_spv_path'], first_block_height, last_block_height-1, \
                                 p2p_port=blockchain_opts['bitcoind_p2p_port'], tx_filter=tx_filter)
            rc = downloader.run()

            if not rc:
                delay = min(3600, 2**i + (2**i)*random.random())
                log.error("Failed to fetch %s-%s; trying again in %s seconds" % (first_block_height, last_block_height-1, delay))
                time.sleep(delay)
                continue
            else:
                break
        except SystemExit, s:
            log.error("Aborting on blockchain sync")
            os.abort()

        except Exception, e:
            log.exception(e)
            delay = min(3600, 2 ** i + (2 ** i) * random.random())
            log.error("Failed to fetch %s-%s; trying again in %s seconds" % (
            first_block_height, last_block_height - 1, delay))
            time.sleep(delay)
            continue

    if not rc:
        log.error("Failed to fetch blocks %s-%s" % (first_block_height, last_block_height-1))
        return None

    block_info = downloader.get_block_info()
    log.info("The length of downloaded block is %s" % len(block_info))
    return block_info











