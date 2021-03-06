from flask import Flask, jsonify, send_from_directory, render_template, request, redirect, url_for, g, flash
from flask_wtf import FlaskForm, RecaptchaField
from flask_wtf.file import FileAllowed, FileRequired
from wtforms import HiddenField, FileField, StringField, TextAreaField, SubmitField, SelectField, DecimalField
from wtforms.validators import InputRequired, DataRequired, Length, ValidationError
from wtforms.widgets import Input
from werkzeug.utils import secure_filename, escape, unescape
from markupsafe import Markup
import pdb
import sqlite3
import os
import datetime
from secrets import token_hex

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = "secretkey"
app.config["ALLOWED_IMAGE_EXTENSIONS"] = ["jpeg", "jpg", "png"]
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["IMAGE_UPLOADS"] = os.path.join(basedir, "uploads")

app.config["TESTING"] = True

app.config["RECAPTCHA_PUBLIC_KEY"] = "6LcWV-oUAAAAAKfYclh9ynPiXSeEEtDBGSXWdh3P"
app.config["RECAPTCHA_PRIVATE_KEY"] = "6LcWV-oUAAAAAChXUsv0nEkimbDv9xCJj0prGT24"

# custome widget of price for input checking
class PriceInput(Input):
    input_type = "number"

    def __call__(self, field, **kwargs):
        kwargs.setdefault("id", field.id)
        kwargs.setdefault("type", self.input_type)
        kwargs.setdefault("step", "0.01")
        if "value" not in kwargs:
            kwargs["value"] = field._value()
        if "required" not in kwargs and "required" in getattr(field, "flags", []):
            kwargs["required"] = True
        return Markup("""<div class="input-group mb-3">
                    <div class="input-group-prepend">
                        <span class="input-group-text">$</span>
                    </div>
                    <input %s>
        </div>""" % self.html_params(name=field.name, **kwargs))

class PriceField(DecimalField):
    widget = PriceInput()

# customed selectfield
class CustomSelectField(SelectField):
    def __init__(self, label=None, validators=None, coerce=int, choices=None, table=None, columns=[], allow_blank=False, **kwargs):
        super(CustomSelectField, self).__init__(label, validators, coerce, choices, **kwargs)
        self.allow_blank = allow_blank
        if not table:
            raise AttributeError("CustomSelectField does not work without the table parameter.")
        if not len(columns):
            raise AttributeError("CustomSelectField does not work without the list of columns.")
        self.table = table
        self.columns = columns

    def iter_choices(self):
        rows = self.get_rows()
        for value, label in rows:
            yield(value, label, self.coerce(value) == self.data)

    def pre_validate(self, form):
        """validate if the picked choice is one of the allowed choices and raise an error if it isn't."""
        rows = self.get_rows() 
        for v, _ in rows:
            if self.data == v:
                break
            else:
                raise ValueError("The chosen option does not exist.")

    def get_rows(self):
        """get select rows form database"""
        c = get_db().cursor()
        try:
            c.execute("SELECT {}, {} FROM {}".format(self.columns[0], self.columns[1], self.table))
        except:
            raise AttributeError("Something went wrong.")
        rows = c.fetchall()
        if self.allow_blank:
            rows.insert(0, (0, "---"))
        return rows

class ItemForm(FlaskForm):
    title       = StringField("Title", validators=[InputRequired("Input is required!"),
                            DataRequired("Data is required!"), 
                            Length(min=5, max=20, message="Input must be between 5 and 20 characters long")])
    price       = PriceField("Price")
    description = TextAreaField("Description", validators=[InputRequired("Input is required!"), 
                            DataRequired("Data is required!"), 
                            Length(min=5, max=50, message="Input must be between 5 and 50 characters long")])
    image       = FileField("Image", validators=[FileRequired(), FileAllowed(app.config["ALLOWED_IMAGE_EXTENSIONS"], "Images only!")])

# add customized validator for select field
class BelongsToOtherFieldOption:
    def __init__(self, table, belongs_to, foreign_key=None, message=None):
        if not table:
            raise AttributeError("""
            BelongsToOtherFieldOption validator needs tha table parameter
            """)
        if not belongs_to:
            raise AttributeError("""
            BelongsToOtherFeildOption validator needs the belongs_to parameter
            """)
        self.table = table
        self.belongs_to = belongs_to

        if not foreign_key:
            foreign_key = belongs_to + "_id"
        if not message:
            message = "Chosen option is not valid."

        self.foreign_key = foreign_key
        self.message = message

    def __call__(self, form, field):
        c = get_db().cursor()
        try:
            c.execute("""SELECT COUNT(*) FROM {} 
                    WHERE id = ? AND {} = ?""".format(
                        self.table,
                        self.foreign_key
                    ),
                    (field.data, getattr(form, self.belongs_to).data)
            )
        except Exception as e:
            raise AttributeError("""
            Passed parameters are not correct. {}
            """.format(e))
        exists = c.fetchone()[0]
        if not exists:
            raise ValidationError(self.message)

# rewrite to class BelongsToOtherFieldOption
# def belongs_to_category(message):
#     message = message

