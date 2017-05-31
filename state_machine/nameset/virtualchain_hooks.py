from config import *
from namedb import *
import virtualchain
import os
import sys
import config
from state_machine.operations import *
log = get_logger("virtualchain_hooks")

DISPOSITION_RO = "readonly"
DISPOSITION_RW = 'readwrite'

def get_db_state( disposition = DISPOSITION_RO ):
    impl = config.get_implementation()
    if impl is None:
        impl = sys.modules[__name__]

    db_filename = config.get_db_filename(impl=impl)
    lastblock_filename = config.get_lastblock_filename()


    firstcheck = True
    for path in [db_filename, lastblock_filename]:
        if os.path.exists(path):
            # have already create the db
            firstcheck = False
    if not firstcheck and not os.path.exists(lastblock_filename):
        log.error("FATAL: no such file or directory: %s" % lastblock_filename)

    # verify that it is well-formed if it exists
    elif os.path.exists( lastblock_filename ):
        try:
            with open(lastblock_filename, "r") as f:
                int(f.read().strip())
        except Exception, e:
            log.error("FATAL: failed to parse: %s " % lastblock_filename)
            log.exception(e)
            os.abort()

    db_inst = ZonefileManageDB(db_filename, disposition)
    return db_inst


def get_readonly_db_state(disposition = DISPOSITION_RO):
    impl = config.get_implementation()
    db_filename = config.get_db_filename(impl=impl)
    db_inst = ZonefileManageDB(db_filename, disposition)
    return db_inst

def db_parse(block_id, txid, vtxindex, op, data, senders, inputs, outputs, db_state=None):
    """
    Required by the state engine
    """

    try:
        opcode = op_get_opcode_name(op)
        assert opcode is not None, "Unrecongnized opcode '%s'" % op
    except Exception, e:
        log.exception(e)
        log.error("Skipping unreconginzed opcode")
        return None

    # Get the data
    op = None
    try:
        op = op_extract( opcode, data, senders, inputs, outputs, block_id, vtxindex, txid )
    except Exception, e:
        log.exception(e)
        op = None

    if op is not None:
        op['vtxindex'] = int(vtxindex)
        op['txid'] = str(txid)
        op['block_number'] = block_id

    else:
        log.error("Unparseable op '%s'" % opcode)

    return op


def db_commit(block_id, op, op_data, txid, vtxindex, db_state=None):
    """
    (required by virtualchain state engine)

    Advance the state of the state engine: get a list of all
    externally visible state transitions.

    Given a block ID and checked opcode, record it as
    part of the database.  This does *not* need to write
    the data to persistent storage, since save() will be
    called once per block processed.

    Returns one or more new name operations on success, which will
    be fed into virtualchain to translate into a string
    to be used to generate this block's consensus hash.
    """

    if db_state is not None:
        if op_data is not None:

            try:
                assert 'txid' in op_data, "BUG: No txid given"
                assert 'vtxindex' in op_data, "BUG: No vtxindex given"
                assert op_data['txid'] == txid, "BUG: txid mismatch"
                assert op_data['vtxindex'] == vtxindex, "BUG: vtxindex mismatch"
                # opcode = op_get_opcode_name( op_data['op'] )
                opcode = op_data.get('opcode', None)
                log.info('opcode is %s' % opcode)
                assert opcode in  OPCODE_NAME_STATE_CREATIONS + OPCODE_NAME_STATE_TRANSITIONS, "BUG: uncategorized opcode '%s'" % opcode
            except Exception, e:
                log.exception(e)
                log.error("FATAL: failed to commit operation")
                os.abort()

            op_seq = db_state.commit_operation(op_data, block_id)
            return op_seq

        else:
            # final commit for this block
            try:
                db_state.commit_finished(block_id)
            except Exception, e:
                log.exception(e)
                log.error("FATAL: failed to commit at block %s" % block_id)
                os.abort()

            return None

    else:
        log.error("FATAL: no state engine given")
        os.abort()


def db_save(block_id, consensus_hash, pending_ops, filename, db_state=None):
    """
    (required by virtualchain state engine)

    Save all persistent state to stable storage.
    Called once per block.

    Return True on success
    Return False on failure.
    """

    if db_state is not None:

        try:
            # pre-calculate the ops hash for SNV
            ops_hash = ZonefileManageDB.calculate_block_ops_hash(db_state, block_id)
            # db_state.store_block_ops_hash(block_id, ops_hash)
        except Exception, e:
            log.exception(e)
            log.error("FATAL: failed to calculate ops hash at block %s" % block_id)
            os.abort()

        try:
            # flush the database
            db_state.commit_finished(block_id)
        except Exception, e:
            log.exception(e)
            log.error("FATAL: failed to commit at block %s" % block_id)
            os.abort()


        return True

    else:
        log.error("FATAL: no state engine given")
        os.abort()


def db_continue( block_id, consensus_hash ):
    """
    (required by virtualchain state engine)

    Called when virtualchain has synchronized all state for this block.
    Blockstack uses this as a preemption point where it can safely
    exit if the user has so requested.
    """

    # every so often, clean up
    if (block_id % 20) == 0:
        log.debug("Pre-emptive garbage collection at %s" % block_id)
        gc.collect(2)

    return is_running() or os.environ.get("ZONEFILEMANAGE_TEST") == "1"


def db_check( block_id, new_ops, op, op_data, txid, vtxindex, checked_ops, db_state=None ):
    """
    Given a block id and a parsed operation, check to see if this is a valid operation
    """
    accept = True

    if db_state is not None:

        try:
            assert 'txid' in op_data, "Missing txid from op"
            assert 'vtxindex' in op_data, "Missing vtxindex from op"
            opcode = op_get_opcode_name(op)
            assert opcode is not None, "BUG: unknown op '%s'" % op
        except Exception, e:
            log.exception(e)
            log.error("FATAL: invalid operation")
            os.abort()

        log.info("CHECK %s at (%s, %s)" % (opcode, block_id, vtxindex))
        rc = op_check(db_state, op_data, block_id, checked_ops)
        if rc:

            try:
                opcode = op_data.get('opcode', None)
                assert opcode is not None, "BUG: op_check did not set an opcode"
            except Exception, e:
                log.exception(e)
                log.error("FATAL: no opcode set")
                os.abort()
        else:
            accept = False

    return accept

def check_mutate_fields( op, op_data ):
    """
    Verify that all mutate fields are present.
    """

    mutate_fields = op_get_mutate_fields( op )
    assert mutate_fields is not None, "No mutate fields defined for %s" % op

    missing = []
    for field in mutate_fields:
        if not op_data.has_key(field):
            missing.append(field)

    assert len(missing) == 0, "Missing mutation fields for %s: %s" % (op, ",".join(missing))
    return True

def get_first_block_id():
    """
    Get the id of the first block
    """
    start_block = FIRST_BLOCK_MAINNET
    return start_block
