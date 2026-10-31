from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length

MIN_PASSWORD_LENGTH = 8
VALID_EMAIL = "Enter an email like name@example.com."


def strip(value):
    return value.strip() if isinstance(value, str) else value


class SignupForm(FlaskForm):
    name = StringField(
        "Your name",
        validators=[
            DataRequired("Enter your name."),
            Length(max=120, message="Keep it under 120 characters."),
        ],
    )
    email = EmailField(
        "Email",
        filters=[strip],
        validators=[
            DataRequired("Enter your email."),
            Email(VALID_EMAIL),
            Length(max=255, message="Keep it under 255 characters."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired("Choose a password."),
            Length(
                min=MIN_PASSWORD_LENGTH, message=f"Use at least {MIN_PASSWORD_LENGTH} characters."
            ),
            Length(max=128, message="Use 128 characters or fewer."),
        ],
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[
            DataRequired("Type the password again."),
            EqualTo("password", message="The two passwords don't match."),
        ],
    )


class LoginForm(FlaskForm):
    email = EmailField(
        "Email", filters=[strip], validators=[DataRequired("Enter your email."), Email(VALID_EMAIL)]
    )
    password = PasswordField("Password", validators=[DataRequired("Enter your password.")])
    remember = BooleanField("Keep me logged in")


class LogoutForm(FlaskForm):
    """Empty form; it only carries the CSRF token for the logout button."""
