import asyncio
import psycopg2
import os
import time
from datetime import datetime, timedelta
from db_handler import DatabaseHandler
from exchanges.exchange import Exchange
from tables import metadata
from utilities import read_config, yaml_loader, get_exchange_names, REQUEST_PARAMS


async def main(all_exchanges, database_handler):
    """
    The main() function to run the program. Loads the database, including the database_handler.
    The exchange_names are extracted with a helper method in utilities based on existing yaml-files.
    In an asynchronous manner it is iterated over the exchanges and and the responses are awaited and collected
        by await asyncio.gather(..)
    As soon as all responses from the exchanges are returned, the values get extracted, formatted into tuples
        by the exchange.get_ticker(..) method and persisted by the into the database by the database_handler.
    :param database_handler DatabaseHandler
    :param exchanges dict
        The dictionary of all given exchanges.
    """
    # start_time : datetime when request run is started
    # delta : given microseconds for the datetime
    start_time = datetime.utcnow()
    delta = start_time.microsecond
    # rounding the given datetime on seconds
    start_time = start_time - timedelta(microseconds=delta)
    if delta >= 500000:
        start_time = start_time + timedelta(seconds=1)

    primary_exchanges = {}
    secondary_exchanges = {}
    for exchange in all_exchanges:
        if exchanges[exchange].active_flag:
            primary_exchanges[exchanges[exchange].name] = exchanges[exchange]
        else:
            secondary_exchanges[exchanges[exchange].name] = exchanges[exchange]
    # todo: exception handling, falls keine exchange abgefragt wird ( primary_exchanges leer ist )

    responses = await asyncio.gather(*(primary_exchanges[ex].request('ticker', start_time) for ex in primary_exchanges))
    for response in responses:
        if response:
            print('Response: {}'.format(response))
            exchange = primary_exchanges[response[0]]
            formatted_response = exchange.format_ticker(response)
            database_handler.persist_tickers(formatted_response)

    # todo: ping test for exchanges in secondary list, possible changing of the active flag back to active at successful
    #  ping test, secondary execution right for tasks for the secondary list

    # variables of flag will be updated
    for exchange in primary_exchanges:
        primary_exchanges[exchange].update_exception_counter()
    # variables in database will be updated because of information purpose
    database_handler.update_exchanges(primary_exchanges)
    # variables of exception counter will be updated
    for exchange in primary_exchanges:
        primary_exchanges[exchange].update_consecutive_exception()


if __name__ == "__main__":
    try:
        db_params = read_config('database')
        databaseHandler = DatabaseHandler(metadata, **db_params)
        # run program with single exchange or selected list of exchanges for debugging/testing purposes
        # exchange_names = ['coinsbit', 'bibox']
        exchange_names = get_exchange_names()
        exchanges = {exchange_name: Exchange(yaml_loader(exchange_name), databaseHandler.request_params)
                     for exchange_name in exchange_names}
        while True:
            asyncio.run(main(exchanges, databaseHandler))
            print("5 Minuten Pause.")
            time.sleep(300)
    except Exception as e:
        print(e, e.__cause__)
        pass
