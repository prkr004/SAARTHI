"""
Model configuration with performance metrics and user-friendly labels.
Helps users choose appropriate models based on their hardware capabilities.
"""

# Model registry with human-friendly labels and descriptions
AVAILABLE_MODELS = [
    {
        "id": "phi:2.7b",
        "name": "Phi 2.7B",
        "label": "⚡ Ultra-Lightweight",
        "category": "lightweight",
        "parameters": "2.7 billion",
        "description": "Fastest option • Minimal RAM • Best for basic queries",
        "ram_needed": "4-6 GB",
        "suitable_for": "Slow CPUs, laptops, frontend work",
        "speed": "Very Fast",
        "quality": "Good for basic questions",
        "recommended": True,
    },
    {
        "id": "mistral:7b",
        "name": "Mistral 7B",
        "label": "⚙️ Balanced",
        "category": "balanced",
        "parameters": "7 billion",
        "description": "Good balance • Moderate resource usage • Quality responses",
        "ram_needed": "8-10 GB",
        "suitable_for": "Mid-range CPUs, general use",
        "speed": "Fast",
        "quality": "Good for complex queries",
        "recommended": False,
    },
    {
        "id": "llama2:7b",
        "name": "Llama 2 7B",
        "label": "⚙️ Balanced",
        "category": "balanced",
        "parameters": "7 billion",
        "description": "Reliable option • Good quality • Moderate resource usage",
        "ram_needed": "8-10 GB",
        "suitable_for": "Mid-range CPUs, general use",
        "speed": "Fast",
        "quality": "Good quality responses",
        "recommended": False,
    },
    {
        "id": "llama3.1:8b",
        "name": "Llama 3.1 8B",
        "label": "🚀 Powerful",
        "category": "powerful",
        "parameters": "8 billion",
        "description": "Most capable • Higher resource usage • Best quality",
        "ram_needed": "10-12+ GB",
        "suitable_for": "Powerful CPUs, detailed analysis",
        "speed": "Moderate",
        "quality": "Excellent quality responses",
        "recommended": False,
    },
]


def get_model_by_id(model_id: str) -> dict | None:
    """Get model config by ID."""
    for model in AVAILABLE_MODELS:
        if model["id"] == model_id:
            return model
    return None


def get_model_info_text(model: dict) -> str:
    """Generate user-friendly info text for a model."""
    return (
        f"**{model['name']}** — {model['label']}\n"
        f"• {model['description']}\n"
        f"• RAM needed: {model['ram_needed']}\n"
        f"• Speed: {model['speed']}\n"
        f"• Quality: {model['quality']}\n"
        f"\n_**What are billion parameters?**_ "
        f"Parameters are numeric weights the AI uses. More parameters = better quality "
        f"but slower & uses more memory. {model['parameters']} means {model['name']} has "
        f"{model['parameters'].split()[0]} million adjustable values."
    )


def get_recommended_model(cpu_type: str = "ryzen_5_4500u") -> str:
    """Suggest a model based on CPU type."""
    if cpu_type.lower() == "ryzen_5_4500u":
        return "phi:2.7b"  # Perfect for AMD Ryzen 5 4500U
    return "phi:2.7b"  # Default recommendation for low-resource systems
