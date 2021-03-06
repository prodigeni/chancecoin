#! /usr/bin/python3

"""Burn BTC to earn CHA during a special period of time."""

import struct
import decimal
D = decimal.Decimal

from . import (util, config, exceptions, bitcoin, util)

ID = 60


def validate (db, source, destination, quantity, block_index=None):
    problems = []

    # Check destination address.
    if destination != config.UNSPENDABLE:
        problems.append('wrong destination address')

    # Try to make sure that the burned funds won't go to waste.
    if config.PREFIX != config.UNITTEST_PREFIX:    # For test suite.
        if not block_index: block_index = util.last_block(db)['block_index']
        if block_index < config.BURN_START:
            problems.append('too early')
        elif block_index > config.BURN_END:
            problems.append('too late')

    return problems

def create (db, source, quantity, unsigned=False):
    destination = config.UNSPENDABLE
    problems = validate(db, source, destination, quantity, None)
    if problems: raise exceptions.BurnError(problems)

    burns = util.get_burns(db, validity='valid')
    already_burned = sum([burn['burned'] for burn in burns])
    if quantity > (config.MAX_BURN * config.UNIT - already_burned):
        raise exceptions.BurnError('Too many coins have already been burned.')
    return bitcoin.transaction(source, destination, quantity, config.MIN_FEE, None, unsigned=unsigned)

def parse (db, tx, message=None):
    burn_parse_cursor = db.cursor()
    validity = 'valid'

    if validity == 'valid':
        problems = validate(db, tx['source'], tx['destination'], tx['btc_amount'], tx['block_index'])
        if problems: validity = 'invalid: ' + ';'.join(problems)

        if tx['btc_amount'] != None:
            sent = tx['btc_amount']
        else:
            sent = 0

    if validity == 'valid':
        # Calculate quantity of XPC earned. (Maximum 1 BTC in total, ever.)
        burns = util.get_burns(db, validity='valid')
        already_burned = sum([burn['earned'] for burn in burns])
        max_burn = config.MAX_BURN*config.UNIT - already_burned
        if sent > max_burn: burned = max_burn   # Exceeded maximum burn; earn what you can.
        else: burned = sent

        total_time = D(config.BURN_END - config.BURN_START)
        partial_time = D(config.BURN_END - tx['block_index'])
        multiplier = config.MULTIPLIER + ((partial_time / total_time)*(config.MULTIPLIER_INITIAL-config.MULTIPLIER))
        earned = round(burned * multiplier)

        # For test suite.
        if config.PREFIX == config.UNITTEST_PREFIX:
            earned = 1500 * burned

        # Credit source address with earned CHA.
        util.credit(db, tx['block_index'], tx['source'], 'CHA', earned, event=tx['tx_hash'])
    else:
        burned = 0
        earned = 0

    # Add parsed transaction to message-type–specific table.
    # TODO: store sent in table
    bindings = {
        'tx_index': tx['tx_index'],
        'tx_hash': tx['tx_hash'],
        'block_index': tx['block_index'],
        'source': tx['source'],
        'burned': burned,
        'earned': earned,
        'validity': validity,
    }
    sql='insert into burns values(:tx_index, :tx_hash, :block_index, :source, :burned, :earned, :validity)'
    burn_parse_cursor.execute(sql, bindings)


    burn_parse_cursor.close()

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
