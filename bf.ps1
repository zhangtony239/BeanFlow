#!/usr/bin/env pwsh
# BeanFlow CLI wrapper with UTF-8 encoding
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

& .venv\Scripts\python.exe -m bf.cli @args