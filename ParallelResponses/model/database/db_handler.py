from datetime import datetime
from typing import List, Tuple, Iterator, Iterable, Dict
from contextlib import contextmanager

import psycopg2
import sqlalchemy
from sqlalchemy import create_engine, MetaData
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy_utils import database_exists, create_database

from model.database.tables import Currency, Exchange, ExchangeCurrencyPair, Ticker, HistoricRate, \
    ExchangeCurrencyPairView


class DatabaseHandler:
    """
    Class which handles every interaction with the database.
    This includes most of the time checking if values exist in
    the database or storing/querying values.

    For querying and storing values the library sqlalchemy is used.

    Attributes:
        sessionFactory: sessionmaker
           Factory for connections to the database.
    """
    sessionFactory: sessionmaker

    def __init__(self,
                 metadata: MetaData,
                 sqltype: str,
                 client: str,
                 user_name: str,
                 password: str,
                 host: str,
                 port: str,
                 db_name: str):
        """
        Initializes the database-handler.

        Builds the connection-string and tries to connect to the database.

        Creates with the given metadata tables which do not already exist.
        Won't make a new table if the name already exists,
        so changes to the table-structure have to be made by hand in the database
        or the table has to be deleted.

        Initializes the sessionFactory with the created engine.
        Engine variable is no attribute and currently only exists in the constructor.

        :param metadata: Metadata
            Information about the table-structure of the database.
            See tables.py for more information.
        :param sqltype: atr
            Type of the database sql-dialect. ('postgresql' for us)
        :param client: str
            Name of the Client which is used to connect to the database.
        :param user_name: str
            Username under which this program connects to the database.
        :param password: str
            Password for this username.
        :param host: str
            Hostname or Hostaddress from the database.
        :param port: str
            Connection-Port (usually 5432 for Postgres)
        :param db_name: str
            Name of the database.
        """

        conn_string = '{}+{}://{}:{}@{}:{}/{}'.format(sqltype, client, user_name, password, host, port, db_name)
        print(conn_string)
        engine = create_engine(conn_string)

        if not database_exists(engine.url):
            create_database(engine.url)
            print(f"Database '{db_name}' created")

        try: #this is done since one cant test if view-table exists already. if it does an error occurs
            metadata.create_all(engine)
        except ProgrammingError:
            print('View already exists.')
            pass
        self.sessionFactory = sessionmaker(bind=engine)

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.sessionFactory()
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()

    def persist_tickers(self,
                        queried_currency_pairs: List[ExchangeCurrencyPair],
                        tickers: Iterator[Tuple[str, datetime, datetime, str, str, float, float, float, float]]):
        """
        Persists the given tuples of ticker-data.
        TUPLES MUST HAVE THE DESCRIBED STRUCTURE STATED BELOW

        The method checks for each tuple if the referenced exchange and
        currencies exist in the database.
        If so, the Method creates with the stored data of the current tuple
        a new Ticker-object which is then added to the commit.
        After all tuples where checked, the added Ticker-objects will be
        committed and the connection will be closed.

        Exceptions will be caught but not really handled.
        TODO: Exception handling and
        TODO: Logging of Exception

        :param tickers: Iterator
            Iterator of tuples containing ticker-data.
            Tuple must have the following structure:
                (exchange-name,
                 start_time,
                 response_time,
                 first_currency_symbol,
                 second_currency_symbol,
                 ticker_last_price,
                 ticker_best_ask,
                 ticker_best_bid,
                 ticker_daily_volume)
        """
        with self.session_scope() as session:
            tuple_counter: int = 0
            for ticker in tickers:
                exchange_currency_pair: ExchangeCurrencyPair = self.get_exchange_currency_pair(session, ticker[0], ticker[3], ticker[4])
                if exchange_currency_pair is not None:
                    if any(exchange_currency_pair.id == q_cp.id for q_cp in queried_currency_pairs):
                        ticker_tuple = Ticker(exchange_pair_id=exchange_currency_pair.id,
                                              exchange_pair=exchange_currency_pair,
                                              start_time=ticker[1],
                                              response_time=ticker[2],
                                              last_price=ticker[5],
                                              best_ask=ticker[6],
                                              best_bid=ticker[7],
                                              daily_volume=ticker[8])
                        tuple_counter = tuple_counter + 1
                        session.add(ticker_tuple)
                    # session.add(ticker_tuple)
            print('{} ticker added for {}'.format(tuple_counter, ticker[0]))

    def get_active_exchanges(self):
        """
        Query every inactive exchange from the database
        :return: list of all inactive exchange
        """

        session = self.sessionFactory()
        query = set(session.query(Exchange.name).filter(Exchange.active == False).all())
        session.close()
        return query

    def get_all_currency_pairs_from_exchange(self, exchange_name: str) -> List[ExchangeCurrencyPair]:
        """
        @param exchange_name:
            Name of the exchange that the currency-pairs should be queried for.
        @return:
            List of all currency-pairs for the given exchange.
        """
        # todo : session factory -> session scope
        session = self.sessionFactory()
        currency_pairs = list()
        exchange_id = session.query(Exchange.id).filter(Exchange.name.__eq__(exchange_name.upper())).first()
        if exchange_id is not None:
            currency_pairs = session.query(ExchangeCurrencyPair).filter(
                ExchangeCurrencyPair.exchange_id.__eq__(exchange_id)).all()
        session.close()
        return currency_pairs

    def get_currency_pairs_with_first_currency(self, exchange_name: str, currency_names: str) -> List[
        ExchangeCurrencyPair]:
        # todo: doku
        all_found_currency_pairs: List[ExchangeCurrencyPair] = list()
        if exchange_name is not None and exchange_name:
            exchange_id: int = self.get_exchange_id(exchange_name)

            with self.session_scope() as session:
                if currency_names is not None:
                    for currency_name in currency_names:
                        if currency_name is not None and currency_name:
                            first_id: int = self.get_currency_id(currency_name)

                            found_currency_pairs = session.query(ExchangeCurrencyPair).filter(
                                ExchangeCurrencyPair.exchange_id.__eq__(exchange_id),
                                ExchangeCurrencyPair.first_id.__eq__(first_id)).all()

                            if found_currency_pairs is not None:
                                all_found_currency_pairs.extend(found_currency_pairs)
                session.expunge_all()
        return all_found_currency_pairs

    def get_currency_pairs_with_second_currency(self, exchange_name: str, currency_names: str) \
            -> List[ExchangeCurrencyPair]:
        # todo: doku
        all_found_currency_pairs: List[ExchangeCurrencyPair] = list()
        if exchange_name:
            exchange_id: int = self.get_exchange_id(exchange_name)

            with self.session_scope() as session:
                if currency_names is not None:
                    for currency_name in currency_names:
                        if currency_name:
                            second_id: int = self.get_currency_id(currency_name)

                            found_currency_pairs = session.query(ExchangeCurrencyPair).filter(
                                ExchangeCurrencyPair.exchange_id.__eq__(exchange_id),
                                ExchangeCurrencyPair.second_id.__eq__(second_id)).all()

                            if found_currency_pairs is not None:
                                all_found_currency_pairs.extend(found_currency_pairs)

                session.expunge_all()
        return all_found_currency_pairs

    def get_currency_pairs(self, exchange_name: str, currency_pairs: List[Dict[str, str]]) \
            -> List[ExchangeCurrencyPair]:
        found_currency_pairs: List[ExchangeCurrencyPair] = list()

        if exchange_name:
            exchange_id: int = self.get_exchange_id(exchange_name)
            with self.session_scope() as session:
                if currency_pairs is not None:
                    for currency_pair in currency_pairs:
                        first_currency = currency_pair['first'][0]
                        second_currency = currency_pair['second'][0]
                        if first_currency and second_currency:
                            first_id: int = self.get_currency_id(first_currency)
                            second_id: int = self.get_currency_id(second_currency)

                            found_currency_pair = session.query(ExchangeCurrencyPair).filter(
                                ExchangeCurrencyPair.exchange_id.__eq__(exchange_id),
                                ExchangeCurrencyPair.first_id.__eq__(first_id),
                                ExchangeCurrencyPair.second_id.__eq__(second_id)).first()

                            if found_currency_pair is not None:
                                found_currency_pairs.append(found_currency_pair)
                    session.expunge_all()

        return found_currency_pairs

    def collect_exchanges_currency_pairs(self, exchange_name: str, currency_pairs: [Dict[str, str]], first_currencies: [str], second_currencies: [str]) -> [ExchangeCurrencyPair]:
        found_currency_pairs: List[ExchangeCurrencyPair] = list()
        if 'all' in currency_pairs:
            found_currency_pairs.extend(self.get_all_currency_pairs_from_exchange(exchange_name))
        elif currency_pairs[0] is not None:
            found_currency_pairs.extend(self.get_currency_pairs(exchange_name, currency_pairs))
        found_currency_pairs.extend(self.get_currency_pairs_with_first_currency(exchange_name, first_currencies))
        found_currency_pairs.extend(self.get_currency_pairs_with_second_currency(exchange_name, second_currencies))
        result: List = list()


        for pair in found_currency_pairs:
            if not any(pair.id == result_pair.id for result_pair in result):
                result.append(pair)
        return result

    def get_exchange_id(self, exchange_name: str) -> int:
        with self.session_scope() as session:
            return session.query(Exchange.id).filter(Exchange.name.__eq__(exchange_name.upper())).first()

    def get_currency_id(self, currency_name: str):
        with self.session_scope() as session:
            return session.query(Currency.id).filter(Currency.name.__eq__(currency_name.upper())).first()

    def persist_exchange(self, exchange_name: str):
        """
        Persists the given exchange-name if it's not already in the database.

        @param exchange_name:
            Name that should is to persist.
        """
        session = self.sessionFactory()
        exchange_id = session.query(Exchange.id).filter(Exchange.name.__eq__(exchange_name.upper())).first()
        if exchange_id is None:
            exchange = Exchange(name=exchange_name)
            session.add(exchange)
            session.commit()
        session.close()

    def persist_exchange_currency_pairs(self, currency_pairs: Iterable[Tuple[str, str, str]]):
        """
        Persists the given already formatted ExchangeCurrencyPair-tuple if they not already exist.
        The formatting ist done in @see{Exchange.format_currency_pairs()}.

        Tuple needs to have the following structure:
            (exchange-name, first currency-name, second currency-name)

        @param currency_pairs:
            Iterator of currency-pair tuple that are to persist.
        """
        if currency_pairs is not None:
            session = self.sessionFactory()
            ex_currency_pairs: List[ExchangeCurrencyPair] = list()

            try:
                for cp in currency_pairs:
                    exchange_name = cp[0]
                    first_currency_name = cp[1]
                    second_currency_name = cp[2]

                    if exchange_name is None or first_currency_name is None or second_currency_name is None:
                        continue

                    existing_exchange = session.query(Exchange).filter(Exchange.name == exchange_name.upper()).first()
                    exchange: Exchange = existing_exchange if existing_exchange is not None else Exchange(
                        name=exchange_name)

                    existing_first_cp = session.query(Currency).filter(
                        Currency.name == first_currency_name.upper()).first()
                    first: Currency = existing_first_cp if existing_first_cp is not None else Currency(
                        name=first_currency_name)

                    existing_second_cp = session.query(Currency).filter(
                        Currency.name == second_currency_name.upper()).first()
                    second: Currency = existing_second_cp if existing_second_cp is not None else Currency(
                        name=second_currency_name)

                    existing_exchange_pair = session.query(ExchangeCurrencyPair).filter(
                        ExchangeCurrencyPair.exchange_id == exchange.id,
                        ExchangeCurrencyPair.first_id == first.id,
                        ExchangeCurrencyPair.second_id == second.id).first()

                    if existing_exchange_pair is None:
                        exchange_pair = ExchangeCurrencyPair(exchange=exchange, first=first, second=second)
                        ex_currency_pairs.append(exchange_pair)
                        session.add(exchange_pair)

                session.commit()
                # TODO: Reactivate
                # print('{} Currency Pairs für {} hinzugefügt'.format(ex_currency_pairs.__len__(), exchange_name))
            except Exception as e:
                print(e, e.__cause__)
                session.rollback()
                pass
            finally:
                session.close()

    def persist_exchange_currency_pair(self, exchange_name: str, first_currency_name: str,
                                       second_currency_name: str) -> ExchangeCurrencyPair:
        """
        Adds a single ExchangeCurrencyPair to the database is it does not already exist.

        @param exchange_name:
            Name of the exchange.
        @param first_currency_name:
            Name of the first currency.
        @param second_currency_name:
            Name of the second currency.
        """
        self.persist_exchange_currency_pairs([(exchange_name, first_currency_name, second_currency_name)])

    def get_exchange_currency_pair(self, session: Session, exchange_name: str, first_currency_name: str,
                                   second_currency_name: str):
        # todo: doku
        # todo: sollte so nicht final sein

        if exchange_name is None or first_currency_name is None or second_currency_name is None:
            return None
        # sollte raus in der actual Implementierung
        self.persist_exchange_currency_pair(exchange_name, first_currency_name, second_currency_name)
        ex = session.query(Exchange).filter(Exchange.name == exchange_name.upper()).first()
        first = session.query(Currency).filter(Currency.name == first_currency_name.upper()).first()
        second = session.query(Currency).filter(Currency.name == second_currency_name.upper()).first()

        cp = session.query(ExchangeCurrencyPair).filter(ExchangeCurrencyPair.exchange.__eq__(ex),
                                                        ExchangeCurrencyPair.first.__eq__(first),
                                                        ExchangeCurrencyPair.second.__eq__(second)).first()
        return cp

    def persist_historic_rates(self, historic_rates: Iterable[Tuple[int, datetime, float, float, float, float, float]]):
        """
        Persists the given already formatted historic-rates-tuple if they not already exist.
        The formatting ist done in @see{Exchange.format_historic_rates()}.

        @param historic_rates:
            Iterator containing the already formatted historic-rates-tuple.
        """
        try:
            i = 0
            for historic_rate in historic_rates:
                with self.session_scope() as session:
                    tuple_exists = session.query(HistoricRate.exchange_pair_id). \
                        filter(
                        HistoricRate.exchange_pair_id == historic_rate[0],
                        HistoricRate.timestamp == historic_rate[1]
                    ). \
                        first()
                    if tuple_exists is None:
                        i += 1
                        hr_tuple = HistoricRate(exchange_pair_id=historic_rate[0],
                                                timestamp=historic_rate[1],
                                                open=historic_rate[2],
                                                high=historic_rate[3],
                                                low=historic_rate[4],
                                                close=historic_rate[5],
                                                volume=historic_rate[6])
                        session.add(hr_tuple)
                session.commit()
                print('{} tupel eingefügt in historic rates.'.format(i))
        except Exception as e:
            print(e, e.__cause__)
            session.rollback()
            pass
        finally:
            session.close()

    def get_readable_tickers(self):
        with self.session_scope() as session:
            data = session.query(
                ExchangeCurrencyPairView.exchange_name,
                ExchangeCurrencyPairView.first_name,
                ExchangeCurrencyPairView.second_name)
            print(data)

