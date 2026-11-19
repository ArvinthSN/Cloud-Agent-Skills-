import os
from fastapi import FastAPI
app=FastAPI()
@app.get('/health')
def h(): return {'service':'api'}
