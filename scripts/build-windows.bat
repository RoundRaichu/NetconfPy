@echo off
path = %path%;C:\Program Files (x86)\Inno Setup 6\;C:\Program Files\7-Zip\

@rem clean cache
rmdir /s /q build
rmdir /s /q dist

@rem create build env
python -m venv venv
call venv\Scripts\activate.bat
pip install -r ..\requirements.txt

set dirty=0
for /F %%i in ('git status --porcelain') do set dirty=1
for /f %%i in ('git rev-parse --short HEAD') do set commit_sha=%%i

if %dirty%==1 (set commit_sha=%commit_sha%-dirty)

echo cvs=%commit_sha% > RELEASE_INFO
echo btime=%date:~0,10% %time:~0,5% >> RELEASE_INFO

type RELEASE_INFO

@rem compile qrc resource
pyrcc5 -o ..\res_rc.py ..\res.qrc

@rem create exec
set /P version_code=<..\VERSION
create-version-file version_file.yaml --outfile file_version_info.txt --version %version_code%

@rem start pyinstall build
pyinstaller --noconfirm NetConfTool.spec

del /q /s file_version_info.txt

@rem deactivate env
call venv\Scripts\deactivate.bat

@rem remove unused files
del /s /q dist\NetConfTool\PyQt5\Qt5\translations\*.*
del /s /q dist\NetConfTool\PyQt5\Qt5\bin\d3dcompiler_47.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\bin\libEGL.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\bin\libGLESv2.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\bin\opengl32sw.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\bin\Qt5Qml.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\bin\Qt5QmlModels.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\bin\Qt5Quick.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\bin\Qt5WebSockets.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\bin\Qt5Network.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\bin\Qt5Svg.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\plugins\imageformats\qwebp.dll
del /s /q dist\NetConfTool\PyQt5\Qt5\plugins\imageformats\qwbmp.dll

@rem build setup installer
ISCC.exe NetConfSetup.iss


@rem build portable package
cd dist
7z.exe a -tzip ..\release\NetConfTool_Portable_v%version_code%.zip NetConfTool
cd ..


@rem post build
git restore RELEASE_INFO

pause