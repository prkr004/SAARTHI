# 🚀 Quick Commands Reference

## Essential Commands

### 1. Install Phi 2.7B (Recommended for You)
```powershell
ollama pull phi:2.7b
```
⏱️ Takes ~10-15 minutes (2.7 GB download)

### 2. Start SAARTHI
```powershell
streamlit run app.py
```
Then open: http://localhost:8501

### 3. Make Ollama Run in Background (Windows)
```powershell
# Start Ollama service
ollama serve
# Keep this terminal open while using SAARTHI
```

## Optional: Install Other Models

```powershell
# Mistral 7B (balanced, 4 GB)
ollama pull mistral:7b

# Llama 2 7B (balanced, 4 GB)
ollama pull llama2:7b

# Llama 3.1 8B (powerful, 4.7 GB - for friends with good CPUs)
ollama pull llama3.1:8b
```

## Using the Model Selector

1. **Open app** → http://localhost:8501
2. **Click** "🤖 Model Settings" section
3. **Select** your model from dropdown
4. **View** model details and comparison
5. **Ask** questions!

## Troubleshooting Commands

```powershell
# Check if Ollama is running
ollama list

# Check installed models
ollama list

# Remove a model if needed
ollama rm phi:2.7b

# Check version
ollama --version
```

## For Your Friends

Share this if they want to use Llama 3.1:

```powershell
# They run this
ollama pull llama3.1:8b

# Then in the app, they select from dropdown
# "Llama 3.1 8B" will appear when they open 🤖 Model Settings
```

## Expected Performance

| Model | Your CPU (Ryzen 5 4500U) | Speed | Use Case |
|-------|-----------|-------|----------|
| Phi 2.7B | ✅ Perfect | 🔥 Very Fast | ← Recommended |
| Mistral 7B | ⚠️ Slow | ⏱️ Fast | If you have time |
| Llama 2 7B | ⚠️ Slow | ⏱️ Fast | If you have time |
| Llama 3.1 8B | ❌ Very Slow | 🐢 Moderate | Only for powerful CPUs |

## One-Time Setup Flow

```
1. ollama pull phi:2.7b           → Wait ~10-15 mins
2. streamlit run app.py           → Opens in browser
3. Click "🤖 Model Settings"      → See dropdown
4. Select "Phi 2.7B"               → Already selected ✓
5. Start asking questions!         → Fast responses 🎉
```

## Common Issues

### "Command not found: ollama"
→ Ollama not installed, download from ollama.ai

### "Could not connect"
→ Ollama not running, run: `ollama serve`

### "Model not found"
→ Model not installed, run: `ollama pull phi:2.7b`

### "Very slow responses"
→ Using wrong model, select Phi 2.7B from dropdown

---

That's it! 🎊
