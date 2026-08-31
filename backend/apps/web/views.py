"""Web cabinet API — registration funnel, JWT auth, billing status, webhooks.

Auth model: SimpleJWT. The ACCESS token travels in the response body (the SPA
keeps it in memory); the REFRESH token is set as an httpOnly cookie scoped to
the auth endpoints, so XSS can never read it. Refresh rotates the token and
blacklists the old one.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.api.errors import ApiError, ErrorCode
from apps.billing import services
from apps.billing.models import Subscription
from apps.billing.providers import get_provider
from apps.companies.models import Company
from apps.core import domains
from apps.core.models import AuditLog

from .serializers import (
    EmailVerifySerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
)

REFRESH_COOKIE = "doocall_refresh"
REFRESH_COOKIE_PATH = "/api/web/v1/auth"


def _set_refresh_cookie(response: Response, refresh: RefreshToken, request: Request) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        str(refresh),
        max_age=int(refresh.lifetime.total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
        path=REFRESH_COOKIE_PATH,
        # Shared across company subdomains on product hosts only.
        domain=domains.cookie_domain_for(request.get_host()),
    )


def _audit(company: Company | None, actor: User | None, action: str, **changes: Any) -> None:
    AuditLog.objects.create(company=company, actor=actor, action=action, changes=dict(changes))


class RegisterView(APIView):
    """§7 registration funnel: one call → trial company + admin user."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(request=RegisterSerializer, summary="Register a company (trial)")
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        email = data["admin_email"].lower()
        if User.objects.filter(username=email).exists():
            raise ApiError(
                ErrorCode.MISSING_FIELD, "email already registered", http.HTTP_400_BAD_REQUEST
            )
        slug = slugify(data["company_name"])
        if not slug or Company.objects.filter(slug=slug).exists():
            raise ApiError(
                ErrorCode.MISSING_FIELD,
                "company name already taken",
                http.HTTP_400_BAD_REQUEST,
            )

        # Referral attribution: valid ACTIVE code binds; anything else
        # silently falls back to self_signup (A: never block registration).
        integrator = None
        if ref := (data.get("ref") or "").strip().upper():
            from apps.partners.models import Integrator

            integrator = Integrator.objects.filter(
                referral_code=ref, status=Integrator.Status.ACTIVE
            ).first()

        trial_days = services.effective_trial_days()
        now = timezone.now()
        with transaction.atomic():
            company = Company(
                name=data["company_name"],
                slug=slug,
                status=Company.Status.TRIAL,
                trial_ends_at=now + timedelta(days=trial_days),
                integrator=integrator,
                acquired_via=Company.AcquiredVia.REFERRAL_LINK
                if integrator
                else Company.AcquiredVia.SELF_SIGNUP,
            )
            company.save()
            user = User.objects.create_user(
                username=email,
                email=email,
                password=data["password"],
                phone=data["phone"],
                company=company,
                is_company_admin=True,  # first user = cabinet admin
            )
            Subscription.all_objects.create(
                company=company,
                status=Subscription.Status.TRIAL,
                price_per_operator_uzs=services.effective_price(company),
                trial_ends_at=company.trial_ends_at,
            )
            _audit(company, user, "web.register", trial_days=trial_days)

        if settings.EMAIL_VERIFICATION_ENABLED:
            self._send_verification_email(user)

        return Response(
            {
                "success": True,
                "company": {"name": company.name, "slug": company.slug},
                "trial_ends_at": company.trial_ends_at.isoformat()
                if company.trial_ends_at
                else None,
                "email_verification_required": settings.EMAIL_VERIFICATION_ENABLED,
            },
            status=http.HTTP_201_CREATED,
        )

    @staticmethod
    def _send_verification_email(user: User) -> None:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        send_mail(
            "dooCall — confirm your email",
            f"Confirm your email: https://{settings.DOMAIN_APP}/verify-email?uid={uid}&token={token}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )


class LoginView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(request=LoginSerializer, summary="Web login (JWT + refresh cookie)")
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = authenticate(request, username=data["email"].lower(), password=data["password"])
        if user is None:
            raise ApiError(
                ErrorCode.INVALID_CREDENTIALS,
                "invalid email or password",
                http.HTTP_401_UNAUTHORIZED,
            )
        if settings.EMAIL_VERIFICATION_ENABLED and not user.email_verified:
            raise ApiError("EMAIL_NOT_VERIFIED", "email is not verified", http.HTTP_403_FORBIDDEN)

        # On a company subdomain only THAT company's users may sign in —
        # a foreign account would render an empty cabinet (all data 403s).
        sub = domains.company_subdomain(request.get_host())
        if sub is not None and (user.company is None or user.company.slug != sub):
            raise ApiError(
                ErrorCode.INVALID_CREDENTIALS,
                "invalid email or password",
                http.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        _audit(user.company, user, "web.login")
        from apps.partners.services import portal_for, role_name

        role = role_name(user)
        response = Response(
            {
                "success": True,
                "access": str(refresh.access_token),
                "user": {
                    "email": user.email,
                    "company": user.company.slug if user.company else None,
                    "role": role,
                    "portal": portal_for(role),  # admin | partner | cabinet
                    "cabinet_url": domains.cabinet_url_for(request, user.company.slug)
                    if user.company
                    else None,
                },
            }
        )
        _set_refresh_cookie(response, refresh, request)
        return response


class RefreshView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(request=None, summary="Rotate refresh cookie → new access token")
    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(REFRESH_COOKIE)
        if not raw:
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "no refresh cookie", http.HTTP_401_UNAUTHORIZED
            )
        try:
            old = RefreshToken(cast("Any", raw))
            user = User.objects.get(pk=int(old.payload["user_id"]))
        except (TokenError, User.DoesNotExist, KeyError, TypeError, ValueError):
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "invalid refresh token", http.HTTP_401_UNAUTHORIZED
            ) from None

        # Refuse to mint a session on a foreign company's subdomain BEFORE
        # rotating — the user's own-domain session must survive the visit.
        sub = domains.company_subdomain(request.get_host())
        if sub is not None and (user.company is None or user.company.slug != sub):
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "wrong company domain", http.HTTP_401_UNAUTHORIZED
            )

        try:
            old.blacklist()  # rotation: the old token can never be replayed
        except TokenError:
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "invalid refresh token", http.HTTP_401_UNAUTHORIZED
            ) from None

        refresh = RefreshToken.for_user(user)
        from apps.partners.services import portal_for, role_name

        role = role_name(user)
        response = Response(
            {
                "success": True,
                "access": str(refresh.access_token),
                "user": {
                    "email": user.email,
                    "company": user.company.slug if user.company else None,
                    "role": role,
                    "portal": portal_for(role),
                    "cabinet_url": domains.cabinet_url_for(request, user.company.slug)
                    if user.company
                    else None,
                },
            }
        )
        _set_refresh_cookie(response, refresh, request)
        return response


