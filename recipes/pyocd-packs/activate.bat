@echo off
if defined CONDA_PREFIX (
    python "%CONDA_PREFIX%\etc\conda\activate.d\update_pyocd.py"
)
