#!/usr/bin/env python3
"""
Script to check if the tau_emotion data directory is properly configured.
"""

import sys

from tau_emotion.utils.utils import DATA_DIR


def main():
    """Main function to check data directory."""
    print("tau_emotion Data Directory Checker")
    print("=" * 40)

    print(f"Data directory: {DATA_DIR}")

    if DATA_DIR.exists():
        print("✅ Data directory exists")
        print("You can now run tau_emotion commands.")
    else:
        print("❌ Data directory does not exist!")
        print("\nTo fix this, you can:")
        print("1. Set the TAU_EMOTION_DATA_DIR environment variable:")
        print("   export TAU_EMOTION_DATA_DIR=/path/to/your/tau_emotion-bench/data")
        print("2. Or ensure the data directory exists in the expected location")
        sys.exit(1)


if __name__ == "__main__":
    main()
