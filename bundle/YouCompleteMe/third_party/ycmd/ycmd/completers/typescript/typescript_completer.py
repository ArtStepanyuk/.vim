# Copyright (C) 2015 - 2016 Google Inc.
#               2016 ycmd contributors
#
# This file is part of ycmd.
#
# ycmd is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ycmd is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import json
import logging
import os
import re
import subprocess
import itertools

from threading import Thread
from threading import Event
from threading import Lock
from tempfile import NamedTemporaryFile

from ycmd import responses
from ycmd import utils
from ycmd.completers.completer import Completer

BINARY_NOT_FOUND_MESSAGE = ( 'tsserver not found. '
                             'TypeScript 1.5 or higher is required' )

MAX_DETAILED_COMPLETIONS = 100
RESPONSE_TIMEOUT_SECONDS = 10

_logger = logging.getLogger( __name__ )


class DeferredResponse( object ):
  """
  A deferred that resolves to a response from TSServer.
  """

  def __init__( self, timeout = RESPONSE_TIMEOUT_SECONDS ):
    self._event = Event()
    self._message = None
    self._timeout = timeout


  def resolve( self, message ):
    self._message = message
    self._event.set()


  def result( self ):
    self._event.wait( timeout = self._timeout )
    if not self._event.isSet():
      raise RuntimeError( 'Response Timeout' )
    message = self._message
    if not message[ 'success' ]:
      raise RuntimeError( message[ 'message' ] )
    if 'body' in message:
      return self._message[ 'body' ]


