# Copyright (C) 2011, 2012 Google Inc.
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
from future.utils import PY2, native

import tempfile
import os
import sys
import signal
import socket
import stat
import subprocess


# Creation flag to disable creating a console window on Windows. See
# https://msdn.microsoft.com/en-us/library/windows/desktop/ms684863.aspx
CREATE_NO_WINDOW = 0x08000000
# Executable extensions used on Windows
WIN_EXECUTABLE_EXTS = [ '.exe', '.bat', '.cmd' ]

# Don't use this! Call PathToCreatedTempDir() instead. This exists for the sake
# of tests.
RAW_PATH_TO_TEMP_DIR = os.path.join( tempfile.gettempdir(), 'ycm_temp' )

# Readable, writable and executable by everyone.
ACCESSIBLE_TO_ALL_MASK = ( stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH |
                           stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP )


# Python 3 complains on the common open(path).read() idiom because the file
# doesn't get closed. So, a helper func.
# Also, all files we read are UTF-8.
def ReadFile( filepath ):
  with open( filepath, encoding = 'utf8' ) as f:
    return f.read()


# Returns a file object that can be used to replace sys.stdout or sys.stderr
def OpenForStdHandle( filepath ):
  # Need to open the file in binary mode on py2 because of bytes vs unicode.
  # If we open in text mode (default), then third-party code that uses `print`
  # (we're replacing sys.stdout!) with an `str` object on py2 will cause
  # tracebacks because text mode insists on unicode objects. (Don't forget,
  # `open` is actually `io.open` because of future builtins.)
  return open( filepath, 'wb' if PY2 else 'w' )


# Given an object, returns a str object that's utf-8 encoded. This is meant to
# be used exclusively when producing strings to be passed to the C++ Python
# plugins. For other code, you likely want to use ToBytes below.
def ToCppStringCompatible( value ):
  if isinstance( value, str ):
    return native( value.encode( 'utf8' ) )
  if isinstance( value, bytes ):
    return native( value )
  return native( str( value ).encode( 'utf8' ) )


# Returns a unicode type; either the new python-future str type or the real
# unicode type. The difference shouldn't matter.
def ToUnicode( value ):
  if not value:
    return str()
  if isinstance( value, str ):
    return value
  if isinstance( value, bytes ):
    # All incoming text should be utf8
    return str( value, 'utf8' )
  return str( value )


# Consistently returns the new bytes() type from python-future. Assumes incoming
# strings are either UTF-8 or unicode (which is converted to UTF-8).
def ToBytes( value ):
  if not value:
    return bytes()

  # This is tricky. On py2, the bytes type from builtins (from python-future) is
  # a subclass of str. So all of the following are true:
  #   isinstance(str(), bytes)
  #   isinstance(bytes(), str)
  # But they don't behave the same in one important aspect: iterating over a
  # bytes instance yields ints, while iterating over a (raw, py2) str yields
  # chars. We want consistent behavior so we force the use of bytes().
  if type( value ) == bytes:
    return value

  # This is meant to catch Python 2's native str type.
  if isinstance( value, bytes ):
    return bytes( value, encoding = 'utf8' )

  if isinstance( value, str ):
    # On py2, with `from builtins import *` imported, the following is true:
    #
    #   bytes(str(u'abc'), 'utf8') == b"b'abc'"
    #
    # Obviously this is a bug in python-future. So we work around it. Also filed
    # upstream at: https://github.com/PythonCharmers/python-future/issues/193
    # We can't just return value.encode( 'utf8' ) on both py2 & py3 because on
    # py2 that *sometimes* returns the built-in str type instead of the newbytes
    # type from python-future.
    if PY2:
      return bytes( value.encode( 'utf8' ), encoding = 'utf8' )
    else:
      return bytes( value, encoding = 'utf8' )

  # This is meant to catch `int` and similar non-string/bytes types.
  return ToBytes( str( value ) )


def PathToCreatedTempDir( tempdir = RAW_PATH_TO_TEMP_DIR ):
  try:
    os.makedirs( tempdir )
    # Needed to support multiple users working on the same machine;
    # see issue 606.
    MakeFolderAccessibleToAll( tempdir )
  except OSError:
    # Folder already exists, skip folder creation.
    pass
  return tempdir


def MakeFolderAccessibleToAll( path_to_folder ):
  current_stat = os.stat( path_to_folder )
  flags = current_stat.st_mode | ACCESSIBLE_TO_ALL_MASK
  os.chmod( path_to_folder, flags )


def GetUnusedLocalhostPort():
  sock = socket.socket()
  # This tells the OS to give us any free port in the range [1024 - 65535]
  sock.bind( ( '', 0 ) )
  port = sock.getsockname()[ 1 ]
  sock.close()
  return port


def RemoveIfExists( filename ):
  try:
    os.remove( filename )
  except OSError:
    pass


