from rest_framework import serializers
from .models import CustomUser, OTP, UserProfile 
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate

from payment.models import Subscription
User = get_user_model()


class CustomUserSerializer(serializers.ModelSerializer):
    user_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'role', 'user_profile']
        read_only_fields = ['id', 'is_active', 'is_staff', 'is_superuser']

    def get_user_profile(self, obj):
        try:
            profile = obj.user_profile
            return UserGetProfileSerializer(profile).data
        except UserProfile.DoesNotExist:
            return None





class CustomUserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(write_only=True)  # Add name as a write-only field for UserProfile
    last_name  = serializers.CharField(write_only=True)  # Add name as a write-only field for UserProfile

    class Meta:
        model = User
        fields = ['id', 'email', 'password', 'role', 'first_name', 'last_name']  # Include name in fields
    
    def create(self, validated_data):
        from .views import create_otp_user
        # Extract name from validated_data
        first_name = validated_data.pop('first_name')  # Remove name since it's not part of the User model
        last_name = validated_data.pop('last_name')  # Remove name since it's not part of the User model
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data.get('role', 'user')
        )
        UserProfile.objects.create(
            user=user,
            first_name=first_name,
            last_name = last_name
        )
        # create_otp_user(validated_data['email'])
        Subscription.objects.create(user=user)
        return user

class OTPSerializer(serializers.ModelSerializer):
    class Meta:
        model = OTP
        fields = ['id', 'email', 'otp', 'created_at', 'attempts']
        read_only_fields = ['id', 'created_at', 'attempts']

class UserProfileSerializer(serializers.ModelSerializer):
   

    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'first_name', 'last_name' ,'address','profile_picture','phone_number', 'joined_date','is_verified']
        read_only_fields = ['id', 'joined_date']


class UserGetProfileSerializer(serializers.ModelSerializer):
   

    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'first_name', 'last_name','address','profile_picture','phone_number', 'joined_date','is_verified']
        read_only_fields = ['id', 'joined_date']


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
   

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
      

        user = authenticate(email=email, password=password)
        if not user or not user.is_active:
            raise serializers.ValidationError("Invalid credentials")
        return user