from datetime import date
from wtforms import StringField, PasswordField, DecimalField, SelectField, DateField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange
from flask_wtf import FlaskForm

class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    confirm = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Create Account")

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log In")

class CategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=64)])
    icon = SelectField(
        "Icon",
        choices=[
            ("tag", "Tag"),
            ("cart", "Shopping"),
            ("basket", "Groceries"),
            ("cash", "Cash"),
            ("credit-card", "Credit Card"),
            ("piggy-bank", "Savings"),
            ("dollar-sign", "Income"),
            ("wallet2", "Wallet"),
            ("house", "Housing"),
            ("building", "Rent/Mortgage"),
            ("car-front", "Car"),
            ("bus-front", "Public Transport"),
            ("bicycle", "Bike"),
            ("airplane", "Flights"),
            ("train-front", "Train"),
            ("fuel-pump", "Fuel"),
            ("bolt", "Utilities"),
            ("lightbulb", "Electricity"),
            ("droplet", "Water"),
            ("wifi", "Internet"),
            ("phone", "Phone"),
            ("tv", "Streaming/TV"),
            ("heart", "Health"),
            ("capsule", "Medicine"),
            ("hospital", "Hospital"),
            ("utensils", "Food"),
            ("cup-straw", "Coffee"),
            ("beer", "Drinks"),
            ("egg-fried", "Dining"),
            ("cake", "Dessert"),
            ("gift", "Gifts"),
            ("balloon", "Events"),
            ("gamepad", "Games"),
            ("controller", "Entertainment"),
            ("music-note", "Music"),
            ("film", "Movies"),
            ("book", "Books"),
            ("graduation-cap", "Education"),
            ("scissors", "Personal Care"),
            ("person", "Personal"),
            ("briefcase", "Work"),
            ("tools", "Repairs"),
            ("hammer", "Home Projects"),
            ("tree", "Outdoors"),
            ("sun", "Vacation"),
            ("snow", "Winter"),
            ("cloud-rain", "Rainy Day Fund"),
        ],
        default="tag",
        coerce=str,
        validators=[DataRequired()],
    )
    submit = SubmitField("Save")

class BudgetForm(FlaskForm):
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    month = StringField("Month (YYYY-MM)", validators=[DataRequired(), Length(min=7, max=7)])
    amount = DecimalField("Amount", places=2, rounding=None, validators=[DataRequired(), NumberRange(min=0)])
    recurrence = SelectField("Recurrence", choices=[("one_time","One Time"),("monthly","Monthly")], default="one_time")
    submit = SubmitField("Save Budget")

class TransactionForm(FlaskForm):
    type = SelectField("Type", choices=[("expense", "Expense"), ("income", "Income")], validators=[DataRequired()])
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    amount = DecimalField("Amount", places=2, validators=[DataRequired(), NumberRange(min=0)])
    date = DateField("Date", default=date.today, validators=[DataRequired()])
    description = TextAreaField("Description", validators=[Length(max=255)])
    submit = SubmitField("Add Transaction")

class SavingsStartForm(FlaskForm):
    month = StringField("Month (YYYY-MM)", validators=[DataRequired(), Length(min=7, max=7)])
    amount = DecimalField("Starting Savings", places=2, validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField("Save Starting Savings")

