import os\nfrom fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef h(): return {'service':'api'}
