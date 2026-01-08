from flask import Flask 


app = Flask(__name__)

from app import routes #routes after flask is created