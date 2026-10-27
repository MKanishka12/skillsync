# SkillSync - Connect Skills. Build Teams. Create Opportunities.

## Run on Windows (VS Code)
1. Unzip the folder and open it in VS Code (File > Open Folder).
2. Open the terminal (Ctrl + `) and run:
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
3. (Optional, for demo data) python seed_demo.py
   Demo logins: aarav@demo.edu / demo1234 (all demo users share this password)
4. python app.py
5. Open http://127.0.0.1:5000

If PowerShell blocks activation, run once:
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
To reset all data, stop the app and delete skillsync.db.
