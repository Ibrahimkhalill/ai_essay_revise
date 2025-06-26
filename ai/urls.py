
from django.urls import path
from .views import analyze_essay, upload_file, download_revision, health_check , compare_documents

urlpatterns = [
    path('analyze/', analyze_essay),
    path('upload/', upload_file),
    path('download/', download_revision),
    path('health/', health_check),
    path('compare_documents/', compare_documents),
]
