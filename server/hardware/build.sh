#!/bin/bash
# Build C++ hardware driver as Python extension for RPi CM5
#
# Prerequisites:
#   sudo apt install libgpiod-dev python3-pybind11 python3-dev g++
#
# Run from server/hardware/ directory:
#   chmod +x build.sh && ./build.sh

set -e

echo "Building sCure hardware driver..."

g++ -O2 -shared -fPIC \
    -o hw_driver$(python3-config --extension-suffix) \
    hw_driver.cpp \
    $(python3 -m pybind11 --includes) \
    -lgpiod -lpthread

echo "Done! hw_driver built successfully."
echo "Copy to server/ directory: cp hw_driver*.so ../"
