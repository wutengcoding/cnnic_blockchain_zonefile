import json
import random
import sqlite3
import os
import traceback

import copy

from config import *
import time
log = get_logger("db")


ZONEFILEMANAGE_DB_SCRIPT = ""
ZONEFILEMANAGE_DB_SCRIPT += """
CREATE TABLE name_records( name STRING NOT NULL,
                           value_hash TEXT,
                           recipient_address TEXT NOT NULL,
                           recipient TEXT,
                           block_number INT NOT NULL,
                           first_registered INT NOT NULL,
                           last_renewed INT NOT NULL,
                           op TEXT NOT NULL,
                           txid TEXT NOT NULL,
                           vtxindex INT NOT NULL,
                           consensus TEXT,
                           revoked INT,
                           PRIMARY KEY(name, block_number)
                           );

"""
ZONEFILEMANAGE_DB_SCRIPT += """
CREATE TABLE ops_hashed( block_id INTEGER PRIMARY KEY NOT NULL,
                         ops_hash STRING NOT NULL);
"""

ZONEFILEMANAGE_DB_SCRIPT += """
CREATE INDEX value_hash_names_index on name_records( value_hash, name );
"""
def namedb_open( path ):
    """
    Open a connection to the database
    """
    conn = sqlite3.connect( path, isolation_level=None, timeout=2**30 )
    conn.row_factory = namedb_row_factory

    return conn

def namedb_create( path ):
    """
    Create a sqlite3 db at the given path
    Create all tables and indexes we need
    """
    global ZONEFILEMANAGE_DB_SCRIPT

    if os.path.exists(path):
        raise Exception("Database '%s' already exists" % path)

    lines = [ l + ";" for l in ZONEFILEMANAGE_DB_SCRIPT.split(";")]
    conn = sqlite3.connect( path, isolation_level=None, timeout=2**30)

    for line in lines:
        conn.execute(line)

    conn.row_factory = namedb_row_factory
    return conn

def namedb_row_factory(cursor, row):
    """
    Row factor to enforce some additional types:
    * force 'revoked' to be a bool
    """
    d = {}
    for idx, col in enumerate(cursor.description):
        if col[0] == 'revoked':
            if row[idx] == 0:
                d[col[0]] = False
            elif row[idx] == 1:
                d[col[0]] = True
            elif row[idx] is None:
                d[col[0]] = None
            else:
                raise Exception("Invalid value for 'revoked': %s" % row[idx])

        else:
            d[col[0]] = row[idx]

    return d


def namedb_query_execute(cur, query, values):
    """
    Execute a query.  If it fails, exit.

    DO NOT CALL THIS DIRECTLY.
    """

    timeout = 1.0
    while True:
        try:
            ret = cur.execute(query, values)
            return ret
        except sqlite3.OperationalError as oe:
            if oe.message == "database is locked":
                timeout = timeout * 2 + timeout * random.random()
                log.error(
                    "Query timed out due to lock; retrying in %s: %s" % (timeout, namedb_format_query(query, values)))
                time.sleep(timeout)

            else:
                log.exception(oe)
                log.error("FATAL: failed to execute query (%s, %s)" % (query, values))
                log.error("\n".join(traceback.format_stack()))
                os.abort()

        except Exception, e:
            log.exception(e)
            log.error("FATAL: failed to execute query (%s, %s)" % (query, values))
            log.error("\n".join(traceback.format_stack()))
            os.abort()

def namedb_format_query( query, values ):
    """
    Turn a query into a string for printing.
    Useful for debugging.
    """

    return "".join( ["%s %s" % (frag, "'%s'" % val if type(val) in [str, unicode] else val) for (frag, val) in zip(query.split("?"), values + ("",))] )



