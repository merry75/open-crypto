#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This module contains possibilities to adjust several settings

Classes:
 - Setting: Contains advanced options for the program.
"""
import os
import shutil
from typing import Union
import oyaml as yaml
import logging


class Setting:
    """
    Class to get and manipulate advanced program settings.
    """

    PATH = "/resources/configs/program_config/config.yaml"

    @staticmethod
    def get() -> os.startfile:
        """
        Opens the current program config file in a text editor.
        """
        os.startfile(os.getcwd() + Setting.PATH)

    @staticmethod
    def set(block: str, key: str, val: Union[str, int, float]) -> None:

        try:
            with open(os.getcwd() + Setting.PATH, "r") as f:
                file = yaml.load(f, Loader=yaml.FullLoader)

            file.get(block).update({key: val})
            with open(os.getcwd() + Setting.PATH, "w") as f:
                yaml.dump(file, f)

        except (KeyError, FileNotFoundError):
            logging.error("Program config could not be updated.")
            print("Error updating program config!")

    @staticmethod
    def reset() -> None:
        """
        Creates a new template config file with all default settings.
        """

        filename = "program_config.yaml"

        source = os.path.dirname(os.path.realpath(__file__)) + "/resources/templates/"
        destination = os.getcwd() + "/resources/configs/program_config/"

        if os.path.exists(os.path.join(destination, filename)):
            os.remove(os.path.join(destination, filename.split("_")[1]))
        shutil.copy(os.path.join(source, filename),
                    os.path.join(destination, filename.split("_")[1]))

        print("Settings reset successful.")


