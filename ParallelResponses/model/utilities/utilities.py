import calendar
import datetime
import os
from typing import List, Any, Dict
import yaml #install PyYaml
import pathlib
from pathlib import Path

#bin ich in master

TYPE_CONVERSION = {

    """
    Type Conversions used to convert extracted values from the API-Response into the desired type ("first", "second").
    The values are specified in the .yaml-file of each exchange under the "mapping" of each method.
    The function is called in the Mapping Class of utilities.py under the method convert_types().
    
    "first": 
        The actual type extracted from the API-Request (.json)
    "second": 
        The desired type to convert
    "function": 
        the actual function to apply
    "params": 
        the number of additional parameters needed    
    """

    : {  # Tested
        "function": str,
        "params": 0
    },
    ("bool", "int"): {  # Tested
        "function": int,
        "params": 0
    },
    ("int", "bool"): {  # Tested
        "function": bool,
        "params": 0
    },
    ("int", "fromtimestamp"): {  # Partially tested
        "function": datetime.datetime.fromtimestamp,
        "params": 0
    },
    ("int", "utcfromtimestamp"): {  # Partially tested
        "function": datetime.datetime.utcfromtimestamp,
        "params": 0
    },
    ("int", "fromtimestampms"): {  # Partially tested
        "function": lambda timestampms: datetime.datetime.fromtimestamp(
            timestampms / 1000),
        "params": 0
    },
    ("int", "fromtimestampns"): {  # Not tested
        "function": lambda timestampns: datetime.datetime.fromtimestamp(
            timestampns / 1000000),
        "params": 0
    },
    ("float", "fromtimestamp"): {  # Partially tested
        "function": datetime.datetime.fromtimestamp,
        "params": 0
    },
    ("float", "utcfromtimestamp"): {  # Partially tested
        "function": datetime.datetime.utcfromtimestamp,
        "params": 0
    },
    ("str", "bool"): {  # Tested
        "function": lambda string: string.lower() == "true",
        "params": 0
    },
    ("str", "int"): {  # Tested
        "function": int,
        "params": 0
    },
    ("str", "float"): {  # Tested
        "function": float,
        "params": 0
    },
    ("str", "floatNA"): {
        "function": lambda string: float(string) if string != "N/A" else None,
        "params": 0
    },
    ("str", "strptime"): {  # Partially tested
        "function": lambda string, *args:
        datetime.datetime.strptime(string, args[0]),
        "params": 1
    },
    ("str", "split"): {  # Tested
        "function": lambda string, *args: string.split(args[0])[args[1]],
        "params": 2
    },
    ("str", "splitupper"): {
        "function": lambda string, *args: string.split(args[0])[args[1]].upper(),
        "params": 2
    },
    ("str", "slice"): {  # Partially tested
        "function": lambda string, *args: string[args[0]:args[1]],
        "params": 2
    },
    ("str", "upper"): {  # Not tested
        "function": lambda string: string.upper(),
        "params": 0
    },
    ("str", "lower"): {  # Not tested
        "function": lambda string: string.lower(),
        "params": 0
    },
    ("datetime", "strftime"): {  # Partially tested
        "function": lambda time, *args:
        datetime.datetime.strftime(time, args[0]),
        "params": 1
    },
    ("datetime", "totimestamp"): {  # Partially tested
        "function": lambda time: int(time.timestamp()),
        "params": 0
    },
    ("datetime", "totimestampms"): {  # Partially tested
        "function": lambda time: int(round(time.timestamp() * 1000)),
        "params": 0
    },
    ("datetime", "utctotimestamp"): {  # Partially tested
        "function": lambda time: calendar.timegm(time.utctimetuple()),
        "params": 0
    },
    ("none", "nowstrptime"): {
        "function": lambda arg: datetime.datetime.strptime(datetime.datetime.now().strftime("%Y-%m-%d"), "%Y-%m-%d"),
        "params": 0
    },
    ("none", "now"): {
        "function": lambda arg: datetime.datetime.now(),
        "params": 0
    },
    ("none", "constant"): {  # Returns the first argument
        "function": lambda arg, *args: args[0],
        "params": 1
    },
}


"""A dictionary containing lambda function calls in order to get request parameters variable. The function calls 
will be stored in the respective .yaml-file of each exchange and executed, outside the yaml environment, 
during the preparation of the API request.

'name' : call name of the lambda function
'function' : the actual lambda function to execute
'params' : amount of additional parameters if necessary.
'session' : ORM-Session if necessary.
"""
REQUEST_PARAMS = {
    "add": {    #for debugging purposes.
        "name": 'add',
        "function": lambda x: x+1,
        "params": 1,
        "session": False
    },
    "exchange": {
        "name": 'exchange',
        "function": lambda session, table: session.query(table),
        'params': 1,
        "session": True
    },
    "last_ts": {
        "name": 'last_ts',
        "function": lambda session, table, exchange, pair: session.query(table).filter()
    }
}


def read_config(section: str, filename='config.yaml') -> Dict[str, Any]:
    """
    @param section: str
        Name of the section the information is stored in.
    @param filename: str
        Name of the config file.
    @return:
        Parameters for the program as a dictionary.
        Keys are the names of the parameters in the config-file.
    """

    config_yaml = open(filename)
    config_dict: Dict = yaml.load(config_yaml, Loader=yaml.FullLoader)

    for general_section in config_dict.keys():
        if section == general_section:
            return config_dict[general_section]

        for nested_section in config_dict[general_section].keys():
            if section == nested_section:
                return config_dict[general_section][nested_section]

    Exception()


def yaml_loader(exchange: str):
    """
    Loads, reads and returns the data of a .yaml-file specified by the param exchange.

    :param exchange: str
        the file name to load (exchange)
    :return: data: dict
        returns a dict of the loaded data from the .yaml-file
    :exceptions Exception: the .yaml file could not be evaluated for a given exchange
    """

    with open(YAML_PATH + exchange + '.yaml', 'r') as f:
        try:
            data = yaml.load(f, Loader=yaml.FullLoader)
            print(exchange)
            return data
        except Exception as ex:
            # create an instance of the exception dictionary to safe the exchange which have thrown the exchange
            exception = ExceptionDict()
            exception.get_dict()['{}'.format(exchange)] = 1


def get_exchange_names() -> List[str]:
    """
    Gives information about all exchange that the program will send
    requests to. This means if the name of a exchange is not part of the
    list that is returned, the program will not send any request to said
    exchange.
    :param: session: orm_session
        Connection to the Database in order to query all ACTIVE exchange.
    :return: List[str]
        Names from all the exchange, which have a .yaml-file in
        the directory described in YAML_PATH.
"""
    path_to_resoureces: Path = pathlib.Path().parent.absolute()
    exchanges_list = os.listdir(Path.joinpath(path_to_resoureces, YAML_PATH))
    exchange_names = list([str(x.split(".")[0]) for x in exchanges_list if ".yaml" in x])
    exchanges = exchange_names
    exchange_names.sort()
    return exchanges


# Constant that contains the path to the yaml-files of working exchange.
YAML_PATH = read_config('utilities')['yaml_path']