#     def _belongs_to_category(form, field):
#         c = get_db().cursor()
#         c.execute("""SELECT COUNT(*) FROM subcategories 
#                     WHERE id = ? AND category_id = ?""",
#                     (field.data, form.category.data)
#         )
#         exists = c.fetchone()[0]
#         if not exists:
#             raise ValidationError(message)
#     return _belongs_to_category


class NewItemForm(ItemForm):
    category    = CustomSelectField(
                        "Category", 
                        coerce=int,
                        table="categories",
                        columns=["id", "name"]
    )
    subcategory = CustomSelectField(
                        "Subcategory", 
                        coerce=int,
                        table="subcategories",
                        columns=["id", "name"],
                        validators=[
                            BelongsToOtherFieldOption(table="subcategories", 
                                                    belongs_to="category", 
                                                    message="Subcategory does not belong to that category.")]
    )
    recaptcha   = RecaptchaField()
    submit      = SubmitField("Submit")

class EditItemForm(ItemForm):
    submit      = SubmitField("Update item")

class DeleteItemForm(FlaskForm):
    submit      = SubmitField("Delete item")

class FilterForm(FlaskForm):
    title       = StringField("Title", validators=[Length(max=20)])
    price       = SelectField("Price", coerce=int, choices=[(0, "---"), (1, "Max to Min"), (2, "Min to Max")])
    category    = CustomSelectField(
                        "Category", 
                        coerce=int,
                        table="categories",
                        columns=["id", "name"],
                        allow_blank=True
    )
    subcategory = CustomSelectField(
                        "Subcategory", 
                        coerce=int,
                        table="subcategories",
                        columns=["id", "name"],
                        allow_blank=True,
                        validators=[
                            BelongsToOtherFieldOption(table="subcategories", 
                                                    belongs_to="category", 
                                                    message="Subcategory does not belong to that category.")]
    )
    submit      = SubmitField("Filter")

class NewCommentForm(FlaskForm):
    content = TextAreaField("Comment", validators=[InputRequired("Input is required."), DataRequired("Data is required.")])
    item_id = HiddenField(validators=[DataRequired()])
    submit  = SubmitField("Submit")

@app.route("/comment/new", methods=["POST"])
def new_comment():
    conn = get_db()
    c = conn.cursor()
    form = NewCommentForm()

    # 判断是否是Ajax提交
    try:
        is_ajax = int(request.form["ajax"])
    except:
        is_ajax = 0

    if form.validate_on_submit():
        c.execute("""INSERT INTO comments (content, item_id)
                     VALUES (?, ?)""",
                     (
                         escape(form.content.data),
                         form.item_id.data
                     )
        )
        conn.commit()
        if is_ajax:
            return render_template("_comment.html", content=form.content.data)
    if is_ajax:
        return " Content is required.", 404
    return redirect(url_for('item', item_id=form.item_id.data))

@app.route("/")
def home():
    conn = get_db()
    c = conn.cursor()

    form = FilterForm(request.args, meta={"csrf": False})

    c.execute("SELECT id, name FROM categories")
    categories = c.fetchall()
    categories.insert(0, (0, "---"))
    form.category.choices = categories

    c.execute("SELECT id, name FROM subcategories")
    subcategories = c.fetchall()
    subcategories.insert(0, (0, "---"))
    form.subcategory.choices = subcategories

    query = """
            SELECT 
            i.id, i.title, i.description, i.price, i.image, c.name, s.name
            FROM
            items AS i
            INNER JOIN categories AS c ON i.category_id = c.id
            INNER JOIN subcategories AS s ON i.subcategory_id  = s.id
    """

    try:
        is_ajax = int(request.form["ajax"])
    except:
        is_ajax = 0

    if form.validate():

        filter_queries = []
        parameters = []

        if form.title.data.strip():
            filter_queries.append("i.title LIKE ?")
            parameters.append("%" + form.title.data + "%")
        
        if form.category.data:
            filter_queries.append("i.category_id = ?")
            parameters.append(form.category.data)

        if form.subcategory.data:
            filter_queries.append("i.subcategory_id = ?")
            parameters.append(form.subcategory.data)

        if filter_queries:
            query += " WHERE "
            query += " AND ".join(filter_queries)

        if form.price.data:
            if form.price.data == 1:
                query += " ORDER BY i.price DESC"
            else:
                query += " ORDER BY i.price"
        else:
            query += " ORDER BY i.id DESC"

        items_from_db = c.execute(query, tuple(parameters))
        # print(query)
    else:
        items_from_db = c.execute( query + "ORDER BY i.id DESC")

    items = []
    for row in items_from_db:
        item = {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "price": row[3],
            "image": row[4],
            "category": row[5],
            "subcategory": row[6]
        }
        items.append(item)

    if is_ajax:
        return render_template("_items.html", items=items)

    return render_template("home.html", items=items, form=form)

# @app.route("/static/<filename>")
# def static(filename):
#     return send_from_directory("static", filename)

