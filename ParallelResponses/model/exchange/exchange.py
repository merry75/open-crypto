import itertools
import time
import logging
import traceback
from datetime import datetime
from typing import Iterator, Dict, List, Tuple, Optional
import aiohttp
from aiohttp import ClientConnectionError
from model.exchange.Mapping import Mapping
from model.database.tables import ExchangeCurrencyPair
from model.utilities.utilities import TYPE_CONVERSION
from model.database.db_handler import DatabaseHandler


class Exchange:
    """
    Attributes:
        Embodies the characteristics of a crypto-currency-exchange.
        Each exchange is an Exchange-object.
        Each 'job' is in the end a method called on every exchange.

        The Attributes and mappings are all extracted from the
        .yaml-files whose location is described in the trades.yaml file.

        name: str
            Name of this exchange.
        terms_url: str
            Url to Terms&Conditions of this exchange.
        scrape_permission: bool
            Permission if scraping data from this exchange is permitted.
        api_url: str
            Url for the public_api of this exchange.
        request_urls: dict[request_name: List[url, params]
            Dictionary which contains for each request(key)
            the given url and necessary parameters.
            (See .yaml and def extract_request_urls() for more info)
        response_mappings: dict
            Dictionary which contains for each request(key)
            the necessary mapping-objects for extracting the value.
            (See .yaml and def extract_mappings() for more info)
        exception_counter: int
            Integer which counts the exceptions thrown by this exchange.
        consecutive_exception: bool
            Boolean which represents if the exceptions has been thrown consecutive.
        active_flag: bool
            Boolean which represents if this exchange is active or passive. If an exchange will throw three exception
            consecutive, it will be set to passive and will no longer be requested.
    """
    name: str
    terms_url: str
    is_exchange: bool
    scrape_permission: bool
    api_url: str
    rate_limit: float
    request_urls: dict
    response_mappings: dict
    exception_counter: int
    consecutive_exception: bool
    active_flag: bool
    exchange_currency_pairs: List[ExchangeCurrencyPair]

    def __init__(self, yaml_file: Dict):
        """
        Creates a new Exchange-object.

        Checks the content of the .yaml if it contains certain keys.
        If searched keys exist, the constructor sets the values for the described attributes.
        The constructor also calls extract_request_urls() and extract_mappings()
        to create request_urls and the necessary Mapping-Objects.

        :param yaml_file: Dict
            Content of a .yaml file as a dict-object.
            Constructor does not check if content is viable.

        :param database_handler_request_params: Function
            DatabaseHandler-Function from the model() database_handler instance.
            This is necessary to perform function calls from the request parameters which include
            database queries. Database connections should only take place from DatabaseHandler instances.
        """
        self.name = yaml_file['name']
        if yaml_file.get('terms'):
            if yaml_file['terms'].get('terms_url'):
                self.terms_url = yaml_file['terms']['terms_url']
            if yaml_file['terms'].get('permission'):
                self.scrape_permission = yaml_file['terms']['permission']

        self.api_url = yaml_file['api_url']
        if yaml_file.get('rate_limit') and yaml_file.get('units') and yaml_file.get('max'):
            if yaml_file['rate_limit']['max'] <= 0:
                self.rate_limit = 0
            else:
                self.rate_limit = yaml_file['rate_limit']['units'] / yaml_file['rate_limit']['max']
        else:
            self.rate_limit = 0
        self.response_mappings = self.extract_mappings(
            yaml_file['requests'])  # Dict in dem für jede Request eine Liste von Mappings ist
        self.request_urls = self.extract_request_urls(yaml_file['requests'])
        self.exception_counter = 0
        self.active_flag = True
        self.consecutive_exception = False
        self.is_exchange = yaml_file.get('exchange')
        self.exchange_currency_pairs = list()

    def add_exchange_currency_pairs(self, currency_pairs: list):
        """
        Method that adds the given currency-pairs to exchange-currency-pairs.
        TODO: check if contains is enough to prevent duplicates of pairs
        @param currency_pairs:
            Pairs that should be added to exchange_currency_pairs.
        """
        for cp in currency_pairs:
            if not self.exchange_currency_pairs.__contains__(cp):
                self.exchange_currency_pairs.append(cp)

    async def test_connection(self) -> Tuple[str, bool, Dict]:
        """
        This method sends either a connectivity test ( like a ping call or a call which sends the exchange server time )
        or, if no calls like this are available or exist in the public web api, a ticker request will be send.
        Exceptions will be caught and in this case the connectivity test failed.

        The Method is asynchronous so that after the request is send, the program does not wait
        until the response arrives. For asynchrony we use the library asyncio.
        For sending and dealing with requests/responses the library aiohttp is used.

        The methods gets the requests matching url out of request_urls.
        If it does not exist None will be returned. Otherwise it sends and awaits the response(.json).

        :return: (str, bool)
            Tuple of the following structure:
                (exchange_name, response)
                response represents the result of the connectivity test
        :exceptions ClientConnectionError: the connection to the exchange timed out or the exchange did not answered
                    Exception: the given response of an exchange could not be evaluated
        """
        if self.request_urls.get('test_connection'):
            async with aiohttp.ClientSession() as session:
                request_url_and_params = self.request_urls['test_connection']
                try:
                    response = await session.get(request_url_and_params[0], params=request_url_and_params[1])
                    response_json = await response.json(content_type=None)
                    # print('{} bekommen:'.format(request_url_and_params[0]) + '{} .'.format(response_json))
                    return self.name, True, response_json
                except ClientConnectionError:
                    return self.name, False, {}
                except Exception as ex:
                    return self.name, False, {}

    async def request(self,
                      request_name: str,
                      currency_pairs: List[ExchangeCurrencyPair]) -> \
            Tuple[datetime, str, Tuple[Optional[ExchangeCurrencyPair]]]:

        """
        Method tries to request data for all given methods and currency pairs.
        Depending on if data can be received for all available currency pairs with one request
        the methods sends a request for each currency pair or just one request for all the data.

        The Method is asynchronous so that after the request is send, the program does not wait
        until the response arrives. For asynchronicity we use the library asyncio.
        For sending and dealing with requests/responses the library aiohttp is used.

        The methods gets the requests matching url out of request_urls.
        Parameters are passed in a dictionary.
        If it does not exist None will be returned. Otherwise it sends and awaits the response(.json)
        and tries afterwards to parse the json to a dictionary.
        The parsed json is then returned with the name of this exchange, so
        the response is assignable to this exchange and the time when the response arrived.

        Exceptions will be caught and a suitable message is printed.
        None will be returned in this case.

        TODO: Gutes differenziertes Exception handling
        TODO: Logging von Exceptions / option in config
        TODO: Saving responses / option in config

        @param request_name: str
            Name of the request. i.e. 'ticker' for ticker-request
        @param currency_pairs:
            List of currency pairs that should be requested.

        @return: (str, datetime, datetime, .json)
            Tuple of the following structure:
                (exchange_name, start time, response time, response)
                - time of arrival is a datetime-object in utc
        @exceptions ClientConnectionError: the connection to the exchange timed out or the exchange did not answered
                    Exception: the given response of an exchange could not be evaluated
        """
        if request_name in self.request_urls.keys() and self.request_urls[request_name]:
            async with aiohttp.ClientSession() as session:
                request_url_and_params = self.request_urls[request_name]
                responses = dict()
                params = request_url_and_params['params']
                pair_template_dict = request_url_and_params['pair_template']
                # when there is no pair formatting section then all ticker data can be accessed with one request
                pair_formatting_needed = pair_template_dict
                for cp in currency_pairs:
                    url: str = request_url_and_params['url']
                    if pair_formatting_needed:
                        pair_formatted: str = self.apply_currency_pair_format(request_name, cp)

                        # if formatted currency pair needs to be a parameter
                        if 'alias' in pair_template_dict.keys() and pair_template_dict['alias']:
                            params[pair_template_dict['alias']] = pair_formatted
                        else:
                            url = url.format(currency_pair=pair_formatted)

                    try:
                        response = await session.get(url=url, params=params)
                        response_json = await response.json(content_type=None)
                        # print(response_json)
                        if pair_formatting_needed:
                            responses[cp] = response_json
                        else:  # when ticker data is returned for all available currency pairs
                            responses[None] = response_json
                            break
                    except ClientConnectionError:
                        logging.error('Could not establish connection to {}'.format(self.name))
                        print('{} hat einen ConnectionError erzeugt.'.format(self.name))
                        self.exception_counter += 1
                        self.consecutive_exception = True
                    except Exception as ex:
                        print('Unable to read response from {}. Check exchange config file.\n'
                              'Url: {}, Parameters: {}'
                              .format(self.name, request_url_and_params['url'], request_url_and_params['params']))
                        logging.error('Unable to read response from {}. Check config file.\n'
                                      'Url: {}, Parameters: {}'
                                      .format(self.name, request_url_and_params['url'],
                                              request_url_and_params['params']))

            return datetime.utcnow(), self.name, responses
        else:
            logging.warning('{} has no Ticker request. Check {}.yaml if it should.'.format(self.name, self.name))
            print("{} has no {} request.".format(self.name, request_name))

    def apply_currency_pair_format(self, request_name: str, currency_pair: ExchangeCurrencyPair) -> str:
        """
        Helper method that applies the format described in the yaml for the specific request on the given currency-pair.
        Does currently not test if the given name with the needed parameters exist in request_urls.

        @param request_name:
            Key for the request_urls dict. Is the name of the request in the yaml for this exchange.
            So something like "historic_rates", "ticker" ...
        @param currency_pair:
            Currency-pair that needs to be formatted.
        @return:
            String of the formatted currency-pair.
            Example: BTC and ETH -> "btc_eth"
        """
        request_url_and_params: Dict = self.request_urls[request_name]
        pair_template_dict = request_url_and_params['pair_template']
        pair_template = pair_template_dict['template']

        formatted_string: str = pair_template.format(first=currency_pair.first.name, second=currency_pair.second.name)

        if pair_template_dict['lower_case']:
            formatted_string = formatted_string.lower()

        return formatted_string

    async def request_currency_pairs(self, request_name: str) -> Tuple[str, Dict]:
        """
        Tries to retrieve all available currency-pairs that are traded on this exchange.

        @param request_name:
            Key for the request_urls dict. Is the name of the request in the yaml for this exchange.
            Should be named "currency_pairs" in the provided yaml-files.
        @return Tuple[str, Dict]:
            Returns a tuple containing the name of this exchange and the response from the Rest-API.
            Dict might be None if an error occurred during the request or the request_name
            does not exist or is empty in the yaml.
        """
        response_json = None
        if request_name in self.request_urls.keys() and self.request_urls[request_name]:
            async with aiohttp.ClientSession() as session:
                request_url_and_params = self.request_urls[request_name]
                try:
                    response = await session.get(request_url_and_params['url'], params=request_url_and_params['params'])
                    response_json = await response.json(content_type=None)

                except ClientConnectionError:
                    print('{} hat einen ConnectionError erzeugt.'.format(self.name))
                except Exception as ex:
                    print('Unable to read response from {}. Check exchange config file.\n'
                          'Url: {}, Parameters: {}'
                          .format(self.name, request_url_and_params['url'], request_url_and_params['params']))
                    logging.warning('Unable to read response from {}. Check config file.\n'
                                    'Url: {}, Parameters: {}'
                                    .format(self.name, request_url_and_params['url'], request_url_and_params['params']))
        else:
            logging.warning('{} has no currency pair request. Check {}.yaml if it should.'.format(self.name, self.name))
            print("{} has no currency-pair request.".format(self.name))
        return self.name, response_json

    def extract_request_urls(self, requests: dict) -> Dict[str, Dict[str, Dict]]:
        """
        Helper-Method which should be only called by the constructor.
        Extracts from the section of requests from the .yaml-file
        the necessary attachment for the url and parameters for each request.

        api_url has to be initialized already.

        Example for one request:
            in bibox.yaml (request ticker):
                api_url: https://api.bibox.com/v1/
                requests:
                    test_connection:
                        request:
                            template: mdata?cmd=ping
                        ...
                    ticker:
                        request:
                            template: mdata?cmd=marketAll
                            pair_template: null
                            params: null

            Result:
                request_urls = { 'ticker': ('https://api.bibox.com/v1/mdata?cmd=marketAll', {}) ,
                                 'test_connection': ('https://api.bibox.com/v1/mdata?cmd=ping', {})
                                }

        Example for one request:
            in bibox.yaml (request ticker):
                api_url: https://api.bibox.com/v1/
                template: mdata
                params:
                    cmd:
                        type: str
                        default: marketAll

            Result:
                url = https://api.bibox.com/v1/mdata
                params = {cmd: marketAll}

                in result dictionary:
                    {'ticker': [url, params], ...}
                    '...'  Means dictionary-entry for different request i.e. 'historic rates'.

        If 'params' contains the key-word "func", this method calls the corresponding
        function. The functions are defined in "utilities - REQUEST_PARAMS" as a dictionary.
        The executing method is named DatabaseHandler.request_params(dict{function, #params), params).
        The yaml-file needs to be written the following way:
                ....
                   params:
                     <parameter name>:
                       func:
                         <function name>
                         <func parameter>
                         <func parameter>
                         ...


        :param requests: Dict[str: Dict[param_name: value]]
            requests-section from a exchange.yaml as dictionary.
            Viability of dict is not checked.

        :return:
            See example above.
        """
        urls = dict()

        for request in requests:
            request_parameters = dict()
            url = self.api_url
            request_dict = requests[request]['request']

            if 'template' in request_dict.keys() and request_dict['template']:
                url += '{}'.format(request_dict['template'])
            request_parameters['url'] = url

            pair_template = dict()
            if 'pair_template' in request_dict.keys() and request_dict['pair_template']:
                pair_template = request_dict['pair_template']
            request_parameters['pair_template'] = pair_template

            params = dict()
            if 'params' in request_dict.keys() and request_dict['params']:
                for param in request_dict['params']:
                    if 'default' in request_dict['params'][param]:
                        params[param] = str(request_dict['params'][param]['default'])

                    if 'function' in request_dict['params'][param]:
                        conv_params = request_dict['params'][param]['function']
                        conversion_tuple = (conv_params[0], conv_params[1])

                        params[param] = TYPE_CONVERSION[conversion_tuple]['function']

            request_parameters['params'] = params

            urls[request] = request_parameters

        return urls

    def extract_mappings(self, requests: dict) -> Dict[str, List[Mapping]]:
        """
        Helper-Method which should be only called by the constructor.
        Extracts out of a given exchange .yaml-requests-section for each
        request the necessary mappings so the values can be extracted from
        the response for said request.

        The key-value in the dictionary is the same as the key for the request.
        i.e. behind 'ticker' are all the mappings stored which are necessary for
        extracting the values out of a ticker-response.

        If there is no mapping specified in the .yaml for a value which is contained
        by the response, the value will not be extracted later on because there won't
        be a Mapping-object for said value.

        :param requests: Dict[str: List[Mapping]]
            Requests-section from a exchange.yaml as dictionary.
            Method does not check if dictionary contains viable information.

        :return:
            Dictionary with the following structure:
                {'request_name': List[Mapping]}
        """
        response_mappings = dict()
        for request in requests:
            request_mapping: dict = requests[request]

            if 'mapping' in request_mapping.keys():
                mapping = request_mapping['mapping']
                mapping_list = list()

                for entry in mapping:
                    mapping_list.append(Mapping(entry['key'], entry['path'], entry['type']))

                response_mappings[request] = mapping_list

        return response_mappings

    def format_currency_pairs(self, response: Tuple[str, Dict]) -> Iterator[Tuple[str, str, str]]:
        """
        Extracts the currency-pairs of out of the given json-response
        that was collected from the Rest-API of this exchange.

        Process is similar to @see{self.format_ticker()}.

        @param response:
            Raw json-response from the Rest-API of this exchange that needs be formatted.
        @return:
            Iterator containing tuples of the following structure:
            (self.name, name of first currency-pair, name of second currency-pair)
        """
        if response[0] != self.name:
            return None

        results = {'currency_pair_first': [],
                   'currency_pair_second': []}
        mappings = self.response_mappings['currency_pairs']

        for mapping in mappings:
            results[mapping.key] = mapping.extract_value(response[1])

        # ToDo:Das funktioniert nicht!
        assert (len(results[0]) == len(result) for result in results)

        return list(itertools.zip_longest(itertools.repeat(self.name, len(results['currency_pair_first'])),
                                          results['currency_pair_first'],
                                          results['currency_pair_second']))

    def format_data(self,
                    method,
                    response: Iterator[Tuple[str, Dict[object, list]]],
                    **kwargs):

        """
        Extracts from the response-dictionary, with help of the suitable Mapping-Objects,
        the requested values and formats them to fitting tuples for persist_response() in db_handler.

        Starts with a dictionary of empty lists where each key is the possible key-name from a mapping.
        This is necessary because not every exchange returns every value that we try to store but a list
        is later necessary to fill up 'empty places'.
        i.e. Some exchange don't return trade_volumes for their currencies.

        Each Mapping stored behind response_mappings[method] is then called to extract its' values.
        i.e. The Mapping-Object with the key_name 'currency_pair_first' extracts a list which is ordered
        from first to last line with all the symbols of the first named currency.
        The return from extract_values() is then stored behind the key-name,
        e.g. the empty list is now replaced with the extracted values.

        The overall result of this process looks something like the following:
            first_currency =    ['BTC', 'ETH', ...]
            second_currency =   ['XRP', 'USD', ...]
            ticker_last_price = []  <--- no Mapping-Object in exchange.yaml specified
            ticker_best_ask =   [0.123, 5.456, ...]
            ...
        Lists which are filled have the same length.
        (obviously because extraction of the same number of lines in response)
        The X-th elements from each value-list(extracted with Mapping-object) represent
        one 'response-line' in the given json.

        Because returning just the dictionary containing the lists is not intuitive
        the last step is formatting the extracted values into fitting tuples.
        This is done by using itertools.zip_longest() which works like the following:
            a = itertools.repeat('a', len(b))
            b = [1, 2, 3]
            c = []
            d = [1, 2]

            result:
                ('a', 1, None, 1)
                ('a', 2, None, 2)
                ('a', 3, None, None)

        We are using the length of currency_pair_first because every entry in general ticker_data
        has to contain a currency pair. It is always viable because the lists of extracted values
        all need to have the same length.
        The formatted list of ticker-data-tuples is then returned.

        AMEN

        :param method: str
            The request method name, i.e. ticker, trades,...
        :param response: Iterator
            response is a parsed json -> Dict.
                Tuple might contain None if there was no Mapping-Object for a key (every x-th element of all
                 the tuples is none or the extracted value was simply None.
        :param kwargs: Dict
            Key:Value pairs that will be added to each data tuple. Currently 'start_time', i.e a datetime object
            when the scheduler started the request and 'time', i.e. the timestamp an exchange responded.

        :return List of Tuples with the formatted data and the name of the mapping_keys to map the data points.
        """

        if response[0] != self.name:
            return None
        results = list()
        mappings = self.response_mappings[method]
        responses = response[1]
        currency_pair: ExchangeCurrencyPair
        mapping_keys = [mapping.key for mapping in mappings]
        updated_mappings=[]
        for currency_pair in responses.keys():
            # creating dictionary where key is the name of the mapping which holds an empty list
            temp_results = dict(zip((key for key in mapping_keys),
                                    itertools.repeat([], len(mappings))))
            if currency_pair:  # responses had to be collected individually
                current_response = responses[currency_pair]
            else:  # data for all currency_pairs in one response
                current_response = responses[None]

            if current_response:
                try:
                    # extraction of actual values; note that currencies might not be in mappings (later important)
                    for mapping in mappings:
                        # TODO: does extract_value never need currency-pair info?
                        temp_results[mapping.key] = mapping.extract_value(current_response)
                except Exception:
                    print('Error while formatting {}: {}'.format(method, currency_pair))
                    traceback.print_exc()
                    pass
                else:
                    extracted_data_is_valid: bool = True
                    for extracted_field in temp_results.keys():
                        if temp_results[extracted_field] is None:
                            print("{} has no valid data in {}".format(currency_pair, extracted_field))
                            extracted_data_is_valid = False
                            break

                    if not extracted_data_is_valid:
                        continue

                    # asserting that the extracted lists for each mapping are having the same length
                    assert (len(results[0]) == len(result) for result in temp_results)

                    # TODO: can't len_results = results[0] since we asserted that all lists have the same length?
                    len_results = {key: len(value) for key, value in temp_results.items() if hasattr(value, '__iter__')}
                    len_results = max(len_results.values()) if bool(len_results) else 1

                    if 'position' in temp_results.keys():
                        temp_results['position'] = range(len_results)

                    # adding pair id when we don't have currencies in mapping
                    # TODO: do we benefit from this later in persist-method since we know id already?
                    if 'currency_pair_first' and 'currency_pair_second' not in mapping_keys:
                        temp_results.update({'exchange_pair_id': currency_pair.id})

                    # update new keys only if not already exsits to prevent overwriting!
                    temp_results = {**kwargs, **temp_results}
                    result = [v if hasattr(v, '__iter__')
                              else itertools.repeat(v, len_results) for k, v in temp_results.items()]

                    result = list(itertools.zip_longest(*result))
                    updated_mappings = temp_results.keys()
                    results.extend(result)

        return results, updated_mappings



