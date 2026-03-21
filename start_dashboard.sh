#!/bin/bash
cd /Users/jonaspenaso/Desktop
source /Users/jonaspenaso/Desktop/Phmex2/venv/bin/activate 2>/dev/null || pip3 install streamlit pandas plotly -q
streamlit run dashboard.py
