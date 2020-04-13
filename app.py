from flask import Flask, render_template, request, redirect, url_for
import pdb

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("home.html")

# @app.route("/static/<filename>")
# def static(filename):
#     return send_from_directory("static", filename)

@app.route("/item/new", methods=["GET", "POST"])
def new_item():
    # pdb.set_trace()
    if request.method == "POST":
        # Process the from data
        print("From data:")
        print("Title: {}, Description: {}".format(
            request.form.get('title'), request.form.get('description')
        ))
        # Redirect to top page
        return redirect(url_for("home"))
        
    return render_template("new_item.html")
