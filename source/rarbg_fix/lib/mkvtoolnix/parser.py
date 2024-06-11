#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    plugins.parser.py

    Written by:               k29t59dh
    Date:                     08 Jun 2024, (5:24 PM)

    Copyright:

        This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
        Public License as published by the Free Software Foundation, version 3.

        This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
        implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
        for more details.

        You should have received a copy of the GNU General Public License along with this program.
        If not, see <https://www.gnu.org/licenses/>.

"""
from .. import ffmpeg

class Parser(ffmpeg.Parser):
    def parse_progress(self, line_text):
        """
        Given a single line of STDOUT text, parse it using regex and extract progress as a percent value.

        :param line_text:
        :return:
        """
        # Fetch data from line text
        if line_text and 'Progress: ' in line_text:
            _percent = None
            try:
                _percent = line_text.split("Progress: ")[1].split('%')[0]
            except IndexError:
                pass

            if _percent and int(_percent) > int(self.percent):
                self.percent = str(_percent)

        # Return the values.
        # Currently Unmanic only cares about the percent. So for now we will ignore everything else.
        return {
            'percent': self.percent
        }

