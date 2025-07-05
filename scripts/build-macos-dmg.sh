#!/bin/bash

architecture='intel'

echo "Clear build dir"
rm -rf build
rm -rf dist

echo "Create build env"
python3 -m venv venv
source ./venv/bin/activate

pip install -r ../requirements.txt

if [ -n "$(git status --porcelain)" ]; then
    echo cvs=`git rev-parse --short HEAD`-dirty > RELEASE_INFO
else
    echo cvs=`git rev-parse --short HEAD` > RELEASE_INFO
fi
echo btime=`date '+%Y/%m/%d %H:%M'` >> RELEASE_INFO
cat RELEASE_INFO

echo "compile qrc resource"
pyrcc5 -o ../res_rc.py ../res.qrc

echo "start pyinstall build"
pyinstaller --noconfirm NetConfTool.spec

# gen version
version_code=$(head -n 1 dist/NetConfTool/VERSION)
dmg_name="NetConfTool_${version_code}_macos-${architecture}.dmg"
# Create a folder (named dmg) to prepare our DMG in (if it doesn't already exist).
mkdir -p dist/dmg
mkdir -p release
# Empty the dmg folder.
rm -rf dist/dmg/*
# Copy the app bundle to the dmg folder.
cp -rf "dist/NetConf Tool.app" dist/dmg
# If the DMG already exists, delete it.
test -f "release/${dmg_name}" && rm "release/${dmg_name}"

create-dmg \
  --volname "NetConf Tool" \
  --volicon "../res/logo.icns" \
  --window-pos 200 120 \
  --window-size 600 600 \
  --icon-size 100 \
  --icon "NetConf Tool.app" 175 120 \
  --hide-extension "NetConf Tool.app" \
  --app-drop-link 425 120 \
  --add-file "VERSION.txt" "../VERSION" 175 370 \
  --add-file "CHANGELOG.txt" "../CHANGELOG.txt" 425 370 \
  --hdiutil-quiet \
  "release/${dmg_name}" \
  "dist/dmg/"

# post build
git restore RELEASE_INFO