class CompaniesView(APIView):
    """Landing-header dropdown: the account's companies + portal target."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="My companies (landing cabinet menu)")
    def get(self, request: Request) -> Response:
        from apps.partners.models import Integrator
        from apps.partners.services import portal_for, role_name

        user = cast(User, request.user)
        role = role_name(user)
        portal = portal_for(role)

        companies: list[dict[str, Any]] = []
        if portal == "cabinet" and user.company:
            companies = [
                {
                    "name": user.company.name,
                    "slug": user.company.slug,
                    "url": domains.cabinet_url_for(request, user.company.slug),
                }
            ]
            target = companies[0]["url"]
        elif portal == "partner":
            integrator = Integrator.objects.filter(user=user).first()
            if integrator:
                companies = [
                    {
                        "name": c.name,
                        "slug": c.slug,
                        "url": domains.cabinet_url_for(request, c.slug),
                    }
                    for c in integrator.companies.all()[:50]
                ]
            target = domains.portal_url_for(request, "partner")
        else:  # platform staff
            target = domains.portal_url_for(request, "admin")

        return Response(
            {
                "success": True,
                "portal": portal,
                "portal_url": target,
                "companies": companies,
            }
        )


class HandoffCreateView(APIView):
    """One-time cross-domain sign-in code (landing → company subdomain).

    Browsers refuse to share cookies across some dev/parent domains
    (e.g. *.localhost), so the landing dropdown exchanges the signed-in
    session for a 60-second single-use code carried in the URL; the
    subdomain redeems it into its own host cookie.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, summary="Mint a one-time subdomain sign-in code")
    def post(self, request: Request) -> Response:
        import secrets

        from django.core.cache import cache

        code = secrets.token_urlsafe(32)
        cache.set(f"handoff:{code}", cast(User, request.user).pk, timeout=60)
        return Response({"success": True, "code": code})


class HandoffRedeemView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(summary="Redeem a one-time code → session on this host")
    def post(self, request: Request) -> Response:
        from django.core.cache import cache

        code = str(request.data.get("code") or "")
        key = f"handoff:{code}"
        user_id = cache.get(key) if code else None
        if user_id is None:
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "invalid or expired code", http.HTTP_401_UNAUTHORIZED
            )
        cache.delete(key)  # single use
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "invalid or expired code", http.HTTP_401_UNAUTHORIZED
            )

        # Same rule as login: a company subdomain only signs in its own users.
        sub = domains.company_subdomain(request.get_host())
        if sub is not None and (user.company is None or user.company.slug != sub):
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "wrong company domain", http.HTTP_401_UNAUTHORIZED
            )

        refresh = RefreshToken.for_user(user)
        from apps.partners.services import portal_for, role_name

        role = role_name(user)
        response = Response(
            {
                "success": True,
                "access": str(refresh.access_token),
                "user": {
                    "email": user.email,
                    "company": user.company.slug if user.company else None,
                    "role": role,
                    "portal": portal_for(role),
                    "cabinet_url": domains.cabinet_url_for(request, user.company.slug)
                    if user.company
                    else None,
                },
            }
        )
        _set_refresh_cookie(response, refresh, request)
        return response


