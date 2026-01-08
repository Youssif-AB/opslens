from app import app
from flask import render_template
from flask import request

@app.route("/", methods = ["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded_csv = request.files.get("file")

        if uploaded_csv.filename == "":
            return "No File Input"
        
        uploaded_csv.seek(0)
        text_prev = uploaded_csv.read(500).decode("utf-8", errors="replace")
        
        return ( 
            "<pre>"
            f"File Recieved: {uploaded_csv.filename}\n\n"
            f"Preview: \n{text_prev}"
            "</pre>"
        )
    return render_template("base.html")

@app.route("/health")
def health():
    return "OK"

