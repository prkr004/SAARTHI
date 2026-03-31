# 🤖 SAARTHI Model Selector - Setup Guide

## What's New?

You can now choose between different AI models based on your computer's capabilities! This allows:
- **Your setup (AMD Ryzen 5 4500U)**: Use lightweight models without lag
- **Your friends' powerful systems**: Use larger, more capable models
- **Everyone**: Keep using the original functionality

## Quick Start

### 1. Pull the Recommended Model (Phi 2.7B)

Run this command in PowerShell/CMD:

```powershell
ollama pull phi:2.7b
```

Or use the interactive setup script:

```powershell
python setup_models.py
```

Then select option 1 to install Phi 2.7B (recommended for your CPU).

### 2. Start SAARTHI

```powershell
streamlit run app.py
```

### 3. Select Your Model

- Open the app in your browser
- Click the **"🤖 Model Settings"** section
- Choose your preferred model from the dropdown
- The app remembers your choice for the session

## Available Models

| Model | Label | Best For | RAM Needed | Speed |
|-------|-------|----------|-----------|-------|
| **Phi 2.7B** | ⚡ Ultra-Lightweight | Your CPU (Ryzen 5 4500U) | 4-6 GB | Very Fast |
| **Llama 2 7B** | ⚙️ Balanced | Mid-range CPUs | 8-10 GB | Fast |
| **Mistral 7B** | ⚙️ Balanced | Mid-range CPUs | 8-10 GB | Fast |
| **Llama 3.1 8B** | 🚀 Powerful | Powerful CPUs | 10-12+ GB | Moderate |

## Understanding the Labels

- **⚡ Ultra-Lightweight**: Best for weak CPUs, minimal lag, instant responses
- **⚙️ Balanced**: Good quality, reasonable speed, mid-range hardware
- **🚀 Powerful**: Best quality, slower responses, needs powerful CPU

## What's "Billion Parameters"?

Parameters are like the AI's "brain weights". More parameters = smarter but slower.

- **2.7 billion** = Fast, lighter brain (Phi)
- **7 billion** = Good balance (Llama 2, Mistral)
- **8 billion** = Powerful brain, needs resources (Llama 3.1)

## Installation Commands

Install specific models:

```powershell
ollama pull phi:2.7b           # Ultra-lightweight for your CPU ⭐
ollama pull mistral:7b         # Balanced option
ollama pull llama2:7b          # Another balanced option
ollama pull llama3.1:8b        # Most powerful (if you have the hardware)
```

Or let friends know to pull their preferred model:

```powershell
# Your friend with a powerful GPU can run:
ollama pull llama3.1:8b
```

## How to Use in the App

1. **First run**: The app defaults to Phi 2.7B for your system
2. **Change model**: Click "🤖 Model Settings" and select from dropdown
3. **See details**: Hover over model names to see specs
4. **Compare models**: The settings panel shows all models side-by-side

## Expected Performance

### On Your AMD Ryzen 5 4500U with Phi 2.7B
- Response time: **10-30 seconds** (vs 2-5 minutes with Llama 3.1:8b)
- Browser lag: **Minimal** (vs noticeable lag before)
- Quality: **Good for basic regulatory questions**

### For Powerful Systems (Your Friends)
- Can use Llama 3.1 8B for better quality
- Just change dropdown to "Llama 3.1 8B"
- Must have Ollama running with that model pulled

## Troubleshooting

### "Could not connect to the language model"
- Ollama is not running
- Fix: Start Ollama (Windows/Mac: click the app, Linux: `ollama serve`)

### Model download fails
- Check internet connection
- Try again: `ollama pull <model_name>`
- Models are 2-14 GB each, can take time

### Model too slow
- Choose a smaller model (Phi 2.7B recommended)
- Close other applications
- Ensure Ollama is the only heavy process

### Old functionality missing?
- Don't worry! All original features are preserved
- Just select "Llama 3.1 8B" in model settings to use the original model
- All RAG queries, temporal comparison, source citations remain intact

## File Changes Summary

**New files:**
- `models_config.py` - Model configuration with labels and specs
- `setup_models.py` - Interactive model installation helper

**Modified files:**
- `app.py` - Added model dropdown selector, maintains all original functionality
- `query.py` - Unchanged (still works with any model)

## Notes

- Each user in the app can select their own model
- Selection is remembered for the session
- Original functionality (RAG, temporal comparison) works with all models
- All source citations and document references work the same way

Enjoy faster responses on your system! 🚀
