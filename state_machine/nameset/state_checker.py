from config import get_logger
import sys
log = get_logger("state_checker")

def state_check_collisions(state_engine, nameop, history_id_key, block_id, checked_ops, collision_checker):
    # verify no collisions against already-accepted names
    collision_check = getattr(state_engine, collision_checker, None)
    try:
        assert collision_check is not None, "Collision-checker '%s' not defined" % collision_checker
        assert hasattr(collision_check, "__call__"), "Collision-checker '%s' is not callable" % collision_checker
        assert history_id_key in nameop.keys(), "History ID key '%s' not in name operation" % (history_id_key)
        assert 'op' in nameop.keys(), "BUG: no op in nameop"
    except Exception, e:
        log.exception(e)
        log.error("FATAL: incorrect state_create() decorator")
        sys.exit(1)

    rc = collision_check(nameop[history_id_key], block_id, checked_ops)
    return rc

# # sanity check decorator for state-creating operations
def state_create(history_id_key, table_name, collision_checker):
    # handle function
    def wrap(check):
        # handle decorator args
        def wrapped_check(state_engine, nameop, block_id, checked_ops):
            rc = check(state_engine, nameop, block_id, checked_ops)
            nameop['__table__'] = table_name
            nameop['__state_create__'] = True
            return rc
        return wrapped_check
    return wrap


def state_transition(history_id_key, table_name, collision_checker):
    # Handle function
    def wrap(check):
        def wrapped_check(state_engine, nameop, block_id, checked_ops):
            rc = check(state_engine, nameop, block_id, checked_ops)
            nameop['__table__'] = table_name
            nameop['__state_transition__'] = True
            return rc
        return wrapped_check
    return wrap

def state_create_get_table(nameop):
    """
    Get the table of a state-creating operation
    """
    return nameop['__table__']

def state_create_invariant_tags():
    """
    Get a list of state-create invariant tags.
    """
    return [
        '__table__',
        '__state_create__'
    ]
def state_transition_invariant_tags():
    """
    Get a list of state-create invariant tags.
    """
    return [
        '__table__',
        '__state_transition__',
        'sender',
        'sender_address'
    ]

def get_state_invariant_tags():
    """
    Get the set of state invariant tags for a given opcode
    """
    return list(set( state_create_invariant_tags() + state_transition_invariant_tags() ))