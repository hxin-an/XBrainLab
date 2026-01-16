#!/usr/bin/env python3
"""
Test runner script for XBrainLab.
Provides functions referenced in pyproject.toml for running specific subsets of tests.
"""

import os
import subprocess
import sys


def run_pytest(args):
    """Run pytest with given arguments."""
    cmd = ["pytest"] + args
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    sys.exit(result.returncode)

def backend():
    """Run backend unit tests."""
    print("Running Backend Tests...")
    # Using Agg backend to prevent UI issues if code accidentally imports matplotlib.pyplot
    os.environ["MPLBACKEND"] = "Agg"
    run_pytest(["tests/unit/backend"])

def ui():
    """Run UI unit tests."""
    print("Running UI Tests...")
    run_pytest(["tests/unit/ui"])

def run_llm_tests():
    """Run LLM unit tests."""
    print("Running LLM Tests...")
    run_pytest(["tests/unit/llm"])

def run_remote_tests():
    """Run tests suitable for remote/headless environment (skips UI that requires display)."""
    print("Running Remote/Headless Tests (Backend + LLM)...")
    os.environ["MPLBACKEND"] = "Agg"
    # Run everything except the 'ui' directory or specific known failing files
    # For now, we explicitly run backend and llm.
    # If there are integration tests that are safe, those should be added too.
    run_pytest(["tests/unit/backend", "tests/unit/llm"])

def all_tests():
    """Run all tests."""
    print("Running All Tests...")
    run_pytest(["tests"])

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "backend":
            backend()
        elif command == "ui":
            ui()
        elif command == "llm":
            run_llm_tests()
        elif command == "remote":
            run_remote_tests()
        elif command == "all":
            all_tests()
        else:
            print(f"Unknown command: {command}")
            print("Available commands: backend, ui, llm, remote, all")
            sys.exit(1)
    else:
        all_tests()