class TypeScriptCompleter( Completer ):
  """
  Completer for TypeScript.

  It uses TSServer which is bundled with TypeScript 1.5

  See the protocol here:
  https://github.com/Microsoft/TypeScript/blob/2cb0dfd99dc2896958b75e44303d8a7a32e5dc33/src/server/protocol.d.ts
  """


  def __init__( self, user_options ):
    super( TypeScriptCompleter, self ).__init__( user_options )

    # Used to prevent threads from concurrently writing to
    # the tsserver process' stdin
    self._writelock = Lock()

    binarypath = utils.PathToFirstExistingExecutable( [ 'tsserver' ] )
    if not binarypath:
      _logger.error( BINARY_NOT_FOUND_MESSAGE )
      raise RuntimeError( BINARY_NOT_FOUND_MESSAGE )

    self._logfile = _LogFileName()
    tsserver_log = '-file {path} -level {level}'.format( path = self._logfile,
                                                         level = _LogLevel() )
    # TSServer get the configuration for the log file through the environment
    # variable 'TSS_LOG'. This seems to be undocumented but looking at the
    # source code it seems like this is the way:
    # https://github.com/Microsoft/TypeScript/blob/8a93b489454fdcbdf544edef05f73a913449be1d/src/server/server.ts#L136
    self._environ = os.environ.copy()
    utils.SetEnviron( self._environ, 'TSS_LOG', tsserver_log )

    # Each request sent to tsserver must have a sequence id.
    # Responses contain the id sent in the corresponding request.
    self._sequenceid = itertools.count()

    # Used to prevent threads from concurrently accessing the sequence counter
    self._sequenceid_lock = Lock()

    # TSServer ignores the fact that newlines are two characters on Windows
    # (\r\n) instead of one on other platforms (\n), so we use the
    # universal_newlines option to convert those newlines to \n. See the issue
    # https://github.com/Microsoft/TypeScript/issues/3403
    # TODO: remove this option when the issue is fixed.
    # We also need to redirect the error stream to the output one on Windows.
    self._tsserver_handle = utils.SafePopen( binarypath,
                                             stdout = subprocess.PIPE,
                                             stdin = subprocess.PIPE,
                                             stderr = subprocess.STDOUT,
                                             env = self._environ,
                                             universal_newlines = True )

    # Used to map sequence id's to their corresponding DeferredResponse
    # objects. The reader loop uses this to hand out responses.
    self._pending = {}

    # Used to prevent threads from concurrently reading and writing to
    # the pending response dictionary
    self._pendinglock = Lock()

    # Start a thread to read response from TSServer.
    self._thread = Thread( target = self._ReaderLoop, args = () )
    self._thread.daemon = True
    self._thread.start()

    _logger.info( 'Enabling typescript completion' )


  def _ReaderLoop( self ):
    """
    Read responses from TSServer and use them to resolve
    the DeferredResponse instances.
    """

    while True:
      try:
        message = self._ReadMessage()

        # We ignore events for now since we don't have a use for them.
        msgtype = message[ 'type' ]
        if msgtype == 'event':
          eventname = message[ 'event' ]
          _logger.info( 'Recieved {0} event from tsserver'.format( eventname ) )
          continue
        if msgtype != 'response':
          _logger.error( 'Unsuported message type {0}'.format( msgtype ) )
          continue

        seq = message[ 'request_seq' ]
        with self._pendinglock:
          if seq in self._pending:
            self._pending[ seq ].resolve( message )
            del self._pending[ seq ]
      except Exception as e:
        _logger.error( 'ReaderLoop error: {0}'.format( str( e ) ) )


  def _ReadMessage( self ):
    """Read a response message from TSServer."""

    # The headers are pretty similar to HTTP.
    # At the time of writing, 'Content-Length' is the only supplied header.
    headers = {}
    while True:
      headerline = self._tsserver_handle.stdout.readline().strip()
      if not headerline:
        break
      key, value = headerline.split( ':', 1 )
      headers[ key.strip() ] = value.strip()

    # The response message is a JSON object which comes back on one line.
    # Since this might change in the future, we use the 'Content-Length'
    # header.
    if 'Content-Length' not in headers:
      raise RuntimeError( "Missing 'Content-Length' header" )
    contentlength = int( headers[ 'Content-Length' ] )
    return json.loads( self._tsserver_handle.stdout.read( contentlength ) )


  def _BuildRequest( self, command, arguments = None ):
    """Build TSServer request object."""

    with self._sequenceid_lock:
      seq = next( self._sequenceid )
    request = {
      'seq':     seq,
      'type':    'request',
      'command': command
    }
    if arguments:
      request[ 'arguments' ] = arguments
    return request


  def _SendCommand( self, command, arguments = None ):
    """
    Send a request message to TSServer but don't wait for the response.
    This function is to be used when we don't care about the response
    to the message that is sent.
    """

    request = self._BuildRequest( command, arguments )
    with self._writelock:
      self._tsserver_handle.stdin.write( json.dumps( request ) )
      self._tsserver_handle.stdin.write( "\n" )
      self._tsserver_handle.stdin.flush()


  def _SendRequest( self, command, arguments = None ):
    """
    Send a request message to TSServer and wait
    for the response.
    """

    request = self._BuildRequest( command, arguments )
    deferred = DeferredResponse()
    with self._pendinglock:
      seq = request[ 'seq' ]
      self._pending[ seq ] = deferred
    with self._writelock:
      self._tsserver_handle.stdin.write( json.dumps( request ) )
      self._tsserver_handle.stdin.write( "\n" )
      self._tsserver_handle.stdin.flush()
    return deferred.result()


  def _Reload( self, request_data ):
    """
    Syncronize TSServer's view of the file to
    the contents of the unsaved buffer.
    """

    filename = request_data[ 'filepath' ]
    contents = request_data[ 'file_data' ][ filename ][ 'contents' ]
    tmpfile = NamedTemporaryFile( delete = False )
    tmpfile.write( utils.ToBytes( contents ) )
    tmpfile.close()
    self._SendRequest( 'reload', {
      'file':    filename,
      'tmpfile': tmpfile.name
    } )
    os.unlink( tmpfile.name )


  def SupportedFiletypes( self ):
    return [ 'typescript' ]


  def ComputeCandidatesInner( self, request_data ):
    self._Reload( request_data )
    entries = self._SendRequest( 'completions', {
      'file':   request_data[ 'filepath' ],
      'line':   request_data[ 'line_num' ],
      'offset': request_data[ 'column_num' ]
    } )

    # A less detailed version of the completion data is returned
    # if there are too many entries. This improves responsiveness.
    if len( entries ) > MAX_DETAILED_COMPLETIONS:
      return [ _ConvertCompletionData(e) for e in entries ]

    names = []
    namelength = 0
    for e in entries:
      name = e[ 'name' ]
      namelength = max( namelength, len( name ) )
      names.append( name )

    detailed_entries = self._SendRequest( 'completionEntryDetails', {
      'file':       request_data[ 'filepath' ],
      'line':       request_data[ 'line_num' ],
      'offset':     request_data[ 'column_num' ],
      'entryNames': names
    } )
    return [ _ConvertDetailedCompletionData( e, namelength )
             for e in detailed_entries ]


  def GetSubcommandsMap( self ):
    return {
      'GoToDefinition' : ( lambda self, request_data, args:
                           self._GoToDefinition( request_data ) ),
      'GoToReferences' : ( lambda self, request_data, args:
                           self._GoToReferences( request_data ) ),
      'GetType'        : ( lambda self, request_data, args:
                           self._GetType( request_data ) ),
      'GetDoc'         : ( lambda self, request_data, args:
                           self._GetDoc( request_data ) ),
      'RefactorRename' : ( lambda self, request_data, args:
                           self._RefactorRename( request_data, args ) ),
    }


  def OnBufferVisit( self, request_data ):
    filename = request_data[ 'filepath' ]
    self._SendCommand( 'open', { 'file': filename } )


  def OnBufferUnload( self, request_data ):
    filename = request_data[ 'filepath' ]
    self._SendCommand( 'close', { 'file': filename } )


  def OnFileReadyToParse( self, request_data ):
    self._Reload( request_data )


  def _GoToDefinition( self, request_data ):
    self._Reload( request_data )
    try:
      filespans = self._SendRequest( 'definition', {
        'file':   request_data[ 'filepath' ],
        'line':   request_data[ 'line_num' ],
        'offset': request_data[ 'column_num' ]
      } )

      span = filespans[ 0 ]
      return responses.BuildGoToResponse(
        filepath   = span[ 'file' ],
        line_num   = span[ 'start' ][ 'line' ],
        column_num = span[ 'start' ][ 'offset' ]
      )
    except RuntimeError:
      raise RuntimeError( 'Could not find definition' )


  def _GoToReferences( self, request_data ):
    self._Reload( request_data )
    response = self._SendRequest( 'references', {
      'file':   request_data[ 'filepath' ],
      'line':   request_data[ 'line_num' ],
      'offset': request_data[ 'column_num' ]
    } )
    return [ responses.BuildGoToResponse(
               filepath    = ref[ 'file' ],
               line_num    = ref[ 'start' ][ 'line' ],
               column_num  = ref[ 'start' ][ 'offset' ],
               description = ref[ 'lineText' ]
             ) for ref in response[ 'refs' ] ]


  def _GetType( self, request_data ):
    self._Reload( request_data )
    info = self._SendRequest( 'quickinfo', {
      'file':   request_data[ 'filepath' ],
      'line':   request_data[ 'line_num' ],
      'offset': request_data[ 'column_num' ]
    } )
    return responses.BuildDisplayMessageResponse( info[ 'displayString' ] )


  def _GetDoc( self, request_data ):
    self._Reload( request_data )
    info = self._SendRequest( 'quickinfo', {
      'file':   request_data[ 'filepath' ],
      'line':   request_data[ 'line_num' ],
      'offset': request_data[ 'column_num' ]
    } )

    message = '{0}\n\n{1}'.format( info[ 'displayString' ],
                                   info[ 'documentation' ] )
    return responses.BuildDetailedInfoResponse( message )


  def _RefactorRename( self, request_data, args ):
    if len( args ) != 1:
      raise ValueError( 'Please specify a new name to rename it to.\n'
                        'Usage: RefactorRename <new name>' )

    self._Reload( request_data )

    response = self._SendRequest( 'rename', {
      'file':   request_data[ 'filepath' ],
      'line':   request_data[ 'line_num' ],
      'offset': request_data[ 'column_num' ],
      'findInComments': False,
      'findInStrings': False,
    } )

    if not response[ 'info' ][ 'canRename' ]:
      raise RuntimeError( 'Value cannot be renamed: {0}'.format(
        response[ 'info' ][ 'localizedErrorMessage' ] ) )

    # The format of the response is:
    #
    # body {
    #   info {
    #     ...
    #     triggerSpan: {
    #       length: original_length
    #     }
    #   }
    #
    #   locs [ {
    #     file: file_path
    #     locs: [
    #       start: {
    #         line: line_num
    #         offset: offset
    #       }
    #       end {
    #         line: line_num
    #         offset: offset
    #       }
    #     ] }
    #   ]
    # }
    #
    new_name = args[ 0 ]
    location = responses.Location( request_data[ 'line_num' ],
                                   request_data[ 'column_num' ],
                                   request_data[ 'filepath' ] )

    chunks = []
    for file_replacement in response[ 'locs' ]:
      chunks.extend( _BuildFixItChunksForFile( new_name, file_replacement ) )

    return responses.BuildFixItResponse( [
      responses.FixIt( location, chunks )
    ] )


  def Shutdown( self ):
    self._SendCommand( 'exit' )
    if not self.user_options[ 'server_keep_logfiles' ]:
      os.unlink( self._logfile )
      self._logfile = None


  def DebugInfo( self, request_data ):
    return ( 'TSServer logfile:\n  {0}' ).format( self._logfile )


