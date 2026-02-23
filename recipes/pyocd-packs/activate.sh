#!/bin/sh
if [ -n "$CONDA_PREFIX" ]; then
    if command -v python >/dev/null 2>&1; then
        python "$CONDA_PREFIX/etc/conda/activate.d/update_pyocd.py"
    fi
fi
