# ✅ Verification Checklist

Complete this checklist to ensure everything works correctly.

## Pre-Setup Verification

- [ ] Ollama is installed (`ollama --version` shows version)
- [ ] You have internet (models are 2-14 GB downloads)
- [ ] 15+ GB free disk space
- [ ] Python 3.8+
- [ ] Streamlit already working with your app

## Installation Steps

- [ ] Ran: `ollama pull phi:2.7b` (took ~10-15 minutes)
- [ ] Download completed without errors
- [ ] No "Connection refused" errors (Ollama is running)

## File Verification

Check if all new files exist:
- [ ] `models_config.py` exists
- [ ] `setup_models.py` exists
- [ ] `MODEL_SELECTOR_GUIDE.md` exists
- [ ] `IMPLEMENTATION_NOTES.md` exists
- [ ] `QUICK_START.md` exists
- [ ] `SUMMARY.md` exists

## Code Verification

Run these in PowerShell/CMD to verify Python files work:

```powershell
# Test 1: Check models_config.py
python -c "from models_config import AVAILABLE_MODELS; print(f'✓ Found {len(AVAILABLE_MODELS)} models')"
# Expected: ✓ Found 4 models

# Test 2: Check setup_models.py
python -c "import setup_models; print('✓ setup_models.py loads correctly')"
# Expected: ✓ setup_models.py loads correctly

# Test 3: Check Ollama
ollama list
# Expected: Shows available models including phi:2.7b
```

## Runtime Verification

1. **Start SAARTHI**
   ```powershell
   streamlit run app.py
   ```

2. **In browser (http://localhost:8501), verify:**
   - [ ] Page loads without errors
   - [ ] "SAARTHI — Regulatory Q&A Assistant" title visible
   - [ ] "🤖 Model Settings" section visible below title
   - [ ] All original UI elements present

3. **Click "🤖 Model Settings" expander**
   - [ ] Expands smoothly
   - [ ] Shows "Choose AI Model" dropdown
   - [ ] Shows "Current" metric card
   - [ ] Dropdown has 4 options:
     - [ ] Phi 2.7B
     - [ ] Mistral 7B
     - [ ] Llama 2 7B
     - [ ] Llama 3.1 8B

4. **Check Model Info Display**
   - [ ] "Phi 2.7B ⚡ Ultra-Lightweight" is selected by default
   - [ ] Shows detailed info text
   - [ ] Shows "What are billion parameters?" explanation
   - [ ] Shows all models comparison table

5. **Test Model Switching**
   - [ ] Select "Llama 2 7B" from dropdown
   - [ ] Display updates to show that model's info
   - [ ] "Current" metric changes
   - [ ] Selection indicator shows "✓ Current"

6. **Test Query with Phi 2.7B**
   - [ ] Type a question: "What is SAARTHI?"
   - [ ] Press Enter or click input
   - [ ] Shows "SAARTHI is retrieving relevant sections…"
   - [ ] Returns answer within 30-60 seconds
   - [ ] Shows sources below answer
   - [ ] No errors in console

7. **Test Query with Llama 3.1:8B**
   - [ ] (Only if you have >10GB RAM and time)
   - [ ] Select "Llama 3.1 8B" from dropdown
   - [ ] Verify model switches correctly
   - [ ] Can still ask questions

## Features Verification

- [ ] **Original Functionality Preserved**
  - [ ] Welcome card shows
  - [ ] Chat history works
  - [ ] Clear history button works (🗑️)
  - [ ] Source citations display correctly
  - [ ] Citation links work

- [ ] **Model Selector Works**
  - [ ] Can switch models
  - [ ] Selection saves for session
  - [ ] Model info displays correctly
  - [ ] Comparison table shows all models

- [ ] **Session State**
  - [ ] Refresh page → model stays selected
  - [ ] Close browser → model resets to default (phi:2.7b)
  - [ ] Multiple users each can select their model

## Performance Verification

- [ ] Response time improved (10-30 sec vs 2-5 min)
- [ ] Browser not lagging
- [ ] System remains responsive
- [ ] CPU not at 100%
- [ ] RAM usage reasonable

## Troubleshooting Verification

If something fails, check:

1. **"Module not found: models_config"**
   - [ ] `models_config.py` exists in SAARTHI folder
   - [ ] No typos in filename
   - [ ] File is not blank

2. **"Could not connect to language model"**
   - [ ] Ollama is running (`ollama serve`)
   - [ ] Model is installed (`ollama list`)
   - [ ] Try again after waiting 5 seconds

3. **"Phi 2.7B model not found"**
   - [ ] Run: `ollama pull phi:2.7b`
   - [ ] Wait for download to complete
   - [ ] Verify with: `ollama list`

4. **Dropdown not showing models**
   - [ ] `models_config.py` loaded correctly
   - [ ] Check browser console for errors (F12)
   - [ ] Refresh page (Ctrl+R or Cmd+R)

5. **Model selector not visible**
   - [ ] Click "🤖 Model Settings" to expand
   - [ ] Check if it's collapsed
   - [ ] Refresh page if still not visible

## Documentation Verification

- [ ] Opened `QUICK_START.md` ✓ (one page reference)
- [ ] Opened `MODEL_SELECTOR_GUIDE.md` ✓ (detailed setup)
- [ ] Opened `IMPLEMENTATION_NOTES.md` ✓ (technical details)

## Sign-Off

Print this and mark completion:

```
Setup Date: _______________
Verified By: _______________
All Tests Passed: YES / NO
Comments: _________________________________
```

---

## If All Checks Pass ✅

You're ready to use SAARTHI with model selection!

1. Phi 2.7B is recommended for your Ryzen 5 4500U
2. Share the app with friends (they pick their model)
3. Enjoy fast responses!

## If Checks Failed ❌

1. Re-read the relevant guide
2. Try troubleshooting steps
3. Verify all files exist
4. Check console/terminal for errors
5. Ask for help with the specific error message

---

**Quick Help**
- Commands: See `QUICK_START.md`
- Setup: See `MODEL_SELECTOR_GUIDE.md`
- Details: See `IMPLEMENTATION_NOTES.md`

Good luck! 🚀