class LogoutView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(request=None, summary="Logout: blacklist refresh + clear cookie")
    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(REFRESH_COOKIE)
        if raw:
            # Already-invalid token → clearing the cookie is enough.
            with contextlib.suppress(TokenError):
                RefreshToken(cast("Any", raw)).blacklist()
        response = Response({"success": True})
        response.delete_cookie(
            REFRESH_COOKIE,
            path=REFRESH_COOKIE_PATH,
            domain=domains.cookie_domain_for(request.get_host()),
        )
        return response


class PasswordResetRequestView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(request=PasswordResetRequestSerializer, summary="Send reset email")
    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email=serializer.validated_data["email"].lower()).first()
        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            send_mail(
                "dooCall — password reset",
                f"Reset your password: https://{settings.DOMAIN_APP}/reset-password"
                f"?uid={uid}&token={token}",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
        # Same response either way — no account enumeration.
        return Response({"success": True})


class PasswordResetConfirmView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(request=PasswordResetConfirmSerializer, summary="Set a new password")
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = self._user_from_uid(data["uid"])
        if user is None or not default_token_generator.check_token(user, data["token"]):
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "invalid reset token", http.HTTP_400_BAD_REQUEST
            )
        user.set_password(data["new_password"])
        user.save(update_fields=["password"])
        _audit(user.company, user, "web.password_reset")
        return Response({"success": True})

    @staticmethod
    def _user_from_uid(uid: str) -> User | None:
        try:
            return User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
        except (User.DoesNotExist, ValueError, OverflowError):
            return None


class EmailVerifyView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(request=EmailVerifySerializer, summary="Confirm email address")
    def post(self, request: Request) -> Response:
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = PasswordResetConfirmView._user_from_uid(data["uid"])
        if user is None or not default_token_generator.check_token(user, data["token"]):
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "invalid verification token", http.HTTP_400_BAD_REQUEST
            )
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        return Response({"success": True})


class BillingStatusView(APIView):
    """Cabinet billing status; 402 + paywall payload when inactive."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, summary="Billing status / paywall payload")
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        company = user.company
        if company is None:
            raise ApiError(
                ErrorCode.MISSING_FIELD, "user has no company", http.HTTP_400_BAD_REQUEST
            )
        subscription = Subscription.all_objects.filter(company=company).first()
        seats = services.seat_count(company)
        price = (
            subscription.price_per_operator_uzs
            if subscription
            else services.effective_price(company)
        )
        body = {
            "success": True,
            "company": company.slug,
            "status": subscription.status if subscription else company.status,
            "seats": seats,
            "price_per_operator_uzs": price,
            "amount_due_uzs": seats * price,
            "trial_ends_at": company.trial_ends_at.isoformat() if company.trial_ends_at else None,
            "current_period_end": subscription.current_period_end.isoformat()
            if subscription and subscription.current_period_end
            else None,
        }
        inactive = company.status == Company.Status.SUSPENDED or (
            company.status == Company.Status.TRIAL
            and company.trial_ends_at is not None
            and company.trial_ends_at < timezone.now()
        )
        if inactive:
            # Paywall payload the frontend renders directly.
            body["success"] = False
            body["error_code"] = ErrorCode.SUBSCRIPTION_INACTIVE
            body["paywall"] = {
                "reason": "trial_expired"
                if company.status == Company.Status.TRIAL
                else "suspended",
                "seats": seats,
                "price_per_operator_uzs": price,
                "amount_due_uzs": seats * price,
                "providers": ["payme", "click", "manual"],
            }
            return Response(body, status=http.HTTP_402_PAYMENT_REQUIRED)
        return Response(body)


class ProviderWebhookView(APIView):
    """POST /api/web/v1/billing/webhooks/<provider> — Payme/Click callbacks."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(request=None, summary="Payment provider webhook")
    def post(self, request: Request, provider_name: str) -> Response:
        provider = get_provider(provider_name)
        if provider is None or provider.name == "manual":
            raise ApiError(ErrorCode.MISSING_FIELD, "unknown provider", http.HTTP_404_NOT_FOUND)
        if not provider.verify(request):
            result = provider.bad_signature_response()
            _audit(None, None, "payment.webhook_rejected", provider=provider.name)
            return Response(result.body, status=result.status_code)
        result = provider.handle(request)
        _audit(None, None, "payment.webhook", provider=provider.name)
        return Response(result.body, status=result.status_code)
