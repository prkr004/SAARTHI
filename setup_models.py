"""
Ollama model setup helper — Install and manage models easily.
Run this before starting the app to ensure models are available.
"""

import subprocess
import sys
from models_config import AVAILABLE_MODELS


def run_command(cmd: str) -> tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def check_ollama_running() -> bool:
    """Check if Ollama service is running."""
    success, _ = run_command("ollama list")
    return success


def pull_model(model_id: str) -> bool:
    """Pull a model from Ollama."""
    print(f"\n🔄 Pulling {model_id}... (this may take several minutes)")
    success, output = run_command(f"ollama pull {model_id}")
    if success:
        print(f"✓ Successfully installed {model_id}")
        return True
    else:
        print(f"✗ Failed to install {model_id}")
        print(output)
        return False


def list_installed_models() -> bool:
    """List models currently available in Ollama."""
    print("\n📦 Checking installed models...")
    success, output = run_command("ollama list")
    if success:
        print(output)
        return True
    else:
        print("Could not list models")
        return False


def main():
    print("=" * 60)
    print("SAARTHI — Ollama Model Setup Helper")
    print("=" * 60)
    
    # Check Ollama
    print("\n1️⃣ Checking if Ollama is running...")
    if not check_ollama_running():
        print(
            "✗ Ollama is not running!\n"
            "Please start Ollama:\n"
            "  • Windows/Mac: Open the Ollama application\n"
            "  • Linux: Run 'ollama serve' in another terminal\n"
            "Then run this script again."
        )
        sys.exit(1)
    
    print("✓ Ollama is running")
    
    # Show menu
    print("\n2️⃣ Available models to install:")
    for i, model in enumerate(AVAILABLE_MODELS, 1):
        recommended = " ⭐ (Recommended for Ryzen 5 4500U)" if model.get("recommended") else ""
        print(f"  {i}. {model['name']} - {model['description']}{recommended}")
    
    print("\nOptions:")
    print("  [1-4] Install a specific model")
    print("  [a]   Install all models")
    print("  [l]   List currently installed models")
    print("  [q]   Quit")
    
    choice = input("\nEnter your choice: ").strip().lower()
    
    if choice == "q":
        print("Bye! 👋")
        return
    
    elif choice == "l":
        list_installed_models()
        return
    
    elif choice == "a":
        print("\n📥 Installing all models... (this will take a while)")
        for model in AVAILABLE_MODELS:
            pull_model(model["id"])
    
    elif choice in ["1", "2", "3", "4"]:
        idx = int(choice) - 1
        if 0 <= idx < len(AVAILABLE_MODELS):
            pull_model(AVAILABLE_MODELS[idx]["id"])
        else:
            print("Invalid choice")
    
    else:
        print("Invalid choice")
        return
    
    print("\n✓ Done! You can now start SAARTHI with: streamlit run app.py")


if __name__ == "__main__":
    main()