# Currently unused or outdated methods.

# async def request(self, request_name: str, currency_pairs: List[ExchangeCurrencyPair]) \
#         -> Tuple[str, Dict[ExchangeCurrencyPair, Dict]]:
#     """
#     Sends a request for the historic rates of each given currency-pair and returns the
#     responses that were collected. Is asynchronous so there can be multiple resquests
#     be send without the need of waiting for each response before the next request can be send.
#
#     @param request_name: str
#         Name of the request specified in the yaml-file for getting the historic rates.
#         Aka. the key for the request_urls dict.
#     @param currency_pairs: List[ExchangeCurrencyPairs]
#         List of currency-pairs the data should be retrieved for.
#     @return: (str, Dict[ExchangeCurrencyPair, json]) or None
#         Tuple containing the name of this exchange and a Dict which contains the responses
#         accessible through the ExchangeCurrencyPair.
#
#         Returns None if the request could not be found in requesst_urls or if the
#         connection to the Rest-API failed and a ClientConnectionError was thrown.
#         So either the given request_name was wrong or this exchange has no reqeust
#         named after request_name in it's yaml.
#     """
#     if self.request_urls.get(request_name):
#         async with aiohttp.ClientSession() as session:
#             request_url_and_params: Dict = self.request_urls[request_name]
#             responses = dict()
#             params = request_url_and_params['params']
#             pair_template_dict = request_url_and_params['pair_template']
#
#             for cp in currency_pairs:
#                 url: str = request_url_and_params['url']
#
#                 pair_formatted: str = self.apply_currency_pair_format(request_name, cp)
#
#                 # if formatted currency pair needs to be a parameter
#                 if 'alias' in pair_template_dict.keys() and pair_template_dict['alias']:
#                     params[pair_template_dict['alias']] = pair_formatted
#                 else:
#                     url = url.format(currency_pair=pair_formatted)
#
#                 try:
#                     response = await session.get(url=url, params=params)
#                     response_json = await response.json(content_type=None)
#
#                     # print(response_json)
#                     responses[cp] = response_json
#                     self.consecutive_exception = False
#
#                 except ClientConnectionError:
#                     logging.error('Could not establish connection to {}'.format(self.name))
#                     print('{} hat einen ConnectionError erzeugt.'.format(self.name))
#                 except Exception as ex:
#                     print('Unable to read response from {}. Check exchange config file.\n'
#                           'Url: {}, Parameters: {}'
#                           .format(self.name, request_url_and_params['url'], request_url_and_params['params']))
#                     logging.error('Unable to read response from {}. Check config file.\n'
#                                   'Url: {}, Parameters: {}'
#                                   .format(self.name, request_url_and_params['url'],
#                                           request_url_and_params['params']))
#                 finally:
#                     time.sleep(self.rate_limit)
#
#             return self.name, responses
#     else:
#         print('{} hat keine {}'.format(self.name, request_name.capitalize()))
#         return self.name, None