def PathToFirstExistingExecutable( executable_name_list ):
  for executable_name in executable_name_list:
    path = FindExecutable( executable_name )
    if path:
      return path
  return None


# On Windows, distutils.spawn.find_executable only works for .exe files
# but .bat and .cmd files are also executables, so we use our own
# implementation.
def FindExecutable( executable ):
  paths = os.environ[ 'PATH' ].split( os.pathsep )
  base, extension = os.path.splitext( executable )

  if OnWindows() and extension.lower() not in WIN_EXECUTABLE_EXTS:
    extensions = WIN_EXECUTABLE_EXTS
  else:
    extensions = ['']

  for extension in extensions:
    executable_name = executable + extension
    if not os.path.isfile( executable_name ):
      for path in paths:
        executable_path = os.path.join(path, executable_name )
        if os.path.isfile( executable_path ):
          return executable_path
    else:
      return executable_name
  return None


def ExecutableName( executable ):
  return executable + ( '.exe' if OnWindows() else '' )


def OnWindows():
  return sys.platform == 'win32'


def OnCygwin():
  return sys.platform == 'cygwin'


def OnMac():
  return sys.platform == 'darwin'


def OnTravis():
  return 'TRAVIS' in os.environ


def ProcessIsRunning( handle ):
  return handle is not None and handle.poll() is None


# From here: http://stackoverflow.com/a/8536476/1672783
def TerminateProcess( pid ):
  if OnWindows():
    import ctypes
    PROCESS_TERMINATE = 1
    handle = ctypes.windll.kernel32.OpenProcess( PROCESS_TERMINATE,
                                                 False,
                                                 pid )
    ctypes.windll.kernel32.TerminateProcess( handle, -1 )
    ctypes.windll.kernel32.CloseHandle( handle )
  else:
    os.kill( pid, signal.SIGTERM )


def PathsToAllParentFolders( path ):
  folder = os.path.normpath( path )
  if os.path.isdir( folder ):
    yield folder
  while True:
    parent = os.path.dirname( folder )
    if parent == folder:
      break
    folder = parent
    yield folder


def ForceSemanticCompletion( request_data ):
  return ( 'force_semantic' in request_data and
           bool( request_data[ 'force_semantic' ] ) )


# A wrapper for subprocess.Popen that fixes quirks on Windows.
def SafePopen( args, **kwargs ):
  if OnWindows():
    # We need this to start the server otherwise bad things happen.
    # See issue #637.
    if kwargs.get( 'stdin_windows' ) is subprocess.PIPE:
      kwargs[ 'stdin' ] = subprocess.PIPE
    # Do not create a console window
    kwargs[ 'creationflags' ] = CREATE_NO_WINDOW
    # Python 2 fails to spawn a process from a command containing unicode
    # characters on Windows.  See https://bugs.python.org/issue19264 and
    # http://bugs.python.org/issue1759845.
    # Since paths are likely to contains such characters, we convert them to
    # short ones to obtain paths with only ascii characters.
    if PY2:
      args = ConvertArgsToShortPath( args )

  kwargs.pop( 'stdin_windows', None )
  return subprocess.Popen( args, **kwargs )


# We need to convert environment variables to native strings on Windows and
# Python 2 to prevent a TypeError when passing them to a subprocess.
def SetEnviron( environ, variable, value ):
  if OnWindows() and PY2:
    environ[ native( ToBytes( variable ) ) ] = native( ToBytes( value ) )
  else:
    environ[ variable ] = value


# Convert paths in arguments command to short path ones
def ConvertArgsToShortPath( args ):
  def ConvertIfPath( arg ):
    if os.path.exists( arg ):
      return GetShortPathName( arg )
    return arg

  if isinstance( args, str ) or isinstance( args, bytes ):
    return ConvertIfPath( args )
  return [ ConvertIfPath( arg ) for arg in args ]


# Get the Windows short path name.
# Based on http://stackoverflow.com/a/23598461/200291
def GetShortPathName( path ):
  if not OnWindows():
    return path

  from ctypes import windll, wintypes, create_unicode_buffer

  # Set the GetShortPathNameW prototype
  _GetShortPathNameW = windll.kernel32.GetShortPathNameW
  _GetShortPathNameW.argtypes = [ wintypes.LPCWSTR,
                                  wintypes.LPWSTR,
                                  wintypes.DWORD]
  _GetShortPathNameW.restype = wintypes.DWORD

  output_buf_size = 0

  while True:
    output_buf = create_unicode_buffer( output_buf_size )
    needed = _GetShortPathNameW( path, output_buf, output_buf_size )
    if output_buf_size >= needed:
      return output_buf.value
    else:
      output_buf_size = needed


# Shim for imp.load_source so that it works on both Py2 & Py3. See upstream
# Python docs for info on what this does.
def LoadPythonSource( name, pathname ):
  if PY2:
    import imp
    return imp.load_source( name, pathname )
  else:
    import importlib
    return importlib.machinery.SourceFileLoader( name, pathname ).load_module()
