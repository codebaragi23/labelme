#!/bin/bash

title="build mindAT for ubuntu18.04"
echo -ne '\033k'$title'\033\\'

pip install virtualenv

if ! [ -d "venv" ]; then
  echo "------------------->>Create virtualenv"
  virtualenv venv
  invalide_venv=1
fi

. ./venv/bin/activate

if [ -z "$invalide_venv" ]; then
  echo "------------------->>Install python packages"
  pip install -r requirements_ubuntu18.04.txt
  pip install pyinstaller
fi

if [-f "./build"]; then
  rm -rf "./build"
fi

if [-f "./dist"]; then
  rm -rf "./dist"
fi

echo "------------------->>Build spec"
pyinstaller mindAT_ubutnu18.04.spec

. ./venv/bin/deactivate
