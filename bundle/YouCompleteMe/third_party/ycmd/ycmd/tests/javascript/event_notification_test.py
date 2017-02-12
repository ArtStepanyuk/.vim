# Copyright (C) 2015 ycmd contributors
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

from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import division
from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

from hamcrest import assert_that, empty
from mock import patch
from nose.tools import eq_
from pprint import pformat
import http.client
import os

from ycmd.tests.test_utils import BuildRequest, ErrorMatcher
from ycmd.tests.javascript import ( IsolatedYcmd, PathToTestFile,
                                    WaitUntilTernServerReady )
from ycmd.utils import ReadFile


@IsolatedYcmd
def EventNotification_OnFileReadyToParse_ProjectFile_cwd_test( app ):
  contents = ReadFile( PathToTestFile( 'simple_test.js' ) )

  response = app.post_json( '/event_notification',
                            BuildRequest(
                              event_name = 'FileReadyToParse',
                              contents = contents,
                              filetype = 'javascript' ),
                            expect_errors = True)

  eq_( response.status_code, http.client.OK )
  assert_that( response.json, empty() )


@IsolatedYcmd
def EventNotification_OnFileReadyToParse_ProjectFile_parentdir_test( app ):
  os.chdir( PathToTestFile( 'lamelib' ) )
  contents = ReadFile( PathToTestFile( 'simple_test.js' ) )

  response = app.post_json( '/event_notification',
                            BuildRequest(
                              event_name = 'FileReadyToParse',
                              contents = contents,
                              filetype = 'javascript' ),
                            expect_errors = True)

  eq_( response.status_code, http.client.OK )
  assert_that( response.json, empty() )


@IsolatedYcmd
@patch( 'ycmd.completers.javascript.tern_completer.GlobalConfigExists',
        return_value = False )
def EventNotification_OnFileReadyToParse_NoProjectFile_test( app, *args ):
  # We raise an error if we can't detect a .tern-project file.
  # We only do this on the first OnFileReadyToParse event after a
  # server startup.
  os.chdir( PathToTestFile( '..' ) )
  contents = ReadFile( PathToTestFile( 'simple_test.js' ) )

  response = app.post_json( '/event_notification',
                            BuildRequest(
                              event_name = 'FileReadyToParse',
                              contents = contents,
                              filetype = 'javascript' ),
                            expect_errors = True )

  print( 'event response: {0}'.format( pformat( response.json ) ) )

  eq_( response.status_code, http.client.INTERNAL_SERVER_ERROR )

  assert_that(
    response.json,
    ErrorMatcher( RuntimeError,
                  'Warning: Unable to detect a .tern-project file '
                  'in the hierarchy before ' + os.getcwd() +
                  ' and no global .tern-config file was found. '
                  'This is required for accurate JavaScript '
                  'completion. Please see the User Guide for '
                  'details.' )
  )

  # Check that a subsequent call does *not* raise the error

  response = app.post_json( '/event_notification',
                            BuildRequest(
                              event_name = 'FileReadyToParse',
                              contents = contents,
                              filetype = 'javascript' ),
                            expect_errors = True )

  print( 'event response: {0}'.format( pformat( response.json ) ) )

  eq_( response.status_code, http.client.OK )
  assert_that( response.json, empty() )

  # Restart the server and check that it raises it again

  app.post_json( '/run_completer_command',
                 BuildRequest( command_arguments = [ 'StopServer' ],
                               filetype = 'javascript',
                               contents = contents,
                               completer_target = 'filetype_default' ) )
  app.post_json( '/run_completer_command',
                 BuildRequest( command_arguments = [ 'StartServer' ],
                               filetype = 'javascript',
                               contents = contents,
                               completer_target = 'filetype_default' ) )

  WaitUntilTernServerReady( app )

  response = app.post_json( '/event_notification',
                            BuildRequest( event_name = 'FileReadyToParse',
                                          contents = contents,
                                          filetype = 'javascript' ),
                            expect_errors = True )

  print( 'event response: {0}'.format( pformat( response.json ) ) )

  eq_( response.status_code, http.client.INTERNAL_SERVER_ERROR )

  assert_that(
    response.json,
    ErrorMatcher( RuntimeError,
                  'Warning: Unable to detect a .tern-project file '
                  'in the hierarchy before ' + os.getcwd() +
                  ' and no global .tern-config file was found. '
                  'This is required for accurate JavaScript '
                  'completion. Please see the User Guide for '
                  'details.' )
  )


@IsolatedYcmd
@patch( 'ycmd.completers.javascript.tern_completer.GlobalConfigExists',
        return_value = True )
def EventNotification_OnFileReadyToParse_UseGlobalConfig_test( app, *args ):
  os.chdir( PathToTestFile( '..' ) )
  contents = ReadFile( PathToTestFile( 'simple_test.js' ) )

  response = app.post_json( '/event_notification',
                            BuildRequest( event_name = 'FileReadyToParse',
                                          contents = contents,
                                          filetype = 'javascript' ),
                            expect_errors = True )

  print( 'event response: {0}'.format( pformat( response.json ) ) )

  eq_( response.status_code, http.client.OK )
