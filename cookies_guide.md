# How to Bypass YouTube IP Blocks (cookies.txt)

If you are seeing errors like **"YouTube is blocking requests from your IP"**, it means YouTube's bot detection has flagged the automated requests. The most reliable way to fix this is to provide your browser's session cookies to the application.

## Step-by-Step Guide

### 1. Install a Cookie Export Extension
You need an extension that can export cookies in the **Netscape cookie format**.
- **Chrome/Edge:** Install [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/ccmgnabgoalhpbhghnpehingecgeocbg)
- **Firefox:** Install [Export Cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/)

### 2. Export Cookies from YouTube
1. Open your browser and go to [YouTube.com](https://www.youtube.com).
2. **Make sure you are logged in** (this provides more stable cookies).
3. Click the extension icon and select **"Export"** or **"Export YouTube.com cookies"**.
4. Save the file as `cookies.txt`.

### 3. Save the File to the Project
Move the `cookies.txt` file into the `backend/` directory of this project:
`/Users/rohitchintalapudi99gmail.com/Desktop/YouTube-Video-2-Text/backend/cookies.txt`

### 4. Restart the App
The backend will automatically detect the file and use it to "pretend" to be your logged-in browser session. This usually bypasses all IP blocks and rate limits.

> [!TIP]
> Do not share your `cookies.txt` file with others, as it contains your login session information.
