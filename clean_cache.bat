@echo off
echo ========================================
echo  清理项目在C盘的缓存文件
echo ========================================
echo.

set USERPROFILE=%USERPROFILE%

echo 正在清理以下目录：
echo.

if exist "%USERPROFILE%\.EasyOCR" (
    echo [1/6] %USERPROFILE%\.EasyOCR
    rmdir /s /q "%USERPROFILE%\.EasyOCR"
    echo       已删除
) else (
    echo [1/6] %USERPROFILE%\.EasyOCR (不存在，跳过)
)

if exist "%USERPROFILE%\.paddlex" (
    echo [2/6] %USERPROFILE%\.paddlex
    rmdir /s /q "%USERPROFILE%\.paddlex"
    echo       已删除
) else (
    echo [2/6] %USERPROFILE%\.paddlex (不存在，跳过)
)

if exist "%USERPROFILE%\.paddleocr" (
    echo [3/6] %USERPROFILE%\.paddleocr
    rmdir /s /q "%USERPROFILE%\.paddleocr"
    echo       已删除
) else (
    echo [3/6] %USERPROFILE%\.paddleocr (不存在，跳过)
)

if exist "%USERPROFILE%\.cache\paddle" (
    echo [4/6] %USERPROFILE%\.cache\paddle
    rmdir /s /q "%USERPROFILE%\.cache\paddle"
    echo       已删除
) else (
    echo [4/6] %USERPROFILE%\.cache\paddle (不存在，跳过)
)

if exist "%USERPROFILE%\.cache\modelscope" (
    echo [5/6] %USERPROFILE%\.cache\modelscope
    rmdir /s /q "%USERPROFILE%\.cache\modelscope"
    echo       已删除
) else (
    echo [5/6] %USERPROFILE%\.cache\modelscope (不存在，跳过)
)

if exist "%USERPROFILE%\.cache\huggingface" (
    echo [6/6] %USERPROFILE%\.cache\huggingface
    rmdir /s /q "%USERPROFILE%\.cache\huggingface"
    echo       已删除
) else (
    echo [6/6] %USERPROFILE%\.cache\huggingface (不存在，跳过)
)

echo.
echo ========================================
echo  清理完成！
echo ========================================
echo.
echo 项目所需的EasyOCR模型已保存在：
echo   models\easyocr\
echo.
pause
