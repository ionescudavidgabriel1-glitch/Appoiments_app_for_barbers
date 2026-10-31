from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length

MIN_PASSWORD_LENGTH = 8


def strip(value):
    return value.strip() if isinstance(value, str) else value


class SignupForm(FlaskForm):
    name = StringField("Your name", validators=[DataRequired(), Length(max=120)])
    email = EmailField(
        "Email", filters=[strip], validators=[DataRequired(), Email(), Length(max=255)]
    )
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=MIN_PASSWORD_LENGTH, max=128)]
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )


class LoginForm(FlaskForm):
    email = EmailField("Email", filters=[strip], validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Keep me logged in")


class LogoutForm(FlaskForm):
    """Empty form; it only carries the CSRF token for the logout button."""
