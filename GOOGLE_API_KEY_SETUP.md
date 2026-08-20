# Google Gemini API Key Setup

## ⚠️ Current Issue
Your Google API key is invalid:
```
google_api_key=yAQ.Ab8RN6KD7l_9pgbjS2O50YxSZVTfwhF2Xg09UcI6db5NLYaFtw
```

Error: `API key not valid. Please pass a valid API key.`

## ✅ How to Fix

### Step 1: Get a Valid API Key

1. **Visit Google AI Studio**: https://aistudio.google.com/app/apikey
   
2. **Sign in** with your Google account

3. **Click "Get API Key"** or **"Create API Key"**

4. **Copy the generated key** (will look like: `AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`)

### Step 2: Update the `.env` File

Replace the invalid key in `.env`:

```bash
# BEFORE (INVALID):
google_api_key=yAQ.Ab8RN6KD7l_9pgbjS2O50YxSZVTfwhF2Xg09UcI6db5NLYaFtw

# AFTER (YOUR NEW VALID KEY):
google_api_key=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### Step 3: Restart the Server

After updating the API key:

```bash
# Stop the current server (Ctrl+C in terminal)
# Then restart:
python3 -m uvicorn app.main:app --reload --port 8000
```

## 📝 Notes

- **Free Tier**: Google Gemini API has a generous free tier (60 requests per minute)
- **Quota**: Check your quota at https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com/quotas
- **API Key Format**: Valid keys start with `AIza` followed by alphanumeric characters
- **Keep it Secret**: Never commit the API key to Git (already in `.gitignore`)

## 🔗 Useful Links

- **Get API Key**: https://aistudio.google.com/app/apikey
- **Google AI Studio**: https://aistudio.google.com/
- **Documentation**: https://ai.google.dev/tutorials/python_quickstart
- **Pricing**: https://ai.google.dev/pricing

## ✅ Testing After Setup

Once you have a valid key, test it:

```bash
# Run the setup test data script
python3 setup_test_data.py

# Or test the chatbot UI
python3 chatbot_ui.py
```

## 🆘 Troubleshooting

**If you still get errors:**

1. **Check API is enabled**: https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com
2. **Verify quota**: Make sure you haven't exceeded free tier limits
3. **Check key format**: Must start with `AIza`
4. **Try regenerating**: Delete old key and create a new one

---

**Last Updated**: 2026-08-20