def _LogFileName():
  with NamedTemporaryFile( dir = utils.PathToCreatedTempDir(),
                           prefix = 'tsserver_',
                           suffix = '.log',
                           delete = False ) as logfile:
    return logfile.name


def _LogLevel():
  return 'verbose' if _logger.isEnabledFor( logging.DEBUG ) else 'normal'


def _ConvertCompletionData( completion_data ):
  return responses.BuildCompletionData(
    insertion_text = completion_data[ 'name' ],
    menu_text      = completion_data[ 'name' ],
    kind           = completion_data[ 'kind' ],
    extra_data     = completion_data[ 'kind' ]
  )


def _ConvertDetailedCompletionData( completion_data, padding = 0 ):
  name = completion_data[ 'name' ]
  display_parts = completion_data[ 'displayParts' ]
  signature = ''.join( [ p[ 'text' ] for p in display_parts ] )

  # needed to strip new lines and indentation from the signature
  signature = re.sub( '\s+', ' ', signature )
  menu_text = '{0} {1}'.format( name.ljust( padding ), signature )
  return responses.BuildCompletionData(
    insertion_text = name,
    menu_text      = menu_text,
    kind           = completion_data[ 'kind' ]
  )


def _BuildFixItChunkForRange( new_name, file_name, source_range ):
  """ returns list FixItChunk for a tsserver source range """
  return responses.FixItChunk(
      new_name,
      responses.Range(
        start = responses.Location(
                            source_range[ 'start' ][ 'line' ],
                            source_range[ 'start' ][ 'offset' ],
                            file_name ),
        end = responses.Location(
                            source_range[ 'end' ][ 'line' ],
                            source_range[ 'end' ][ 'offset' ],
                            file_name ) ) )


def _BuildFixItChunksForFile( new_name, file_replacement ):
  """ returns a list of FixItChunk for each replacement range for the
  supplied file"""

  # On windows, tsserver annoyingly returns file path as C:/blah/blah,
  # whereas all other paths in Python are of the C:\\blah\\blah form. We use
  # normpath to have python do the conversion for us.
  file_path = os.path.normpath( file_replacement[ 'file' ] )
  _logger.debug( 'Converted {0} to {1}'.format( file_replacement[ 'file' ],
                                                file_path ) )
  return [ _BuildFixItChunkForRange( new_name, file_path, r )
           for r in file_replacement[ 'locs' ] ]
