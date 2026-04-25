#!/bin/bash
cd `dirname $0`
source venv/bin/activate
python3 src/image_viewer.py "$1"
