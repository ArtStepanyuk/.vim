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

from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

from nose.tools import eq_
from hamcrest import ( assert_that, contains, contains_inanyorder, empty,
                       has_item, has_items, has_entry, has_entries )
import http.client

from ycmd.completers.cpp.clang_completer import NO_COMPLETIONS_MESSAGE
from ycmd.responses import UnknownExtraConf, NoExtraConfDetected
from ycmd.tests.clang import IsolatedYcmd, PathToTestFile, SharedYcmd
from ycmd.tests.test_utils import ( BuildRequest, CompletionEntryMatcher,
                                    ErrorMatcher, UserOption )
from ycmd.utils import ReadFile

NO_COMPLETIONS_ERROR = ErrorMatcher( RuntimeError, NO_COMPLETIONS_MESSAGE )


def RunTest( app, test ):
  """
  Method to run a simple completion test and verify the result

  Note: uses the .ycm_extra_conf from general_fallback/ which:
   - supports cpp, c and objc
   - requires extra_conf_data containing 'filetype&' = the filetype

  this should be sufficient for many standard test cases

  test is a dictionary containing:
    'request': kwargs for BuildRequest
    'expect': {
       'response': server response code (e.g. httplib.OK)
       'data': matcher for the server response json
    }
  """
  app.post_json( '/load_extra_conf_file', {
    'filepath': PathToTestFile( 'general_fallback',
                                '.ycm_extra_conf.py' ) } )


  contents = ReadFile( test[ 'request' ][ 'filepath' ] )

  def CombineRequest( request, data ):
    kw = request
    request.update( data )
    return BuildRequest( **kw )

  # Because we aren't testing this command, we *always* ignore errors. This
  # is mainly because we (may) want to test scenarios where the completer
  # throws an exception and the easiest way to do that is to throw from
  # within the FlagsForFile function.
  app.post_json( '/event_notification',
                 CombineRequest( test[ 'request' ], {
                   'event_name': 'FileReadyToParse',
                   'contents': contents,
                 } ),
                 expect_errors = True )

  # We also ignore errors here, but then we check the response code ourself.
  # This is to allow testing of requests returning errors.
  response = app.post_json( '/completions',
                            CombineRequest( test[ 'request' ], {
                              'contents': contents
                            } ),
                            expect_errors = True )

  eq_( response.status_code, test[ 'expect' ][ 'response' ] )

  assert_that( response.json, test[ 'expect' ][ 'data' ] )


@SharedYcmd
def GetCompletions_ForcedWithNoTrigger_test( app ):
  RunTest( app, {
    'description': 'semantic completion with force query=DO_SO',
    'request': {
      'filetype'  : 'cpp',
      'filepath'  : PathToTestFile( 'general_fallback',
                                    'lang_cpp.cc' ),
      'line_num'  : 54,
      'column_num': 8,
      'extra_conf_data': { '&filetype': 'cpp' },
      'force_semantic': True,
    },
    'expect': {
      'response': http.client.OK,
      'data': has_entries( {
        'completions': contains(
          CompletionEntryMatcher( 'DO_SOMETHING_TO', 'void' ),
          CompletionEntryMatcher( 'DO_SOMETHING_WITH', 'void' ),
        ),
        'errors': empty(),
      } )
    },
  } )


@SharedYcmd
def GetCompletions_Fallback_NoSuggestions_test( app ):
  # TESTCASE1 (general_fallback/lang_c.c)
  RunTest( app, {
    'description': 'Triggered, fallback but no query so no completions',
    'request': {
      'filetype'  : 'c',
      'filepath'  : PathToTestFile( 'general_fallback', 'lang_c.c' ),
      'line_num'  : 29,
      'column_num': 21,
      'extra_conf_data': { '&filetype': 'c' },
      'force_semantic': False,
    },
    'expect': {
      'response': http.client.OK,
      'data': has_entries( {
        'completions': empty(),
        'errors': has_item( NO_COMPLETIONS_ERROR ),
      } )
    },
  } )


@SharedYcmd
def GetCompletions_Fallback_NoSuggestions_MinimumCharaceters_test( app ):
  # TESTCASE1 (general_fallback/lang_cpp.cc)
  RunTest( app, {
    'description': 'fallback general completion obeys min chars setting '
                   ' (query="a")',
    'request': {
      'filetype'  : 'cpp',
      'filepath'  : PathToTestFile( 'general_fallback',
                                    'lang_cpp.cc' ),
      'line_num'  : 21,
      'column_num': 22,
      'extra_conf_data': { '&filetype': 'cpp' },
      'force_semantic': False,
    },
    'expect': {
      'response': http.client.OK,
      'data': has_entries( {
        'completions': empty(),
        'errors': has_item( NO_COMPLETIONS_ERROR ),
      } )
    },
  } )