@app.route("/category/<int:category_id>")
def category(category_id):
    c = get_db().cursor()
    c.execute("""SELECT id, name FROM subcategories
                 WHERE category_id = ?""", (category_id,)
    )
    subcategories = c.fetchall()
    return jsonify(subcategories=subcategories)

@app.route("/item/<int:item_id>/delete", methods=["POST"])
def delete_item(item_id):
    conn = get_db()
    c = conn.cursor()

    item_from_db = c.execute("SELECT * FROM items WHERE id = ?", (item_id,))
    row = c.fetchone()
    try:
        item = {
            "id": row[0],
            "title": row[1]
        }
    except:
        item = {}
    
    if item:
        c.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
        flash("Item {} has been successfully deleted.".format(item["title"]), "success")
    else:
        flash("This item does not exist.", "danger")
    
    return redirect(url_for("home"))


@app.route("/item/<int:item_id>")
def item(item_id):
    c = get_db().cursor()
    item_from_db = c.execute("""SELECT
                   i.id, i.title, i.description, i.price, i.image, c.name, s.name
                   FROM
                   items AS i
                   INNER JOIN categories AS c ON i.category_id = c.id
                   INNER JOIN subcategories AS s ON i.subcategory_id = s.id
                   WHERE i.id = ?""",
                   (item_id,)

    )
    row = c.fetchone()

    try:
        item = {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "price": row[3],
            "image": row[4],
            "category": row[5],
            "subcategory": row[6]
        }
    except:
        item = {}

    if item:
        # add show comments
        comments_from_db = c.execute("""SELECT content FROM comments
                    WHERE item_id = ? ORDER BY id DESC""", (item_id,)
        )
        comments = []
        for row in comments_from_db:
            comment = {
                "content": row[0]
            }
            comments.append(comment)
        commentForm    = NewCommentForm()
        commentForm.item_id.data = item_id

        deleteItemForm = DeleteItemForm()

        return render_template("item.html", commentForm=commentForm, item=item, comments=comments, deleteItemForm=deleteItemForm)
    return redirect(url_for("home"))


@app.route("/item/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(item_id):
    conn = get_db()
    c = conn.cursor()
    
    item_from_db = c.execute("SELECT * FROM items WHERE id = ?", (item_id,))
    row = c.fetchone()
    try:
        item = {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "price": row[3],
            "image": row[4]
        }
    except:
        item = {}
    if item:
        form = EditItemForm()
        if form.validate_on_submit():
            
            filename = item["image"]
            if form.image.data:
                filename = save_image_upload(form.image)

            c.execute("""UPDATE items SET
            title = ?, description = ?, price = ?, image = ?
            WHERE id = ?""",
                (
                    form.title.data,
                    form.description.data,
                    float(form.price.data),
                    filename,
                    item_id
                )
            )
            conn.commit()
            flash("Item {} has been successfully updated.".format(form.title.data), "success")
            return redirect(url_for("item", item_id=item_id))
        form.title.data       = unescape(item["title"])
        form.description.data = unescape(item["description"])
        form.price.data       = item["price"]

        # if form.errors:
        #     flash("{}".format(form.errors), "danger")

        return render_template("edit_item.html", item=item, form=form)
    return redirect(url_for("home"))

@app.route("/uploads/<filename>")
def uploads(filename):
    return send_from_directory(app.config["IMAGE_UPLOADS"], filename)

@app.route("/item/new", methods=["GET", "POST"])
def new_item():
    conn = get_db()
    c = conn.cursor()
    form = NewItemForm()

    c.execute("SELECT id, name FROM categories")
    categories = c.fetchall()
    # [(1, 'Food'), (2, 'Technology'), (3, 'Books')]
    form.category.choices = categories

    c.execute("SELECT id, name FROM subcategories")
    subcategories = c.fetchall()
    form.subcategory.choices = subcategories

    # pdb.set_trace()
    if form.validate_on_submit() and form.image.validate(form, extra_validators=(FileRequired(),)):
        filename = save_image_upload(form.image)

        # Process the from data
        # print("From data:")
        # print("Title: {}, Description: {}".format(
        #     request.form.get('title'), request.form.get('description')
        # ))
        c.execute("""INSERT INTO items
                    (title, description, price, image, category_id, subcategory_id)
                        VALUES (?,?,?,?,?,?)""",
                        (
                            escape(form.title.data),
                            escape(form.description.data),
                            float(form.price.data),
                            filename,
                            form.category.data,
                            form.subcategory.data
                        )
        )
        conn.commit()
        # Redirect to top page
        flash("Item {} has been successfully submitted".format(request.form.get("title")), "success")
        return redirect(url_for("home"))
    # if form.errors:
    #     flash("{}".format(form.errors), "danger")
    return render_template("new_item.html", form=form)

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect("db/globomantics.db")
    return db

def save_image_upload(image):
    format = "%Y%m%dT%H%M%S"
    now = datetime.datetime.utcnow().strftime(format)
    random_string = token_hex(2)
    filename = random_string + "_" + now + "_" + image.data.filename
    filename = secure_filename(filename)
    image.data.save(os.path.join(app.config["IMAGE_UPLOADS"], filename))
    return filename

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()
