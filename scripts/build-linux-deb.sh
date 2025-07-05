#!/bin/bash

architecture='amd64'

echo "Clear build dir"
rm -rf build
rm -rf dist
rm -rf deb-gen
rm -rf release

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

echo "clean unused files"
rm -vf dist/NetConfTool/libQt5Egl*
rm -vf dist/NetConfTool/libQt5Network*
rm -vf dist/NetConfTool/libQt5QmlModels*
rm -vf dist/NetConfTool/libQt5Qml*
rm -vf dist/NetConfTool/libQt5Quick*
rm -vf dist/NetConfTool/libQt5WebSockets*
rm -vf dist/NetConfTool/libicu*66
rm -vf dist/NetConfTool/libicu*70
rm -vf dist/NetConfTool/PyQt5/Qt5/translations/*
rm -vf dist/NetConfTool/PyQt5/Qt5/plugins/egldeviceintegrations/*
rm -vf dist/NetConfTool/PyQt5/Qt5/plugins/platforms/libqeglfs*
rm -vf dist/NetConfTool/PyQt5/Qt5/plugins/platforms/libqwebgl*
rm -vf dist/NetConfTool/PyQt5/Qt5/plugins/platforms/libqminimalegl*

mkdir -p deb-gen/usr/lib
mkdir -p deb-gen/usr/share/applications
mkdir -p deb-gen/usr/bin

cp -a linux/DEBIAN deb-gen
# gen version
version_code=$(head -n 1 dist/NetConfTool/VERSION)
sed -i "2 i version: ${version_code}" deb-gen/DEBIAN/control
sed -i "3 i architecture: ${architecture}" deb-gen/DEBIAN/control

cp -a 'dist/NetConfTool' deb-gen/usr/lib/
ln -sf '/usr/lib/NetConfTool/NetConf Tool' deb-gen/usr/bin/netconftool
cp -a linux/NetConfTool.desktop deb-gen/usr/share/applications

mkdir -p release
dpkg -b deb-gen release/netconftool_${version_code}_${architecture}.deb

# post build
git restore RELEASE_INFO