def namedb_get_name(cur, name, current_block, included_expired=False, include_history=False):
    select_query = "SELECT * FROM name_records WHERE NAME = ? and REVOKED = ?;"
    args = (name, 0)
    name_rows = namedb_query_execute(cur, select_query, args)
    name_row = name_rows.fetchone()

    if name_row is None:
        return None
    log.info("already has name_rows %s" % json.dumps(name_row))
    name_rec = {}
    name_rec.update(name_row)
    return name_rec


def namedb_state_transition(cur, opcode, new_record, block_id, vtxindex, txid, record_table):
    if opcode in OPCODE_NAME_STATE_TRANSITIONS:
        rc = namedb_name_update(cur, new_record)
    return True

def namedb_state_create(cur, opcode, new_record, block_id, vtxindex, txid, record_table):
    if opcode in OPCODE_NAME_STATE_CREATIONS:
        rc = namedb_name_insert(cur, new_record)
    return True

def namedb_name_update(cur, record):
    query, values = namedb_update_prepare(cur, record, "name_records")
    namedb_query_execute(cur, query, values)
    return True

def namedb_name_insert(cur, input_name_rec):
    name_rec = copy.deepcopy(input_name_rec)
    try:
        query, values = namedb_insert_prepare(cur, name_rec, "name_records")
    except Exception, e:
        log.exception(e)
        log.error("FATAL: Failed to insert name '%s'" % name_rec['name'])
        os.abort()

    namedb_query_execute(cur, query, values)
    return True
def namedb_update_prepare(cur, record, table_name):
    copyed_record = deepcopy(record)
    update_columns = copyed_record.keys()

    to_remove_records = ['name', 'first_registered']
    for r in to_remove_records:
        if r in update_columns:
            update_columns.remove(r)

    update_values = []
    for c in update_columns:
        if record[c] == False:
            update_values.append(0)
        elif record[c] == True:
            update_values.append(1)
        else:
            update_values.append(record[c])

    update_values = tuple(update_values)
    update_set = [("%s = ?" % c) for c in update_columns]

    where_values = (record['name'],)

    query = "UPDATE %s SET %s WHERE name = ?" % (table_name, ", ".join(update_set))

    log.debug(namedb_format_query(query, update_values))

    return (query, update_values + where_values)


def namedb_insert_prepare(cur, record, table_name):

    # namedb_assert_fields_match(cur, record, table_name)

    columns = record.keys()
    columns.sort()

    values = []
    for c in columns:
        if record[c] == False:
            values.append(0)
        elif record[c] == True:
            values.append(1)
        else:
            values.append(record[c])

    values = tuple(values)

    field_placeholders = ",".join(["?"] * len(columns))

    query = "INSERT INTO %s(%s) VALUES (%s);" % (table_name, ",".join(columns), field_placeholders)
    log.debug(namedb_format_query(query, values))

    return (query, values)


def namedb_assert_fields_match(cur, record, table_name, record_matches_columns=True, columns_match_record=True):
    """
    Ensure that the fields of a given record match
    the columns of the given table.
    * if record_match_columns, then the keys in record must match all columns.
    * if columns_match_record, then the columns must match the keys in the record.

    Return True if so.
    Raise an exception if not.
    """

    rec_missing = []
    rec_extra = []

    # sanity check: all fields must be defined
    # name_fields_rows = cur.execute("PRAGMA table_info(%s);" % table_name)
    name_fields_rows = cur.execute("PRAGMA table_info(name_records)")
    for name in name_fields_rows.fetchall():
        print name
    name_fields = []
    for row in name_fields_rows:
        name_fields.append(row[1])

    if columns_match_record:
        # make sure each column has a record field
        for f in name_fields:
            if f not in record.keys():
                rec_missing.append(f)

    if record_matches_columns:
        # make sure each record field has a column
        for k in record.keys():
            if k not in name_fields:
                rec_extra.append(k)

    if len(rec_missing) != 0 or len(rec_extra) != 0:
        raise Exception("Invalid record: missing = %s, extra = %s" %
                        (",".join(rec_missing), ",".join(rec_extra)))

    return True