# def format_ticker(self, response: Tuple[str, datetime, datetime, dict]) -> Iterator[Tuple[str,
#                                                                                           datetime,
#                                                                                           datetime,
#                                                                                           str,
#                                                                                           str,
#                                                                                           float,
#                                                                                           float,
#                                                                                           float,
#                                                                                           float,
#                                                                                           float]]:
#
#     """
#     Extracts from the response-dictionary, with help of the suitable Mapping-Objects,
#     the requested values and formats them to fitting tuples for persist_tickers() in db_handler.
#
#     Starts with a dictionary of empty lists where each key is the possible key-name from a mapping.
#     This is necessary because not every exchange returns every value that we try to store but a list
#     is later necessary to fill up 'empty places'.
#     i.e. Some exchange don't return last_trade volumes for their currencies.
#
#     TODO: prevent hardcoding key_names ( nice to have )
#
#     Each Mapping stored behind response_mappings['ticker'] is then called to extract its values.
#     i.e. The Mapping-Object with the key_name 'currency_pair_first' extracts a list which is ordered
#     from first to last line with all the symbols of the first named currency.
#     The return from extract_values() is then stored behind the key-name,
#     e.g. the empty list is now replaced with the extracted values.
#
#     The overall result of this process looks something like the following:
#         first_currency =    ['BTC', 'ETH', ...]
#         second_currency =   ['XRP', 'USDT', ...]
#         ticker_last_price = []  <--- no Mapping-Object in exchange.yaml specified
#         ticker_best_ask =   [0.123, 5.456, ...]
#         ...
#     Lists which are filled have the same length.
#     (obviously because extraction of the same number of lines in response)
#     The X-th elements from each value-list(extracted with Mapping-object) represent
#     one 'response-line' in the given json.
#
#     Because returning just the dictionary containing the lists is not intuitive
#     the last step is formatting the extracted values into fitting tuples.
#     This is done by using itertools.zip_longest() which works like the following:
#         a = itertools.repeat('a', len(b))
#         b = [1, 2, 3]
#         c = []
#         d = [1, 2]
#
#         result:
#             ('a', 1, None, 1)
#             ('a', 2, None, 2)
#             ('a', 3, None, None)
#
#     We are using the length of currency_pair_first because every entry in general ticker_data
#     has to contain a currency pair. It is always viable because the lists of extracted values
#     all need to have the same length.
#
#     The formatted list of ticker-data-tuples is then returned.
#
#     AMEN
#
#     :param response: Tuple[exchange_name, time of arrival, response from exchange-api]
#         response is a parsed json -> Dict.
#
#     :return: Iterator of tuples with the following structure:
#             (exchange-name,
#              timestamp,
#              timestamp,
#              first_currency_symbol,
#              second_currency_symbol,
#              ticker_last_price,
#              ticker_last_trade,
#              ticker_best_ask,
#              ticker_best_bid,
#              ticker_daily_volume)
#
#             Tuple might contain None if there was no Mapping-Object for a key(every x-th element of all
#              the tuples is none or the extracted value was simply None.
#
#         Returns None if the given exchange-name of is not the name of this exchange.
#     """
#     if response[0] != self.name:
#         return None
#
#     results = list()
#
#     mappings = self.response_mappings['ticker']
#     responses = response[3]
#     currency_pair: ExchangeCurrencyPair
#
#     for currency_pair in responses.keys():
#         temp_results = {'currency_pair_first': [],
#                         'currency_pair_second': [],
#                         'ticker_last_price': [],
#                         'ticker_best_ask': [],
#                         'ticker_best_bid': [],
#                         'ticker_daily_volume': []}
#
#         current_response = responses[currency_pair]
#         curr_pair_string_formatted: str = None
#         currency_pair_info: (str, str, str) = None
#         if currency_pair:
#             curr_pair_string_formatted = self.apply_currency_pair_format('ticker', currency_pair)
#             currency_pair_info = (currency_pair.first.name, currency_pair.second.name, curr_pair_string_formatted)
#
#         for mapping in mappings:
#             temp_results[mapping.key] = mapping.extract_value(current_response,
#                                                               currency_pair_info=currency_pair_info)
#             if not hasattr(temp_results[mapping.key], "__iter__") or isinstance(temp_results[mapping.key], str):
#                 #if only one value extracted wrap in list
#                 temp_results[mapping.key] = [temp_results[mapping.key]]
#
#         result = list(itertools.zip_longest(itertools.repeat(response[0], len(temp_results['currency_pair_first'])),
#                                             itertools.repeat(response[1], len(temp_results['currency_pair_first'])),
#                                             itertools.repeat(response[2], len(temp_results['currency_pair_first'])),
#                                             temp_results['currency_pair_first'],
#                                             temp_results['currency_pair_second'],
#                                             temp_results['ticker_last_price'],
#                                             temp_results['ticker_best_ask'],
#                                             temp_results['ticker_best_bid'],
#                                             temp_results['ticker_daily_volume']))
#         results.extend(result)
#     return results
