#!/bin/bash

set -ev

####################
# OS-specific setup
####################

# Requirements of OS-specific install:
#  - install any software which is not installed by Travis configuration
#  - set up everything necessary so that pyenv can build python
source ci/travis/travis_install.${TRAVIS_OS_NAME}.sh

#############
# pyenv setup
#############

# DON'T exit if error
set +e
git clone https://github.com/yyuu/pyenv.git ~/.pyenv
git fetch --tags
git checkout v20160202
# Exit if error
set -e

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

eval "$(pyenv init -)"

if [ "${YCMD_PYTHON_VERSION}" == "2.6" ]; then
  PYENV_VERSION="2.6.6"
elif [ "${YCMD_PYTHON_VERSION}" == "2.7" ]; then
  PYENV_VERSION="2.7.6"
else
  PYENV_VERSION="3.3.6"
fi

pyenv install --skip-existing ${PYENV_VERSION}
pyenv rehash
pyenv global ${PYENV_VERSION}

# It is quite easy to get the above series of steps wrong. Verify that the
# version of python actually in the path and used is the version that was
# requested, and fail the build if we broke the travis setup
python_version=$(python -c 'import sys; print( "{0}.{1}".format( sys.version_info[0], sys.version_info[1] ) )')
echo "Checking python version (actual ${python_version} vs expected ${YCMD_PYTHON_VERSION})"
test ${python_version} == ${YCMD_PYTHON_VERSION}


############
# pip setup
############

pip install -U pip wheel setuptools
pip install -r test_requirements.txt
npm install -g typescript

# We run coverage tests only on a single build, where COVERAGE=true
if [ x"${COVERAGE}" = x"true" ]; then
  pip install coveralls
fi


############
# rust setup
############

# Need rust available, but travis doesn't give it to you without language: rust
pushd ${HOME}
git clone --recursive https://github.com/brson/multirust
cd multirust
git reset --hard f3974f2b966476ad656afba311b50a9c23fe6d2e
./build.sh
./install.sh --prefix=${HOME}
popd

multirust update stable
multirust default stable

# The build infrastructure prints a lot of spam after this script runs, so make
# sure to disable printing, and failing on non-zero exit code after this script
# finishes
set +ev