@SharedYcmd
def GetCompletions_Fallback_Suggestions_test( app ):
  # TESTCASE1 (general_fallback/lang_c.c)
  RunTest( app, {
    'description': '. after macro with some query text (.a_)',
    'request': {
      'filetype'  : 'c',
      'filepath'  : PathToTestFile( 'general_fallback', 'lang_c.c' ),
      'line_num'  : 29,
      'column_num': 23,
      'extra_conf_data': { '&filetype': 'c' },
      'force_semantic': False,
    },
    'expect': {
      'response': http.client.OK,
      'data': has_entries( {
        'completions': has_item( CompletionEntryMatcher( 'a_parameter',
                                                         '[ID]' ) ),
        'errors': has_item( NO_COMPLETIONS_ERROR ),
      } )
    },
  } )


@SharedYcmd
def GetCompletions_Fallback_Exception_test( app ):
  # TESTCASE4 (general_fallback/lang_c.c)
  # extra conf throws exception
  RunTest( app, {
    'description': '. on struct returns identifier because of error',
    'request': {
      'filetype'  : 'c',
      'filepath'  : PathToTestFile( 'general_fallback', 'lang_c.c' ),
      'line_num'  : 62,
      'column_num': 20,
      'extra_conf_data': { '&filetype': 'c', 'throw': 'testy' },
      'force_semantic': False,
    },
    'expect': {
      'response': http.client.OK,
      'data': has_entries( {
        'completions': contains(
          CompletionEntryMatcher( 'a_parameter', '[ID]' ),
          CompletionEntryMatcher( 'another_parameter', '[ID]' ),
        ),
        'errors': has_item( ErrorMatcher( ValueError, 'testy' ) )
      } )
    },
  } )


@SharedYcmd
def GetCompletions_Forced_NoFallback_test( app ):
  # TESTCASE2 (general_fallback/lang_c.c)
  RunTest( app, {
    'description': '-> after macro with forced semantic',
    'request': {
      'filetype'  : 'c',
      'filepath'  : PathToTestFile( 'general_fallback', 'lang_c.c' ),
      'line_num'  : 41,
      'column_num': 30,
      'extra_conf_data': { '&filetype': 'c' },
      'force_semantic': True,
    },
    'expect': {
      'response': http.client.INTERNAL_SERVER_ERROR,
      'data': NO_COMPLETIONS_ERROR,
    },
  } )


@SharedYcmd
def GetCompletions_FilteredNoResults_Fallback_test( app ):
  # no errors because the semantic completer returned results, but they
  # were filtered out by the query, so this is considered working OK
  # (whereas no completions from the semantic engine is considered an
  # error)

  # TESTCASE5 (general_fallback/lang_cpp.cc)
  RunTest( app, {
    'description': '. on struct returns IDs after query=do_',
    'request': {
      'filetype':   'c',
      'filepath':   PathToTestFile( 'general_fallback', 'lang_c.c' ),
      'line_num':   71,
      'column_num': 18,
      'extra_conf_data': { '&filetype': 'c' },
      'force_semantic': False,
    },
    'expect': {
      'response': http.client.OK,
      'data': has_entries( {
        'completions': contains_inanyorder(
          # do_ is an identifier because it is already in the file when we
          # load it
          CompletionEntryMatcher( 'do_', '[ID]' ),
          CompletionEntryMatcher( 'do_something', '[ID]' ),
          CompletionEntryMatcher( 'do_another_thing', '[ID]' ),
        ),
        'errors': empty()
      } )
    },
  } )


@SharedYcmd
def GetCompletions_WorksWithExplicitFlags_test( app ):
  app.post_json(
    '/ignore_extra_conf_file',
    { 'filepath': PathToTestFile( '.ycm_extra_conf.py' ) } )
  contents = """
struct Foo {
  int x;
  int y;
  char c;
};

int main()
{
  Foo foo;
  foo.
}
"""

  completion_data = BuildRequest( filepath = '/foo.cpp',
                                  filetype = 'cpp',
                                  contents = contents,
                                  line_num = 11,
                                  column_num = 7,
                                  compilation_flags = ['-x', 'c++'] )

  response_data = app.post_json( '/completions', completion_data ).json
  assert_that( response_data[ 'completions'],
               has_items( CompletionEntryMatcher( 'c' ),
                          CompletionEntryMatcher( 'x' ),
                          CompletionEntryMatcher( 'y' ) ) )
  eq_( 7, response_data[ 'completion_start_column' ] )


@SharedYcmd
def GetCompletions_NoCompletionsWhenAutoTriggerOff_test( app ):
  with UserOption( 'auto_trigger', False ):
    app.post_json(
      '/ignore_extra_conf_file',
      { 'filepath': PathToTestFile( '.ycm_extra_conf.py' ) } )
    contents = """
struct Foo {
  int x;
  int y;
  char c;
};

int main()
{
  Foo foo;
  foo.
}
"""

    completion_data = BuildRequest( filepath = '/foo.cpp',
                                    filetype = 'cpp',
                                    contents = contents,
                                    line_num = 11,
                                    column_num = 7,
                                    compilation_flags = ['-x', 'c++'] )

    results = app.post_json( '/completions',
                             completion_data ).json[ 'completions' ]
    assert_that( results, empty() )


