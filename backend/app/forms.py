from datetime import time
from zoneinfo import available_timezones

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateTimeLocalField,
    DecimalField,
    EmailField,
    FieldList,
    Form,
    FormField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    TimeField,
)
from wtforms.fields.choices import SelectChoice
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

from .models import WorkingHours

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


class ActionForm(FlaskForm):
    """Empty form; it only carries the CSRF token for buttons that POST
    (log out, hide a service, revoke an invite...)."""


# Catalog (phase 3)

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
CURRENCIES = ["RON", "EUR", "USD", "GBP"]
SLOT_CHOICES = [
    SelectChoice(str(minutes), label)
    for minutes, label in [
        (5, "Every 5 minutes"),
        (10, "Every 10 minutes"),
        (15, "Every 15 minutes"),
        (20, "Every 20 minutes"),
        (30, "Every 30 minutes"),
        (60, "Every hour"),
    ]
]
TIMEZONES = sorted(
    tz for tz in available_timezones() if "/" in tz and not tz.startswith(("Etc/", "SystemV/"))
)


class ShopForm(FlaskForm):
    name = StringField(
        "Shop name",
        validators=[
            DataRequired("Enter the shop's name."),
            Length(max=120, message="Keep it under 120 characters."),
        ],
    )
    slug = StringField(
        "Booking page address",
        description="Customers book at /s/your-address. Lowercase letters, numbers and dashes. "
        "Leave empty to make one from the shop name.",
        filters=[lambda v: v.strip().lower() if isinstance(v, str) else v],
        validators=[
            Optional(),
            Length(min=3, max=60, message="Use 3 to 60 characters."),
            Regexp(
                SLUG_PATTERN,
                message="Use lowercase letters, numbers and single dashes, like fade-street.",
            ),
        ],
    )
    address = StringField("Address", filters=[strip], validators=[Optional(), Length(max=255)])
    phone = StringField("Phone", filters=[strip], validators=[Optional(), Length(max=40)])
    timezone = SelectField("Timezone", choices=TIMEZONES, default="Europe/Bucharest")
    currency = SelectField("Currency", choices=CURRENCIES, default="RON")
    slot_minutes = SelectField(
        "Offer booking times",
        choices=SLOT_CHOICES,
        coerce=int,
        default=15,
        description="How often a booking can start, e.g. 10:00, 10:15, 10:30.",
    )


class ServiceForm(FlaskForm):
    name = StringField(
        "Service name",
        validators=[
            DataRequired("Enter a name, like Haircut."),
            Length(max=120, message="Keep it under 120 characters."),
        ],
    )
    duration_min = IntegerField(
        "Duration in minutes",
        validators=[
            DataRequired("Enter how long it takes, in minutes."),
            NumberRange(min=5, max=480, message="Use between 5 and 480 minutes."),
        ],
    )
    price = DecimalField(
        "Price",
        places=2,
        validators=[
            Optional(),
            NumberRange(min=0, max=100000, message="Enter a price from 0 to 100000."),
        ],
        description="Leave empty for free.",
    )

    def validate_duration_min(self, field):
        if field.data and field.data % 5:
            raise ValidationError("Use a multiple of 5 minutes, like 30 or 45.")


class DayHoursForm(Form):
    """One weekday: an optional first shift and an optional second shift after a break.
    Empty means a day off."""

    start1 = TimeField("From", validators=[Optional()])
    end1 = TimeField("To", validators=[Optional()])
    start2 = TimeField("From", validators=[Optional()])
    end2 = TimeField("To", validators=[Optional()])

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        ok = True
        for start, end in ((self.start1, self.end1), (self.start2, self.end2)):
            if (start.data is None) != (end.data is None):
                end.errors.append("Fill in both times, or leave both empty.")
                ok = False
            elif start.data is not None and stored_end(end.data) <= start.data:
                if end.data < start.data:
                    end.errors.append(
                        "This goes past midnight. End at 00:00 and add the rest to the next day."
                    )
                else:
                    end.errors.append("End after it starts.")
                ok = False
        if ok and self.start2.data is not None:
            if self.start1.data is None:
                self.start2.errors.append("Fill in the first shift first.")
                ok = False
            elif self.start2.data < stored_end(self.end1.data):
                self.start2.errors.append("Start the second shift after the first one ends.")
                ok = False
        return ok

    def intervals(self):
        return [
            (start.data, stored_end(end.data))
            for start, end in ((self.start1, self.end1), (self.start2, self.end2))
            if start.data is not None
        ]


def stored_end(end: time) -> time:
    """An end time of 00:00 means "until midnight"."""
    return WorkingHours.END_OF_DAY if end == time(0) else end


def shown_end(end: time) -> time:
    """How a stored end time appears in the form: midnight as 00:00."""
    return time(0) if end == WorkingHours.END_OF_DAY else end


class WorkingHoursForm(FlaskForm):
    # One entry per weekday, Monday first, matching datetime.weekday().
    days = FieldList(FormField(DayHoursForm), min_entries=7, max_entries=7)


# Booking (phase 4)


class BookingDetailsForm(FlaskForm):
    """The guest's contact details. The chosen service, barber and time come from
    the same form's radio buttons and are checked by the booking view."""

    guest_name = StringField(
        "Your name",
        filters=[strip],
        validators=[
            DataRequired("Enter your name."),
            Length(max=120, message="Keep it under 120 characters."),
        ],
    )
    guest_email = EmailField(
        "Email",
        filters=[strip],
        description="We'll use it for your confirmation.",
        validators=[DataRequired("Enter your email."), Email(VALID_EMAIL), Length(max=255)],
    )
    guest_phone = StringField(
        "Phone",
        filters=[strip],
        description="In case the shop needs to reach you.",
        validators=[
            DataRequired("Enter your phone number."),
            Regexp(
                r"^\+?[0-9 ()./-]{7,20}$", message="Enter a phone number, like +40 712 345 678."
            ),
        ],
    )


# Management (phase 5)


class TimeOffForm(FlaskForm):
    """A stretch of time a barber can't be booked, in the shop's local time."""

    start = DateTimeLocalField("From", validators=[DataRequired("Pick when it starts.")])
    end = DateTimeLocalField("Until", validators=[DataRequired("Pick when it ends.")])
    reason = StringField(
        "Note",
        filters=[strip],
        description="Only the shop sees this, e.g. Holiday.",
        validators=[Optional(), Length(max=255, message="Keep it under 255 characters.")],
    )

    def validate_end(self, field):
        if self.start.data and field.data and field.data <= self.start.data:
            raise ValidationError("End after it starts.")
