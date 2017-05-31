from virtualchain_hooks import *
from indexer import *
from namedb import *
from db import *


NUMEREC_FIELDS = [
    'name',
    'value_hash',   # the hash of the name's associated profile
    'sender',   # the scriptPubkey hex that owns this name
    'sender_pubkey',    # the public key of the sender
    'address',  # the address of the sender
    'block_number',
    'first_registered',
    'last_renewed',
    'revoked',
    'op',
    'txid',
    'vtxindex'
]



