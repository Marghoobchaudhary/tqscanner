import os

def create_output_dir(name: str):
    """Ensure output/<name> exists."""
    os.makedirs(os.path.join("output", name), exist_ok=True)
