from integration_test.testlib import *

from config import get_logger

logger = get_logger("register_update_transfer_revoke")
wallets = [
    #prvate key wif
    Wallet( "5JesPiN68qt44Hc2nT8qmyZ1JDwHebfoh9KQ52Lazb1m1LaKNj9", 100000000000 ),
    Wallet( "5KHqsiU9qa77frZb6hQy9ocV7Sus9RWJcQGYYBJJBb2Efj1o77e", 100000000000 ),
    Wallet( "5Kg5kJbQHvk1B64rJniEmgbD83FpZpbw2RjdAZEzTefs9ihN3Bz", 100000000000 ),
    Wallet( "5JuVsoS9NauksSkqEjbUZxWwgGDQbMwPsEfoRBSpLpgDX1RtLX7", 100000000000 ),
    Wallet( "5KEpiSRr1BrT8vRD7LKGCEmudokTh1iMHbiThMQpLdwBwhDJB1T", 100000000000 )
]
consensus = "17ac43c1d8549c3181b200f1bf97eb7d"

def scenario( wallets, **kw ):

    resp = zonefilemanage_name_register('foo', wallets[0].privkey)
    logger.info(resp)
    next_block(**kw)

    resp = zonefilemanage_name_update('foo', '1'*20, wallets[0].privkey)
    logger.info(resp)

    next_block(**kw)

    resp = zonefilemanage_name_transfer('foo', wallets[0].privkey, wallets[1].privkey)
    logger.info(resp)
    next_block(**kw)

    resp = zonefilemanage_name_revoke('foo', wallets[1].privkey)
    logger.info(resp)
    next_block(**kw)

    print 'scenario successfully'

def check( state_engine ):
    print 'check successfully'