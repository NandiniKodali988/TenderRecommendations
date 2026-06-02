import os
from dotenv import load_dotenv
load_dotenv()

from database import get_client, get_all_profiles
from agents import run_pipeline


def main():
    client = get_client()
    profiles = get_all_profiles(client)
    print(f"Profiles found: {len(profiles)}")
    run_pipeline(client, profiles)
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
