"""Session and preference operations."""

from typing import Literal

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils.translation import gettext as _
from ninja import Router, Schema
from ninja.throttling import AnonRateThrottle

from accounts.models import HOME_BLOCKS, UserPreference
from config.currencies import CURRENCIES
from config.security import require_csrf

router = Router()

CurrencyCode = Literal[tuple(CURRENCIES)]
DateFormat = Literal["DMY", "MDY"]
NumberFormat = Literal["COMMA", "POINT"]
HomeBlock = Literal[HOME_BLOCKS]


class UserOut(Schema):
    username: str
    email: str


class PreferencesOut(Schema):
    base_currency: CurrencyCode
    date_format: DateFormat
    #: COMMA: 1.234,56. POINT: 1,234.56. For every number that is shown or typed.
    number_format: NumberFormat
    home_blocks: list[HomeBlock]

    @staticmethod
    def resolve_home_blocks(preferences):
        # A stored name that this version no longer has is dropped.
        return [name for name in preferences.home_blocks if name in HOME_BLOCKS]


class SessionOut(Schema):
    user: UserOut | None
    preferences: PreferencesOut | None
    allow_signups: bool


class LoginIn(Schema):
    username: str
    password: str


class SignupIn(Schema):
    username: str
    email: str
    password: str


class PreferencesIn(Schema):
    base_currency: CurrencyCode | None = None
    date_format: DateFormat | None = None
    number_format: NumberFormat | None = None
    #: The shown blocks in order. An empty list hides every block.
    home_blocks: list[HomeBlock] | None = None


def session_of(request):
    user = request.user if request.user.is_authenticated else None
    return {
        "user": user,
        "preferences": UserPreference.for_user(user) if user else None,
        "allow_signups": settings.ALLOW_SIGNUPS,
    }


@router.get("", auth=None, response=SessionOut, summary="Read the current session")
def read_session(request):
    # The client reads the CSRF cookie that this call sets, then sends it back
    # in the X-CSRFToken header of every state-changing request.
    get_token(request)
    return session_of(request)


@router.post(
    "/login",
    auth=None,
    response=SessionOut,
    throttle=[AnonRateThrottle(settings.AUTH_THROTTLE)],
    summary="Sign in",
)
def sign_in(request, payload: LoginIn):
    require_csrf(request)
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None:
        # One message for both causes: it must not reveal that a username exists.
        raise ValidationError(_("The username or the password is not correct."))
    login(request, user)
    return session_of(request)


@router.post("/logout", response={204: None}, summary="Sign out")
def sign_out(request):
    logout(request)
    return 204, None


@router.post(
    "/signup",
    auth=None,
    response=SessionOut,
    throttle=[AnonRateThrottle(settings.AUTH_THROTTLE)],
    summary="Create a user and sign in",
)
def sign_up(request, payload: SignupIn):
    require_csrf(request)
    if not settings.ALLOW_SIGNUPS:
        raise ValidationError(_("Registration is closed on this installation."))
    User = get_user_model()
    user = User(username=payload.username.strip(), email=payload.email.strip())
    errors = {}
    try:
        user.full_clean(exclude=["password"])
    except ValidationError as error:
        errors.update(error.message_dict)
    if not user.email:
        errors.setdefault("email", []).append(_("This field is required."))
    try:
        validate_password(payload.password, user)
    except ValidationError as error:
        errors["password"] = error.messages
    if errors:
        raise ValidationError(errors)
    with transaction.atomic():
        user.set_password(payload.password)
        user.save()
        UserPreference.objects.create(user=user)
    login(request, user)
    return session_of(request)


@router.patch("/preferences", response=PreferencesOut, summary="Change the preferences")
def change_preferences(request, payload: PreferencesIn):
    preferences = UserPreference.for_user(request.user)
    changes = payload.dict(exclude_none=True)
    if "home_blocks" in changes:
        # Each block once, in the order given.
        changes["home_blocks"] = list(dict.fromkeys(changes["home_blocks"]))
    for field, value in changes.items():
        setattr(preferences, field, value)
    if changes:
        preferences.save(update_fields=list(changes))
    return preferences
