# This runs separately from your bot, on another screen

from flask import Flask
from flask_cors import CORS
import json


app = Flask(__name__)
CORS(app)


@app.route('/<user_id>')
def get_latex(user_id):
    with open('./equations.json') as f:
        data = json.load(f)
    return json.dumps(data[user_id])


app.run(host='0.0.0.0')
