#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright 2014 The Plaso Project Authors.
# Please see the AUTHORS file for details on individual authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Parser for Windows IIS Log file.

More documentation on fields can be found here:
http://www.microsoft.com/technet/prodtechnol/WindowsServer2003/Library/
IIS/676400bc-8969-4aa7-851a-9319490a9bbb.mspx?mfr=true

"""

import logging

import pyparsing

from plaso.events import time_events
from plaso.lib import eventdata
from plaso.lib import timelib
from plaso.parsers import text_parser


__author__ = 'Ashley Holtz (ashley.a.holtz@gmail.com)'


class IISEventObject(time_events.TimestampEvent):
  """Convenience class to handle the IIS event object."""

  DATA_TYPE = 'iis:log:line'

  def __init__(self, timestamp, structure):
    """Initializes the IIS event object.

    Args:
      timestamp: The timestamp time value, epoch.
      structure: The structure with any parsed log values to iterate over.
    """
    super(IISEventObject, self).__init__(timestamp,
        eventdata.EventTimestamp.WRITTEN_TIME)

    for key, value in structure.iteritems():
      if key in ('time', 'date'):
        continue
      if value == u'-':
        continue
      if type(value) is pyparsing.ParseResults:
         setattr(self, key, u''.join(value))
      else:
        try:
          save_value = int(value, 10)
        except ValueError:
          save_value = value
      setattr(self, key, save_value)


class WinIISParser(text_parser.PyparsingSingleLineTextParser):
  """Parses the Windows IIS Log file."""

  NAME = 'winiis'

  # Common Fields (6.0: date time s-sitename s-ip cs-method cs-uri-stem
  # cs-uri-query s-port cs-username c-ip cs(User-Agent) sc-status
  # sc-substatus sc-win32-status.
  # Common Fields (7.5): date time s-ip cs-method cs-uri-stem cs-uri-query
  # s-port cs-username c-ip cs(User-Agent) sc-status sc-substatus
  # sc-win32-status time-taken

  # Define common structures.
  BLANK = pyparsing.Literal(u'-')
  WORD = pyparsing.Word(pyparsing.alphanums + u'-') | BLANK
  INT = pyparsing.Word(pyparsing.nums, min=1) | BLANK
  IP = (
      text_parser.PyparsingConstants.IPV4_ADDRESS |
      text_parser.PyparsingConstants.IPV6_ADDRESS | BLANK)
  PORT = pyparsing.Word(pyparsing.nums, min=1, max=6) | BLANK
  URI = pyparsing.Word(pyparsing.alphanums + u'/.?&+;_=()-:,%') | BLANK

  # Define how a log line should look like for version 6.0.
  LOG_LINE_6_0 = (
      text_parser.PyparsingConstants.DATE.setResultsName('date') +
      text_parser.PyparsingConstants.TIME.setResultsName('time') +
      WORD.setResultsName('s_sitename') + IP.setResultsName('dest_ip') +
      WORD.setResultsName('http_method') + URI.setResultsName('cs_uri_stem') +
      URI.setResultsName('cs_uri_query') + PORT.setResultsName('dest_port') +
      WORD.setResultsName('cs_username') + IP.setResultsName('source_ip') +
      URI.setResultsName('user_agent') + INT.setResultsName('sc_status') +
      INT.setResultsName('sc_substatus') +
      INT.setResultsName('sc_win32_status'))

  _LOG_LINE_STRUCTURES = {}

  # Common fields. Set results name with underscores, not hyphens because regex
  # will not pick them up.
  _LOG_LINE_STRUCTURES['date'] = (
      text_parser.PyparsingConstants.DATE.setResultsName('date'))
  _LOG_LINE_STRUCTURES['time'] = (
      text_parser.PyparsingConstants.TIME.setResultsName('time'))
  _LOG_LINE_STRUCTURES['s-sitename'] = WORD.setResultsName('s_sitename')
  _LOG_LINE_STRUCTURES['s-ip'] = IP.setResultsName('dest_ip')
  _LOG_LINE_STRUCTURES['cs-method'] = WORD.setResultsName('http_method')
  _LOG_LINE_STRUCTURES['cs-uri-stem'] = URI.setResultsName('requested_uri_stem')
  _LOG_LINE_STRUCTURES['cs-uri-query'] = URI.setResultsName('cs_uri_query')
  _LOG_LINE_STRUCTURES['s-port'] = PORT.setResultsName('dest_port')
  _LOG_LINE_STRUCTURES['cs-username'] = WORD.setResultsName('cs_username')
  _LOG_LINE_STRUCTURES['c-ip'] = IP.setResultsName('source_ip')
  _LOG_LINE_STRUCTURES['cs(User-Agent)'] = URI.setResultsName('user_agent')
  _LOG_LINE_STRUCTURES['sc-status'] = INT.setResultsName('http_status')
  _LOG_LINE_STRUCTURES['sc-substatus'] = INT.setResultsName('sc_substatus')
  _LOG_LINE_STRUCTURES['sc-win32-status'] = (
      INT.setResultsName('sc_win32_status'))

  # Less common fields.
  _LOG_LINE_STRUCTURES['s-computername'] = URI.setResultsName('s_computername')
  _LOG_LINE_STRUCTURES['sc-bytes'] = INT.setResultsName('sent_bytes')
  _LOG_LINE_STRUCTURES['cs-bytes'] = INT.setResultsName('received_bytes')
  _LOG_LINE_STRUCTURES['time-taken'] = INT.setResultsName('time_taken')
  _LOG_LINE_STRUCTURES['cs-version'] = WORD.setResultsName('protocol_version')
  _LOG_LINE_STRUCTURES['cs-host'] = WORD.setResultsName('cs_host')
  _LOG_LINE_STRUCTURES['cs(Cookie)'] = URI.setResultsName('cs_cookie')
  _LOG_LINE_STRUCTURES['cs(Referrer)'] = URI.setResultsName('cs_referrer')

  # Define the available log line structures. Default to the IIS v. 6.0
  # common format.
  LINE_STRUCTURES = [
      ('comment', text_parser.PyparsingConstants.COMMENT_LINE_HASH),
      ('logline', LOG_LINE_6_0)]

  def __init__(self, pre_obj, config):
    """Initializes the parser.

    Args:
      pre_obj: pre-parsing object.
      config: configuration object.
    """
    super(WinIISParser, self).__init__(pre_obj, config)
    self.version = None
    self.software = None

  def VerifyStructure(self, line):
    """Verify that this file is an IIS log file."""
    # TODO: Examine other versions of the file format and if this parser should
    # support them. For now just checking if it contains the IIS header.
    if '#Software: Microsoft Internet Information Services' in line:
        return True
    return False

  def ParseRecord(self, key, structure):
    """Parse each record structure and return an EventObject if applicable."""
    if key == 'comment':
      self._ParseCommentRecord(structure)
    elif key == 'logline':
      return self._ParseLogLine(structure)
    else:
      logging.warning(
          u'Unable to parse record, unknown structure: {0:s}'.format(key))

  def _ParseCommentRecord(self, structure):
    """Parse a comment and store appropriate attributes."""
    comment = structure[1]
    if comment.startswith('Version'):
      _, _, self.version = comment.partition(':')
    elif comment.startswith('Software'):
      _, _, self.software = comment.partition(':')
    elif comment.startswith('Date'):
      _, _, date = comment.partition(':')

    # Check if there's a Fields line. If not, LOG_LINE defaults to IIS 6.0
    # common format.
    elif comment.startswith('Fields'):
      log_line = ''
      for member in comment[7:].split():
        log_line += self._LOG_LINE_STRUCTURES.get(member, self.URI)
      self._line_structures[1] = ('logline', log_line)

  def _ParseLogLine(self, structure):
    """Parse a single log line and return an EventObject."""
    date = structure.get('date', None)
    time = structure.get('time', None)

    if not (date and time):
      logging.warning(
        u'Unable to extract timestamp from IIS log line with structure: {0:s}.'
        .format(structure))
      return

    year, month, day = date
    hour, minute, second = time

    timestamp = timelib.Timestamp.FromTimeParts(
        year, month, day, hour, minute, second)

    if not timestamp:
      return

    return IISEventObject(timestamp, structure)