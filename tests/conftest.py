"""conftest.py — добавляет корень репозитория в sys.path для всех тестов."""
import sys
import os

# repo root = parent of tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
