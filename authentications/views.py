from django.shortcuts import render
from django.contrib.auth.hashers import make_password
# Create your views here.
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import OTP, UserProfile
from .serializers import (
    CustomUserSerializer,
    CustomUserCreateSerializer,
    UserProfileSerializer,
    OTPSerializer,
    LoginSerializer
)
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from payment.models import Subscription
from payment.serializers import SubscriptionSerializer
from django.contrib.auth.hashers import check_password

import random

def generate_otp():
    return str(random.randint(100000, 999999))  # Generates a 6-digit OTP


User = get_user_model()


def send_otp_email(email, otp):
    html_content = render_to_string('otp_email_template.html', {'otp': otp, 'email': email})
    msg = EmailMultiAlternatives(
        subject='Your OTP Code',
        body=f'Your OTP is {otp}',
        from_email='hijabpoint374@gmail.com',
        to=[email]
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)



# ✅ Register user
@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    serializer = CustomUserCreateSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




@api_view(["POST"])
def login(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data
        refresh = RefreshToken.for_user(user)
        
        # Choose profile based on role
        if user.role in ['user', 'admin']:
            try:
                profile = user.user_profile
            except UserProfile.DoesNotExist:
                profile = UserProfile.objects.create(user=user, name=user.email.split('@')[0])
            profile_serializer = UserProfileSerializer(profile)
       
        return Response({
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
            "profile": profile_serializer.data
        }, status=status.HTTP_200_OK)
    print("serializer.errors",serializer.errors)
    return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)


# ✅ List all users (admin only)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def list_users(request):
    users = User.objects.all()
    serializer = CustomUserSerializer(users, many=True)
    return Response(serializer.data)

# ✅ Get or update the profile of the current user


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    try:
        profile = request.user.user_profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == 'GET':
        subscription = Subscription.objects.get(user=request.user)
        serializer = SubscriptionSerializer(subscription)
        # serializer = UserProfileSerializer(profile)
        return Response(serializer.data)

    if request.method == 'PUT':
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




def create_otp_user(email):
    
    # Generate a 6-digit OTP
    otp = generate_otp()
    otp_data = {'email': email, 'otp': otp}

    # Delete previous OTP if any and save the new one
    OTP.objects.filter(email=email).delete()
    serializer = OTPSerializer(data=otp_data)

    if serializer.is_valid():
        serializer.save()
        send_otp_email(email=email, otp=otp)

      

# ✅ Create OTP
@api_view(['POST'])
@permission_classes([AllowAny])
def create_otp(request):
    email = request.data.get('email')
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Generate a 6-digit OTP
    otp = generate_otp()
    otp_data = {'email': email, 'otp': otp}

    # Delete previous OTP if any and save the new one
    OTP.objects.filter(email=email).delete()
    serializer = OTPSerializer(data=otp_data)

    if serializer.is_valid():
        serializer.save()
        send_otp_email(email=email, otp=otp)
        # Optionally, send OTP to email (this can be done through Django's email system)
        return Response({"message": "OTP created and sent to email"}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ✅ Verify OTP
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    email = request.data.get('email')
    otp_value = request.data.get('otp')
    
    try:
        otp_obj = OTP.objects.get(email=email)
        if otp_obj.otp == otp_value:
            if not otp_obj.is_expired():
                return Response({"message": "OTP verified successfully"})
            return Response({"error": "OTP expired"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"error": "Incorrect OTP"}, status=status.HTTP_400_BAD_REQUEST)
    except OTP.DoesNotExist:
        return Response({"error": "No OTP found for this email"}, status=status.HTTP_404_NOT_FOUND)



@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp_after_signup(request):
    email = request.data.get('email')
    otp_value = request.data.get('otp')
    
    try:
        user = User.objects.filter(email=email).first()
        user_profile = UserProfile.objects.filter(user=user).first()
        otp_obj = OTP.objects.get(email=email)
        if otp_obj.otp == otp_value:
            if not otp_obj.is_expired():
                user.is_active = True
                user.save()
                user_profile.is_verified = True
                user_profile.save()
                return Response({"message": "OTP verified successfully"})
            return Response({"error": "OTP expired"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"error": "Incorrect OTP"}, status=status.HTTP_400_BAD_REQUEST)
    except OTP.DoesNotExist:
        return Response({"error": "No OTP found for this email"}, status=status.HTTP_404_NOT_FOUND)





# Step 1: Request password reset (create OTP again)
@api_view(['POST'])
@permission_classes([AllowAny])
def request_password_reset(request):
    email = request.data.get('email')
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Generate a 6-digit OTP
    otp = generate_otp()
    otp_data = {'email': email, 'otp': otp}

    # Delete previous OTP if any and save the new one
    OTP.objects.filter(email=email).delete()
    serializer = OTPSerializer(data=otp_data)

    if serializer.is_valid():
        serializer.save()
        send_otp_email(email=email, otp=otp)
        # Optionally, send OTP to email (this can be done through Django's email system)
        return Response({"message": "OTP created and sent to email"}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Step 2: Reset password with OTP
@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    email = request.data.get('email')
    otp_value = request.data.get('otp')
    new_password = request.data.get('new_password')

    if not all([email, otp_value, new_password]):
        return Response({'error': 'All fields are required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        otp_obj = OTP.objects.get(email=email)
        if otp_obj.otp != otp_value:
            return Response({'error': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)
        if otp_obj.is_expired():
            return Response({'error': 'OTP expired'}, status=status.HTTP_400_BAD_REQUEST)

        # Update password
        user = User.objects.get(email=email)
        user.password = make_password(new_password)
        user.save()

        # Clean up OTP
        otp_obj.delete()

        return Response({'message': 'Password reset successful'})
    except OTP.DoesNotExist:
        return Response({'error': 'No OTP found for this email'}, status=status.HTTP_404_NOT_FOUND)
    except User.DoesNotExist:
        return Response({'error': 'User with this email does not exist'}, status=status.HTTP_404_NOT_FOUND)
    
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    current_password = request.data.get('current_password')
    new_password = request.data.get('new_password')

    if not current_password or not new_password:
        return Response({'error': 'Current password and new password are required.'}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user

    if not user.check_password(current_password):
        return Response({'error': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        validate_password(new_password, user)
    except ValidationError as e:
        return Response({'error': e.messages}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save()

    return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)