@IsolatedYcmd
def GetCompletions_UnknownExtraConfException_test( app ):
  filepath = PathToTestFile( 'basic.cpp' )
  completion_data = BuildRequest( filepath = filepath,
                                  filetype = 'cpp',
                                  contents = ReadFile( filepath ),
                                  line_num = 11,
                                  column_num = 7,
                                  force_semantic = True )

  response = app.post_json( '/completions',
                            completion_data,
                            expect_errors = True )

  eq_( response.status_code, http.client.INTERNAL_SERVER_ERROR )
  assert_that( response.json,
               has_entry( 'exception',
                          has_entry( 'TYPE', UnknownExtraConf.__name__ ) ) )

  app.post_json(
    '/ignore_extra_conf_file',
    { 'filepath': PathToTestFile( '.ycm_extra_conf.py' ) } )

  response = app.post_json( '/completions',
                            completion_data,
                            expect_errors = True )

  eq_( response.status_code, http.client.INTERNAL_SERVER_ERROR )
  assert_that( response.json,
               has_entry( 'exception',
                          has_entry( 'TYPE',
                                     NoExtraConfDetected.__name__ ) ) )


@IsolatedYcmd
def GetCompletions_WorksWhenExtraConfExplicitlyAllowed_test( app ):
  app.post_json(
    '/load_extra_conf_file',
    { 'filepath': PathToTestFile( '.ycm_extra_conf.py' ) } )

  filepath = PathToTestFile( 'basic.cpp' )
  completion_data = BuildRequest( filepath = filepath,
                                  filetype = 'cpp',
                                  contents = ReadFile( filepath ),
                                  line_num = 11,
                                  column_num = 7 )

  results = app.post_json( '/completions',
                           completion_data ).json[ 'completions' ]
  assert_that( results, has_items( CompletionEntryMatcher( 'c' ),
                                   CompletionEntryMatcher( 'x' ),
                                   CompletionEntryMatcher( 'y' ) ) )


@SharedYcmd
def GetCompletions_ExceptionWhenNoFlagsFromExtraConf_test( app ):
  app.post_json(
    '/load_extra_conf_file',
    { 'filepath': PathToTestFile( 'noflags',
                                  '.ycm_extra_conf.py' ) } )

  filepath = PathToTestFile( 'noflags', 'basic.cpp' )

  completion_data = BuildRequest( filepath = filepath,
                                  filetype = 'cpp',
                                  contents = ReadFile( filepath ),
                                  line_num = 11,
                                  column_num = 7,
                                  force_semantic = True )

  response = app.post_json( '/completions',
                            completion_data,
                            expect_errors = True )
  eq_( response.status_code, http.client.INTERNAL_SERVER_ERROR )

  assert_that( response.json,
               has_entry( 'exception',
                          has_entry( 'TYPE', RuntimeError.__name__ ) ) )


@SharedYcmd
def GetCompletions_ForceSemantic_OnlyFilteredCompletions_test( app ):
  contents = """
int main()
{
  int foobar;
  int floozar;
  int gooboo;
  int bleble;

  fooar
}
"""

  completion_data = BuildRequest( filepath = '/foo.cpp',
                                  filetype = 'cpp',
                                  force_semantic = True,
                                  contents = contents,
                                  line_num = 9,
                                  column_num = 8,
                                  compilation_flags = ['-x', 'c++'] )

  results = app.post_json( '/completions',
                           completion_data ).json[ 'completions' ]
  assert_that(
    results,
    contains_inanyorder( CompletionEntryMatcher( 'foobar' ),
                         CompletionEntryMatcher( 'floozar' ) )
  )


@SharedYcmd
def GetCompletions_ClientDataGivenToExtraConf_test( app ):
  app.post_json(
    '/load_extra_conf_file',
    { 'filepath': PathToTestFile( 'client_data',
                                  '.ycm_extra_conf.py' ) } )

  filepath = PathToTestFile( 'client_data', 'main.cpp' )
  completion_data = BuildRequest( filepath = filepath,
                                  filetype = 'cpp',
                                  contents = ReadFile( filepath ),
                                  line_num = 9,
                                  column_num = 7,
                                  extra_conf_data = {
                                    'flags': ['-x', 'c++']
                                  } )

  results = app.post_json( '/completions',
                           completion_data ).json[ 'completions' ]
  assert_that( results, has_item( CompletionEntryMatcher( 'x' ) ) )


@SharedYcmd
def GetCompletions_FilenameCompleter_ClientDataGivenToExtraConf_test( app ):
  app.post_json(
    '/load_extra_conf_file',
    { 'filepath': PathToTestFile( 'client_data',
                                  '.ycm_extra_conf.py' ) } )

  filepath = PathToTestFile( 'client_data', 'include.cpp' )
  completion_data = BuildRequest( filepath = filepath,
                                  filetype = 'cpp',
                                  contents = ReadFile( filepath ),
                                  line_num = 1,
                                  column_num = 11,
                                  extra_conf_data = {
                                    'flags': ['-x', 'c++']
                                  } )

  results = app.post_json( '/completions',
                           completion_data ).json[ 'completions' ]
  assert_that(
    results,
    has_item( CompletionEntryMatcher( 'include.hpp',
              extra_menu_info = '[File]' ) )
  )
