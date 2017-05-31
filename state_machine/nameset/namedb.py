import shutil
import traceback

import indexer
from db import *
from config import *
from state_machine.operations import *
from state_machine.nameset import *
from state_machine.nameset.state_checker import *
DISPOSITION_RO = "readonly"
DISPOSITION_RW = "readwrite"
log = get_logger("namedb")



class ZonefileManageDB(indexer.StateEngine):
    """
    State engine implementation for ZonefileManage
    """
    def __init__(self, db_filename, disposition, expected_snapshots={}):

        initial_snapshots = GENESIS_SNAPSHOT
        if not os.path.exists( db_filename ):
            log.info("Initialze database from '%s' " % db_filename)
        else:
            log.info("Connect to database '%s'" % db_filename )

        self.db = None

        zonefilemanage_impl = get_implementation()

        self.db_filename = db_filename
        if os.path.exists(db_filename):
            self.db = namedb_open( db_filename )
        else:
            self.db = namedb_create( db_filename )

        self.disposition = disposition
        read_only = (disposition == DISPOSITION_RO)

        super(ZonefileManageDB, self).__init__( MAGIC_BYTES,
                                                OPCODES,
                                                ZonefileManageDB.make_opfields(),
                                                impl=zonefilemanage_impl,
                                                initial_snapshots=initial_snapshots,
                                                state=self,
                                                expected_snapshots=expected_snapshots,
                                                read_only=read_only)
        backup_frequency = 1008  # once a week; 10 minute block time
        backup_max_age = 12096  # 12 weeks
        self.set_backup_frequency(backup_frequency)
        self.set_backup_max_age(backup_max_age)

        # collision detection
        self.collisions = {}




    @classmethod
    def make_opfields(cls):
        """
        Calculate the virtualchain-required opfields dict.
        """
        opfields = {}
        for opname in SERIALIZE_FIELDS.keys():
            opcode = NAME_OPCODES[opname]
            opfields[opcode] = SERIALIZE_FIELDS[opname]

        return opfields


    def export_db(self, path):
        """
        Copy the database to the given path
        """
        if self.db is not None:
            self.db.commit()

        shutil.copyfile(self.get_db_path(), path)

    def get_name(self, name, lastblock=None, included_expired=False):
        if lastblock is None:
            lastblock = self.lastblock

        cur = self.db.cursor()
        name_rec = namedb_get_name(cur, name, lastblock, included_expired = included_expired)
        return name_rec

    def get_db_path(self):
        return self.db_filename

    def is_name_registered(self, name):
        name_rec = self.get_name(name)
        if name_rec is None:
            return False

        if name_rec['revoked']:
            return False
        return True



    def commit_operation(self, nameop, current_block_number):
        """
        Commit an operation, thereby carrying out a state transition.
        """

        # have to have read-write disposition
        if self.disposition != DISPOSITION_RW:
            log.error("FATAL: borrowing violation: not a read-write connection")
            traceback.print_stack()
            os.abort()

        cur = self.db.cursor()
        op_seq = None
        op_seq_type_str = None
        opcode = nameop.get('opcode', None)
        history_id = None

        try:
            assert opcode is not None, "Undefined op '%s'" % nameop['op']
        except Exception, e:
            log.exception(e)
            log.error("FATAL: unrecognized op '%s'" % nameop['op'])
            os.abort()

        if opcode in OPCODE_NAME_STATE_CREATIONS:
            # creation
            op_seq = self.commit_state_create(nameop, current_block_number)
            op_seq_type_str = "state_create"

        elif opcode in OPCODE_NAME_STATE_TRANSITIONS:
            # transition
            op_seq = self.commit_state_transition(nameop, current_block_number)
            op_seq_type_str = "state_transition"

        else:
            raise Exception("Unknown operation '%s'" % opcode)

        if op_seq is None:
            log.error("FATAL: no op-sequence generated (for %s)" % op_seq_type_str)
            os.abort()

        if type(op_seq) != list:
            op_seq = [op_seq]

        # # make sure all the mutate fields necessary to derive
        # # the next consensus hash are in place.
        # for i in xrange(0, len(op_seq)):
        #
        #     cur = self.db.cursor()
        #     history = None
        #
        #     # temporarily store history...
        #     if history_id is not None:
        #         history = namedb_get_history(cur, history_id)
        #         op_seq[i]['history'] = history
        #
        #         # set all extra consensus fields
        #     self.add_all_commit_consensus_values(opcode, op_seq[i], nameop, current_block_number)
        #
        #     # revert...
        #     if history is not None:
        #         del op_seq[i]['history']
        #
        #     self.log_commit(current_block_number, op_seq[i]['vtxindex'], op_seq[i]['op'], opcode, op_seq[i])

        return op_seq


    def commit_finished( self, block_id ):
        """
        Called when the block is finished.
        Commits all data.
        """

        self.db.commit()

    def sanitize_op(self, op_data):

        # remove invariant tags (i.e. added by our invariant state_* decorators)
        to_remove = get_state_invariant_tags()
        for tag in to_remove:
            if tag in op_data.keys():
                del op_data[tag]

        for extra_field in ['opcode']:
            if extra_field in op_data:
                del op_data[extra_field]

        return op_data

    def commit_state_create(self, nameop, current_block_number):
        # have to have read-write disposition
        if self.disposition != DISPOSITION_RW:
            log.error("FATAL: borrowing violation: not a read-write connection")
            traceback.print_stack()
            os.abort()

        cur = self.db.cursor()
        opcode = nameop.get('opcode', None)

        log.info('nameop is %s' % nameop)

        table = state_create_get_table(nameop)
        initial_state = self.sanitize_op(nameop)

        rc = namedb_state_create(cur, opcode, initial_state,
                                 current_block_number, initial_state['vtxindex'], initial_state['txid'], table)

        if not rc:
            self.db.rollback()
            os.abort()

        self.db.commit()

        return initial_state




    def commit_state_transition(self, nameop, current_block_number):
        # have to have read-write disposition
        if self.disposition != DISPOSITION_RW:
            log.error("FATAL: borrowing violation: not a read-write connection")
            traceback.print_stack()
            os.abort()

        cur = self.db.cursor()
        opcode = nameop.get('opcode', None)

        table = state_create_get_table(nameop)
        initial_state = self.sanitize_op(nameop)
        # create from preorder
        rc = namedb_state_transition(cur, opcode, initial_state,
                                 current_block_number, initial_state['vtxindex'], initial_state['txid'], table)

        if not rc:
            self.db.rollback()
            os.abort()

        self.db.commit()
        return initial_state


    @classmethod
    def calculate_block_ops_hash(cls, db_state, block_id):
        """
        Get the hash of the sequence of operations that occurred in a particular block.
        Return the hash on success.
        """

        # from ..consensus import rec_restore_snv_consensus_fields
        #
        # # calculate the ops hash and save that
        # prior_recs = db_state.get_all_ops_at(block_id, include_history=True)
        # if prior_recs is None:
        #     prior_recs = []
        #
        # restored_recs = []
        # for i in xrange(0, len(prior_recs)):
        #     if (i + 1) % 10 == 0:
        #         log.debug("Strategic garbage collect at block %s op %s" % (block_id, i))
        #         gc.collect()
        #
        #     restored_rec = rec_restore_snv_consensus_fields(prior_recs[i], block_id)
        #     restored_recs.append(restored_rec)
        #
        # # NOTE: extracts only the operation-given fields, and ignores ancilliary record fields
        # serialized_ops = [
        #     virtualchain.StateEngine.serialize_op(str(op['op'][0]), op, BlockstackDB.make_opfields(), verbose=True) for
        #     op in restored_recs]
        # ops_hash = virtualchain.StateEngine.make_ops_snapshot(serialized_ops)

        ops_hash = "%064x" % 1142423
        return ops_hash



    def store_block_ops_hash(self, block_id, ops_hash):
        """
        Store the operation hash for a block ID, calculated from
        @calculate_block_ops_hash.
        """
        cur = self.db.cursor()
        namedb_set_block_ops_hash(cur, block_id, ops_hash)
        self.db.commit()

        log.debug("ops hash at %s is %s" % (block_id, ops_hash))
        return True

def namedb_set_block_ops_hash( cur, block_number, ops_hash ):
    """
    Set the operations hash for a block height
    """
    insert_query = "INSERT INTO ops_hashes (block_id,ops_hash) VALUES (?,?);"
    insert_args = (block_number, ops_hash)

    namedb_query_execute( cur, insert_query, insert_args )


