import json
import os
import traceback
from collections import defaultdict

import copy

import binascii

import pybitcoin
import shutil
import simplejson
import sys

import time
from utilitybelt import is_hex

import config
from virtualchain.bitcoin_blockchain import transactions


RESERVED_KEYS = [
   'virtualchain_opcode',
   'virtualchain_outputs',
   'virtualchain_senders',
   'virtualchain_block_number',
   'virtualchain_accepted',
   'virtualchain_txid',
   'virtualchain_txindex'
]


log = config.get_logger("indexer")

class StateEngine(object):
    def __init__(self, magic_bytes, opcodes, opfields, impl=None, state=None, initial_snapshots = {}, expected_snapshots={}, backup_frequency=None, backup_max_age=None, read_only=False):
        self.consensus_hashes = initial_snapshots
        self.pending_opts = defaultdict(list)
        self.magic_bytes = magic_bytes
        self.opcodes = opcodes[:]
        self.opfields = copy.deepcopy(opfields)
        self.state = state
        self.impl = impl
        self.lastblock = self.impl.get_first_block_id() - 1
        self.pool = None
        self.rejected = {}
        self.expected_snapshots = expected_snapshots
        self.backup_frequency = backup_frequency
        self.backup_max_age = backup_max_age
        self.read_only = read_only

        firsttime = True

        consensus_snapshots_filename = config.get_snapshots_filename(impl)
        lastblock_filename = config.get_lastblock_filename(impl)

        # check whether it is the first time
        for fp in [consensus_snapshots_filename, lastblock_filename]:
            if os.path.exists(fp):
                firsttime = False

        # Attempt to load the snapshots
        if os.path.exists(consensus_snapshots_filename):
            log.debug("Consensus snapshots at %s" % consensus_snapshots_filename)

            try:
                with open(consensus_snapshots_filename, "r") as f:
                    db_dict = json.loads(f.read())
                    assert 'snapshots' in db_dict
                    self.consensus_hashes = db_dict['snapshots']

            except Exception, e:
                log.error("FATAL: Failed to read consensus snapshots at %s" % (consensus_snapshots_filename))
                log.exception(e)
                os.abort()
        elif firsttime:
            log.debug("Consensus snapshots at %s" % consensus_snapshots_filename)

            try:
                with open(consensus_snapshots_filename, "w") as f:
                    f.write(json.dumps({'snapshots': self.consensus_hashes}))
                    f.flush()
            except Exception, e:
                log.error("FATAL: Failed to store initial consensus snapshot to %s" % consensus_snapshots_filename)
                log.exception(e)
                os.abort()
        else:
            log.error("No such file or directory: %s " % consensus_snapshots_filename)
            os.abort()

        # Process the last block
        if os.path.exists( lastblock_filename ):

            log.debug("Lastblock at %s" % lastblock_filename)

            self.lastblock = self.get_lastblock()
            log.debug("Last block: %s(%s) " % (self.lastblock, lastblock_filename))
            if self.lastblock is None:
                log.error("FATAL: Failed to read last block id at %s" % lastblock_filename)
                log.exception(e)
                os.abort()

        elif firsttime:
            log.debug("lastblock at %s" % lastblock_filename)

            try:
                with open(lastblock_filename, "w") as f:
                    f.write("%s" % self.lastblock)
                    f.flush()
            except Exception, e:
                log.error("FATAL: Failed to store initial last block(%s) to %s" % (self.lastblock, lastblock_filename))
                log.exception(e)
                os.abort()

        else:
            log.error("FATAL: No such file or directory exists: %s" % lastblock_filename)
            os.abort()

    def get_lastblock(self, lastblock_filename=None, impl=None):
        """
        Get the last block
        """
        if lastblock_filename is None:

            if impl is None:
                impl = self.impl

            lastblock_filename = config.get_lastblock_filename()

        if os.path.exists( lastblock_filename ):
            try:
                with open(lastblock_filename) as f:
                    lastblock_str = f.read().strip()
                    return int(lastblock_str)
            except Exception, e:
                log.error("Failed to read last block number at: %s" % lastblock_filename)
                return None
        return None


    def set_backup_frequency(self, backup_frequency):
        self.backup_frequency = backup_frequency

    def set_backup_max_age(self, backup_max_age):
        self.set_backup_max_age = backup_max_age

    @classmethod
    def build(cls, bitcoind_opts, end_block_id, state_engine, expected_snapshots={}, tx_filter=None):
        """
        Top-level call to process all blocks in the zonefilemanage
        Goes and fetch all OP_RETURN nulldata in order, and feeds them into the state-engine using db_parse, db_check, db_commit and db_save
        """
        first_block_id = state_engine.lastblock + 1
        if first_block_id >= end_block_id:
            log.info("Up-to-date (%s -> %s)" % (first_block_id, end_block_id))
            return True

        rc = True
        batch_size = config.BLOCK_BATCH_SIZE

        log.info("Sync virtualchain state from %s to %s " % (first_block_id, end_block_id ))

        for block_id in xrange(first_block_id, end_block_id, batch_size):

            if not rc:
                break

            last_block_id = min(block_id + batch_size, end_block_id)
            block_ids_and_txs = transactions.get_virtual_transactions(bitcoind_opts, first_block_id, last_block_id )
            if block_ids_and_txs is None:
                raise Exception("Failed to get virtual transactions %s to %s" % (block_id, block_id + last_block_id))

            # sort by block height
            block_ids_and_txs.sort()
            # log.info('block_ids_txs is %s' % block_ids_and_txs)
            for processed_block_id, txs in block_ids_and_txs:

                if state_engine.get_consensus_at(processed_block_id) is not None:
                    raise Exception("Already processed block %s (%s)" % (processed_block_id, state_engine.get_consensus_at(processed_block_id)))

                ops = state_engine.parse_block( processed_block_id, txs)
                consensus_hash = state_engine.process_block(processed_block_id, ops, expected_snapshots=expected_snapshots)

                # if consensus_hash is not None:
                #     rc = False
                #     log.debug("Stopped processing at block %s" % processed_block_id)
                #     break
                #
                # log.debug("CONSENSUS(%s) :%s" % (processed_block_id, state_engine.get_consensus_at(processed_block_id)))
                #
                # # Sanity check if given
                #
                # expected_consensus_hash = state_engine.get_expected_consensus_at(processed_block_id)
                # if expected_snapshots is not None:
                #     if str(consensus_hash) != str(expected_consensus_hash):
                #         rc = False
                #         log.error("FATAL: Divergence detected at %s: %s != %s" % (processed_block_id, consensus_hash, expected_consensus_hash))
                #         traceback.print_stack()
                #         os.abort()
                # if not rc:
                #     break

            log.debug("Last block is %s" % state_engine.lastblock)

            return rc





    def get_expected_consensus_at(self, block_id):
        """
        Get the expected consensus hash at a given block
        """
        return self.expected_snapshots.get(str(block_id), None)




    def get_consensus_at(self, block_id):
        """
        Get the consensus hash at a given block
        """
        return self.consensus_hashes.get(str(block_id), None)


    def parse_transaction(self, block_id, tx):
        """
        Given a block ID and OP_RETURN transaction, try to parse it into a virtual chain operation
        """

        op_return_hex = tx['nulldata']
        inputs = tx['vin']
        outputs = tx['vout']
        senders = tx['senders']

        if not is_hex(op_return_hex):
            return None

        if len(op_return_hex) % 2 != 0:
            return None

        try:
            op_return_bin = binascii.unhexlify(op_return_hex)
        except Exception, e:
            log.error("Failed to parse transaction: %s (OP_RETUAN= %s)" % (tx, op_return_hex))
            raise e

        if not op_return_bin.startswith( self.magic_bytes ):
            return None
        op_code = op_return_bin[len(self.magic_bytes)]

        if op_code not in self.opcodes:
            return None

        op_payload = op_return_bin[len(self.magic_bytes) + 1:]

        op = self.impl.db_parse( block_id, tx['txid'], tx['txindex'], op_code, op_payload, senders, inputs, outputs, db_state=self.state )

        if op is None:
            return None

        op['virtualchain_opcode'] = op_code
        op['virtualchain_outputs'] = outputs
        op['virtualchain_senders'] = senders
        op['virtualchain_block_number'] = block_id
        op['virtualchain_accepted'] = False  # not yet accepted
        op['virtualchain_txid'] = tx['txid']
        op['virtualchain_txindex'] = tx['txindex']

        return op


    def parse_block(self, block_id, txs):
        """
        Given the sequence of transactions in a block, turn them into a sequence of virtual chain operations
        """

        ops = []

        for i in xrange(0, len(txs)):

            tx = txs[i]
            op = self.parse_transaction( block_id, tx )
            if op is not None:
                ops.append(op)

        return ops

    def remove_reserved_keys(self, op):

        sanitized = {}
        reserved = {}

        for k in op.keys():
            if str(k) not in RESERVED_KEYS:
                sanitized[str(k)] = copy.deepcopy(op[k])
            else:
                reserved[str(k)] = copy.deepcopy(op[k])

        return sanitized, reserved



    def process_ops(self, block_id, ops):
        """
        Given a transaction-orded sequence of parsed operations, check the validity and give them to the state engine to affect state changes.
        """
        new_ops = defaultdict(list)

        for op in self.opcodes:
            new_ops[op] = []

        new_ops['virtualchain_ordered'] = []
        new_ops['virtualchain_all_ops'] = ops

        to_commit_sanitized = []
        to_commit_reserved = []

        # Let the implementation do an initial scan over the blocks
        initial_scan = []


        for i in xrange(0, len(ops)):
            op_data = ops[i]
            op_sanitized, _ = self.remove_reserved_keys(op_data)
            initial_scan.append(copy.deepcopy(op_sanitized))

        for i in xrange(0, len(ops)):
            op_data = ops[i]
            op_sanitized, reserved = self.remove_reserved_keys(op_data)

            opcode = reserved['virtualchain_opcode']

            # Check this op
            rc = self.impl.db_check(block_id, new_ops, opcode, op_sanitized, reserved['virtualchain_txid'], reserved['virtualchain_txindex'], to_commit_sanitized, db_state=self.state)
            if rc:
                new_op_list = self.impl.db_commit(block_id, opcode, op_sanitized, reserved['virtualchain_txid'], reserved['virtualchain_txindex'], db_state=self.state)
                if type(new_op_list) != list:
                    new_op_list = [new_op_list]

                for new_op in new_op_list:
                    if new_op is not None:
                        if type(new_op) == dict:
                            to_commit_sanitized_op = copy.deepcopy(new_op)
                            to_commit_sanitized.append(to_commit_sanitized_op)

                            new_op.update(reserved)
                            new_ops[opcode].append(new_op)
                            new_ops['virtualchain_ordered'].append(new_op)

                        else:
                            continue

            else:
                log.error("Reject block_id : %s" % block_id)

        # final commit
        # the implementation has a chance here to feed any extra data into the consensus hash with this call
        # (e.g. to affect internal state transitions that occur as seconary, holistic consequences to the sequence
        # of prior operations for this block).
        final_op = self.impl.db_commit(block_id, 'virtualchain_final', None, None, None, db_state=self.state)
        if final_op is not None:
            final_op['virtualchain_opcode'] = 'final'

            new_ops['virtualchain_final'] = [final_op]
            new_ops['virtualchain_ordered'].append(final_op)
            new_ops['virtualchain_all_ops'].append(final_op)

        return new_ops



    @classmethod
    def serialize_op(cls, opcode, opdata, opfields, verbose=True):
        fields = opfields.get(opcode, None)
        if fields is None:
            log.error("Unrecognized opcode '%s'" % opcode)
            return None

        all_values = []
        debug_all_values = []
        missing = []

        for field in fields:
            if not opdata.has_key(field):
                missing.append(field)

            field_value = opdata.get(field, None)
            if field_value is None:
                field_value = ""

            # netstring format
            debug_all_values.append(str(field) + "=" + str(len(str(field_value))) + ":" + str(field_value))
            all_values.append(str(len(str(field_value))) + ":" + str(field_value))

        if len(missing) > 0:
            log.error("Missing fields; dump follows:\n%s" % simplejson.dumps(opdata, indent=4, sort_keys=True))
            raise Exception("BUG: missing fields '%s'" % (",".join(missing)))

        if verbose:
            log.debug("SERIALIZE: %s:%s" % (opcode, ",".join(debug_all_values)))

        field_values = ",".join(all_values)

        return opcode + ":" + field_values

    @classmethod
    def make_ops_snapshot(cls, serialized_ops):
        """
        Generate a deterministic hash over the sequence of (serialized) operations.
        """
        record_hashes = []
        for serialized_op in serialized_ops:
            record_hash = binascii.hexlify(pybitcoin.hash.bin_double_sha256(serialized_op))
            record_hashes.append(record_hash)

        if len(record_hashes) == 0:
            record_hashes.append(binascii.hexlify(pybitcoin.hash.bin_double_sha256("")))

        # put records into their own Merkle tree, and mix the root with the consensus hashes.
        record_hashes.sort()
        record_merkle_tree = pybitcoin.MerkleTree(record_hashes)
        record_root_hash = record_merkle_tree.root()

        return record_root_hash

    @classmethod
    def make_snapshot(cls, serialized_ops, prev_consensus_hashes):
        """
        Generate a consensus hash, using the tx-ordered list of serialized name
        operations, and a list of previous consensus hashes that contains
        the (k-1)th, (k-2)th; (k-3)th; ...; (k - (2**i - 1))th consensus hashes,
        all the way back to the beginning of time (prev_consensus_hashes[i] is the
        (k - (2**(i+1) - 1))th consensus hash)
        """

        record_root_hash = StateEngine.make_ops_snapshot(serialized_ops)
        log.debug("Snapshot('%s', %s)" % (record_root_hash, prev_consensus_hashes))
        return cls.make_snapshot_from_ops_hash(record_root_hash, prev_consensus_hashes)

    @classmethod
    def make_snapshot_from_ops_hash( cls, record_root_hash, prev_consensus_hashes ):
        """
        Generate the consensus hash from the hash over the current ops, and
        all previous required consensus hashes.
        """

        # mix into previous consensus hashes...
        all_hashes = prev_consensus_hashes[:] + [record_root_hash]
        all_hashes.sort()
        all_hashes_merkle_tree = pybitcoin.MerkleTree( all_hashes )
        root_hash = all_hashes_merkle_tree.root()

        consensus_hash = StateEngine.calculate_consensus_hash( root_hash )
        return consensus_hash

    @classmethod
    def calculate_consensus_hash(self, merkle_root):
        """
        Given the Merkle root of the set of records processed, calculate the consensus hash.
        """
        return binascii.hexlify(pybitcoin.hash.bin_hash160(merkle_root, True)[0:16])

    def snapshot(self, block_id, oplist):

        log.debug("Snapshotting block %s" % (block_id))

        serialized_ops = []
        for opdata in oplist:
            serialized_record = StateEngine.serialize_op(opdata['virtualchain_opcode'], opdata, self.opfields)
            serialized_ops.append(serialized_record)

        previous_consensus_hashes = []
        k = block_id
        i = 1
        while k - (2 ** i - 1) >= self.impl.get_first_block_id():
            prev_block = k - (2 ** i - 1)
            prev_ch = self.get_consensus_at(prev_block)
            log.debug("Snapshotting block %s: consensus hash of %s is %s" % (block_id, prev_block, prev_ch))

            if prev_ch is None:
                log.error("BUG: None consensus for %s" % prev_block)
                traceback.print_stack()
                os.abort()

            previous_consensus_hashes.append(prev_ch)
            i += 1

        consensus_hash = StateEngine.make_snapshot(serialized_ops, previous_consensus_hashes)

        self.consensus_hashes[str(block_id)] = consensus_hash

        return consensus_hash

    def commit(self, backup=False, startup=False):
        """
        Move all written but uncommitted data into place.
        Return True on success
        Return False on error (in which case the caller should rollback())

        It is safe to call this method repeatedly until it returns True.
        """

        if self.read_only:
            log.error("FATAL: read-only")
            os.abort()

        tmp_db_filename = config.get_db_filename(impl=self.impl) + ".tmp"
        tmp_snapshot_filename = config.get_snapshots_filename(impl=self.impl) + ".tmp"
        tmp_lastblock_filename = config.get_lastblock_filename(impl=self.impl) + ".tmp"

        if not os.path.exists(tmp_lastblock_filename) and (
            os.path.exists(tmp_db_filename) or os.path.exists(tmp_snapshot_filename)):
            # we did not successfully stage the write.
            # rollback
            log.error("Partial write detected.  Not committing.")
            return False

        # basic sanity checks: don't overwrite the db if the file is zero bytes, or if we can't load it
        if os.path.exists(tmp_db_filename):
            db_dir = os.path.dirname(tmp_db_filename)

            try:
                dirfd = os.open(db_dir, os.O_DIRECTORY)
                os.fsync(dirfd)
                os.close(dirfd)
            except Exception, e:
                log.exception(e)
                log.error("FATAL: failed to sync directory %s" % db_dir)
                traceback.print_stack()
                os.abort()

            sb = os.stat(tmp_db_filename)
            if sb.st_size == 0:
                log.error("Partial write detected: tried to overwrite with zero-sized db!  Will rollback.")
                return False

            if startup:
                # make sure we can load this
                try:
                    with open(tmp_snapshot_filename, "r") as f:
                        db_txt = f.read()

                    db_json = json.loads(db_txt)
                except:
                    log.error("Partial write detected: corrupt partially-committed db!  Will rollback.")
                    return False

        backup_time = int(time.time() * 1000000)

        listing = []
        listing.append(("lastblock", tmp_lastblock_filename, config.get_lastblock_filename(impl=self.impl)))
        listing.append(("snapshots", tmp_snapshot_filename, config.get_snapshots_filename(impl=self.impl)))
        listing.append(("db", tmp_db_filename, config.get_db_filename(impl=self.impl)))

        for i in xrange(0, len(listing)):
            file_type, tmp_filename, filename = listing[i]

            dir_path = os.path.dirname(tmp_filename)
            dirfd = None
            try:
                dirfd = os.open(dir_path, os.O_DIRECTORY)
                os.fsync(dirfd)
            except Exception, e:
                log.exception(e)
                log.error("FATAL: failed to sync directory %s" % dir_path)
                traceback.print_stack()
                os.abort()

            if not os.path.exists(tmp_filename):
                # no new state written
                os.close(dirfd)
                continue

                # commit our new lastblock, consensus hash set, and state engine data
            try:

                # NOTE: rename fails on Windows if the destination exists
                if sys.platform == 'win32' and os.path.exists(filename):
                    log.debug("Clear old '%s' %s" % (file_type, filename))
                    os.unlink(filename)
                    os.fsync(dirfd)

                if not backup:
                    log.debug("Rename '%s': %s --> %s" % (file_type, tmp_filename, filename))
                    os.rename(tmp_filename, filename)
                    os.fsync(dirfd)

                else:
                    log.debug("Rename and back up '%s': %s --> %s" % (file_type, tmp_filename, filename))
                    shutil.copy(tmp_filename, tmp_filename + (".%s" % backup_time))
                    os.rename(tmp_filename, filename)
                    os.fsync(dirfd)

            except Exception, e:
                log.exception(e)
                log.error("Failed to rename '%s' to '%s'" % (tmp_filename, filename))
                os.close(dirfd)
                return False

            os.close(dirfd)

        return True
    def save(self, block_id, consensus_hash, pending_ops, backup=False):
        """
        Write out all state to the working directory.
        Calls the implementation's 'db_save' method to store any state for this block.
        Calls the implementation's 'db_continue' method at the very end, to signal
        to the implementation that all virtualchain state has been saved.  This method
        can return False, in which case, indexing stops

        Return True on success
        Return False if the implementation wants to exit.
        Aborts on fatal error
        """

        if self.read_only:
            log.error("FATAL: read only")
            traceback.print_stack()
            os.abort()

        if block_id < self.lastblock:
            log.error("FATAL: Already processed up to block %s (got %s)" % (self.lastblock, block_id))
            traceback.print_stack()
            os.abort()

        # stage data to temporary files
        tmp_db_filename = (config.get_db_filename(impl=self.impl) + ".tmp")
        tmp_snapshot_filename = (config.get_snapshots_filename(impl=self.impl) + ".tmp")
        tmp_lastblock_filename = (config.get_lastblock_filename(impl=self.impl) + ".tmp")

        try:
            with open(tmp_snapshot_filename, 'w') as f:
                db_dict = {
                    'snapshots': self.consensus_hashes
                }
                f.write(json.dumps(db_dict))
                f.flush()

            with open(tmp_lastblock_filename, "w") as lastblock_f:
                lastblock_f.write("%s" % block_id)
                lastblock_f.flush()

        except Exception, e:
            # failure to save is fatal
            log.exception(e)
            log.error("FATAL: Could not stage data for block %s" % block_id)
            traceback.print_stack()
            os.abort()

        rc = self.impl.db_save(block_id, consensus_hash, pending_ops, tmp_db_filename, db_state=self.state)
        if not rc:
            # failed to save
            # this is a fatal error
            log.error("FATAL: Implementation failed to save at block %s to %s" % (block_id, tmp_db_filename))

            try:
                os.unlink(tmp_lastblock_filename)
            except:
                pass

            try:
                os.unlink(tmp_snapshot_filename)
            except:
                pass

            traceback.print_stack()
            os.abort()

        rc = self.commit(backup=backup)
        if not rc:
            log.error("Failed to commit data at block %s.  Rolling back and aborting." % block_id)

            self.rollback()
            traceback.print_stack()
            os.abort()

        else:
            self.lastblock = block_id

            # # make new backups
            # self.make_backups(block_id)
            #
            # # clear out old backups
            # self.clear_old_backups(block_id)
        return True

    def process_block(self, block_id, ops, backup=False, expected_snapshots=None):

        log.debug("Process block %s (%s virtual transactions)" % (block_id, len(ops)))

        if expected_snapshots is None:
            expected_snapshots = self.expected_snapshots

        # IMPORTANT logic here
        new_ops = self.process_ops(block_id, ops)
        sanitized_ops = {}

        consensus_hash = '0'*20
        # consensus_hash = self.snapshot(block_id, new_ops['virtualchain_ordered'])
        #
        # # Sanity check
        #
        # if expected_snapshots.has_key(block_id) and expected_snapshots[block_id] != consensus_hash:
        #     log.error("FATAL: Consensus hash mismatch at height %s: %s != %s" % (block_id, expected_snapshots[block_id], consensus_hash))
        #     traceback.print_stack()
        #     os.abort()
        #
        # for op in new_ops.keys():
        #     sanitized_ops[op] = []
        #     for i in xrange(0, len(new_ops[op])):
        #
        #         op_sanitized, op_reserved = self.remove_reserved_keys(new_ops[op][i])
        #         sanitized_ops[op].append(op_sanitized)
        #
        rc = self.save(block_id, consensus_hash, sanitized_ops, backup=backup)
        # if not rc:
        #     log.debug("Early indexing termination at %s" % block_id)
        #
        #     return None

        return consensus_hash










