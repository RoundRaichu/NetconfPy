#!/bin/bash
VER=$(head -n 1 ../VERSION)

cp -avf ../CHANGELOG.txt /srv/netconftool
echo -n ${VER} > /srv/netconftool/LATEST.TXT

# Windows
release_path="/srv/netconftool/windows"
if [ -f release/NetConfTool_Setup_v${VER}.exe ];then
   cp -avf release/NetConfTool_Setup_v${VER}.exe ${release_path}
   ln -svf NetConfTool_Setup_v${VER}.exe ${release_path}/NetConfTool-win-lastest.exe
   cp -avf ../CHANGELOG.txt ${release_path}
   echo -n ${VER} > ${release_path}/LATEST.TXT
fi

if [ -f release/NetConfTool_Portable_v${VER}.zip ]; then
    cp -avf release/NetConfTool_Portable_v${VER}.zip ${release_path}
    ln -svf NetConfTool_Portable_v${VER}.zip ${release_path}/NetConfTool-win-Portable-lastest.zip
    cp -avf ../CHANGELOG.txt ${release_path}
    echo -n ${VER} > ${release_path}/LATEST.TXT

    echo "Publish ${release_path} success"
    echo "The lastest version: "$(cat ${release_path}/LATEST.TXT)
fi

# macOS
release_path="/srv/netconftool/macos"
if [ -f release/NetConfTool_${VER}_macos-intel.dmg ];then
    cp -avf release/NetConfTool_${VER}_macos-intel.dmg ${release_path}
    ln -svf NetConfTool_${VER}_macos-intel.dmg ${release_path}/NetConfTool-macos-intel-lastest.dmg
    cp -avf ../CHANGELOG.txt ${release_path}
    echo -n ${VER} > ${release_path}/LATEST.TXT

    echo "Publish ${release_path} success"
    echo "The lastest version: "$(cat ${release_path}/LATEST.TXT)
fi

# Linux
release_path="/srv/netconftool/linux"
if [ -f release/netconftool_${VER}_amd64.deb ];then
   cp -avf release/netconftool_${VER}_amd64.deb ${release_path}
   ln -svf netconftool_${VER}_amd64.deb ${release_path}/netconftool-linux-amd64-latest.deb
   cp -avf ../CHANGELOG.txt ${release_path}
   echo -n ${VER} > ${release_path}/LATEST.TXT

   echo "Publish ${release_path} success"
   echo "The lastest version: "$(cat ${release_path}/LATEST.TXT)
fi

# release code
echo "Do Source Code release"
cd ..
git archive --format tgz -o scripts/release/netconftool_src_${VER}.tgz master
cp -avf scripts/release/netconftool_src_${VER}.tgz /srv/netconftool/netconftool_src_${VER}.tgz

echo "Publish Done"
