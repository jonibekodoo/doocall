"""Request serializers for the web cabinet API (/api/web/v1)."""

from __future__ import annotations

from rest_framework import serializers


class RegisterSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=200)
    admin_email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(min_length=8, trim_whitespace=False)
    # Optional integrator referral code (Addendum A: referral attribution).
    ref = serializers.CharField(required=False, allow_blank=True, default="")


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, trim_whitespace=False)


class EmailVerifySerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
